from datetime import datetime, timezone
import logging
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


async def get_active_board_id(
    db: AsyncIOMotorDatabase, requested_board_id: Optional[str] = None
) -> str:
    """Resolves the currently active Trello board ID."""
    if requested_board_id and str(requested_board_id).strip():
        return str(requested_board_id).strip()

    try:
        active_doc = await db["boards"].find_one({"is_active": True})
        if active_doc and active_doc.get("board_id"):
            return str(active_doc["board_id"]).strip()

        # If none marked active, try ensure default
        seeded = await ensure_default_board(db)
        if seeded and seeded.get("board_id"):
            return str(seeded["board_id"]).strip()
    except Exception as exc:
        logger.warning(f"Error querying active board from database: {exc}")

    return settings.TRELLO_BOARD_ID or ""
