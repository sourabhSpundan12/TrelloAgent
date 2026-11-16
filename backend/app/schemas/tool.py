from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ToolCategory(str, Enum):
    TRELLO = "trello"
    REPORTING = "reporting"
    EMPLOYEE = "employee"
    ANALYTICS = "analytics"
    SYSTEM = "system"


class ToolPermission(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class ToolDefinitionBase(BaseModel):
    name: str = Field(..., description="Unique tool identifier, e.g. trello_create_card")
    description: str = Field(..., description="Clear functional description used by LLM and discovery")
    category: ToolCategory = Field(..., description="Tool category classification")
    version: str = Field(default="1.0.0", description="Semantic version of the tool")
    parameters_schema: Dict[str, Any] = Field(
        ...,
        description="JSON Schema (OpenAPI compliant) defining input parameters"
    )
    required_permissions: List[str] = Field(
        default_factory=lambda: ["write"],
        description="Permissions required to invoke this tool"
    )
    is_mutation: bool = Field(
        default=False,
        description="Whether this tool mutates data and requires human preview/approval"
    )
    requires_approval: bool = Field(
        default=False,
        description="Whether this tool strictly mandates a 2-phase human-in-the-loop approval"
    )
    executor_key: str = Field(
        ...,
        description="Internal executor mapping key matching registered Python handler"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Search tags for keyword and semantic discovery"
    )
    is_active: bool = Field(
        default=True,
        description="Whether the tool is active for discovery and execution"
    )


class ToolDefinitionCreate(ToolDefinitionBase):
    pass


class ToolDefinitionUpdate(BaseModel):
    description: Optional[str] = None
    parameters_schema: Optional[Dict[str, Any]] = None
    required_permissions: Optional[List[str]] = None
    is_mutation: Optional[bool] = None
    requires_approval: Optional[bool] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


class ToolDefinition(ToolDefinitionBase):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ToolDiscoveryRequest(BaseModel):
    query: str = Field(..., description="User natural language command or intent search query")
    category: Optional[ToolCategory] = Field(None, description="Optional category filter")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum number of tools to return")
    min_score: float = Field(default=0.1, ge=0.0, le=1.0, description="Minimum relevance score threshold")


class DiscoveredTool(BaseModel):
    tool: ToolDefinition
    relevance_score: float = Field(..., description="Relevance score between 0.0 and 1.0")
    matched_by: List[str] = Field(default_factory=list, description="Criteria that matched (category, tag, keyword, semantic)")


class ToolDiscoveryResponse(BaseModel):
    query: str
    total_discovered: int
    tools: List[DiscoveredTool]
    gemini_declarations: List[Dict[str, Any]] = Field(
        ...,
        description="Tools formatted ready for Google GenAI function_declarations"
    )


class ToolExecutionRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    user_id: str = Field(default="user_default")
    user_permissions: List[str] = Field(default_factory=lambda: ["read", "write"])
    force_execute: bool = Field(
        default=False,
        description="If True, only executed if tool does not require approval"
    )


class ToolExecutionResponse(BaseModel):
    tool_name: str
    status: str = Field(..., description="'SUCCESS', 'REQUIRES_APPROVAL', 'VALIDATION_ERROR', 'PERMISSION_DENIED'")
    is_mutation: bool
    requires_approval: bool
    preview: Optional[Dict[str, Any]] = None
    payload_hash: Optional[str] = None
    result: Optional[Any] = None
    message: str

