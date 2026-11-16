from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

# For backwards compatibility with existing codebase
from app.integrations.gemini.schemas import (
    GeminiIntentOutput,
    AIInterpretRequest,
    AIInterpretResponse,
)

# Provider-agnostic alias
IntentOutput = GeminiIntentOutput

__all__ = [
    "GeminiIntentOutput",
    "IntentOutput",
    "AIInterpretRequest",
    "AIInterpretResponse",
]

