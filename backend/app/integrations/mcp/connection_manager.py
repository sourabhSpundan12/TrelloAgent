import time
from typing import Any, Dict, Optional
import httpx
from app.core.logging import logger
from app.integrations.mcp.exceptions import MCPServerConnectionError, MCPSSRFError
from app.integrations.mcp.transport import create_mcp_client_session


class MCPConnectionManager:
    """Manages connectivity verification and session health for MCP servers."""

    async def test_connection(
        self,
        server_doc: Dict[str, Any],
        custom_http_client: Optional[httpx.AsyncClient] = None,
    ) -> Dict[str, Any]:
        """
        Attempts to establish an MCP session and send a ping to verify server responsiveness.
        Returns status dictionary with latency.
        """
        server_id = server_doc.get("server_id")
        transport_type = server_doc.get("transport_type", "streamable_http")
        url = server_doc.get("url")
        command = server_doc.get("command")
        args = server_doc.get("args", [])
        headers = server_doc.get("headers", {})
        timeout = float(server_doc.get("timeout_seconds", 10.0))
        allow_internal = bool(server_doc.get("allow_internal", False))

        start_time = time.monotonic()
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
                try:
                    await session.send_ping()
                except Exception as ping_err:
                    logger.debug(f"Ping request returned {ping_err}, but initialize succeeded.")

                duration_ms = round((time.monotonic() - start_time) * 1000, 2)
                logger.info(f"Successfully connected to MCP server '{server_id}' in {duration_ms}ms")
                return {
                    "status": "CONNECTED",
                    "server_id": server_id,
                    "latency_ms": duration_ms,
                    "transport_type": transport_type,
                }
        except MCPSSRFError:
            raise
        except Exception as e:
            logger.error(f"Failed to connect to MCP server '{server_id}': {e}")
            raise MCPServerConnectionError(f"Connection to MCP server '{server_id}' failed: {str(e)}") from e

