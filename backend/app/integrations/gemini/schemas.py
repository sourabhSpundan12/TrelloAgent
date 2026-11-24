from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class GeminiIntentOutput(BaseModel):
    """Structured intent representation validated from LLM output."""

    intent: str = Field(..., description="High-level extracted intent, e.g. create_card, move_card, update_card, delete_card, search_cards")
    entity: str = Field(default="card", description="Target domain entity, e.g. card, task, report, employee")
    entities: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted domain entities e.g. {'card': 'API Integration', 'person': 'Rahul'}",
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Non-sensitive extracted entity parameters matching tool input schema",
    )
    action_parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured action parameters matching tool execution schema",
    )
    selected_template: Optional[str] = Field(
        default=None,
        description="Identifier or name of automatically selected task description template, e.g. 'tmpl_backend'",
    )
    missing_fields: List[str] = Field(
        default_factory=list,
        description="List of required parameter fields missing from user command (e.g. ['name'] or ['card_name'])",
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

    @model_validator(mode="before")
    @classmethod
    def sync_parameters_and_entities(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Sync parameters <-> action_parameters
            params = data.get("parameters") or {}
            action_params = data.get("action_parameters") or {}
            if not params and action_params:
                data["parameters"] = dict(action_params)
            elif not action_params and params:
                data["action_parameters"] = dict(params)

            # Sync entity <-> entities
            entities = data.get("entities") or {}
            entity = data.get("entity") or "card"
            if not entities:
                ent_dict = {entity: data.get("parameters", {}).get("name") or data.get("parameters", {}).get("card_name") or entity}
                if data.get("parameters", {}).get("member_name"):
                    ent_dict["person"] = data.get("parameters", {}).get("member_name")
                data["entities"] = ent_dict
            elif not data.get("entity") and entities:
                data["entity"] = list(entities.keys())[0]

            # If missing fields exist, ensure clarification is flagged
            missing = data.get("missing_fields") or []
            if missing and not data.get("requires_clarification"):
                data["requires_clarification"] = True
                if not data.get("clarification_message"):
                    missing_str = ", ".join(missing)
                    data["clarification_message"] = f"Please provide the missing information: {missing_str}."

        return data


class AIInterpretRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=1000, description="Natural language command from user")
    active_action_id: Optional[str] = None
    conversation_id: Optional[str] = None
    board_id: Optional[str] = None
    model_id: Optional[str] = None


class AIInterpretResponse(BaseModel):
    command: str
    intent: str
    entity: str
    parameters: Dict[str, Any]
    entities: Optional[Dict[str, Any]] = None
    action_parameters: Optional[Dict[str, Any]] = None
    selected_template: Optional[str] = None
    missing_fields: Optional[List[str]] = None
    board_id: Optional[str] = None
    model_id: Optional[str] = None
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
    conversation_id: Optional[str] = None

