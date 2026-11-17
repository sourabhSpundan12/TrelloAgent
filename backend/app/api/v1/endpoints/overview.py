from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.dependencies import get_current_user
from app.database.mongodb import get_database
from app.mcp_server import trello_tools
from app.schemas.user import UserResponse
from app.services.board_service import get_active_board_id

router = APIRouter()


@router.get(
    "/stats",
    status_code=status.HTTP_200_OK,
    summary="Get real overview metrics and statistics",
    description="Calculates live statistics from Trello board cards, active tools, and pending actions in MongoDB Atlas.",
)
async def get_overview_stats(
    board_id: Optional[str] = Query(None, description="Optional target Trello board ID"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    # 1. Fetch live Trello cards
    total_cards = 0
    todo_count = 0
    doing_count = 0
    done_count = 0

    try:
        active_board_id = await get_active_board_id(db, board_id)
        cards_res = await trello_tools.trello_list_cards(board_id=active_board_id)
        lists_res = await trello_tools.trello_list_lists(board_id=active_board_id)
        list_map = {l["id"]: l["name"].lower() for l in lists_res.get("lists", [])}

        cards = cards_res.get("cards", [])
        total_cards = len(cards)
        for c in cards:
            lname = list_map.get(c.get("idList"), "")
            if "done" in lname:
                done_count += 1
            elif "doing" in lname or "progress" in lname:
                doing_count += 1
            else:
                todo_count += 1
    except Exception:
        pass

    # 2. Fetch active tools count from Atlas
    tools_count = await db["tools"].count_documents({"enabled": True})

    # 3. Fetch pending actions count and recent actions from Atlas
    pending_count = await db["pending_actions"].count_documents({"status": "PENDING"})
    executed_count = await db["pending_actions"].count_documents({"status": "EXECUTED"})

    cursor = db["pending_actions"].find().sort("created_at", -1).limit(6)
    recent_actions = []
    async for doc in cursor:
        doc.pop("_id", None)
        exec_res = doc.get("execution_result") or {}
        result_obj = exec_res.get("result") or {} if isinstance(exec_res, dict) else {}
        card_obj = result_obj.get("card") or {} if isinstance(result_obj, dict) else {}
        card_url = card_obj.get("url") if isinstance(card_obj, dict) else doc.get("card_url")
        draft_obj = doc.get("draft") or {}
        title = (draft_obj.get("title") if isinstance(draft_obj, dict) else None) or doc.get("tool_name") or "Action"

        recent_actions.append({
            "action_id": doc.get("action_id"),
            "tool_name": doc.get("tool_name", "Trello Action"),
            "status": doc.get("status"),
            "title": title,
            "created_at": str(doc.get("created_at")),
            "card_url": card_url,
        })

    completion_rate = round((done_count / total_cards * 100), 1) if total_cards > 0 else 0.0

    return {
        "status": "SUCCESS",
        "tasks": {
            "total": total_cards,
            "todo": todo_count,
            "doing": doing_count,
            "done": done_count,
            "completion_rate": completion_rate,
        },
        "system": {
            "active_tools": tools_count,
            "pending_approvals": pending_count,
            "executed_mutations": executed_count,
        },
        "recent_activities": recent_actions,
    }

