from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class TaskDraftSchema(BaseModel):
    title: str = Field(..., description="Task title or card name")
    description: Optional[str] = Field(default="", description="Detailed description")
    board_name: Optional[str] = Field(default="Configured Trello Board", description="Board name")
    board_id: Optional[str] = Field(None, description="Board ID")
    list_name: Optional[str] = Field(default="To Do", description="List or column name")
    list_id: Optional[str] = Field(None, description="List ID")
    priority: Optional[str] = Field(default="MEDIUM", description="Task priority (LOW, MEDIUM, HIGH, URGENT)")
    start_date: Optional[str] = Field(None, description="Start date string or ISO format")
    due_date: Optional[str] = Field(None, description="Due date string or ISO format")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Raw parameters sent to tool")


class ApprovalPreviewResponse(BaseModel):
    action_id: str
    tool_id: str
    tool_name: str
    category: str
    action_type: str
    status: str
    payload_hash: str
    draft: TaskDraftSchema
    created_at: datetime
    expires_at: datetime
    message: str
    execution_result: Optional[Dict[str, Any]] = None


class ApprovalEditRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = Field(None, max_length=5000)
    board_name: Optional[str] = None
    board_id: Optional[str] = None
    list_name: Optional[str] = None
    list_id: Optional[str] = None
    priority: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None


class ApprovalConfirmResponse(BaseModel):
    action_id: str
    status: str
    tool_id: str
    card_id: Optional[str] = None
    card_url: Optional[str] = None
    execution_result: Optional[Dict[str, Any]] = None
    message: str


class ApprovalCancelResponse(BaseModel):
    action_id: str
    status: str = "REJECTED"
    message: str

