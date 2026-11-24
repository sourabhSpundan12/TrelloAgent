from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)


async def ensure_default_board(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Ensures that the environment default Trello board exists in the boards collection.
    If it's missing, it is created automatically so it always appears alongside user boards.
    """
    boards_coll = db["boards"]
    default_id = (settings.TRELLO_BOARD_ID or "").strip()

    # 1. Ensure the primary board from settings/env exists
    if default_id:
        existing_primary = await boards_coll.find_one(
            {"$or": [{"board_id": default_id}, {"id": default_id}]}
        )
        if not existing_primary:
            # Check if any board is already active
            has_active = await boards_coll.find_one({"is_active": True})
            now = datetime.now(timezone.utc)
            primary_doc = {
                "id": default_id,
                "board_id": default_id,
                "name": "Primary Trello Board",
                "desc": "Main configured Trello board from platform environment",
                "url": f"https://trello.com/b/{default_id}",
                "is_active": not bool(has_active),
                "created_at": now,
                "updated_at": now,
            }
            await boards_coll.insert_one(primary_doc)
            primary_doc.pop("_id", None)
            logger.info(f"Seeded primary Trello board '{default_id}' into database.")
            return primary_doc
        else:
            # Ensure both id and board_id fields are populated
            if not existing_primary.get("board_id") or not existing_primary.get("id"):
                await boards_coll.update_one(
                    {"_id": existing_primary["_id"]},
                    {"$set": {"board_id": default_id, "id": default_id}},
                )

    # 2. If collection has zero documents, insert fallback
    count = await boards_coll.count_documents({})
    if count == 0:
        fallback_id = default_id or "default-trello-board"
        now = datetime.now(timezone.utc)
        fallback_doc = {
            "id": fallback_id,
            "board_id": fallback_id,
            "name": "Primary Trello Board",
            "desc": "Main configured Trello board from platform environment",
            "url": f"https://trello.com/b/{fallback_id}",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        await boards_coll.insert_one(fallback_doc)
        fallback_doc.pop("_id", None)
        return fallback_doc

    active = await boards_coll.find_one({"is_active": True})
    if active:
        active.pop("_id", None)
        return active

    return {}


async def resolve_active_board(
    db: AsyncIOMotorDatabase,
    requested_board_id: Optional[str] = None,
    command: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Resolves target board ID and name dynamically:
    1. If user explicitly specified a board in command or parameters (e.g. "My Trello Board", "mytrello", "Agentic Task Manager"), match against registered boards in database.
    2. Otherwise, use requested_board_id from client if provided.
    3. Otherwise, use active board (is_active: True) from database.
    4. Otherwise, fallback to default configured board.
    Returns dict: {"board_id": str, "name": str}
    """
    boards_coll = db["boards"]
    all_boards = []
    try:
        cursor = boards_coll.find({})
        async for doc in cursor:
            b_id = str(doc.get("board_id") or doc.get("id") or "").strip()
            if b_id:
                all_boards.append({
                    "board_id": b_id,
                    "name": str(doc.get("name") or "").strip(),
                    "is_active": bool(doc.get("is_active", False)),
                })
    except Exception as exc:
        logger.warning(f"Error reading boards for resolution: {exc}")

    def norm_str(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())

    # 1. Use client-provided requested_board_id FIRST (reflects the currently active board selected in UI)
    if requested_board_id and str(requested_board_id).strip():
        req_id = str(requested_board_id).strip()
        for b in all_boards:
            if b["board_id"] == req_id:
                # Only allow command to override if user explicitly used phrases like "on board <Name>" or "in <Name> board"
                if command:
                    cmd_lower = command.lower()
                    for other_b in all_boards:
                        if other_b["board_id"] == req_id or not other_b["name"]:
                            continue
                        ob_name_lower = other_b["name"].lower()
                        # Require explicit board preposition: "on board X", "in board X", "to board X", "on X board", "in X board", "switch to X"
                        if (
                            f"on board {ob_name_lower}" in cmd_lower
                            or f"in board {ob_name_lower}" in cmd_lower
                            or f"to board {ob_name_lower}" in cmd_lower
                            or f"on {ob_name_lower} board" in cmd_lower
                            or f"in {ob_name_lower} board" in cmd_lower
                            or f"switch to {ob_name_lower}" in cmd_lower
                        ):
                            logger.info(f"Explicit board switch requested in command: '{other_b['name']}' ({other_b['board_id']})")
                            return {"board_id": other_b["board_id"], "name": other_b["name"]}

                return {"board_id": req_id, "name": b["name"] or "Active Board"}
        return {"board_id": req_id, "name": "Active Board"}

    # 2. Check if command explicitly mentions a board with preposition (e.g. "on board X", "in X board")
    if command:
        cmd_lower = command.lower()
        sorted_boards = sorted(all_boards, key=lambda b: len(b["name"]), reverse=True)
        for b in sorted_boards:
            b_name = b["name"]
            if not b_name:
                continue
            b_lower = b_name.lower()
            if (
                f"on board {b_lower}" in cmd_lower
                or f"in board {b_lower}" in cmd_lower
                or f"to board {b_lower}" in cmd_lower
                or f"on {b_lower} board" in cmd_lower
                or f"in {b_lower} board" in cmd_lower
                or f"switch to {b_lower}" in cmd_lower
            ):
                logger.info(f"Resolved board '{b_name}' ({b['board_id']}) from explicit user command preposition: '{command}'")
                return {"board_id": b["board_id"], "name": b_name}

    # 3. Check if parameters specified board_name or board_id
    if parameters:
        p_bname = parameters.get("board_name") or parameters.get("board")
        p_bid = parameters.get("board_id")
        if p_bid:
            for b in all_boards:
                if b["board_id"] == str(p_bid).strip():
                    return {"board_id": b["board_id"], "name": b["name"] or "Trello Board"}
            return {"board_id": str(p_bid).strip(), "name": "Trello Board"}
        if p_bname:
            norm_pb = norm_str(str(p_bname))
            for b in all_boards:
                b_norm = norm_str(b["name"])
                if norm_pb and (norm_pb == b_norm or norm_pb in b_norm or b_norm in norm_pb):
                    return {"board_id": b["board_id"], "name": b["name"]}

    # 4. Use is_active: True board from database
    for b in all_boards:
        if b["is_active"]:
            return {"board_id": b["board_id"], "name": b["name"] or "Active Board"}

    # 5. Default fallback
    default_id = (settings.TRELLO_BOARD_ID or "").strip()
    for b in all_boards:
        if b["board_id"] == default_id:
            return {"board_id": default_id, "name": b["name"] or "Primary Trello Board"}

    return {"board_id": default_id, "name": "Primary Trello Board"}


async def get_active_board_id(
    db: AsyncIOMotorDatabase,
    requested_board_id: Optional[str] = None,
    command: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> str:
    """Resolves the currently active Trello board ID."""
    res = await resolve_active_board(db, requested_board_id, command, parameters)
    return res["board_id"]
