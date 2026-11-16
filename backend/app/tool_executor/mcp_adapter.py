from typing import Any, Dict
from app.core.logging import logger
from app.integrations.mcp.client_manager import MCPClientManager
from app.tool_executor.exceptions import ToolExecutionError
from app.tool_executor.interfaces import BaseExecutor, ExecutionContext, ExecutionResult


class MCPToolExecutor(BaseExecutor):
    """
    Concrete tool executor delegating execution to remote MCP servers via official MCP ClientSession.
    """

    def __init__(self, client_manager: MCPClientManager):
        self.client_manager = client_manager

    async def execute(
        self,
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        tool_id = tool.get("tool_id", "")
        server_id = tool.get("source_id") or tool.get("server_identifier")
        remote_name = tool.get("remote_tool_name")

        # Fallback to parsing namespaced tool_id: mcp.<server_id>.<remote_tool_name>
        if not server_id or not remote_name:
            parts = tool_id.split(".", 2)
            if len(parts) == 3 and parts[0] == "mcp":
                server_id = server_id or parts[1]
                remote_name = remote_name or parts[2]
            else:
                raise ToolExecutionError(f"Incomplete MCP routing metadata for tool_id='{tool_id}'.")

        logger.info(
            f"MCPToolExecutor routing call for tool_id='{tool_id}' -> server '{server_id}', remote tool '{remote_name}'"
        )

        try:
            raw_result = await self.client_manager.execute_tool(
                server_id=server_id,
                remote_tool_name=remote_name,
                parameters=parameters,
            )

            # Unpack structured result wrapper if needed
            if isinstance(raw_result, dict) and "result" in raw_result and len(raw_result) == 1:
                result_payload = raw_result["result"]
            else:
                result_payload = raw_result

            # Determine mutation status from tool name or explicit approval flag
            is_mutation = tool.get("approval_required", False) or any(
                k in remote_name.lower() for k in ["create", "update", "move", "archive", "delete"]
            )

            return ExecutionResult(
                tool_id=tool_id,
                status="SUCCESS",
                is_mutation=is_mutation,
                result=result_payload,
                message=f"MCP remote tool '{remote_name}' executed successfully on server '{server_id}'.",
            )
        except Exception as e:
            logger.error(f"Failed to execute MCP tool '{tool_id}' on server '{server_id}': {e}")
            raise

