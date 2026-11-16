from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatMessageSchema(BaseModel):
    id: str
    user_id: str
    sender: str  # 'user' or 'assistant'
    content: str
    timestamp: str
    intent: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    selected_tool_id: Optional[str] = None
    selected_tool_name: Optional[str] = None
    approval_required: bool = False
    action_id: Optional[str] = None
    approval_preview: Optional[Dict[str, Any]] = None
    execution_result: Optional[Dict[str, Any]] = None
    execution_status: Optional[str] = None
    discovered_tool: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessageSchema]
    total: int

