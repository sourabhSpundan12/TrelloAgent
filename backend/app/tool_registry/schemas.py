from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolRegisterRequest(BaseModel):
    tool_id: str = Field(..., description="Unique stable identifier (e.g. trello_create_card)")
    name: str = Field(..., min_length=3, max_length=100, description="Tool name")
    description: str = Field(..., min_length=5, description="What the tool does")
    category: str = Field(..., min_length=2, max_length=50, description="Tool category")
    keywords: List[str] = Field(default_factory=list, description="Search keywords")
    synonyms: List[str] = Field(default_factory=list, description="Alternative phrasing expressions")
    capabilities: List[str] = Field(default_factory=list, description="Supported operations")
    input_schema: Dict[str, Any] = Field(..., description="Valid JSON Schema for input validation")
    permissions: List[str] = Field(
        default_factory=lambda: ["EMPLOYEE", "MANAGER", "ADMIN"],
        description="Required roles or permissions",
    )
    executor_type: str = Field(default="mock", description="Executor implementation type")
    executor_key: str = Field(..., description="Registered executor key")
    version: str = Field(default="1.0.0", description="Tool version (semver)")
    enabled: bool = Field(default=True, description="Whether the tool is active")
    approval_required: bool = Field(default=False, description="Whether approval is mandatory")
    source_type: str = Field(default="NATIVE", description="Tool origin: NATIVE, MCP, or N8N")
    source_id: Optional[str] = Field(default=None, description="External origin identifier")
    remote_tool_name: Optional[str] = Field(default=None, description="Original tool name on remote server")
    server_identifier: Optional[str] = Field(default=None, description="Remote server identifier")
    transport_type: Optional[str] = Field(default=None, description="Remote transport type")
    schema_fingerprint: Optional[str] = Field(default=None, description="SHA-256 schema fingerprint")
    last_discovered_at: Optional[datetime] = Field(default=None, description="Timestamp of discovery")


class ToolUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = Field(None, min_length=5)
    category: Optional[str] = Field(None, min_length=2, max_length=50)
    keywords: Optional[List[str]] = None
    synonyms: Optional[List[str]] = None
    capabilities: Optional[List[str]] = None
    input_schema: Optional[Dict[str, Any]] = None
    permissions: Optional[List[str]] = None
    executor_type: Optional[str] = None
    executor_key: Optional[str] = None
    version: Optional[str] = None
    enabled: Optional[bool] = None
    approval_required: Optional[bool] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    remote_tool_name: Optional[str] = None
    server_identifier: Optional[str] = None
    transport_type: Optional[str] = None
    schema_fingerprint: Optional[str] = None
    last_discovered_at: Optional[datetime] = None


class ToolResponse(BaseModel):
    tool_id: str
    name: str
    description: str
    category: str
    keywords: List[str]
    synonyms: List[str]
    capabilities: List[str]
    input_schema: Dict[str, Any]
    permissions: List[str]
    executor_type: str
    executor_key: str
    version: str
    enabled: bool
    approval_required: bool
    source_type: str = "NATIVE"
    source_id: Optional[str] = None
    remote_tool_name: Optional[str] = None
    server_identifier: Optional[str] = None
    transport_type: Optional[str] = None
    schema_fingerprint: Optional[str] = None
    last_discovered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }


class ToolListResponse(BaseModel):
    tools: List[ToolResponse]
    total: int
    page: int
    page_size: int

