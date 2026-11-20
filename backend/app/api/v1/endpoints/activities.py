import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.database.mongodb import get_database
from app.schemas.user import UserResponse
from app.services.activity_service import ActivityService

logger = logging.getLogger(__name__)

router = APIRouter()


class CustomActivityLogRequest(BaseModel):
    event_type: str = "PLATFORM_EVENT"
    title: str
    description: str = ""
    status: str = "EXECUTED"
    tool_name: str = "User Action"
    card_title: Optional[str] = None
    card_url: Optional[str] = None
    board_name: Optional[str] = None


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Get real activity history logs",
    description="Fetches live activity logs from MongoDB Atlas activity_logs, pending_actions, assignment lifecycle, and Trello board actions.",
)
async def get_activity_history(
    board_id: Optional[str] = Query(None, description="Optional target Trello board ID"),
    status_filter: Optional[str] = Query(None, description="Optional status filter"),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    try:
        activities = await ActivityService.get_combined_activities(
            db=db,
            current_user=current_user,
            board_id=board_id,
            limit=limit,
        )

        if status_filter and status_filter.upper() != "ALL":
            activities = [a for a in activities if a.get("status") == status_filter.upper()]

        return {
            "status": "SUCCESS",
            "total": len(activities),
            "activities": activities,
        }
    except Exception as e:
        logger.error(f"Failed to fetch activity history: {e}")
        return {
            "status": "ERROR",
            "total": 0,
            "activities": [],
            "error": str(e),
        }


@router.post(
    "/log",
    status_code=status.HTTP_201_CREATED,
    summary="Log a manual or platform activity event",
    description="Records a new activity event in the persistent activity_logs collection.",
)
async def log_activity_event(
    payload: CustomActivityLogRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    try:
        doc = await ActivityService.log_activity(
            db=db,
            event_type=payload.event_type,
            title=payload.title,
            description=payload.description,
            user_email=current_user.email,
            user_name=current_user.full_name or "Project Manager",
            user_id=current_user.id,
            actor_role=current_user.role,
            status=payload.status,
            tool_name=payload.tool_name,
            card_title=payload.card_title,
            card_url=payload.card_url,
            board_name=payload.board_name,
        )
        return {"status": "SUCCESS", "activity": doc}
    except Exception as e:
        logger.error(f"Failed to log custom activity: {e}")
        return {"status": "ERROR", "error": str(e)}
