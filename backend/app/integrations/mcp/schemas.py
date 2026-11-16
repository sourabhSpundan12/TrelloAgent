from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MCPServerRegisterRequest(BaseModel):
    server_id: str = Field(..., min_length=3, max_length=50, description="Unique server slug e.g. trello-mcp")
    name: str = Field(..., min_length=3, max_length=100, description="Human readable name")
    description: Optional[str] = Field(None, description="Description of capabilities")
    transport_type: str = Field(
        default="streamable_http",
        description="Transport protocol: 'streamable_http', 'sse', or 'stdio'",
    )
    url: Optional[str] = Field(None, description="URL for HTTP/SSE transport")
    command: Optional[str] = Field(None, description="Command executable for trusted local stdio")
    args: List[str] = Field(default_factory=list, description="Command arguments for stdio")
    headers: Dict[str, str] = Field(default_factory=dict, description="Custom headers for remote HTTP/SSE")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0, description="Network timeout in seconds")
    enabled: bool = Field(default=True, description="Whether server is active")
    allow_internal: bool = Field(
        default=False,
        description="Explicitly allow private/localhost network targets in dev/test",
    )


class MCPServerUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = None
    url: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    headers: Optional[Dict[str, str]] = None
    timeout_seconds: Optional[float] = Field(None, ge=1.0, le=60.0)
    enabled: Optional[bool] = None
    allow_internal: Optional[bool] = None


class MCPServerResponse(BaseModel):
    server_id: str
    name: str
    description: Optional[str] = None
    transport_type: str
    url: Optional[str] = None
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    headers: Dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = 10.0
    enabled: bool = True
    status: str = "DISCONNECTED"  # CONNECTED, DISCONNECTED, ERROR
    allow_internal: bool = False
    last_connected_at: Optional[datetime] = None
    last_error: Optional[str] = None
    discovered_tool_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }


class MCPServerListResponse(BaseModel):
    servers: List[MCPServerResponse]
    total: int


class MCPDiscoveredToolsResponse(BaseModel):
    server_id: str
    tools_discovered: int
    tools_registered: int
    tools_updated: int
    tools: List[Dict[str, Any]]

