import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.logging import logger
from app.integrations.mcp.connection_manager import MCPConnectionManager
from app.integrations.mcp.discovery import MCPDiscoveryService
from app.integrations.mcp.exceptions import (
    MCPServerNotFoundError,
    MCPToolExecutionError,
)
from app.integrations.mcp.repository import MCPServerRepository
from app.integrations.mcp.schemas import MCPDiscoveredToolsResponse
from app.integrations.mcp.transport import create_mcp_client_session
from app.tool_registry.repository import ToolRepository


class MCPClientManager:
    """
    Central orchestrator for MCP server connections, discovery, and tool execution.
    Integrates with MongoDB persistence and domain exception handling.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.server_repo = MCPServerRepository(db)
        self.tool_repo = ToolRepository(db)
        self.connection_manager = MCPConnectionManager()
        self.discovery_service = MCPDiscoveryService(db)
        self._custom_http_clients: Dict[str, httpx.AsyncClient] = {}

    def register_custom_http_client(self, server_id: str, client: httpx.AsyncClient) -> None:
        """Register a custom in-memory or mock HTTP client for testing."""
        self._custom_http_clients[server_id] = client

    def unregister_custom_http_client(self, server_id: str) -> None:
        self._custom_http_clients.pop(server_id, None)

    async def get_server_or_fail(self, server_id: str) -> Dict[str, Any]:
        server = await self.server_repo.get_by_server_id(server_id)
        if not server:
            raise MCPServerNotFoundError(f"MCP server with identifier '{server_id}' was not found.")
        return server

    async def connect_server(self, server_id: str) -> Dict[str, Any]:
        """Test and establish connectivity with the specified MCP server."""
        server = await self.get_server_or_fail(server_id)
        custom_client = self._custom_http_clients.get(server_id)
        try:
            result = await self.connection_manager.test_connection(server, custom_http_client=custom_client)
            await self.server_repo.update(
                server_id,
                {
                    "status": "CONNECTED",
                    "last_connected_at": datetime.now(timezone.utc),
                    "last_error": None,
                },
            )
            return result
        except Exception as e:
            await self.server_repo.update(
                server_id,
                {
                    "status": "ERROR",
                    "last_error": str(e),
                },
            )
            raise

    async def disconnect_server(self, server_id: str) -> Dict[str, Any]:
        """Mark an MCP server as disconnected."""
        await self.get_server_or_fail(server_id)
        await self.server_repo.update(server_id, {"status": "DISCONNECTED"})
        logger.info(f"MCP Server '{server_id}' marked as disconnected.")
        return {"status": "DISCONNECTED", "server_id": server_id}

    async def discover_tools(self, server_id: str) -> MCPDiscoveredToolsResponse:
        """Discover tools from remote server and register them in Tool Registry."""
        server = await self.get_server_or_fail(server_id)
        custom_client = self._custom_http_clients.get(server_id)
        return await self.discovery_service.discover_server_tools(server, custom_http_client=custom_client)

    async def execute_tool(
        self,
        server_id: str,
        remote_tool_name: str,
        parameters: Dict[str, Any],
    ) -> Any:
        """
        Executes a remote MCP tool using tools/call via the official MCP ClientSession.
        Normalizes and parses text / structured results.
        """
        server = await self.get_server_or_fail(server_id)
        transport_type = server.get("transport_type", "streamable_http")
        url = server.get("url")
        command = server.get("command")
        args = server.get("args", [])
        headers = server.get("headers", {})
        timeout = float(server.get("timeout_seconds", 10.0))
        allow_internal = bool(server.get("allow_internal", False))
        custom_client = self._custom_http_clients.get(server_id)

        try:
            async with create_mcp_client_session(
                transport_type=transport_type,
                url=url,
                command=command,
                args=args,
                headers=headers,
                timeout_seconds=timeout,
                allow_internal=allow_internal,
                custom_http_client=custom_client,
            ) as session:
                await session.initialize()
                call_result = await session.call_tool(name=remote_tool_name, arguments=parameters)

                is_err = getattr(call_result, "is_error", False) or getattr(call_result, "isError", False)
                if is_err:
                    err_msg = "Remote MCP tool returned an error."
                    if call_result.content:
                        err_msg = "".join(getattr(c, "text", str(c)) for c in call_result.content)
                    raise MCPToolExecutionError(f"Remote tool execution failed: {err_msg}")

                # Structured content extraction
                if hasattr(call_result, "structured_content") and call_result.structured_content:
                    return call_result.structured_content

                # Content item parsing
                if call_result.content:
                    texts = [getattr(c, "text", str(c)) for c in call_result.content]
                    combined = "\n".join(texts)
                    try:
                        return json.loads(combined)
                    except Exception:
                        return {"text": combined}

                return {}

        except MCPToolExecutionError:
            raise
        except Exception as e:
            logger.error(f"Error invoking MCP tool '{remote_tool_name}' on server '{server_id}': {e}")
            raise MCPToolExecutionError(
                f"Failed to execute MCP tool '{remote_tool_name}' on server '{server_id}': {str(e)}"
            ) from e

    async def remove_server_and_tools(self, server_id: str) -> bool:
        """Deregister an MCP server and delete all of its synchronized tools from the Tool Registry."""
        server = await self.server_repo.get_by_server_id(server_id)
        if not server:
            return False

        # Delete from mcp_servers collection
        await self.server_repo.delete(server_id)

        # Remove associated tools from tool registry
        cursor = self.tool_repo.collection.find({"source_type": "MCP", "source_id": server_id})
        tool_ids = []
        async for doc in cursor:
            tool_ids.append(doc.get("tool_id"))

        if tool_ids:
            await self.tool_repo.collection.delete_many({"tool_id": {"$in": tool_ids}})
            logger.info(f"Removed {len(tool_ids)} tools associated with deregistered server '{server_id}'")

        self.unregister_custom_http_client(server_id)
        return True

