from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.logging import logger
from app.tool_discovery.keyword_search import KeywordSearch
from app.tool_discovery.metadata_filter import MetadataFilter
from app.tool_discovery.ranking import CompositeRanker
from app.tool_discovery.schemas import (
    DiscoveredToolItem,
    ToolDiscoveryRequest,
    ToolDiscoveryResponse,
)
from app.tool_discovery.semantic_search import PluggableSemanticSearch
from app.tool_registry.repository import ToolRepository
from app.tool_registry.schemas import ToolResponse
from app.tool_registry.service import ToolRegistryService


class ToolDiscoveryService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.repo = ToolRepository(db)
        self.registry_service = ToolRegistryService(db)
        self.metadata_filter = MetadataFilter()
        self.keyword_search = KeywordSearch()
        self.semantic_search = PluggableSemanticSearch()
        self.ranker = CompositeRanker()

    async def discover_tools(
        self,
        query: str,
        user_role: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 5,
        min_score: float = 0.05,
        required_capabilities: Optional[List[str]] = None,
    ) -> List[DiscoveredToolItem]:
        """
        Dynamically discovers and ranks relevant tools from MongoDB based on user query and permissions.
        Ensures disabled tools are excluded and never exposes all 500+ tools at once.
        """
        # Ensure database has default tools seeded if completely empty
        tool_count = await self.repo.count()
        if tool_count == 0:
            await self.registry_service.seed_default_tools()

        # Step 1: Fetch active enabled tools from MongoDB
        active_tools = await self.repo.get_active_tools(category=category)

        # Step 2: Metadata filtering (enforces permissions, capabilities, categories)
        eligible_tools = self.metadata_filter.filter(
            tools=active_tools,
            user_role=user_role,
            category=category,
            required_capabilities=required_capabilities,
        )

        if not eligible_tools:
            logger.info(f"Discovery found 0 eligible tools for role='{user_role}'")
            return []

        # Step 3: Hybrid Scoring (Keyword + Semantic + Category alignment)
        scored_candidates = []
        for tool in eligible_tools:
            kw_score, matched_terms = self.keyword_search.score(query, tool)
            sem_score = self.semantic_search.compute_similarity(query, tool)

            category_score = 0.0
            if category and str(tool.get("category", "")).lower() == category.lower():
                category_score = 1.0

            scored_candidates.append({
                "tool": tool,
                "keyword_score": kw_score,
                "semantic_score": sem_score,
                "category_score": category_score,
                "matched_by": matched_terms,
            })

        # Step 4: Composite Ranking and Top-K Truncation
        ranked = self.ranker.rank(scored_candidates, limit=limit, min_score=min_score)

        results: List[DiscoveredToolItem] = []
        for item in ranked:
            tool_doc = item["tool"]
            relevance = item["relevance_score"]
            matched_by = item["matched_by"]

            # Human-readable discovery explanation
            match_summary = ", ".join(matched_by[:3]) if matched_by else "semantic context"
            explanation = (
                f"Selected '{tool_doc.get('name')}' (relevance: {int(relevance * 100)}%) "
                f"matched via {match_summary}."
            )

            results.append(
                DiscoveredToolItem(
                    tool=ToolResponse(**tool_doc),
                    relevance_score=relevance,
                    matched_by=matched_by,
                    explanation=explanation,
                )
            )

        logger.info(
            f"Discovered {len(results)} relevant tools for role='{user_role}' (searched {len(active_tools)} tools)"
        )
        return results

    async def handle_discovery_request(
        self,
        req: ToolDiscoveryRequest,
        user_role: Optional[str] = None,
    ) -> ToolDiscoveryResponse:
        """API handler wrapper for standalone tool discovery endpoint."""
        total_active = len(await self.repo.get_active_tools(category=req.category))
        discovered = await self.discover_tools(
            query=req.query,
            user_role=user_role,
            category=req.category,
            limit=req.limit,
            min_score=req.min_score,
        )
        return ToolDiscoveryResponse(
            query=req.query,
            total_candidates_searched=total_active,
            total_matched=len(discovered),
            tools=discovered,
        )

