from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.tool_registry.schemas import ToolResponse


class ToolDiscoveryRequest(BaseModel):
    query: str = Field(..., min_length=2, description="User command or task search query")
    category: Optional[str] = Field(None, description="Optional category filter (e.g. trello, reporting)")
    limit: int = Field(default=5, ge=1, le=20, description="Max candidate tools to return")
    min_score: float = Field(default=0.05, ge=0.0, le=1.0, description="Minimum relevance score threshold")


class DiscoveredToolItem(BaseModel):
    tool: ToolResponse
    relevance_score: float = Field(..., description="Calculated relevance score in [0.0, 1.0]")
    matched_by: List[str] = Field(default_factory=list, description="Matched keywords, synonyms, or metadata")
    explanation: str = Field(..., description="Explanation of why this tool was discovered")


class ToolDiscoveryResponse(BaseModel):
    query: str
    total_candidates_searched: int
    total_matched: int
    tools: List[DiscoveredToolItem]

