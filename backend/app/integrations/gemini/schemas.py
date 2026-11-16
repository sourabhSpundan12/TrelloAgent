from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class GeminiIntentOutput(BaseModel):
    """Structured intent representation validated from Gemini output."""

    intent: str = Field(..., description="High-level extracted intent, e.g. create_card, move_card, search_cards")
    entity: str = Field(default="card", description="Target domain entity, e.g. card, task, report, employee")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Non-sensitive extracted entity parameters matching tool input schema",
    )
    suggested_tool_id: Optional[str] = Field(
        None,
        description="Exact tool_id of the most relevant discovered tool selected by the model",
    )
    requires_clarification: bool = Field(
        default=False,
        description="True if user request is ambiguous, contradictory, or lacks crucial parameters",
    )
    clarification_message: Optional[str] = Field(
        None,
        description="Helpful message asking user to clarify ambiguity when required",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for this interpretation",
    )


class AIInterpretRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=1000, description="Natural language command from user")
    active_action_id: Optional[str] = None
    conversation_id: Optional[str] = None


class AIInterpretResponse(BaseModel):
    command: str
    intent: str
    entity: str
    parameters: Dict[str, Any]
    selected_tool_id: Optional[str] = None
    selected_tool_name: Optional[str] = None
    approval_required: bool = False
    requires_clarification: bool = False
    clarification_message: Optional[str] = None
    confidence: float
    candidate_tools_count: int
    execution_preview: Optional[Dict[str, Any]] = None
    action_id: Optional[str] = None
    execution_result: Optional[Dict[str, Any]] = None
    conversational_message: Optional[str] = None

