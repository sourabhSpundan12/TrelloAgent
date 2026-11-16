from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class BaseMetadataFilter(ABC):
    @abstractmethod
    def filter(
        self,
        tools: List[Dict[str, Any]],
        user_role: Optional[str] = None,
        category: Optional[str] = None,
        required_capabilities: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Filter candidate tools by metadata, enabled state, category, and role permissions."""
        pass


class BaseKeywordSearch(ABC):
    @abstractmethod
    def score(self, query: str, tool: Dict[str, Any]) -> Tuple[float, List[str]]:
        """Scores a tool against the query text and returns (score, matched_terms)."""
        pass


class BaseSemanticSearch(ABC):
    @abstractmethod
    def compute_similarity(self, query: str, tool: Dict[str, Any]) -> float:
        """Computes semantic similarity between query and tool metadata [0.0, 1.0]."""
        pass


class BaseRanker(ABC):
    @abstractmethod
    def rank(
        self,
        scored_candidates: List[Dict[str, Any]],
        limit: int = 5,
        min_score: float = 0.05,
    ) -> List[Dict[str, Any]]:
        """Ranks and selects top candidate tools."""
        pass

