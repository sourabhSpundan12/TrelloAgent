from typing import Any, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.logging import logger
from app.integrations.mcp.client_manager import MCPClientManager
from app.tool_executor.exceptions import (
    ApprovalRequiredError,
    ToolDisabledError,
    ToolNotFoundError,
    ToolPermissionError,
    UnregisteredExecutorError,
)
from app.tool_executor.interfaces import ExecutionContext, ExecutionResult
from app.tool_executor.mcp_adapter import MCPToolExecutor
from app.tool_executor.registry import executor_registry
from app.tool_executor.validators import validate_parameters_against_schema
from app.tool_registry.repository import ToolRepository


class ToolExecutorService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.tool_repo = ToolRepository(db)
        self.registry = executor_registry
        self.client_manager = MCPClientManager(db)
        self.mcp_executor = MCPToolExecutor(self.client_manager)

    async def execute(
        self,
        tool_id: str,
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        """
        Validates policies, schema, and permissions, then delegates to registered executor
        or MCP remote transport. Never executes arbitrary code or unvetted executors.
        """
        # 1. Confirm tool exists
        tool = await self.tool_repo.get_by_tool_id(tool_id)
        if not tool:
            raise ToolNotFoundError(f"Tool with identifier '{tool_id}' does not exist.")

        # 2. Confirm tool is enabled
        if not tool.get("enabled", True):
            raise ToolDisabledError(f"Tool '{tool_id}' is disabled and cannot be executed.")

        # 3. Check user permissions / roles
        user_role = context.user_role.upper()
        allowed_roles = [str(r).upper() for r in tool.get("permissions", [])]
        if user_role != "ADMIN" and allowed_roles and "*" not in allowed_roles:
            if user_role not in allowed_roles:
                raise ToolPermissionError(
                    f"User with role '{user_role}' is not authorized to invoke tool '{tool_id}'. Allowed: {allowed_roles}"
                )

        # 4. Validate input parameters against registered JSON Schema
        input_schema = tool.get("input_schema", {})
        validate_parameters_against_schema(parameters, input_schema)

        # 5. Resolve executor implementation
        source_type = str(tool.get("source_type", "NATIVE")).upper()
        executor_type = str(tool.get("executor_type", "")).lower()
        executor_key = tool.get("executor_key")

        if source_type == "MCP" or executor_type == "mcp":
            executor = self.mcp_executor
        else:
            executor = self.registry.get(executor_key)
            if not executor:
                logger.error(f"No executor registered for executor_key='{executor_key}' (tool_id='{tool_id}')")
                raise UnregisteredExecutorError(
                    f"No vetted executor implementation registered for key '{executor_key}'."
                )

        # 6. Enforce approval policy for mutations
        approval_required = tool.get("approval_required", False)
        if approval_required and not context.confirmed:
            # Execute mock preview or raise approval required
            result = await executor.execute(tool, parameters, context)
            if result.status == "REQUIRES_APPROVAL":
                logger.info(f"Execution of '{tool_id}' paused awaiting human approval.")
                return result
            # If executor didn't self-intercept, intercept here
            raise ApprovalRequiredError(
                f"Tool '{tool_id}' mandates user confirmation before modifying data.",
                details={"parameters": parameters, "tool_id": tool_id},
            )

        # 7. Execute concrete executor
        logger.info(f"Executing tool '{tool_id}' via executor '{executor_key}' for user '{context.user_id}'")
        result = await executor.execute(tool, parameters, context)
        return result

