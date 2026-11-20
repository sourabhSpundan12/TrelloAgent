from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import HTTPException, status

from app.core.logging import logger
from app.integrations.trello.client import TrelloClient, parse_due_date_for_trello
from app.models.task_assignment import (
    TaskAssignmentStatus,
    TaskAssignmentModel,
    TaskAssignmentHistoryModel,
)
from app.services.performance_service import PerformanceCalculationService


class TaskAssignmentService:
    """
    Core service managing task assignments, lifecycle (Module 1),
    and server-side estimated vs actual elapsed time calculations (Module 2).
    """

    @classmethod
    async def create_assignment(
        cls,
        db: AsyncIOMotorDatabase,
        employee_id: str,
        project_manager_id: str,
        board_id: str,
        trello_card_id: str,
        task_title: str,
        task_description: Optional[str] = None,
        due_date: Optional[datetime] = None,
        board_name: Optional[str] = None,
        trello_card_url: Optional[str] = None,
        employee_name: Optional[str] = None,
        employee_email: Optional[str] = None,
        project_manager_name: Optional[str] = None,
        trello_client: Optional[TrelloClient] = None,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        
        # Resolve names and emails if missing
        if not employee_name or not employee_email:
            try:
                emp_user = await db["users"].find_one({"_id": ObjectId(employee_id)})
            except Exception:
                emp_user = await db["users"].find_one({"email": employee_id})
            if emp_user:
                employee_name = employee_name or emp_user.get("full_name")
                employee_email = employee_email or emp_user.get("email")

        if not project_manager_name:
            try:
                pm_user = await db["users"].find_one({"_id": ObjectId(project_manager_id)})
            except Exception:
                pm_user = await db["users"].find_one({"email": project_manager_id})
            if pm_user:
                project_manager_name = pm_user.get("full_name")

        # Sync due date to Trello if provided
        trello_sync_status = "synced"
        last_sync_error = None
        if due_date and trello_card_id:
            client = trello_client or TrelloClient()
            try:
                iso_due = parse_due_date_for_trello(due_date)
                await client.update_card(card_id=trello_card_id, due=iso_due)
            except Exception as err:
                logger.warning(f"Failed to sync due date to Trello on assignment creation: {err}")
                trello_sync_status = "pending_retry"
                last_sync_error = str(err)

        # Calculate initial estimated duration if due date is provided
        estimated_duration = None
        if due_date:
            d_dt = due_date if due_date.tzinfo else due_date.replace(tzinfo=timezone.utc)
            delta = (d_dt - now).total_seconds()
            estimated_duration = max(0, round(delta / 60))

        assignment_doc = {
            "employee_id": str(employee_id),
            "employee_name": employee_name,
            "employee_email": employee_email,
            "project_manager_id": str(project_manager_id),
            "project_manager_name": project_manager_name,
            "board_id": str(board_id),
            "board_name": board_name,
            "trello_card_id": str(trello_card_id),
            "trello_card_url": trello_card_url,
            "task_title": task_title,
            "task_description": task_description,
            "assigned_at": now,
            "status": TaskAssignmentStatus.ASSIGNED.value,
            "due_date": due_date,
            "due_date_set_at": now if due_date else None,
            "due_date_set_by": str(project_manager_id),
            "due_date_set_by_role": "MANAGER",
            "due_date_version": 1,
            "started_at": None,
            "completed_at": None,
            "estimated_duration_minutes": estimated_duration,
            "actual_duration_minutes": None,
            "time_variance_minutes": None,
            "trello_sync_status": trello_sync_status,
            "last_sync_error": last_sync_error,
            "created_at": now,
            "updated_at": now,
        }

        res = await db["task_assignments"].insert_one(assignment_doc)
        cls.invalidate_reconcile_cache()
        assignment_id = str(res.inserted_id)
        assignment_doc["_id"] = str(res.inserted_id)
        assignment_doc["id"] = assignment_id

        # Record history
        await db["task_assignment_history"].insert_one({
            "assignment_id": assignment_id,
            "action": "assigned",
            "actor_id": str(project_manager_id),
            "actor_role": "MANAGER",
            "old_due_date": None,
            "new_due_date": due_date,
            "old_estimated_duration_minutes": None,
            "new_estimated_duration_minutes": estimated_duration,
            "old_status": None,
            "new_status": TaskAssignmentStatus.ASSIGNED.value,
            "reason": "Initial task assignment",
            "timestamp": now,
        })

        try:
            from app.services.activity_service import ActivityService
            await ActivityService.log_activity(
                db=db,
                event_type="TASK_ASSIGNED",
                title=f"Task '{task_title}' assigned to {employee_name or 'Team Member'}",
                description=f"Assigned by Project Manager. Due date: {due_date.isoformat() if due_date else 'No deadline'}.",
                user_email=employee_email or "employee@enterprise.com",
                user_name=employee_name or "Team Member",
                user_id=employee_id,
                status="EXECUTED",
                tool_name="Task Assignment Engine",
                card_id=trello_card_id,
                card_title=task_title,
                card_url=trello_card_url,
                board_id=board_id,
                board_name=board_name,
            )
        except Exception:
            pass

        return assignment_doc

    @classmethod
    async def update_due_date(
        cls,
        db: AsyncIOMotorDatabase,
        assignment_id: str,
        actor_id: str,
        actor_role: str,
        new_due_date: datetime,
        reason: Optional[str] = None,
        trello_client: Optional[TrelloClient] = None,
    ) -> Dict[str, Any]:
        # 1. Fetch assignment
        try:
            assignment = await db["task_assignments"].find_one({"_id": ObjectId(assignment_id)})
        except Exception:
            assignment = await db["task_assignments"].find_one({"id": assignment_id})

        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task assignment not found.")

        # 2. Check authorization:
        # Employee can update only their own assigned tasks
        is_assigned_employee = str(assignment.get("employee_id")) == str(actor_id)
        is_pm_or_admin = actor_role.upper() in ("ADMIN", "MANAGER", "HR")

        if not (is_assigned_employee or is_pm_or_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to update the due date for this task assignment."
            )

        now = datetime.now(timezone.utc)
        old_due = assignment.get("due_date")
        old_est = assignment.get("estimated_duration_minutes")
        started_at = assignment.get("started_at")

        # Normalize new due date
        if not new_due_date.tzinfo:
            new_due_date = new_due_date.replace(tzinfo=timezone.utc)

        # Recalculate estimated duration from when this deadline was set (now) to new_due_date
        delta = (new_due_date - now).total_seconds()
        new_est = max(0, round(delta / 60))

        # If already completed, recalculate variance = actualDurationMinutes - newEstimatedDuration
        new_variance = None
        if assignment.get("status") == TaskAssignmentStatus.COMPLETED.value and assignment.get("actual_duration_minutes") is not None:
            new_variance = assignment["actual_duration_minutes"] - new_est

        due_date_version = assignment.get("due_date_version", 1) + 1

        # Synchronize with Trello card
        trello_sync_status = "synced"
        last_sync_error = None
        trello_card_id = assignment.get("trello_card_id")
        if trello_card_id:
            client = trello_client or TrelloClient()
            try:
                iso_due = parse_due_date_for_trello(new_due_date)
                await client.update_card(card_id=trello_card_id, due=iso_due)
            except Exception as err:
                logger.warning(f"Failed to synchronize due date with Trello card {trello_card_id}: {err}")
                trello_sync_status = "pending_retry"
                last_sync_error = str(err)

        update_fields = {
            "due_date": new_due_date,
            "due_date_set_at": now,
            "due_date_set_by": str(actor_id),
            "due_date_set_by_role": actor_role.upper(),
            "due_date_version": due_date_version,
            "estimated_duration_minutes": new_est,
            "time_variance_minutes": new_variance if new_variance is not None else assignment.get("time_variance_minutes"),
            "trello_sync_status": trello_sync_status,
            "last_sync_error": last_sync_error,
            "updated_at": now,
        }

        await db["task_assignments"].update_one(
            {"_id": assignment["_id"]},
            {"$set": update_fields}
        )
        cls.invalidate_reconcile_cache()

        # Record history
        await db["task_assignment_history"].insert_one({
            "assignment_id": str(assignment["_id"]),
            "action": "due_date_updated",
            "actor_id": str(actor_id),
            "actor_role": actor_role.upper(),
            "old_due_date": old_due,
            "new_due_date": new_due_date,
            "old_estimated_duration_minutes": old_est,
            "new_estimated_duration_minutes": new_est,
            "old_status": assignment.get("status"),
            "new_status": assignment.get("status"),
            "reason": reason or f"Due date updated by {actor_role}",
            "timestamp": now,
        })

        try:
            from app.services.activity_service import ActivityService
            await ActivityService.log_activity(
                db=db,
                event_type="DUE_DATE_UPDATED",
                title=f"Due date updated for '{assignment.get('task_title', 'Task')}'",
                description=f"Deadline updated to {new_due_date.isoformat() if new_due_date else 'None'}. Reason: {reason or 'Schedule adjustment'}.",
                user_email=assignment.get("employee_email") or "employee@enterprise.com",
                user_name=assignment.get("employee_name") or "Team Member",
                status="EXECUTED",
                tool_name="Due Date Manager",
                card_id=assignment.get("trello_card_id"),
                card_title=assignment.get("task_title"),
                card_url=assignment.get("trello_card_url"),
                board_name=assignment.get("board_name"),
            )
        except Exception:
            pass

        assignment.update(update_fields)
        assignment["id"] = str(assignment["_id"])
        return assignment

    @classmethod
    async def start_task(
        cls,
        db: AsyncIOMotorDatabase,
        assignment_id: str,
        actor_id: str,
        actor_role: str,
    ) -> Dict[str, Any]:
        try:
            assignment = await db["task_assignments"].find_one({"_id": ObjectId(assignment_id)})
        except Exception:
            assignment = await db["task_assignments"].find_one({"id": assignment_id})

        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task assignment not found.")

        # Authorization: assigned employee or PM/admin
        is_assigned_employee = str(assignment.get("employee_id")) == str(actor_id)
        is_pm_or_admin = actor_role.upper() in ("ADMIN", "MANAGER", "HR")
        if not (is_assigned_employee or is_pm_or_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to start this task."
            )

        # Prevent duplicate starts
        if assignment.get("started_at") or assignment.get("status") == TaskAssignmentStatus.IN_PROGRESS.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task has already been started."
            )
        if assignment.get("status") == TaskAssignmentStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task has already been completed."
            )

        now = datetime.now(timezone.utc)
        due_date = assignment.get("due_date")

        # Keep existing estimated duration from when due date was set; fallback if missing
        estimated_duration = assignment.get("estimated_duration_minutes")
        if estimated_duration is None and due_date:
            d_dt = due_date if due_date.tzinfo else due_date.replace(tzinfo=timezone.utc)
            delta = (d_dt - now).total_seconds()
            estimated_duration = max(0, round(delta / 60))

        update_fields = {
            "started_at": now,
            "status": TaskAssignmentStatus.IN_PROGRESS.value,
            "estimated_duration_minutes": estimated_duration,
            "actual_duration_minutes": None,
            "time_variance_minutes": None,
            "updated_at": now,
        }

        await db["task_assignments"].update_one(
            {"_id": assignment["_id"]},
            {"$set": update_fields}
        )
        cls.invalidate_reconcile_cache()

        await db["task_assignment_history"].insert_one({
            "assignment_id": str(assignment["_id"]),
            "action": "started",
            "actor_id": str(actor_id),
            "actor_role": actor_role.upper(),
            "old_due_date": due_date,
            "new_due_date": due_date,
            "old_estimated_duration_minutes": assignment.get("estimated_duration_minutes"),
            "new_estimated_duration_minutes": estimated_duration,
            "old_status": assignment.get("status"),
            "new_status": TaskAssignmentStatus.IN_PROGRESS.value,
            "reason": "Task started by employee",
            "timestamp": now,
        })

        try:
            from app.services.activity_service import ActivityService
            await ActivityService.log_activity(
                db=db,
                event_type="TASK_STARTED",
                title=f"Work started on '{assignment.get('task_title', 'Task')}'",
                description=f"Task transitioned to IN_PROGRESS by {assignment.get('employee_name', 'Employee')}.",
                user_email=assignment.get("employee_email") or "employee@enterprise.com",
                user_name=assignment.get("employee_name") or "Employee",
                status="IN_PROGRESS",
                tool_name="Task Execution",
                card_id=assignment.get("trello_card_id"),
                card_title=assignment.get("task_title"),
                card_url=assignment.get("trello_card_url"),
                board_name=assignment.get("board_name"),
            )
        except Exception:
            pass

        assignment.update(update_fields)
        assignment["id"] = str(assignment["_id"])
        return assignment

    @classmethod
    async def complete_task(
        cls,
        db: AsyncIOMotorDatabase,
        assignment_id: str,
        actor_id: str,
        actor_role: str,
    ) -> Dict[str, Any]:
        try:
            assignment = await db["task_assignments"].find_one({"_id": ObjectId(assignment_id)})
        except Exception:
            assignment = await db["task_assignments"].find_one({"id": assignment_id})

        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task assignment not found.")

        # Authorization: assigned employee or PM/admin
        is_assigned_employee = str(assignment.get("employee_id")) == str(actor_id)
        is_pm_or_admin = actor_role.upper() in ("ADMIN", "MANAGER", "HR")
        if not (is_assigned_employee or is_pm_or_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to complete this task."
            )

        # Prevent duplicate completions
        if assignment.get("completed_at") or assignment.get("status") == TaskAssignmentStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task has already been completed."
            )

        now = datetime.now(timezone.utc)
        started_at = assignment.get("started_at")
        if not started_at:
            # Fallback if employee completed directly without clicking start
            started_at = assignment.get("assigned_at") or now

        s_dt = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)

        # Module 2.2: actualDurationMinutes = completedAt - startedAt (elapsed time)
        actual_duration = max(0, round((now - s_dt).total_seconds() / 60))

        # Module 2.2: timeVarianceMinutes = actualDurationMinutes - estimatedDurationMinutes
        # Negative value (< 0): completed prior to estimated time
        # Positive value (> 0): completed with delay past estimated time
        estimated_duration = assignment.get("estimated_duration_minutes")
        time_variance = None
        if estimated_duration is not None:
            time_variance = actual_duration - estimated_duration

        update_fields = {
            "completed_at": now,
            "status": TaskAssignmentStatus.COMPLETED.value,
            "actual_duration_minutes": actual_duration,
            "time_variance_minutes": time_variance,
            "updated_at": now,
        }
        if not assignment.get("started_at"):
            update_fields["started_at"] = started_at

        await db["task_assignments"].update_one(
            {"_id": assignment["_id"]},
            {"$set": update_fields}
        )
        cls.invalidate_reconcile_cache()

        await db["task_assignment_history"].insert_one({
            "assignment_id": str(assignment["_id"]),
            "action": "completed",
            "actor_id": str(actor_id),
            "actor_role": actor_role.upper(),
            "old_due_date": assignment.get("due_date"),
            "new_due_date": assignment.get("due_date"),
            "old_estimated_duration_minutes": estimated_duration,
            "new_estimated_duration_minutes": estimated_duration,
            "old_status": assignment.get("status"),
            "new_status": TaskAssignmentStatus.COMPLETED.value,
            "reason": f"Task completed. Actual duration: {actual_duration}m, Variance: {time_variance}m",
            "timestamp": now,
        })

        try:
            from app.services.activity_service import ActivityService
            await ActivityService.log_activity(
                db=db,
                event_type="TASK_COMPLETED",
                title=f"Task completed: '{assignment.get('task_title', 'Task')}'",
                description=f"Task marked as completed by {assignment.get('employee_name', 'Employee')}. Actual duration: {actual_duration} minutes.",
                user_email=assignment.get("employee_email") or "employee@enterprise.com",
                user_name=assignment.get("employee_name") or "Employee",
                status="COMPLETED",
                tool_name="Task Completion",
                card_id=assignment.get("trello_card_id"),
                card_title=assignment.get("task_title"),
                card_url=assignment.get("trello_card_url"),
                board_name=assignment.get("board_name"),
            )
        except Exception:
            pass

        assignment.update(update_fields)
        assignment["id"] = str(assignment["_id"])

        # Automatically recalculate employee performance level
        try:
            await PerformanceCalculationService.calculate_employee_performance(
                db=db,
                employee_id=str(assignment.get("employee_id")),
                employee_name=assignment.get("employee_name"),
            )
        except Exception as e:
            logger.warning(f"Error recalculating performance for employee {assignment.get('employee_id')}: {e}")

        return assignment

    _last_reconciled: Dict[str, float] = {}

    @classmethod
    def invalidate_reconcile_cache(cls) -> None:
        cls._last_reconciled.clear()

    @classmethod
    async def reconcile_board_cards(
        cls,
        db: AsyncIOMotorDatabase,
        board_id: Optional[str] = None,
        force: bool = False,
    ) -> None:
        """
        Reconciles live Trello board cards into task_assignments so existing cards,
        assigned members, and completion states are seamlessly tracked and counted
        for performance calculation.
        """
        try:
            import time
            from app.services.board_service import get_active_board_id
            from app.mcp_server import trello_tools

            active_board_id = await get_active_board_id(db, board_id)
            board_key = str(active_board_id or "default")
            now_ts = time.time()
            if not force and (now_ts - cls._last_reconciled.get(board_key, 0)) < 15.0:
                return
            cls._last_reconciled[board_key] = now_ts

            cards_res = await trello_tools.trello_list_cards(board_id=active_board_id)
            lists_res = await trello_tools.trello_list_lists(board_id=active_board_id)
            members_res = await trello_tools.trello_list_board_members(board_id=active_board_id)

            cards = cards_res.get("cards", [])
            lists = lists_res.get("lists", [])
            trello_members = members_res.get("members", [])
            list_map = {l["id"]: l["name"] for l in lists}
            member_map = {m["id"]: m for m in trello_members}

            # Map existing users in DB by name and email
            users_cursor = db["users"].find()
            db_users = await users_cursor.to_list(length=200)
            user_by_name = {u.get("full_name", "").lower().strip(): u for u in db_users if u.get("full_name")}

            now = datetime.now(timezone.utc)
            affected_emp_ids = set()

            # 1. Prune assignments whose cards were deleted or archived on Trello
            if cards_res.get("status") == "SUCCESS" or "cards" in cards_res:
                live_cards = [c for c in cards if c.get("id") and not c.get("closed")]
                live_card_ids = [str(c["id"]) for c in live_cards]

                stale_filter: Dict[str, Any] = {
                    "trello_card_id": {"$nin": live_card_ids, "$exists": True, "$ne": None}
                }
                if active_board_id and str(active_board_id).lower() != "all":
                    stale_filter["$or"] = [
                        {"board_id": str(active_board_id)},
                        {"board_id": None},
                        {"board_id": {"$exists": False}},
                    ]

                stale_docs = await db["task_assignments"].find(stale_filter).to_list(length=500)
                if stale_docs:
                    for doc in stale_docs:
                        if doc.get("employee_id"):
                            affected_emp_ids.add(str(doc["employee_id"]))
                    await db["task_assignments"].delete_many(stale_filter)
                    logger.info(f"Pruned {len(stale_docs)} stale/deleted Trello task assignments from MongoDB.")

                # 2. Prune assignments for cards on this board that have no members assigned on Trello
                unassigned_card_ids = [str(c["id"]) for c in live_cards if not c.get("idMembers")]
                if unassigned_card_ids:
                    unassigned_filter: Dict[str, Any] = {
                        "trello_card_id": {"$in": unassigned_card_ids}
                    }
                    unassigned_docs = await db["task_assignments"].find(unassigned_filter).to_list(length=500)
                    if unassigned_docs:
                        for doc in unassigned_docs:
                            if doc.get("employee_id"):
                                affected_emp_ids.add(str(doc["employee_id"]))
                        await db["task_assignments"].delete_many(unassigned_filter)
                        logger.info(f"Pruned {len(unassigned_docs)} unassigned Trello card assignments from MongoDB.")

            for c in cards:
                card_id = c.get("id")
                card_members = c.get("idMembers", [])
                if not card_id or not card_members or c.get("closed"):
                    continue

                list_name = list_map.get(c.get("idList"), "To Do")
                list_lower = list_name.lower()
                is_done = "done" in list_lower or "completed" in list_lower
                is_progress = "doing" in list_lower or "progress" in list_lower or "in-progress" in list_lower

                status_val = (
                    TaskAssignmentStatus.COMPLETED.value if is_done
                    else TaskAssignmentStatus.IN_PROGRESS.value if is_progress
                    else TaskAssignmentStatus.ASSIGNED.value
                )

                due_str = c.get("due")
                due_dt = None
                if due_str:
                    try:
                        clean_iso = due_str.replace("Z", "+00:00")
                        due_dt = datetime.fromisoformat(clean_iso)
                    except Exception:
                        pass

                # Determine card creation timestamp from Trello ObjectId (first 8 hex chars)
                try:
                    card_created_ts = int(card_id[:8], 16)
                    card_created_at = datetime.fromtimestamp(card_created_ts, tz=timezone.utc)
                except Exception:
                    card_created_at = now - timedelta(days=2)

                # Determine completion timestamp
                card_completed_at = None
                if is_done:
                    act_date_str = c.get("dateLastActivity")
                    if act_date_str:
                        try:
                            card_completed_at = datetime.fromisoformat(act_date_str.replace("Z", "+00:00"))
                        except Exception:
                            card_completed_at = now
                    else:
                        card_completed_at = now

                for m_id in card_members:
                    tm = member_map.get(m_id, {})
                    m_name = tm.get("fullName") or tm.get("username") or "Board Member"
                    m_username = tm.get("username", "")

                    # Match with user in DB
                    matched_user = user_by_name.get(m_name.lower().strip())
                    if not matched_user and m_username:
                        for u in db_users:
                            if m_username.lower() in u.get("email", "").lower():
                                matched_user = u
                                break

                    emp_id = str(matched_user["_id"]) if matched_user else m_id
                    emp_name = matched_user.get("full_name") if matched_user else m_name
                    emp_email = matched_user.get("email") if matched_user else f"{m_username}@trello.board"

                    # Check if already in task_assignments
                    existing = await db["task_assignments"].find_one({"trello_card_id": card_id})
                    if not existing:
                        completed_at = card_completed_at if is_done else None
                        started_at = card_created_at if (is_progress or is_done) else None

                        # Calculate accurate estimate, actual and variance based on true timestamps
                        est_duration = None
                        act_duration = None
                        variance = None

                        if due_dt:
                            est_duration = max(1, round((due_dt - card_created_at).total_seconds() / 60))

                        if is_done and completed_at:
                            act_duration = max(1, round((completed_at - card_created_at).total_seconds() / 60))
                            if due_dt:
                                # Formula: variance = completed_at - due_date = actual_duration - estimated_duration
                                # If completed after due date -> positive (delay)
                                # If completed before due date -> negative (prior)
                                variance = round((completed_at - due_dt).total_seconds() / 60)

                        doc = {
                            "employee_id": str(emp_id),
                            "employee_name": emp_name,
                            "employee_email": emp_email,
                            "project_manager_id": "system_admin",
                            "project_manager_name": "System Administrator",
                            "board_id": str(active_board_id),
                            "board_name": "Primary Trello Board",
                            "trello_card_id": card_id,
                            "trello_card_url": c.get("url") or c.get("shortUrl"),
                            "task_title": c.get("name", "Untitled Card"),
                            "task_description": c.get("desc"),
                            "assigned_at": card_created_at,
                            "status": status_val,
                            "due_date": due_dt,
                            "due_date_set_at": card_created_at if due_dt else None,
                            "due_date_set_by": "trello_sync",
                            "due_date_set_by_role": "MANAGER",
                            "due_date_version": 1,
                            "started_at": started_at,
                            "completed_at": completed_at,
                            "estimated_duration_minutes": est_duration,
                            "actual_duration_minutes": act_duration if is_done else None,
                            "time_variance_minutes": variance if is_done else None,
                            "trello_sync_status": "synced",
                            "created_at": card_created_at,
                            "updated_at": now,
                        }
                        await db["task_assignments"].insert_one(doc)
                        affected_emp_ids.add(str(emp_id))
                    else:
                        # Update status or metadata if changed
                        update_data: Dict[str, Any] = {
                            "status": status_val,
                            "updated_at": now,
                            "task_title": c.get("name", "Untitled Card"),
                            "employee_id": str(emp_id),
                            "employee_name": emp_name,
                            "employee_email": emp_email,
                        }
                        if c.get("desc") is not None:
                            update_data["task_description"] = c.get("desc")
                        if existing.get("employee_id") and str(existing["employee_id"]) != str(emp_id):
                            affected_emp_ids.add(str(existing["employee_id"]))
                        target_due = due_dt or existing.get("due_date")
                        if due_dt and not existing.get("due_date"):
                            update_data["due_date"] = due_dt

                        start_dt = existing.get("started_at") or existing.get("due_date_set_at") or existing.get("assigned_at") or card_created_at
                        if not start_dt.tzinfo:
                            start_dt = start_dt.replace(tzinfo=timezone.utc)

                        if target_due:
                            if not target_due.tzinfo:
                                target_due = target_due.replace(tzinfo=timezone.utc)
                            est_mins = max(1, round((target_due - start_dt).total_seconds() / 60))
                            update_data["estimated_duration_minutes"] = est_mins

                        if is_done:
                            comp_dt = card_completed_at or existing.get("completed_at") or now
                            if not comp_dt.tzinfo:
                                comp_dt = comp_dt.replace(tzinfo=timezone.utc)
                            update_data["completed_at"] = comp_dt

                            act_mins = max(1, round((comp_dt - start_dt).total_seconds() / 60))
                            update_data["actual_duration_minutes"] = act_mins

                            if target_due:
                                # Crucial: accurate variance = completed_at - due_date
                                # Positive (> 0): completed after due date -> DELAY
                                # Negative (< 0): completed before due date -> PRIOR
                                update_data["time_variance_minutes"] = round((comp_dt - target_due).total_seconds() / 60)
                        else:
                            # Not completed (e.g. To Do, Doing, In Progress) -> actual & variance must be None
                            update_data["actual_duration_minutes"] = None
                            update_data["time_variance_minutes"] = None
                            update_data["completed_at"] = None

                        await db["task_assignments"].update_one(
                            {"_id": existing["_id"]},
                            {"$set": update_data}
                        )
                        affected_emp_ids.add(str(existing.get("employee_id")))

            # Recalculate performance for affected employees
            for eid in affected_emp_ids:
                try:
                    await PerformanceCalculationService.calculate_employee_performance(db=db, employee_id=eid)
                except Exception as p_err:
                    logger.debug(f"Auto performance calculation skipped for {eid}: {p_err}")
        except Exception as e:
            logger.warning(f"reconcile_board_cards encountered an issue (non-blocking): {e}")

    @classmethod
    async def get_employee_tasks(
        cls,
        db: AsyncIOMotorDatabase,
        employee_id: str,
        board_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        # Match employee flexibly by ID, name, or email
        matched_user = None
        try:
            matched_user = await db["users"].find_one({"_id": ObjectId(employee_id)})
        except Exception:
            pass
        if not matched_user:
            matched_user = await db["users"].find_one({"email": employee_id})
        if not matched_user:
            matched_user = await db["users"].find_one({"full_name": employee_id})

        id_conditions = [{"employee_id": str(employee_id)}]
        if matched_user:
            id_conditions.append({"employee_id": str(matched_user["_id"])})
            if matched_user.get("full_name"):
                id_conditions.append({"employee_name": matched_user["full_name"]})
            if matched_user.get("email"):
                id_conditions.append({"employee_email": matched_user["email"]})

        query: Dict[str, Any] = {"$or": id_conditions}
        if board_id and board_id != "all":
            query["board_id"] = str(board_id)
        if status_filter and status_filter != "all":
            query["status"] = status_filter

        # Ensure datetime bounds have timezone and cover the full end day
        if from_date:
            if not from_date.tzinfo:
                from_date = from_date.replace(tzinfo=timezone.utc)
        if to_date:
            if not to_date.tzinfo:
                to_date = to_date.replace(tzinfo=timezone.utc)
            if to_date.hour == 0 and to_date.minute == 0 and to_date.second == 0:
                to_date = to_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        date_or_conditions = []
        if from_date and to_date:
            from_iso = from_date.isoformat()
            to_iso = to_date.isoformat()
            date_or_conditions = [
                {"due_date": {"$gte": from_date, "$lte": to_date}},
                {"due_date": {"$gte": from_iso, "$lte": to_iso}},
                {"assigned_at": {"$gte": from_date, "$lte": to_date}},
                {"assigned_at": {"$gte": from_iso, "$lte": to_iso}},
                {"created_at": {"$gte": from_date, "$lte": to_date}},
                {"created_at": {"$gte": from_iso, "$lte": to_iso}},
            ]
        elif from_date:
            from_iso = from_date.isoformat()
            date_or_conditions = [
                {"due_date": {"$gte": from_date}},
                {"due_date": {"$gte": from_iso}},
                {"assigned_at": {"$gte": from_date}},
                {"assigned_at": {"$gte": from_iso}},
                {"created_at": {"$gte": from_date}},
                {"created_at": {"$gte": from_iso}},
            ]
        elif to_date:
            to_iso = to_date.isoformat()
            date_or_conditions = [
                {"due_date": {"$lte": to_date}},
                {"due_date": {"$lte": to_iso}},
                {"assigned_at": {"$lte": to_date}},
                {"assigned_at": {"$lte": to_iso}},
                {"created_at": {"$lte": to_date}},
                {"created_at": {"$lte": to_iso}},
            ]

        if date_or_conditions:
            query["$and"] = query.get("$and", []) + [{"$or": date_or_conditions}]

        cursor = db["task_assignments"].find(query).sort("created_at", -1)
        tasks = await cursor.to_list(length=500)

        # Post-filter in Python to guarantee 100% precision across BSON and ISO formats
        if from_date or to_date:
            valid_tasks = []
            for t in tasks:
                d_check = []
                for f_name in ("due_date", "assigned_at", "created_at"):
                    v = t.get(f_name)
                    if not v:
                        continue
                    if isinstance(v, str):
                        try:
                            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
                        except Exception:
                            continue
                    if isinstance(v, datetime):
                        if not v.tzinfo:
                            v = v.replace(tzinfo=timezone.utc)
                        d_check.append(v)

                if not d_check:
                    continue

                matches_range = False
                for d in d_check:
                    if from_date and d < from_date:
                        continue
                    if to_date and d > to_date:
                        continue
                    matches_range = True
                    break

                if matches_range:
                    valid_tasks.append(t)
            tasks = valid_tasks

        now = datetime.now(timezone.utc)
        results = []
        for t in tasks:
            t["id"] = str(t.get("_id") or t.get("id"))
            due = t.get("due_date")
            time_remaining = None
            is_overdue = False
            task_status = t.get("status")

            if task_status in (TaskAssignmentStatus.COMPLETED.value, TaskAssignmentStatus.CANCELLED.value):
                # Completed/Cancelled tasks are finished; remaining time and overdue flags do not apply
                time_remaining = None
                is_overdue = False
            elif due:
                d_dt = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
                diff_mins = round((d_dt - now).total_seconds() / 60)
                time_remaining = diff_mins
                if diff_mins < 0:
                    is_overdue = True

            # Module 2 & User Requirement:
            # Actual time & variance are strictly populated ONLY when task is completed.
            if task_status != TaskAssignmentStatus.COMPLETED.value:
                t["actual_duration_minutes"] = None
                t["time_variance_minutes"] = None
            else:
                # Task IS completed: compute accurate actual elapsed duration & deadline variance
                comp_dt = t.get("completed_at") or t.get("updated_at") or now
                if not comp_dt.tzinfo:
                    comp_dt = comp_dt.replace(tzinfo=timezone.utc)
                t["completed_at"] = comp_dt

                start_ref = t.get("started_at") or t.get("due_date_set_at") or t.get("assigned_at") or t.get("created_at")
                if start_ref:
                    s_ref = start_ref if start_ref.tzinfo else start_ref.replace(tzinfo=timezone.utc)
                    t["actual_duration_minutes"] = max(1, round((comp_dt - s_ref).total_seconds() / 60))

                if due:
                    d_dt = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
                    if start_ref:
                        s_ref = start_ref if start_ref.tzinfo else start_ref.replace(tzinfo=timezone.utc)
                        t["estimated_duration_minutes"] = max(1, round((d_dt - s_ref).total_seconds() / 60))

                    # Crucial mathematical invariant:
                    # variance = actualDuration - estimatedDuration = comp_dt - d_dt
                    # If comp_dt > d_dt: completed after due date -> Positive value (DELAY)
                    # If comp_dt < d_dt: completed before due date -> Negative value (PRIOR)
                    t["time_variance_minutes"] = round((comp_dt - d_dt).total_seconds() / 60)

            # Calculate estimated duration for incomplete tasks if due date is present
            if task_status != TaskAssignmentStatus.COMPLETED.value and t.get("estimated_duration_minutes") is None and due:
                start_ref = t.get("due_date_set_at") or t.get("assigned_at") or t.get("created_at")
                if start_ref:
                    s_ref = start_ref if start_ref.tzinfo else start_ref.replace(tzinfo=timezone.utc)
                    d_dt = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
                    t["estimated_duration_minutes"] = max(1, round((d_dt - s_ref).total_seconds() / 60))

            t["time_remaining_minutes"] = time_remaining
            t["is_overdue"] = is_overdue
            results.append(t)

        return results

