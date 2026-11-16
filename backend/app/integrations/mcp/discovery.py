from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from mcp import types
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.logging import logger
from app.integrations.mcp.exceptions import MCPDiscoveryError
from app.integrations.mcp.repository import MCPServerRepository
from app.integrations.mcp.schemas import MCPDiscoveredToolsResponse
from app.integrations.mcp.tool_adapter import MCPToolAdapter
from app.integrations.mcp.transport import create_mcp_client_session
from app.tool_registry.repository import ToolRepository


class MCPDiscoveryService:
    """Discovers tools exposed by remote MCP servers and synchronizes them into the Tool Registry."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.server_repo = MCPServerRepository(db)
        self.tool_repo = ToolRepository(db)

    async def discover_server_tools(
        self,
        server_doc: Dict[str, Any],
        custom_http_client: Optional[httpx.AsyncClient] = None,
    ) -> MCPDiscoveredToolsResponse:
        server_id = server_doc.get("server_id")
        transport_type = server_doc.get("transport_type", "streamable_http")
        url = server_doc.get("url")
        command = server_doc.get("command")
        args = server_doc.get("args", [])
        headers = server_doc.get("headers", {})
        timeout = float(server_doc.get("timeout_seconds", 10.0))
        allow_internal = bool(server_doc.get("allow_internal", False))

        raw_tools: List[types.Tool] = []

        try:
            async with create_mcp_client_session(
                transport_type=transport_type,
                url=url,
                command=command,
                args=args,
                headers=headers,
                timeout_seconds=timeout,
                allow_internal=allow_internal,
                custom_http_client=custom_http_client,
            ) as session:
                await session.initialize()

                # Paginated tool discovery
                cursor = None
                while True:
                    params = types.PaginatedRequestParams(cursor=cursor) if cursor else None
                    result = await session.list_tools(params=params)
                    raw_tools.extend(result.tools)
                    cursor = getattr(result, "nextCursor", None)
                    if not cursor:
                        break

        except Exception as e:
            logger.error(f"Error during MCP tool discovery on server '{server_id}': {e}")
            await self.server_repo.update(
                server_id,
                {
                    "status": "ERROR",
                    "last_error": str(e),
                },
            )
            raise MCPDiscoveryError(f"Failed to discover tools from MCP server '{server_id}': {str(e)}") from e

        # Synchronize discovered tools into MongoDB ToolRepository
        registered_count = 0
        updated_count = 0
        adapted_tools: List[Dict[str, Any]] = []

        for mcp_tool in raw_tools:
            tool_model = MCPToolAdapter.adapt_to_tool_model(mcp_tool, server_doc)
            tool_dict = tool_model.model_dump()
            adapted_tools.append(tool_dict)

            existing = await self.tool_repo.get_by_tool_id(tool_model.tool_id)
            if existing:
                # Update existing MCP tool definition and refresh timestamp/schema
                await self.tool_repo.update(
                    tool_model.tool_id,
                    {
                        "name": tool_model.name,
                        "description": tool_model.description,
                        "input_schema": tool_model.input_schema,
                        "schema_fingerprint": tool_model.schema_fingerprint,
                        "keywords": tool_model.keywords,
                        "synonyms": tool_model.synonyms,
                        "capabilities": tool_model.capabilities,
                        "last_discovered_at": datetime.now(timezone.utc),
                        "enabled": existing.get("enabled", True),
                    },
                )
                updated_count += 1
            else:
                await self.tool_repo.create(tool_dict)
                registered_count += 1

        # Update MCP server status and tool count in database
        now = datetime.now(timezone.utc)
        await self.server_repo.update(
            server_id,
            {
                "status": "CONNECTED",
                "last_connected_at": now,
                "last_error": None,
                "discovered_tool_count": len(adapted_tools),
            },
        )

        logger.info(
            f"MCP Discovery for '{server_id}' completed: {len(adapted_tools)} tools found "
            f"({registered_count} newly registered, {updated_count} updated)."
        )

        return MCPDiscoveredToolsResponse(
            server_id=server_id,
            tools_discovered=len(adapted_tools),
            tools_registered=registered_count,
            tools_updated=updated_count,
            tools=adapted_tools,
        )

