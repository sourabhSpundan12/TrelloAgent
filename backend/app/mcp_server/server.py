from typing import Any, Dict, List, Optional
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from app.mcp_server.tools import (
    get_sample_board_data,
    get_sample_system_status,
    search_sample_tasks,
)
from app.mcp_server import trello_tools

# Instantiate the official MCP Server
mcp_server = MCPServer(
    name="agentic-task-manager-server",
    instructions="Agentic Task Manager capabilities and live Trello REST API integration exposed via Model Context Protocol.",
)

# ---------------------------------------------------------------------------
# Phase 4B: Existing Built-in Read-Only Capabilities
# ---------------------------------------------------------------------------

@mcp_server.tool(
    name="mcp_get_board_summary",
    description="Retrieve high-level board summary with list names, card counts, and completion metrics.",
)
def mcp_get_board_summary(board_name: Optional[str] = "Sprint Board") -> Dict[str, Any]:
    """Provides high-level board status and summary metrics."""
    data = get_sample_board_data()
    if board_name:
        data["board_name"] = board_name
    return data


@mcp_server.tool(
    name="mcp_search_tasks",
    description="Perform read-only task search across cards by keyword query and optional status.",
)
def mcp_search_tasks(
    query: str = "",
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """Searches tasks matching keyword and optional status filter."""
    matched = search_sample_tasks(query=query, status=status)
    return {
        "query": query,
        "status_filter": status,
        "total_matched": len(matched),
        "tasks": matched,
    }


@mcp_server.tool(
    name="mcp_get_system_status",
    description="Inspect overall platform health, active subsystem status, and MCP runtime version.",
)
def mcp_get_system_status() -> Dict[str, Any]:
    """Returns platform operational health status."""
    return get_sample_system_status()


# ---------------------------------------------------------------------------
# Phase 5: Official Trello MCP Tools
# ---------------------------------------------------------------------------

@mcp_server.tool(
    name="trello_list_boards",
    description="List all Trello boards accessible with current API credentials.",
)
async def tool_trello_list_boards() -> Dict[str, Any]:
    return await trello_tools.trello_list_boards()


@mcp_server.tool(
    name="trello_get_board",
    description="Retrieve details and metadata for a specific Trello board (defaults to configured board ID).",
)
async def tool_trello_get_board(board_id: Optional[str] = None) -> Dict[str, Any]:
    return await trello_tools.trello_get_board(board_id=board_id)


@mcp_server.tool(
    name="trello_list_lists",
    description="List all open columns/lists on a Trello board (defaults to configured board ID).",
)
async def tool_trello_list_lists(board_id: Optional[str] = None) -> Dict[str, Any]:
    return await trello_tools.trello_list_lists(board_id=board_id)


@mcp_server.tool(
    name="trello_create_list",
    description="Create a new column or list on the Trello board (e.g. In-Review, Backlog).",
)
async def tool_trello_create_list(
    name: str,
    board_id: Optional[str] = None,
    pos: Optional[str] = "bottom",
) -> Dict[str, Any]:
    return await trello_tools.trello_create_list(name=name, board_id=board_id, pos=pos)


@mcp_server.tool(
    name="trello_list_cards",
    description="List cards on a Trello board or within a specific list (defaults to configured board ID).",
)
async def tool_trello_list_cards(
    board_id: Optional[str] = None,
    list_id: Optional[str] = None,
) -> Dict[str, Any]:
    return await trello_tools.trello_list_cards(board_id=board_id, list_id=list_id)


@mcp_server.tool(
    name="trello_get_card",
    description="Retrieve details and status for a specific Trello card by ID.",
)
async def tool_trello_get_card(card_id: str) -> Dict[str, Any]:
    return await trello_tools.trello_get_card(card_id=card_id)


@mcp_server.tool(
    name="trello_create_card",
    description="Create a new task card on the Trello board. If list_id is omitted, places in first open list.",
)
async def tool_trello_create_card(
    name: str,
    list_id: Optional[str] = None,
    desc: Optional[str] = "",
    due_date: Optional[str] = None,
    board_id: Optional[str] = None,
    member_name: Optional[str] = None,
) -> Dict[str, Any]:
    return await trello_tools.trello_create_card(
        name=name,
        list_id=list_id,
        desc=desc,
        due_date=due_date,
        board_id=board_id,
        member_name=member_name,
    )


@mcp_server.tool(
    name="trello_update_card",
    description="Update title, description, due date, and/or assign a member to an existing Trello card.",
)
async def tool_trello_update_card(
    card_id: str,
    name: Optional[str] = None,
    desc: Optional[str] = None,
    due_date: Optional[str] = None,
    member_name: Optional[str] = None,
) -> Dict[str, Any]:
    return await trello_tools.trello_update_card(card_id=card_id, name=name, desc=desc, due_date=due_date, member_name=member_name)


@mcp_server.tool(
    name="trello_move_card",
    description="Move an existing Trello card to another list/column on the board, optionally updating due date and description.",
)
async def tool_trello_move_card(
    card_id: str,
    list_id: str,
    due_date: Optional[str] = None,
    desc: Optional[str] = None,
    board_id: Optional[str] = None,
) -> Dict[str, Any]:
    return await trello_tools.trello_move_card(card_id=card_id, list_id=list_id, due_date=due_date, desc=desc, board_id=board_id)


@mcp_server.tool(
    name="trello_archive_card",
    description="Archive (close) an existing Trello card.",
)
async def tool_trello_archive_card(card_id: str) -> Dict[str, Any]:
    return await trello_tools.trello_archive_card(card_id=card_id)


# ---------------------------------------------------------------------------
# Transports
# ---------------------------------------------------------------------------

def create_mcp_streamable_app(streamable_http_path: str = "/mcp") -> Starlette:
    """Creates a configured Starlette app serving the MCP server over Streamable HTTP."""
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    )
    return mcp_server.streamable_http_app(
        streamable_http_path=streamable_http_path,
        transport_security=security,
    )


def create_mcp_sse_app() -> Starlette:
    """Creates a configured Starlette app serving the MCP server over SSE."""
    return mcp_server.sse_app()
