from typing import Any, Dict, Optional
from app.core.exceptions import AppException


class ToolExecutionError(AppException):
    def __init__(
        self,
        message: str = "Tool execution failed.",
        status_code: int = 500,
        error_code: str = "TOOL_EXECUTION_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message=message, status_code=status_code, error_code=error_code, details=details)


class ToolNotFoundError(ToolExecutionError):
    def __init__(self, message: str = "Requested tool was not found in registry."):
        super().__init__(message=message, status_code=404, error_code="TOOL_NOT_FOUND")


class ToolDisabledError(ToolExecutionError):
    def __init__(self, message: str = "Requested tool is currently disabled and cannot be executed."):
        super().__init__(message=message, status_code=400, error_code="TOOL_DISABLED")


class ToolInputValidationError(ToolExecutionError):
    def __init__(self, message: str = "Tool parameters failed schema validation.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=422, error_code="TOOL_VALIDATION_ERROR", details=details)


class ToolPermissionError(ToolExecutionError):
    def __init__(self, message: str = "User possesses insufficient permissions to execute this tool."):
        super().__init__(message=message, status_code=403, error_code="TOOL_PERMISSION_DENIED")


class ApprovalRequiredError(ToolExecutionError):
    def __init__(self, message: str = "Tool requires two-phase human confirmation before execution.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=400, error_code="APPROVAL_REQUIRED", details=details)


class UnregisteredExecutorError(ToolExecutionError):
    def __init__(self, message: str = "No executor implementation has been registered for this tool key."):
        super().__init__(message=message, status_code=500, error_code="UNREGISTERED_EXECUTOR")

