from typing import Any, Dict
from fastapi import APIRouter, Depends, status
from app.core.dependencies import get_current_user
from app.mcp_server import trello_tools
from app.schemas.user import UserResponse

router = APIRouter()


@router.get(
    "/workload",
    status_code=status.HTTP_200_OK,
    summary="Get real workload report metrics",
    description="Computes workload distribution and task velocity from live Trello board cards.",
)
async def get_workload_report(
    current_user: UserResponse = Depends(get_current_user),
) -> Dict[str, Any]:
    cards_res = await trello_tools.trello_list_cards()
    lists_res = await trello_tools.trello_list_lists()

    cards = cards_res.get("cards", [])
    lists = lists_res.get("lists", [])
    list_map = {l["id"]: l["name"] for l in lists}

    todo_count = 0
    in_progress_count = 0
    done_count = 0

    list_breakdown = {l["name"]: 0 for l in lists}

    for c in cards:
        l_name = list_map.get(c.get("idList"), "Other")
        if l_name in list_breakdown:
            list_breakdown[l_name] += 1
        l_lower = l_name.lower()
        if "done" in l_lower:
            done_count += 1
        elif "doing" in l_lower or "progress" in l_lower:
            in_progress_count += 1
        else:
            todo_count += 1

    total = len(cards)
    completion_rate = round((done_count / total * 100), 1) if total > 0 else 0.0

    return {
        "status": "SUCCESS",
        "total_tasks": total,
        "completed": done_count,
        "in_progress": in_progress_count,
        "todo": todo_count,
        "completion_rate": completion_rate,
        "list_breakdown": list_breakdown,
        "health": "OPTIMAL" if in_progress_count <= 10 else "ATTENTION_NEEDED",
    }

