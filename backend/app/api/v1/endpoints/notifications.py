from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from app.core.dependencies import get_current_user
from app.core.logging import logger
from app.database.mongodb import get_database
from app.schemas.user import UserResponse
from app.services.reminder_service import TaskReminderService

router = APIRouter()


class MarkReadRequest(BaseModel):
    notification_id: Optional[str] = None
    mark_all: bool = False


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Get dynamic notifications based on real activities and pending approvals",
    description="Generates real-time notifications from pending_actions and tracks user read state.",
)
async def get_notifications(
    limit: int = Query(default=20, ge=1, le=50),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    # 1. Fetch user read state
    user_state = await db["user_notifications_state"].find_one({"user_id": current_user.id})
    read_ids = set(user_state.get("read_ids", [])) if user_state else set()
    all_read_before = user_state.get("all_read_before") if user_state else None

    # 2. Query recent pending_actions
    cursor = db["pending_actions"].find().sort("created_at", -1).limit(limit)
    notifications: List[Dict[str, Any]] = []

    async for doc in cursor:
        action_id = doc.get("action_id") or "ACT-UNKNOWN"
        status_val = str(doc.get("status") or "PENDING").upper()
        action_type = str(doc.get("action_type") or "MUTATION").upper()
        draft = doc.get("draft") or {}
        card_title = draft.get("title") or doc.get("command") or "Task"
        created_at_dt = doc.get("created_at")
        updated_at_dt = doc.get("updated_at") or created_at_dt

        created_str = created_at_dt.isoformat() if hasattr(created_at_dt, "isoformat") else str(created_at_dt or "")
        updated_str = updated_at_dt.isoformat() if hasattr(updated_at_dt, "isoformat") else str(updated_at_dt or "")

        exec_res = doc.get("execution_result", {})
        card_obj = exec_res.get("result", {}).get("card", {}) if isinstance(exec_res, dict) else {}
        card_url = card_obj.get("url") or doc.get("card_url") or doc.get("draft", {}).get("card_url")

        # Map to dynamic notification type and descriptive message
        if status_val == "PENDING":
            notif_id = f"notif_{action_id}_pending"
            action_verb = "creation" if action_type == "CREATE_CARD" else "update" if action_type == "UPDATE_CARD" else "action"
            title = "Pending Approval Required"
            message = f'"{card_title}" {action_verb} preview is waiting for your confirmation.'
            notif_type = "APPROVAL_REQUIRED"
            timestamp = created_str
            target_tab = "ai-assistant"
        elif status_val == "EXECUTED":
            notif_id = f"notif_{action_id}_executed"
            title = "Action Executed in Trello"
            if action_type == "CREATE_CARD":
                message = f'Card "{card_title}" was successfully created on Trello.'
            elif action_type == "UPDATE_CARD":
                message = f'Card "{card_title}" was successfully updated on Trello.'
            elif action_type == "MOVE_CARD":
                message = f'Card "{card_title}" was successfully moved.'
            else:
                message = f'Action for "{card_title}" was successfully executed.'
            notif_type = "ACTION_EXECUTED"
            timestamp = updated_str
            target_tab = "tasks"
        elif status_val in ("REJECTED", "CANCELLED"):
            notif_id = f"notif_{action_id}_cancelled"
            title = "Action Cancelled"
            message = f'Draft preview for "{card_title}" was cancelled.'
            notif_type = "ACTION_CANCELLED"
            timestamp = updated_str
            target_tab = "ai-assistant"
        elif status_val == "FAILED":
            notif_id = f"notif_{action_id}_failed"
            title = "Action Failed"
            err = doc.get("error_message") or "Unknown error"
            message = f'Action for "{card_title}" failed: {err}'
            notif_type = "ACTION_FAILED"
            timestamp = updated_str
            target_tab = "ai-assistant"
        else:
            notif_id = f"notif_{action_id}_{status_val.lower()}"
            title = f"Action {status_val.title()}"
            message = f'"{card_title}" status is {status_val}.'
            notif_type = "INFO"
            timestamp = updated_str
            target_tab = "ai-assistant"

        is_read = notif_id in read_ids or action_id in read_ids
        if not is_read and all_read_before and updated_at_dt:
            if isinstance(updated_at_dt, datetime):
                comp_dt = updated_at_dt if updated_at_dt.tzinfo else updated_at_dt.replace(tzinfo=timezone.utc)
                read_before_dt = all_read_before if all_read_before.tzinfo else all_read_before.replace(tzinfo=timezone.utc)
                if comp_dt <= read_before_dt:
                    is_read = True

        notifications.append({
            "id": notif_id,
            "type": notif_type,
            "title": title,
            "message": message,
            "created_at": timestamp,
            "is_read": is_read,
            "action_id": action_id,
            "action_type": action_type,
            "card_url": card_url,
            "target_tab": target_tab,
            "priority": draft.get("priority", "MEDIUM"),
        })

    # 3. Dynamic Deadline Reminders: 1 Day, 4 Hours, 1 Hour left alerts for assigned members
    try:
        reminder_service = TaskReminderService()
        await reminder_service.scan_and_generate_reminders(db, current_user=current_user)
        user_reminders = await reminder_service.get_user_reminders_for_notifications(
            db, user_id=str(current_user.id), limit=limit
        )
        for rem in user_reminders:
            r_id = rem["id"]
            is_r_read = r_id in read_ids
            rem["is_read"] = is_r_read
            notifications.append(rem)
    except Exception as e:
        logger.warning(f"Could not process deadline reminders in notifications: {e}")

    # Sort combined notifications by created_at descending
    notifications.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)

    unread_count = sum(1 for n in notifications if not n["is_read"])

    return {
        "status": "SUCCESS",
        "unread_count": unread_count,
        "total": len(notifications),
        "notifications": notifications,
    }


@router.post(
    "/mark-read",
    status_code=status.HTTP_200_OK,
    summary="Mark notifications as read",
)
async def mark_notifications_read(
    payload: MarkReadRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    if payload.mark_all:
        await db["user_notifications_state"].update_one(
            {"user_id": current_user.id},
            {"$set": {"all_read_before": now, "updated_at": now}},
            upsert=True,
        )
    elif payload.notification_id:
        await db["user_notifications_state"].update_one(
            {"user_id": current_user.id},
            {
                "$addToSet": {"read_ids": payload.notification_id},
                "$set": {"updated_at": now},
            },
            upsert=True,
        )

    return {"status": "SUCCESS", "message": "Marked as read"}

