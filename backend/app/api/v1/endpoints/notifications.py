import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.database.mongodb import get_database
from app.schemas.user import UserResponse
from app.services.reminder_service import TaskReminderService

logger = logging.getLogger(__name__)

router = APIRouter()


class MarkReadRequest(BaseModel):
    notification_id: Optional[str] = None
    mark_all: bool = False


class DeleteNotificationRequest(BaseModel):
    notification_id: Optional[str] = None
    delete_all: bool = False


def _parse_dt(val: Any) -> Optional[datetime]:
    """Robustly parse datetime from datetime object or ISO string."""
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, str) and val.strip():
        try:
            clean_str = val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Get dynamic notifications based on real activities and pending approvals",
    description="Generates real-time notifications from pending_actions and tracks user read & deleted states.",
)
async def get_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    user_id_str = str(current_user.id)

    # 1. Fetch user notification state (read & deleted tracking)
    user_state = None
    if db is not None:
        try:
            user_state = await db["user_notifications_state"].find_one({"user_id": user_id_str})
        except Exception as e:
            logger.debug(f"Could not load user_notifications_state: {e}")

    read_ids = set(user_state.get("read_ids", [])) if user_state else set()
    deleted_ids = set(user_state.get("deleted_ids", [])) if user_state else set()
    all_read_before = _parse_dt(user_state.get("all_read_before")) if user_state else None
    all_deleted_before = _parse_dt(user_state.get("all_deleted_before")) if user_state else None

    notifications: List[Dict[str, Any]] = []

    # 2. Query recent pending_actions
    if db is not None:
        try:
            cursor = db["pending_actions"].find().sort("created_at", -1).limit(limit)
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

                # Check deletion state
                if notif_id in deleted_ids or action_id in deleted_ids:
                    continue
                comp_dt = _parse_dt(updated_at_dt) or _parse_dt(created_at_dt) or _parse_dt(timestamp)
                if all_deleted_before and comp_dt and comp_dt <= all_deleted_before:
                    continue

                # Check read state
                is_read = notif_id in read_ids or action_id in read_ids
                if not is_read and all_read_before and comp_dt:
                    if comp_dt <= all_read_before:
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
        except Exception as act_err:
            logger.warning(f"Error querying pending_actions for notifications: {act_err}")

    # 3. Dynamic Deadline Reminders: 1 Day, 4 Hours, 1 Hour left alerts for assigned members
    if db is not None:
        try:
            reminder_service = TaskReminderService()
            await reminder_service.scan_and_generate_reminders(db, current_user=current_user)
            user_reminders = await reminder_service.get_user_reminders_for_notifications(
                db, user_id=user_id_str, limit=limit
            )
            for rem in user_reminders:
                r_id = rem["id"]
                # Check deletion state
                if r_id in deleted_ids:
                    continue
                rem_dt = _parse_dt(rem.get("created_at"))
                if all_deleted_before and rem_dt and rem_dt <= all_deleted_before:
                    continue

                # Check read state (both read_ids AND all_read_before)
                is_r_read = r_id in read_ids
                if not is_r_read and all_read_before and rem_dt:
                    if rem_dt <= all_read_before:
                        is_r_read = True
                rem["is_read"] = is_r_read
                notifications.append(rem)
        except Exception as e:
            logger.warning(f"Could not process deadline reminders in notifications: {e}")

    # 4. Check any explicit persistent notifications in "notifications" collection
    if db is not None:
        try:
            cust_cursor = db["notifications"].find(
                {
                    "$or": [{"user_id": user_id_str}, {"user_id": "all"}],
                    "is_deleted": {"$ne": True},
                }
            ).sort("created_at", -1).limit(limit)

            async for cdoc in cust_cursor:
                c_id = str(cdoc.get("id") or cdoc.get("_id"))
                if c_id in deleted_ids:
                    continue
                c_dt = _parse_dt(cdoc.get("created_at"))
                if all_deleted_before and c_dt and c_dt <= all_deleted_before:
                    continue

                is_c_read = cdoc.get("is_read", False) or c_id in read_ids
                if not is_c_read and all_read_before and c_dt:
                    if c_dt <= all_read_before:
                        is_c_read = True

                notifications.append({
                    "id": c_id,
                    "type": cdoc.get("type", "INFO"),
                    "title": cdoc.get("title", "Notification"),
                    "message": cdoc.get("message", ""),
                    "created_at": cdoc.get("created_at") if isinstance(cdoc.get("created_at"), str) else (c_dt.isoformat() if c_dt else ""),
                    "is_read": is_c_read,
                    "card_url": cdoc.get("card_url"),
                    "target_tab": cdoc.get("target_tab", "overview"),
                    "priority": cdoc.get("priority", "MEDIUM"),
                })
        except Exception as cust_err:
            logger.debug(f"No custom notifications loaded: {cust_err}")

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
    user_id_str = str(current_user.id)

    if db is None:
        return {"status": "SUCCESS", "message": "Marked as read (no-op)"}

    if payload.mark_all:
        # Fetch current notifications to ensure all their IDs are added to read_ids
        current_res = await get_notifications(limit=50, current_user=current_user, db=db)
        all_ids: List[str] = []
        for n in current_res.get("notifications", []):
            if n.get("id"):
                all_ids.append(n["id"])
            if n.get("action_id"):
                all_ids.append(n["action_id"])

        update_ops: Dict[str, Any] = {
            "$set": {"all_read_before": now, "updated_at": now},
        }
        if all_ids:
            update_ops["$addToSet"] = {"read_ids": {"$each": list(set(all_ids))}}

        await db["user_notifications_state"].update_one(
            {"user_id": user_id_str},
            update_ops,
            upsert=True,
        )

        try:
            await db["notifications"].update_many(
                {"$or": [{"user_id": user_id_str}, {"user_id": "all"}]},
                {"$set": {"is_read": True, "read_at": now}},
            )
        except Exception:
            pass

    elif payload.notification_id:
        target_id = payload.notification_id
        ids_to_add = [target_id]
        if target_id.startswith("notif_") and "_" in target_id[6:]:
            # Extract base action ID if applicable (e.g. notif_ACT-123_pending -> ACT-123)
            parts = target_id.split("_")
            if len(parts) >= 2:
                ids_to_add.append(parts[1])

        await db["user_notifications_state"].update_one(
            {"user_id": user_id_str},
            {
                "$addToSet": {"read_ids": {"$each": ids_to_add}},
                "$set": {"updated_at": now},
            },
            upsert=True,
        )

        try:
            await db["notifications"].update_many(
                {"id": target_id},
                {"$set": {"is_read": True, "read_at": now}},
            )
        except Exception:
            pass

    return {"status": "SUCCESS", "message": "Marked as read"}


@router.post(
    "/delete",
    status_code=status.HTTP_200_OK,
    summary="Delete notifications permanently",
)
async def delete_notifications(
    payload: DeleteNotificationRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    user_id_str = str(current_user.id)

    if db is None:
        return {"status": "SUCCESS", "message": "Deleted (no-op)"}

    if payload.delete_all:
        current_res = await get_notifications(limit=50, current_user=current_user, db=db)
        all_ids: List[str] = []
        for n in current_res.get("notifications", []):
            if n.get("id"):
                all_ids.append(n["id"])
            if n.get("action_id"):
                all_ids.append(n["action_id"])

        update_ops: Dict[str, Any] = {
            "$set": {"all_deleted_before": now, "updated_at": now},
        }
        if all_ids:
            update_ops["$addToSet"] = {"deleted_ids": {"$each": list(set(all_ids))}}

        await db["user_notifications_state"].update_one(
            {"user_id": user_id_str},
            update_ops,
            upsert=True,
        )

        try:
            await db["notifications"].update_many(
                {"$or": [{"user_id": user_id_str}, {"user_id": "all"}]},
                {"$set": {"is_deleted": True, "deleted_at": now}},
            )
        except Exception:
            pass

    elif payload.notification_id:
        target_id = payload.notification_id
        ids_to_del = [target_id]
        if target_id.startswith("notif_") and "_" in target_id[6:]:
            parts = target_id.split("_")
            if len(parts) >= 2:
                ids_to_del.append(parts[1])

        await db["user_notifications_state"].update_one(
            {"user_id": user_id_str},
            {
                "$addToSet": {"deleted_ids": {"$each": ids_to_del}},
                "$set": {"updated_at": now},
            },
            upsert=True,
        )

        try:
            await db["notifications"].update_many(
                {"id": target_id},
                {"$set": {"is_deleted": True, "deleted_at": now}},
            )
        except Exception:
            pass

    return {"status": "SUCCESS", "message": "Notification deleted"}


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete single notification",
)
async def delete_single_notification(
    notification_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    return await delete_notifications(
        payload=DeleteNotificationRequest(notification_id=notification_id),
        current_user=current_user,
        db=db,
    )
