import copy
import time
from typing import Any, Dict, List, Optional
from app.core.logging import logger
from app.integrations.trello.client import TrelloClient
from app.integrations.trello.exceptions import TrelloError

# Module-level client factory for easy overriding in tests
_trello_client_instance: Optional[TrelloClient] = None

# In-memory TTL cache for high-frequency read operations to prevent external API stalls
_trello_cache: Dict[str, tuple[float, Any]] = {}
CACHE_TTL_SECONDS = 5.0


def invalidate_trello_cache() -> None:
    """Clear cached Trello API results so next queries fetch fresh data."""
    global _trello_cache
    _trello_cache.clear()


def get_trello_client() -> TrelloClient:
    global _trello_client_instance
    if _trello_client_instance is None:
        return TrelloClient()
    return _trello_client_instance


def set_trello_client(client: Optional[TrelloClient]) -> None:
    global _trello_client_instance
    _trello_client_instance = client
    invalidate_trello_cache()


async def trello_list_boards(force_refresh: bool = False) -> Dict[str, Any]:
    """List all Trello boards accessible with current credentials."""
    cache_key = "boards:all"
    now = time.time()
    if not force_refresh and cache_key in _trello_cache:
        c_time, c_data = _trello_cache[cache_key]
        if now - c_time < CACHE_TTL_SECONDS:
            return copy.deepcopy(c_data)

    client = get_trello_client()
    try:
        boards = await client.list_boards()
        res = {"status": "SUCCESS", "boards": boards, "total": len(boards)}
        _trello_cache[cache_key] = (now, res)
        return copy.deepcopy(res)
    except TrelloError as err:
        logger.warning(f"trello_list_boards failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_get_board(board_id: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """Retrieve details and metadata for a specific Trello board (defaults to configured board ID)."""
    cache_key = f"board:{board_id}"
    now = time.time()
    if not force_refresh and cache_key in _trello_cache:
        c_time, c_data = _trello_cache[cache_key]
        if now - c_time < CACHE_TTL_SECONDS:
            return copy.deepcopy(c_data)

    client = get_trello_client()
    try:
        board = await client.get_board(board_id=board_id)
        res = {"status": "SUCCESS", "board": board}
        _trello_cache[cache_key] = (now, res)
        return copy.deepcopy(res)
    except TrelloError as err:
        logger.warning(f"trello_get_board failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_list_board_members(board_id: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """List all members belonging to the target board."""
    cache_key = f"members:{board_id}"
    now = time.time()
    if not force_refresh and cache_key in _trello_cache:
        c_time, c_data = _trello_cache[cache_key]
        if now - c_time < CACHE_TTL_SECONDS:
            return copy.deepcopy(c_data)

    client = get_trello_client()
    try:
        members = await client.list_board_members(board_id=board_id)
        res = {"status": "SUCCESS", "members": members, "total": len(members)}
        _trello_cache[cache_key] = (now, res)
        return copy.deepcopy(res)
    except TrelloError as err:
        logger.warning(f"trello_list_board_members failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_list_board_actions(board_id: Optional[str] = None, limit: int = 50, force_refresh: bool = False) -> Dict[str, Any]:
    """List recent activity actions from Trello board with caching."""
    cache_key = f"board_actions:{board_id}:{limit}"
    now = time.time()
    if not force_refresh and cache_key in _trello_cache:
        c_time, c_data = _trello_cache[cache_key]
        if now - c_time < CACHE_TTL_SECONDS:
            return copy.deepcopy(c_data)

    client = get_trello_client()
    try:
        actions = await client.list_board_actions(board_id=board_id, limit=limit)
        res = {"status": "SUCCESS", "actions": actions, "total": len(actions)}
        _trello_cache[cache_key] = (now, res)
        return copy.deepcopy(res)
    except Exception as err:
        logger.debug(f"trello_list_board_actions skipped: {err}")
        return {"status": "ERROR", "actions": [], "total": 0, "error": str(err)}


async def trello_list_lists(board_id: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """List all open columns/lists on a Trello board (defaults to configured board ID)."""
    cache_key = f"lists:{board_id}"
    now = time.time()
    if not force_refresh and cache_key in _trello_cache:
        c_time, c_data = _trello_cache[cache_key]
        if now - c_time < CACHE_TTL_SECONDS:
            return copy.deepcopy(c_data)

    client = get_trello_client()
    try:
        lists = await client.list_lists(board_id=board_id)
        res = {"status": "SUCCESS", "lists": lists, "total": len(lists)}
        _trello_cache[cache_key] = (now, res)
        return copy.deepcopy(res)
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
    invalidate_trello_cache()
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
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """List cards on a Trello board or within a specific list (defaults to configured board ID)."""
    cache_key = f"cards:{board_id}:{list_id}"
    now = time.time()
    if not force_refresh and cache_key in _trello_cache:
        c_time, c_data = _trello_cache[cache_key]
        if now - c_time < CACHE_TTL_SECONDS:
            return copy.deepcopy(c_data)

    client = get_trello_client()
    try:
        cards = await client.list_cards(board_id=board_id, list_id=list_id)
        res = {"status": "SUCCESS", "cards": cards, "total": len(cards)}
        _trello_cache[cache_key] = (now, res)
        return copy.deepcopy(res)
    except TrelloError as err:
        logger.warning(f"trello_list_cards failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}


async def trello_get_card(card_id: str, force_refresh: bool = False) -> Dict[str, Any]:
    """Retrieve details and status for a specific Trello card by ID."""
    if not card_id or not card_id.strip():
        return {"status": "ERROR", "error": True, "message": "card_id is required."}
    cache_key = f"card:{card_id.strip()}"
    now = time.time()
    if not force_refresh and cache_key in _trello_cache:
        c_time, c_data = _trello_cache[cache_key]
        if now - c_time < CACHE_TTL_SECONDS:
            return copy.deepcopy(c_data)

    client = get_trello_client()
    try:
        card = await client.get_card(card_id=card_id.strip())
        res = {"status": "SUCCESS", "card": card}
        _trello_cache[cache_key] = (now, res)
        return copy.deepcopy(res)
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
    invalidate_trello_cache()
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
    invalidate_trello_cache()
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
    if desc and str(desc).lower().startswith("move card"):
        desc = None
    invalidate_trello_cache()
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
    invalidate_trello_cache()
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
    invalidate_trello_cache()
    client = get_trello_client()
    try:
        res = await client.delete_card(card_id=card_id.strip())
        return {"status": "SUCCESS", "action": "DELETED", "card": res}
    except Exception as err:
        logger.warning(f"trello_delete_card failed ({err}); attempting archive fallback.")
        return await trello_archive_card(card_id=card_id)


async def trello_add_comment(card_id: str, text: str) -> Dict[str, Any]:
    """Post a comment on an existing Trello card (Module 5 One-Hour Reminder)."""
    if not card_id or not card_id.strip():
        return {"status": "ERROR", "error": True, "message": "card_id is required."}
    if not text or not text.strip():
        return {"status": "ERROR", "error": True, "message": "text is required."}
    client = get_trello_client()
    try:
        comment = await client.add_comment(card_id=card_id.strip(), text=text.strip())
        return {"status": "SUCCESS", "action": "COMMENT_ADDED", "comment": comment}
    except TrelloError as err:
        logger.warning(f"trello_add_comment failed: {err}")
        return {"status": "ERROR", "error": True, "message": err.message, "status_code": err.status_code}
    except Exception as err:
        logger.warning(f"trello_add_comment unexpected error: {err}")
        return {"status": "ERROR", "error": True, "message": str(err)}


