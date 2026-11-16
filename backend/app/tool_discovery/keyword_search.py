import re
from typing import Any, Dict, List, Set, Tuple
from app.tool_discovery.interfaces import BaseKeywordSearch

STOPWORDS: Set[str] = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "with",
    "by", "is", "are", "was", "were", "be", "this", "that", "it",
    "i", "you", "we", "they", "please", "can", "could", "would",
    "my", "our", "me", "want", "need", "like", "do", "help",
}

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_\-]+")


def tokenize(text: str) -> List[str]:
    """Tokenize and filter stop words from a string."""
    tokens = TOKEN_PATTERN.findall(text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


class KeywordSearch(BaseKeywordSearch):
    """Lexical matching across tool IDs, names, descriptions, keywords, and synonyms."""

    def score(self, query: str, tool: Dict[str, Any]) -> Tuple[float, List[str]]:
        raw_query = query.lower().strip()
        query_tokens = tokenize(raw_query)
        if not query_tokens:
            return 0.0, []

        matched_criteria: List[str] = []
        raw_score = 0.0

        # 1. Exact or partial match on synonyms (Highest contextual value)
        synonyms = [s.lower() for s in tool.get("synonyms", [])]
        for syn in synonyms:
            if syn in raw_query or raw_query in syn:
                raw_score += 4.0
                matched_criteria.append(f"synonym_exact:{syn}")
                break
            else:
                syn_tokens = set(tokenize(syn))
                common = syn_tokens.intersection(query_tokens)
                if common:
                    raw_score += 2.0 * len(common)
                    matched_criteria.append(f"synonym_token:{','.join(common)}")

        # 2. Tool Name & Tool ID
        tool_name = str(tool.get("name", "")).lower()
        tool_id = str(tool.get("tool_id", "")).lower()
        name_tokens = set(tokenize(f"{tool_name} {tool_id}"))
        common_name = name_tokens.intersection(query_tokens)
        if common_name:
            raw_score += 3.0 * len(common_name)
            matched_criteria.append(f"name:{','.join(common_name)}")

        # 3. Keywords
        tool_keywords = [str(k).lower() for k in tool.get("keywords", [])]
        matched_kw = [k for k in tool_keywords if k in query_tokens or any(k in t for t in query_tokens)]
        if matched_kw:
            raw_score += 2.5 * len(matched_kw)
            matched_criteria.append(f"keyword:{','.join(matched_kw[:3])}")

        # 4. Capabilities
        tool_caps = [str(c).lower() for c in tool.get("capabilities", [])]
        matched_caps = [c for c in tool_caps if any(c in q or q in c for q in query_tokens)]
        if matched_caps:
            raw_score += 2.0 * len(matched_caps)
            matched_criteria.append(f"capability:{','.join(matched_caps)}")

        # 5. Description
        desc_tokens = set(tokenize(str(tool.get("description", ""))))
        common_desc = desc_tokens.intersection(query_tokens)
        if common_desc:
            raw_score += 0.8 * len(common_desc)
            matched_criteria.append(f"desc:{','.join(list(common_desc)[:2])}")

        # Normalize score into [0.0, 1.0] using an asymptote
        # A raw_score of 6.0 yields approx 0.75, 10.0 yields 0.85, 20.0 yields 0.95
        normalized_score = min(1.0, round(raw_score / (raw_score + 2.0), 4)) if raw_score > 0 else 0.0
        return normalized_score, matched_criteria

