import pytest
from app.tool_discovery.keyword_search import KeywordSearch
from app.tool_discovery.metadata_filter import MetadataFilter
from app.tool_discovery.ranking import CompositeRanker
from app.tool_discovery.semantic_search import PluggableSemanticSearch
from app.tool_discovery.service import ToolDiscoveryService
from app.tool_registry.service import ToolRegistryService


def test_keyword_matching():
    search = KeywordSearch()
    tool = {
        "tool_id": "trello_create_card",
        "name": "Create Trello Card",
        "description": "Creates a new task card on the Trello board.",
        "keywords": ["card", "create", "new", "task"],
        "synonyms": ["add a card", "create a task"],
        "capabilities": ["create_card"],
    }

    # Keyword match
    score, matched = search.score("create a new card", tool)
    assert score > 0.4
    assert len(matched) > 0

    # Irrelevant query
    score_irrelevant, _ = search.score("prepare quarterly tax audit", tool)
    assert score_irrelevant == 0.0


def test_synonym_matching():
    search = KeywordSearch()
    tool = {
        "tool_id": "trello_create_card",
        "name": "Create Trello Card",
        "synonyms": ["post a card", "add an item", "new task"],
        "keywords": [],
        "capabilities": [],
        "description": "",
    }

    score, matched = search.score("post a card for the team", tool)
    assert score > 0.5
    assert any("synonym" in m for m in matched)


def test_metadata_filtering():
    filter_engine = MetadataFilter()
    sample_tools = [
        {
            "tool_id": "tool_enabled",
            "enabled": True,
            "category": "trello",
            "permissions": ["EMPLOYEE", "ADMIN"],
            "capabilities": ["create_card"],
        },
        {
            "tool_id": "tool_disabled",
            "enabled": False,  # Should NEVER be discoverable
            "category": "trello",
            "permissions": ["EMPLOYEE", "ADMIN"],
            "capabilities": ["create_card"],
        },
        {
            "tool_id": "tool_admin_only",
            "enabled": True,
            "category": "reporting",
            "permissions": ["ADMIN"],
            "capabilities": ["admin_report"],
        },
    ]

    # 1. Disabled tools must never pass
    active = filter_engine.filter(sample_tools, user_role="ADMIN")
    assert all(t["enabled"] for t in active)
    assert not any(t["tool_id"] == "tool_disabled" for t in active)

    # 2. Permission filtering: EMPLOYEE should not see admin_only
    emp_tools = filter_engine.filter(sample_tools, user_role="EMPLOYEE")
    assert any(t["tool_id"] == "tool_enabled" for t in emp_tools)
    assert not any(t["tool_id"] == "tool_admin_only" for t in emp_tools)

    # 3. Category filtering
    trello_only = filter_engine.filter(sample_tools, user_role="ADMIN", category="trello")
    assert all(t["category"] == "trello" for t in trello_only)

    # 4. Capability filtering
    cap_filtered = filter_engine.filter(sample_tools, user_role="ADMIN", required_capabilities=["admin_report"])
    assert len(cap_filtered) == 1
    assert cap_filtered[0]["tool_id"] == "tool_admin_only"


def test_composite_ranking():
    ranker = CompositeRanker()
    candidates = [
        {"tool": {"tool_id": "low_match"}, "keyword_score": 0.1, "semantic_score": 0.1, "category_score": 0.0},
        {"tool": {"tool_id": "high_match"}, "keyword_score": 0.9, "semantic_score": 0.8, "category_score": 1.0},
        {"tool": {"tool_id": "mid_match"}, "keyword_score": 0.5, "semantic_score": 0.5, "category_score": 0.0},
    ]

    ranked = ranker.rank(candidates, limit=2)
    assert len(ranked) == 2
    assert ranked[0]["tool"]["tool_id"] == "high_match"
    assert ranked[1]["tool"]["tool_id"] == "mid_match"
    assert ranked[0]["relevance_score"] > ranked[1]["relevance_score"]


@pytest.mark.asyncio
async def test_tool_discovery_service_end_to_end(mock_db):
    reg_service = ToolRegistryService(mock_db)
    await reg_service.seed_default_tools()

    discovery_service = ToolDiscoveryService(mock_db)

    # 1. Natural language query for card creation
    results = await discovery_service.discover_tools(
        query="Add a new card named Deploy Backend to In Progress",
        user_role="EMPLOYEE",
        limit=3,
    )
    assert len(results) >= 1
    assert results[0].tool.tool_id in ["trello_create_card", "trello_move_card"]
    assert results[0].relevance_score > 0.3

    # 2. Workload report discovery
    report_results = await discovery_service.discover_tools(
        query="Show me the weekly workload report for the team",
        user_role="EMPLOYEE",
        limit=3,
    )
    assert len(report_results) >= 1
    assert any("workload" in r.tool.tool_id for r in report_results)

    # 3. Completely unrelated query
    unrelated = await discovery_service.discover_tools(
        query="Bake a chocolate cake with strawberry frosting",
        user_role="EMPLOYEE",
        min_score=0.4,
    )
    assert len(unrelated) == 0

    # 4. Employee directory discovery
    emp_results = await discovery_service.discover_tools(
        query="List staff members and employee directory",
        user_role="EMPLOYEE",
        limit=3,
    )
    assert len(emp_results) >= 1
    assert any("employee" in r.tool.tool_id for r in emp_results)

    # 5. Disabled tool must not be discovered
    await reg_service.disable_tool("trello_create_card")
    after_disable = await discovery_service.discover_tools(
        query="Create a card",
        user_role="EMPLOYEE",
    )
    assert not any(r.tool.tool_id == "trello_create_card" for r in after_disable)

