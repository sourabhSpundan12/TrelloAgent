from typing import Any, Dict, List
from app.tool_discovery.interfaces import BaseRanker


class CompositeRanker(BaseRanker):
    """
    Ranks tool candidates using weighted aggregation of keyword score,
    semantic similarity, category alignment, and capability matches.
    """

    def __init__(
        self,
        weight_keyword: float = 0.55,
        weight_semantic: float = 0.35,
        weight_category: float = 0.10,
    ):
        self.weight_keyword = weight_keyword
        self.weight_semantic = weight_semantic
        self.weight_category = weight_category

    def rank(
        self,
        scored_candidates: List[Dict[str, Any]],
        limit: int = 5,
        min_score: float = 0.05,
    ) -> List[Dict[str, Any]]:
        ranked = []

        for item in scored_candidates:
            kw_score = item.get("keyword_score", 0.0)
            sem_score = item.get("semantic_score", 0.0)
            cat_score = item.get("category_score", 0.0)

            # Weighted final composite score
            composite = (
                (kw_score * self.weight_keyword)
                + (sem_score * self.weight_semantic)
                + (cat_score * self.weight_category)
            )

            # Cap score between 0.0 and 1.0
            final_score = min(1.0, max(0.0, round(composite, 4)))

            if final_score >= min_score:
                candidate_copy = dict(item)
                candidate_copy["relevance_score"] = final_score
                ranked.append(candidate_copy)

        # Sort by relevance_score descending, then by approval_required (read-only first if equal)
        ranked.sort(key=lambda x: x["relevance_score"], reverse=True)

        return ranked[:limit]

