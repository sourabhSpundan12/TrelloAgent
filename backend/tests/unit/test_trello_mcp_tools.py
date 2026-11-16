import pytest
from app.mcp_server.trello_tools import (
    set_trello_client,
    trello_archive_card,
    trello_create_card,
    trello_get_board,
    trello_get_card,
    trello_list_boards,
    trello_list_cards,
    trello_list_lists,
    trello_move_card,
    trello_update_card,
)
from tests.unit.test_trello_client import create_mock_trello_client


@pytest.fixture(autouse=True)
def setup_mock_trello():
    mock_client = create_mock_trello_client()
    set_trello_client(mock_client)
    yield
    set_trello_client(None)


@pytest.mark.asyncio
async def test_mcp_tool_trello_list_boards():
    res = await trello_list_boards()
    assert res["status"] == "SUCCESS"
    assert res["total"] == 2
    assert res["boards"][0]["name"] == "Sprint Board 2026"


@pytest.mark.asyncio
async def test_mcp_tool_trello_get_board():
    res = await trello_get_board(board_id="b101")
    assert res["status"] == "SUCCESS"
    assert res["board"]["id"] == "b101"


@pytest.mark.asyncio
async def test_mcp_tool_trello_list_lists():
    res = await trello_list_lists(board_id="b101")
    assert res["status"] == "SUCCESS"
    assert res["total"] == 3
    assert res["lists"][0]["name"] == "To Do"


@pytest.mark.asyncio
async def test_mcp_tool_trello_list_cards():
    res = await trello_list_cards(board_id="b101")
    assert res["status"] == "SUCCESS"
    assert res["total"] == 2


@pytest.mark.asyncio
async def test_mcp_tool_trello_get_card():
    res = await trello_get_card(card_id="c1")
    assert res["status"] == "SUCCESS"
    assert res["card"]["id"] == "c1"

    # Validation failure on empty ID
    err_res = await trello_get_card(card_id="")
    assert err_res["status"] == "ERROR"
    assert err_res["error"] is True


@pytest.mark.asyncio
async def test_mcp_tool_trello_create_card():
    res = await trello_create_card(name="New Task From MCP", desc="Detailed spec")
    assert res["status"] == "SUCCESS"
    assert res["action"] == "CREATED"
    assert res["card"]["name"] == "New Task From MCP"

    # Empty name error
    err_res = await trello_create_card(name="")
    assert err_res["status"] == "ERROR"


@pytest.mark.asyncio
async def test_mcp_tool_trello_update_card():
    res = await trello_update_card(card_id="c1", name="Updated Task Title")
    assert res["status"] == "SUCCESS"
    assert res["action"] == "UPDATED"
    assert res["card"]["name"] == "Updated Task Title"

    err_res = await trello_update_card(card_id="")
    assert err_res["status"] == "ERROR"


@pytest.mark.asyncio
async def test_mcp_tool_trello_move_card():
    res = await trello_move_card(card_id="c1", list_id="l_done")
    assert res["status"] == "SUCCESS"
    assert res["action"] == "MOVED"
    assert res["card"]["idList"] == "l_done"

    err_res = await trello_move_card(card_id="c1", list_id="")
    assert err_res["status"] == "ERROR"


@pytest.mark.asyncio
async def test_mcp_tool_trello_archive_card():
    res = await trello_archive_card(card_id="c1")
    assert res["status"] == "SUCCESS"
    assert res["action"] == "ARCHIVED"
    assert res["card"]["closed"] is True

    err_res = await trello_archive_card(card_id="")
    assert err_res["status"] == "ERROR"

