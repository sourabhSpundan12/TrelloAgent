from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_serializer


class ChatSessionSchema(BaseModel):
    id: str  # conversation_id
    user_id: str
    board_id: Optional[str] = None
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    @field_serializer("created_at", "updated_at", when_used="json")
    def serialize_dt(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


class ChatSessionListResponse(BaseModel):
    sessions: List[ChatSessionSchema]
    total: int


class ChatMessageSchema(BaseModel):
    id: str
    user_id: str
    conversation_id: Optional[str] = None
    board_id: Optional[str] = None
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

    @field_serializer("created_at", when_used="json")
    def serialize_created_at(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessageSchema]
    total: int
    conversation_id: Optional[str] = None


