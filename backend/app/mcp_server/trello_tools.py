from typing import Any, Dict, List, Optional
from app.core.logging import logger
from app.integrations.trello.client import TrelloClient
from app.integrations.trello.exceptions import TrelloError

# Module-level client factory for easy overriding in tests
_trello_client_instance: Optional[TrelloClient] = None


def get_trello_client() -> TrelloClient:
    global _trello_client_instance
    if _trello_client_instance is None:
        return TrelloClient()
    return _trello_client_instance


def set_trello_client(client: Optional[TrelloClient]) -> None:
    global _trello_client_instance
    _trello_client_instance = client


async def trello_list_boards() -> Dict[str, Any]:
    """List all Trello boards accessible with current credentials."""
    client = get_trello_client()
    try:
        boards = await client.list_boards()
        return {"status": "SUCCESS", "boards": boards, "total": len(boards)}
    except TrelloError as err:
        logger.warning(f"trello_list_boards failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_get_board(board_id: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve details and metadata for a specific Trello board (defaults to configured board ID)."""
    client = get_trello_client()
    try:
        board = await client.get_board(board_id=board_id)
        return {"status": "SUCCESS", "board": board}
    except TrelloError as err:
        logger.warning(f"trello_get_board failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_list_board_members(board_id: Optional[str] = None) -> Dict[str, Any]:
    """List all members belonging to the target board."""
    client = get_trello_client()
    try:
        members = await client.list_board_members(board_id=board_id)
        return {"status": "SUCCESS", "members": members, "total": len(members)}
    except TrelloError as err:
        logger.warning(f"trello_list_board_members failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_list_lists(board_id: Optional[str] = None) -> Dict[str, Any]:
    """List all open columns/lists on a Trello board (defaults to configured board ID)."""
    client = get_trello_client()
    try:
        lists = await client.list_lists(board_id=board_id)
        return {"status": "SUCCESS", "lists": lists, "total": len(lists)}
    except TrelloError as err:
        logger.warning(f"trello_list_lists failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_create_list(
    name: str,
    board_id: Optional[str] = None,
    pos: Optional[str] = "bottom",
) -> Dict[str, Any]:
    """Create a new column/list on the Trello board."""
    if not name or not name.strip():
        return {"status": "ERROR", "error": True, "message": "List name is required."}
    client = get_trello_client()
    try:
        new_list = await client.create_list(name=name.strip(), board_id=board_id, pos=pos)
        return {"status": "SUCCESS", "action": "CREATED", "list": new_list}
    except TrelloError as err:
        logger.warning(f"trello_create_list failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_list_cards(
    board_id: Optional[str] = None,
    list_id: Optional[str] = None,
) -> Dict[str, Any]:
    """List cards on a Trello board or within a specific list (defaults to configured board ID)."""
    client = get_trello_client()
    try:
        cards = await client.list_cards(board_id=board_id, list_id=list_id)
        return {"status": "SUCCESS", "cards": cards, "total": len(cards)}
    except TrelloError as err:
        logger.warning(f"trello_list_cards failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_get_card(card_id: str) -> Dict[str, Any]:
    """Retrieve details and status for a specific Trello card by ID."""
    if not card_id or not card_id.strip():
        return {"status": "ERROR", "error": True, "message": "card_id is required."}
    client = get_trello_client()
    try:
        card = await client.get_card(card_id=card_id.strip())
        return {"status": "SUCCESS", "card": card}
    except TrelloError as err:
        logger.warning(f"trello_get_card failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_create_card(
    name: str,
    list_id: Optional[str] = None,
    desc: Optional[str] = "",
    due_date: Optional[str] = None,
    board_id: Optional[str] = None,
    member_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new task card on the Trello board. If list_id is omitted, places in first open list."""
    if not name or not name.strip():
        return {"status": "ERROR", "error": True, "message": "Card name is required."}
    client = get_trello_client()
    try:
        card = await client.create_card(
            name=name.strip(),
            list_id=list_id,
            desc=desc,
            due=due_date,
            member_name=member_name,
            board_id=board_id,
        )
        return {"status": "SUCCESS", "action": "CREATED", "card": card}
    except TrelloError as err:
        logger.warning(f"trello_create_card failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_update_card(
    card_id: str,
    name: Optional[str] = None,
    desc: Optional[str] = None,
    due_date: Optional[str] = None,
    member_name: Optional[str] = None,
    board_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Update title, description, due date, and/or assign a member to an existing Trello card."""
    if not card_id or not card_id.strip():
        return {"status": "ERROR", "error": True, "message": "card_id is required."}
    if name is None and desc is None and due_date is None and member_name is None:
        return {"status": "ERROR", "error": True, "message": "At least one field ('name', 'desc', 'due_date', or 'member_name') must be provided."}
    client = get_trello_client()
    try:
        card = await client.update_card(
            card_id=card_id.strip(),
            name=name,
            desc=desc,
            due=due_date,
            member_name=member_name,
            board_id=board_id,
        )
        return {"status": "SUCCESS", "action": "UPDATED", "card": card}
    except TrelloError as err:
        logger.warning(f"trello_update_card failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_move_card(
    card_id: str,
    list_id: str,
    due_date: Optional[str] = None,
    desc: Optional[str] = None,
    board_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Move an existing Trello card to another list/column on the board, optionally updating due date and description."""
    if not card_id or not card_id.strip():
        return {"status": "ERROR", "error": True, "message": "card_id is required."}
    if not list_id or not list_id.strip():
        return {"status": "ERROR", "error": True, "message": "list_id is required."}
    client = get_trello_client()
    try:
        card = await client.move_card(card_id=card_id.strip(), list_id=list_id.strip(), due=due_date, desc=desc, board_id=board_id)
        return {"status": "SUCCESS", "action": "MOVED", "card": card}
    except TrelloError as err:
        logger.warning(f"trello_move_card failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_archive_card(card_id: str) -> Dict[str, Any]:
    """Archive (close) an existing Trello card."""
    if not card_id or not card_id.strip():
        return {"status": "ERROR", "error": True, "message": "card_id is required."}
    client = get_trello_client()
    try:
        card = await client.archive_card(card_id=card_id.strip())
        return {"status": "SUCCESS", "action": "ARCHIVED", "card": card}
    except TrelloError as err:
        logger.warning(f"trello_archive_card failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_delete_card(card_id: str) -> Dict[str, Any]:
    """Permanently delete a card from Trello board (falls back to archive if delete endpoint blocked)."""
    if not card_id or not card_id.strip():
        return {"status": "ERROR", "error": True, "message": "card_id is required."}
    client = get_trello_client()
    try:
        res = await client.delete_card(card_id=card_id.strip())
        return {"status": "SUCCESS", "action": "DELETED", "card": res}
    except Exception as err:
        logger.warning(f"trello_delete_card failed ({err}); attempting archive fallback.")
        return await trello_archive_card(card_id=card_id)

