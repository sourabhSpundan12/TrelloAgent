from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ExecutionContext(BaseModel):
    """Contextual metadata accompanying a tool execution request."""

    user_id: str = Field(..., description="ID of user requesting invocation")
    user_role: str = Field(..., description="Role of requesting user")
    confirmed: bool = Field(default=False, description="Whether approval confirmation was explicitly granted")
    action_id: Optional[str] = Field(None, description="Pre-existing approval action ID if previously previewed")


class ExecutionResult(BaseModel):
    """Normalized output from a tool executor."""

    tool_id: str
    status: str = Field(..., description="SUCCESS, REQUIRES_APPROVAL, ERROR, or VALIDATION_ERROR")
    is_mutation: bool
    result: Optional[Any] = None
    preview: Optional[Dict[str, Any]] = None
    payload_hash: Optional[str] = None
    message: str


class BaseExecutor(ABC):
    """Abstract base class for all concrete tool executors."""

    @abstractmethod
    async def execute(
        self,
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        """Executes the tool or returns preview if awaiting approval."""
        pass

