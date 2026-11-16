from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class DetectedEntity(BaseModel):
    """Represents a single PII entity detected in text."""
    entity_type: str
    start: int
    end: int
    score: float
    text: Optional[str] = None


class PIIMaskResult(BaseModel):
    """
    Request-scoped result of a PII masking operation.
    The mapping must NEVER be sent to external LLMs or logged.
    It is retained only in the local request lifecycle for local parameter restoration.
    """
    original_text: str
    masked_text: str
    detected_entities: List[DetectedEntity] = Field(default_factory=list)
    # Mapping of placeholder -> original sensitive value (request-scoped)
    mapping: Dict[str, str] = Field(default_factory=dict)
    # Reverse mapping of original sensitive value -> placeholder
    reverse_mapping: Dict[str, str] = Field(default_factory=dict)

    @property
    def has_pii(self) -> bool:
        return len(self.detected_entities) > 0

    @property
    def entity_count(self) -> int:
        return len(self.detected_entities)

