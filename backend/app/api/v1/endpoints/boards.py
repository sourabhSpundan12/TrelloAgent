from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.database.mongodb import get_database
from app.integrations.trello.client import TrelloClient
from app.schemas.user import UserResponse
from app.services.board_service import ensure_default_board, get_active_board_id

logger = logging.getLogger(__name__)

router = APIRouter()


class BoardCreateRequest(BaseModel):
    board_id: str = Field(..., min_length=4, max_length=64, description="Trello board ID or short link")
    name: Optional[str] = Field(None, max_length=100, description="Display name for the board")
    desc: Optional[str] = Field(None, max_length=300, description="Optional description of the board")
    url: Optional[str] = Field(None, description="Direct Trello URL")


class BoardResponse(BaseModel):
    id: str
    board_id: str
    name: str
    desc: Optional[str] = ""
    url: Optional[str] = None
    is_active: bool = False
    created_at: str
    updated_at: str


class BoardListResponse(BaseModel):
    status: str = "SUCCESS"
    active_board_id: str
    total: int
    boards: List[BoardResponse]


@router.get(
    "",
    response_model=BoardListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all configured Trello boards",
    description="Returns all managed Trello boards, indicating which board is currently active.",
)
async def list_boards(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> BoardListResponse:
    # Ensure default board from .env is registered in the database
    await ensure_default_board(db)

    boards_coll = db["boards"]
    cursor = boards_coll.find({}).sort("created_at", 1)
    board_list = []
    active_id = ""

    async for doc in cursor:
        doc.pop("_id", None)
        b_id = str(doc.get("board_id") or doc.get("id") or "").strip()
        if not b_id:
            continue

        is_act = bool(doc.get("is_active", False))
        if is_act:
            active_id = b_id

        created_val = doc.get("created_at")
        if isinstance(created_val, datetime):
            created_str = created_val.isoformat()
        else:
            created_str = str(created_val or "")

        updated_val = doc.get("updated_at")
        if isinstance(updated_val, datetime):
            updated_str = updated_val.isoformat()
        else:
            updated_str = str(updated_val or "")

        board_list.append(
            BoardResponse(
                id=str(doc.get("id") or b_id),
                board_id=b_id,
                name=str(doc.get("name") or f"Board {b_id[:8]}"),
                desc=str(doc.get("desc") or ""),
                url=str(doc.get("url") or f"https://trello.com/b/{b_id}"),
                is_active=is_act,
                created_at=created_str,
                updated_at=updated_str,
            )
        )

    return BoardListResponse(
        status="SUCCESS",
        active_board_id=active_id,
        total=len(board_list),
        boards=board_list,
    )


@router.get(
    "/active",
    response_model=Optional[BoardResponse],
    status_code=status.HTTP_200_OK,
    summary="Get currently active Trello board",
)
async def get_active_board(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Optional[BoardResponse]:
    await ensure_default_board(db)
    boards_coll = db["boards"]
    doc = await boards_coll.find_one({"is_active": True})

    if not doc:
        return None

    doc.pop("_id", None)
    b_id = str(doc.get("board_id") or doc.get("id") or "")
    return BoardResponse(
        id=str(doc.get("id") or b_id),
        board_id=b_id,
        name=str(doc.get("name") or f"Board {b_id[:8]}"),
        desc=str(doc.get("desc") or ""),
        url=str(doc.get("url") or f"https://trello.com/b/{b_id}"),
        is_active=True,
        created_at=str(doc.get("created_at", "")),
        updated_at=str(doc.get("updated_at", "")),
    )


@router.post(
    "",
    response_model=BoardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add or register a Trello board ID",
    description="Registers a new board ID into the platform. If it already exists, returns and updates the registered board.",
)
async def create_board(
    payload: BoardCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> BoardResponse:
    raw_board_id = payload.board_id.strip()
    # Normalize ID: strip potential full URL if user pasted entire URL
    # e.g., https://trello.com/b/6af5688583f6e4d6f991059b/my-board -> 6af5688583f6e4d6f991059b
    m = re.search(r"trello\.com/b/([a-zA-Z0-9]+)", raw_board_id)
    clean_board_id = m.group(1) if m else raw_board_id

    boards_coll = db["boards"]
    existing = await boards_coll.find_one({"$or": [{"board_id": clean_board_id}, {"id": clean_board_id}]})
    now = datetime.now(timezone.utc)

    # If board already exists, update and return it gracefully without error
    if existing:
        update_fields: Dict[str, Any] = {"updated_at": now, "board_id": clean_board_id, "id": clean_board_id}
        if payload.name and payload.name.strip():
            update_fields["name"] = payload.name.strip()
        if payload.desc and payload.desc.strip():
            update_fields["desc"] = payload.desc.strip()
        if payload.url and payload.url.strip():
            update_fields["url"] = payload.url.strip()

        await boards_coll.update_one(
            {"$or": [{"board_id": clean_board_id}, {"id": clean_board_id}]},
            {"$set": update_fields},
        )
        updated = await boards_coll.find_one({"$or": [{"board_id": clean_board_id}, {"id": clean_board_id}]})
        updated.pop("_id", None)
        return BoardResponse(
            id=str(updated.get("id") or clean_board_id),
            board_id=clean_board_id,
            name=str(updated.get("name") or f"Board {clean_board_id[:8]}"),
            desc=str(updated.get("desc") or ""),
            url=str(updated.get("url") or f"https://trello.com/b/{clean_board_id}"),
            is_active=bool(updated.get("is_active", False)),
            created_at=str(updated.get("created_at", "")),
            updated_at=now.isoformat(),
        )

    # Try fetching board metadata from Trello API if configured
    board_name = payload.name.strip() if payload.name and payload.name.strip() else ""
    board_desc = payload.desc.strip() if payload.desc else ""
    board_url = payload.url.strip() if payload.url else f"https://trello.com/b/{clean_board_id}"

    if settings.TRELLO_API_KEY and settings.TRELLO_TOKEN:
        try:
            client = TrelloClient(board_id=clean_board_id)
            meta = await client.get_board(clean_board_id)
            if not board_name:
                board_name = meta.get("name") or f"Board {clean_board_id[:8]}"
            if not board_desc and meta.get("desc"):
                board_desc = meta.get("desc")
            if meta.get("url"):
                board_url = meta.get("url")
        except Exception as e:
            logger.info(f"Could not query Trello API for board name: {e}")

    if not board_name:
        board_name = f"Trello Board ({clean_board_id[:8]})"

    new_doc = {
        "id": clean_board_id,
        "board_id": clean_board_id,
        "name": board_name,
        "desc": board_desc,
        "url": board_url,
        "is_active": False,
        "created_at": now,
        "updated_at": now,
    }

    await boards_coll.insert_one(new_doc)
    new_doc.pop("_id", None)

    return BoardResponse(
        id=clean_board_id,
        board_id=clean_board_id,
        name=board_name,
        desc=board_desc,
        url=board_url,
        is_active=False,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )


@router.post(
    "/{board_id}/activate",
    response_model=BoardResponse,
    status_code=status.HTTP_200_OK,
    summary="Activate a specific Trello board",
    description="Activates the specified board and deactivates all other boards.",
)
async def activate_board(
    board_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> BoardResponse:
    boards_coll = db["boards"]
    target = await boards_coll.find_one({"$or": [{"board_id": board_id}, {"id": board_id}]})
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board with ID '{board_id}' was not found.",
        )

    now = datetime.now(timezone.utc)
    # Deactivate all boards
    await boards_coll.update_many({}, {"$set": {"is_active": False, "updated_at": now}})

    # Activate the target board
    await boards_coll.update_one(
        {"$or": [{"board_id": board_id}, {"id": board_id}]},
        {"$set": {"is_active": True, "updated_at": now, "board_id": board_id, "id": board_id}},
    )

    target["is_active"] = True
    target["updated_at"] = now.isoformat()
    target.pop("_id", None)

    return BoardResponse(
        id=str(target.get("id") or board_id),
        board_id=board_id,
        name=str(target.get("name") or f"Board {board_id[:8]}"),
        desc=str(target.get("desc") or ""),
        url=str(target.get("url") or f"https://trello.com/b/{board_id}"),
        is_active=True,
        created_at=str(target.get("created_at", "")),
        updated_at=now.isoformat(),
    )


@router.post(
    "/{board_id}/deactivate",
    response_model=BoardResponse,
    status_code=status.HTTP_200_OK,
    summary="Deactivate a specific Trello board",
    description="Marks the specified board as Inactive.",
)
async def deactivate_board(
    board_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> BoardResponse:
    boards_coll = db["boards"]
    target = await boards_coll.find_one({"$or": [{"board_id": board_id}, {"id": board_id}]})
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board with ID '{board_id}' was not found.",
        )

    now = datetime.now(timezone.utc)
    await boards_coll.update_one(
        {"$or": [{"board_id": board_id}, {"id": board_id}]},
        {"$set": {"is_active": False, "updated_at": now}},
    )

    target["is_active"] = False
    target["updated_at"] = now.isoformat()
    target.pop("_id", None)

    return BoardResponse(
        id=str(target.get("id") or board_id),
        board_id=board_id,
        name=str(target.get("name") or f"Board {board_id[:8]}"),
        desc=str(target.get("desc") or ""),
        url=str(target.get("url") or f"https://trello.com/b/{board_id}"),
        is_active=False,
        created_at=str(target.get("created_at", "")),
        updated_at=now.isoformat(),
    )


@router.post(
    "/{board_id}/toggle",
    response_model=BoardResponse,
    status_code=status.HTTP_200_OK,
    summary="Toggle active/inactive status of a board",
)
async def toggle_board(
    board_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> BoardResponse:
    boards_coll = db["boards"]
    target = await boards_coll.find_one({"$or": [{"board_id": board_id}, {"id": board_id}]})
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board with ID '{board_id}' was not found.",
        )

    currently_active = bool(target.get("is_active", False))
    now = datetime.now(timezone.utc)

    if currently_active:
        # Turn it inactive
        await boards_coll.update_one(
            {"$or": [{"board_id": board_id}, {"id": board_id}]},
            {"$set": {"is_active": False, "updated_at": now}},
        )
        new_active = False
    else:
        # Deactivate all, activate this one
        await boards_coll.update_many({}, {"$set": {"is_active": False, "updated_at": now}})
        await boards_coll.update_one(
            {"$or": [{"board_id": board_id}, {"id": board_id}]},
            {"$set": {"is_active": True, "updated_at": now, "board_id": board_id, "id": board_id}},
        )
        new_active = True

    target["is_active"] = new_active
    target["updated_at"] = now.isoformat()
    target.pop("_id", None)

    return BoardResponse(
        id=str(target.get("id") or board_id),
        board_id=board_id,
        name=str(target.get("name") or f"Board {board_id[:8]}"),
        desc=str(target.get("desc") or ""),
        url=str(target.get("url") or f"https://trello.com/b/{board_id}"),
        is_active=new_active,
        created_at=str(target.get("created_at", "")),
        updated_at=now.isoformat(),
    )


@router.delete(
    "/{board_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a registered board",
    description="Removes a board from the registry. Cannot delete if it is the only remaining board.",
)
async def delete_board(
    board_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    boards_coll = db["boards"]
    count = await boards_coll.count_documents({})
    if count <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the only configured board. Add another board first before deleting this one.",
        )

    target = await boards_coll.find_one({"$or": [{"board_id": board_id}, {"id": board_id}]})
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board with ID '{board_id}' was not found.",
        )

    was_active = bool(target.get("is_active", False))
    await boards_coll.delete_one({"$or": [{"board_id": board_id}, {"id": board_id}]})

    # If deleted board was active, activate the first remaining board
    if was_active:
        remaining = await boards_coll.find_one({})
        if remaining:
            await boards_coll.update_one(
                {"_id": remaining["_id"]},
                {"$set": {"is_active": True, "updated_at": datetime.now(timezone.utc)}},
            )

    return {
        "status": "SUCCESS",
        "message": f"Board '{board_id}' was removed.",
        "was_active": was_active,
    }
