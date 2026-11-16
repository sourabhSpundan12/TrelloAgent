import math
from collections import Counter
from typing import Any, Dict, List
from app.tool_discovery.interfaces import BaseSemanticSearch


def get_ngrams(text: str, n: int = 3) -> Counter:
    """Extract character n-grams for subword semantic representation."""
    cleaned = f" {text.lower().strip()} "
    return Counter([cleaned[i : i + n] for i in range(len(cleaned) - n + 1)])


def cosine_similarity(counter_a: Counter, counter_b: Counter) -> float:
    """Compute cosine similarity between two frequency vectors."""
    dot_product = sum(counter_a[k] * counter_b[k] for k in counter_a if k in counter_b)
    norm_a = math.sqrt(sum(v**2 for v in counter_a.values()))
    norm_b = math.sqrt(sum(v**2 for v in counter_b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


class PluggableSemanticSearch(BaseSemanticSearch):
    """
    Pluggable semantic search engine.
    Computes vector cosine similarity over subword n-gram representations.
    Designed to easily plug in MongoDB Atlas Vector Search or Gemini embeddings
    when an external vector database is configured, without local dependency.
    """

    def compute_similarity(self, query: str, tool: Dict[str, Any]) -> float:
        if not query or not query.strip():
            return 0.0

        query_vector = get_ngrams(query)

        # Build composite document representation for the tool
        doc_parts = [
            tool.get("name", ""),
            tool.get("description", ""),
            " ".join(tool.get("synonyms", [])),
            " ".join(tool.get("capabilities", [])),
            " ".join(tool.get("keywords", [])),
        ]
        tool_text = " ".join(p for p in doc_parts if p)
        tool_vector = get_ngrams(tool_text)

        sim = cosine_similarity(query_vector, tool_vector)
        return min(1.0, max(0.0, round(sim, 4)))

