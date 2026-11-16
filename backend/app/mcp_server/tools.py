from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def get_sample_board_data() -> Dict[str, Any]:
    return {
        "board_name": "Sprint Board 2026-Q4",
        "lists": [
            {"id": "list_1", "name": "TODO", "card_count": 8},
            {"id": "list_2", "name": "IN_PROGRESS", "card_count": 5},
            {"id": "list_3", "name": "IN_REVIEW", "card_count": 3},
            {"id": "list_4", "name": "DONE", "card_count": 14},
        ],
        "total_cards": 30,
        "completion_rate_percent": 46.7,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def search_sample_tasks(query: str = "", status: Optional[str] = None) -> List[Dict[str, Any]]:
    tasks = [
        {
            "id": "c101",
            "name": "Implement MCP Integration",
            "status": "IN_PROGRESS",
            "assignee": "EMP-101",
            "priority": "HIGH",
        },
        {
            "id": "c102",
            "name": "Configure Streamable HTTP Transport",
            "status": "DONE",
            "assignee": "EMP-102",
            "priority": "HIGH",
        },
        {
            "id": "c103",
            "name": "Design React Tool Management UI",
            "status": "IN_PROGRESS",
            "assignee": "EMP-103",
            "priority": "MEDIUM",
        },
        {
            "id": "c104",
            "name": "Audit SSRF Protection Rules",
            "status": "DONE",
            "assignee": "EMP-101",
            "priority": "CRITICAL",
        },
        {
            "id": "c105",
            "name": "Implement Employee Workload Dashboard",
            "status": "TODO",
            "assignee": "EMP-104",
            "priority": "LOW",
        },
    ]

    query_lower = query.lower()
    results = []
    for t in tasks:
        match_query = not query_lower or query_lower in t["name"].lower() or query_lower in t["id"].lower()
        match_status = not status or t["status"].upper() == status.upper()
        if match_query and match_status:
            results.append(t)
    return results


def get_sample_system_status() -> Dict[str, Any]:
    return {
        "status": "HEALTHY",
        "service": "agentic-task-manager",
        "version": "1.0.0",
        "mcp_version": "2.3.0",
        "subsystems": {
            "database": "CONNECTED",
            "tool_registry": "OPERATIONAL",
            "orchestrator": "READY",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

