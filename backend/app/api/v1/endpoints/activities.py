from typing import Any, Dict, List
from fastapi import APIRouter, Depends, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.dependencies import get_current_user
from app.database.mongodb import get_database
from app.schemas.user import UserResponse

router = APIRouter()


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Get real activity history logs",
    description="Fetches live activity logs from pending_actions and audit records in MongoDB Atlas.",
)
async def get_activity_history(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    cursor = db["pending_actions"].find().sort("created_at", -1).limit(50)
    activities: List[Dict[str, Any]] = []

    async for doc in cursor:
        doc.pop("_id", None)
        exec_res = doc.get("execution_result", {})
        card_obj = exec_res.get("result", {}).get("card", {}) if isinstance(exec_res, dict) else {}
        card_url = card_obj.get("url") or doc.get("card_url")

        activities.append({
            "id": doc.get("action_id"),
            "action_id": doc.get("action_id"),
            "action_type": doc.get("action_type", "MUTATION"),
            "tool_name": doc.get("tool_name", "Tool Action"),
            "user_email": doc.get("user_email", "admin@example.com"),
            "title": doc.get("draft", {}).get("title") or doc.get("command") or "Action",
            "status": doc.get("status", "PENDING"),
            "created_at": str(doc.get("created_at")),
            "updated_at": str(doc.get("updated_at")),
            "card_url": card_url,
            "description": doc.get("draft", {}).get("description") or "",
            "priority": doc.get("draft", {}).get("priority", "MEDIUM"),
        })

    return {
        "status": "SUCCESS",
        "total": len(activities),
        "activities": activities,
    }

