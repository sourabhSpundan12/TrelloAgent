from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, status
from app.core.dependencies import get_current_user
from app.core.logging import logger
from app.mcp_server import trello_tools
from app.schemas.user import UserResponse

router = APIRouter()


@router.get(
    "/trello",
    status_code=status.HTTP_200_OK,
    summary="Get live Trello board cards and lists",
    description="Fetches live tasks directly from the configured Trello board via MCP tools.",
)
async def get_trello_tasks(
    current_user: UserResponse = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        cards_res = await trello_tools.trello_list_cards()
        lists_res = await trello_tools.trello_list_lists()

        lists = lists_res.get("lists", [])
        cards = cards_res.get("cards", [])

        list_map = {l["id"]: l["name"] for l in lists}

        formatted_cards = []
        for c in cards:
            list_name = list_map.get(c.get("idList"), "To Do")
            formatted_cards.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "desc": c.get("desc") or "",
                "list_id": c.get("idList"),
                "list_name": list_name,
                "url": c.get("url"),
                "short_url": c.get("shortUrl"),
                "due": c.get("due"),
                "closed": c.get("closed", False),
            })

        return {
            "status": "SUCCESS",
            "board_id": lists[0]["idBoard"] if lists else None,
            "total_cards": len(formatted_cards),
            "lists": lists,
            "cards": formatted_cards,
        }
    except Exception as e:
        logger.error(f"Failed to fetch live Trello tasks: {e}")
        return {
            "status": "ERROR",
            "total_cards": 0,
            "lists": [],
            "cards": [],
            "error": str(e),
        }

