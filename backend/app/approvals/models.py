from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class TaskDraft(BaseModel):
    title: str = Field(..., description="Action title or task card name")
    description: str = Field(default="", description="Detailed task description or acceptance criteria")
    board_name: str = Field(default="Configured Trello Board", description="Target Trello board name")
    board_id: Optional[str] = Field(None, description="Target Trello board ID")
    list_name: str = Field(default="To Do", description="Target list or column name")
    list_id: Optional[str] = Field(None, description="Target list ID")
    priority: str = Field(default="MEDIUM", description="Priority level: LOW, MEDIUM, HIGH, URGENT")
    due_date: Optional[str] = Field(None, description="Optional due date in ISO format or string")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Exact parameters to pass to executor")


class PendingActionModel(BaseModel):
    action_id: str = Field(..., description="Unique action slug e.g. ACT-PREV-ABC12345")
    user_id: str = Field(..., description="User ID of author")
    user_email: Optional[str] = Field(None, description="User email for audit trail")
    tool_id: str = Field(..., description="Registered tool ID to invoke upon confirmation")
    tool_name: str = Field(..., description="Display name of target tool")
    category: str = Field(default="TRELLO", description="Tool category")
    action_type: str = Field(default="CREATE_CARD", description="High-level action type")
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING, description="Current approval status")
    payload_hash: str = Field(..., description="Cryptographic SHA-256 hash of execution parameters")
    draft: TaskDraft = Field(..., description="Structured task draft details")
    execution_result: Optional[Dict[str, Any]] = Field(None, description="Output payload from executor after confirmation")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(..., description="TTL expiration timestamp")

