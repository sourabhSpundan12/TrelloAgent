from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolModel(BaseModel):
    """Internal domain model for a registered tool in MongoDB."""

    tool_id: str = Field(..., description="Unique stable identifier, e.g. trello_create_card")
    name: str = Field(..., description="Unique human-readable tool name")
    description: str = Field(..., description="Functional description of what the tool accomplishes")
    category: str = Field(..., description="Tool category (e.g., trello, project_management, reporting)")
    keywords: List[str] = Field(default_factory=list, description="Search keywords for discovery")
    synonyms: List[str] = Field(default_factory=list, description="Alternative phrasing and synonyms")
    capabilities: List[str] = Field(default_factory=list, description="Supported operations or capabilities")
    input_schema: Dict[str, Any] = Field(..., description="Valid JSON Schema for input validation")
    permissions: List[str] = Field(
        default_factory=lambda: ["EMPLOYEE", "MANAGER", "ADMIN"],
        description="Required user roles or permission identifiers to invoke this tool",
    )
    executor_type: str = Field(default="mock", description="Executor implementation type (e.g., mock, python, trello)")
    executor_key: str = Field(..., description="Registered executor identifier mapping to concrete handler")
    version: str = Field(default="1.0.0", description="Semantic tool version (e.g., 1.0.0)")
    enabled: bool = Field(default=True, description="Whether the tool is active and discoverable")
    approval_required: bool = Field(
        default=False,
        description="Whether tool execution strictly requires two-phase human confirmation",
    )
    # Phase 4B: MCP and multi-source tool extensions
    source_type: str = Field(default="NATIVE", description="Tool origin: NATIVE, MCP, or N8N")
    source_id: Optional[str] = Field(default=None, description="External origin identifier (e.g. server_id)")
    remote_tool_name: Optional[str] = Field(default=None, description="Original tool name on remote server")
    server_identifier: Optional[str] = Field(default=None, description="Remote server identifier")
    transport_type: Optional[str] = Field(default=None, description="Remote transport: streamable_http, sse, stdio")
    schema_fingerprint: Optional[str] = Field(default=None, description="SHA-256 hash of input_schema for drift detection")
    last_discovered_at: Optional[datetime] = Field(default=None, description="Timestamp of latest discovery")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }

