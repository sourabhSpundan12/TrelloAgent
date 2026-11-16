import pytest
from app.mcp_server.server import (
    mcp_get_board_summary,
    mcp_get_system_status,
    mcp_search_tasks,
    mcp_server,
)


def test_mcp_get_board_summary():
    data = mcp_get_board_summary(board_name="Sprint Q4")
    assert data["board_name"] == "Sprint Q4"
    assert "lists" in data
    assert len(data["lists"]) == 4
    assert data["total_cards"] == 30
    assert data["completion_rate_percent"] > 0


def test_mcp_search_tasks():
    res = mcp_search_tasks(query="MCP")
    assert res["query"] == "MCP"
    assert res["total_matched"] >= 1
    assert any("MCP" in t["name"] for t in res["tasks"])

    done_res = mcp_search_tasks(query="", status="DONE")
    assert done_res["total_matched"] >= 1
    assert all(t["status"] == "DONE" for t in done_res["tasks"])


def test_mcp_get_system_status():
    status = mcp_get_system_status()
    assert status["status"] == "HEALTHY"
    assert status["subsystems"]["database"] == "CONNECTED"
    assert status["subsystems"]["tool_registry"] == "OPERATIONAL"


@pytest.mark.asyncio
async def test_mcp_server_lists_tools():
    tools = await mcp_server.list_tools()
    tool_names = [t.name for t in tools]
    assert "mcp_get_board_summary" in tool_names
    assert "mcp_search_tasks" in tool_names
    assert "mcp_get_system_status" in tool_names

