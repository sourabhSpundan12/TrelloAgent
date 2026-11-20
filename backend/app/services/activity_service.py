import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.user import UserResponse

logger = logging.getLogger(__name__)


def _parse_dt(val: Any) -> Optional[datetime]:
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


class ActivityService:
    """
    Centralized service for logging, persisting, and querying platform activity history.
    Ensures zero data loss across page refreshes, navigation, and system restarts.
    """

    @staticmethod
    async def log_activity(
        db: AsyncIOMotorDatabase,
        event_type: str,
        title: str,
        description: str = "",
        user_email: str = "system@enterprise.com",
        user_name: str = "System",
        user_id: Optional[str] = None,
        actor_role: str = "MANAGER",
        status: str = "EXECUTED",
        tool_name: str = "Platform Operation",
        action_id: Optional[str] = None,
        card_id: Optional[str] = None,
        card_title: Optional[str] = None,
        card_url: Optional[str] = None,
        board_id: Optional[str] = None,
        board_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if db is None:
            return None

        now = datetime.now(timezone.utc)
        act_id = action_id or f"ACT-{uuid.uuid4().hex[:8].upper()}"

        activity_doc = {
            "id": act_id,
            "action_id": act_id,
            "event_type": event_type,
            "title": title,
            "description": description,
            "user_email": user_email,
            "user_name": user_name,
            "user_id": str(user_id) if user_id else None,
            "actor_role": actor_role.upper() if actor_role else "EMPLOYEE",
            "status": status.upper() if status else "EXECUTED",
            "tool_name": tool_name,
            "card_id": card_id,
            "card_title": card_title or title,
            "card_url": card_url,
            "board_id": board_id,
            "board_name": board_name,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }

        try:
            await db["activity_logs"].update_one(
                {"action_id": act_id},
                {"$set": activity_doc},
                upsert=True,
            )
            return activity_doc
        except Exception as e:
            logger.warning(f"Could not persist activity log '{act_id}': {e}")
            return None

    @classmethod
    async def get_combined_activities(
        cls,
        db: AsyncIOMotorDatabase,
        current_user: Optional[UserResponse] = None,
        board_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        activities_map: Dict[str, Dict[str, Any]] = {}

        if db is None:
            return []

        # 1. Fetch explicitly saved activity logs
        try:
            query: Dict[str, Any] = {}
            if board_id and board_id != "all":
                query["$or"] = [{"board_id": board_id}, {"board_id": {"$exists": False}}]
            cursor = db["activity_logs"].find(query).sort("created_at", -1).limit(limit)
            async for doc in cursor:
                doc.pop("_id", None)
                act_id = doc.get("action_id") or doc.get("id")
                if not act_id:
                    continue
                c_dt = _parse_dt(doc.get("created_at")) or datetime.now(timezone.utc)
                activities_map[act_id] = {
                    "id": act_id,
                    "action_id": act_id,
                    "action_type": doc.get("event_type") or doc.get("action_type", "MUTATION"),
                    "tool_name": doc.get("tool_name", "Platform Action"),
                    "user_email": doc.get("user_email") or (current_user.email if current_user else "admin@example.com"),
                    "user_name": doc.get("user_name") or (current_user.full_name if current_user else "Platform User"),
                    "title": doc.get("title") or "Activity",
                    "status": str(doc.get("status") or "EXECUTED").upper(),
                    "created_at": c_dt.isoformat(),
                    "updated_at": (_parse_dt(doc.get("updated_at")) or c_dt).isoformat(),
                    "card_url": doc.get("card_url"),
                    "description": doc.get("description") or "",
                    "priority": doc.get("priority", "MEDIUM"),
                    "board_name": doc.get("board_name"),
                }
        except Exception as e:
            logger.warning(f"Error reading activity_logs: {e}")

        # 2. Ingest and reconcile from pending_actions
        try:
            cursor = db["pending_actions"].find().sort("created_at", -1).limit(limit)
            async for doc in cursor:
                act_id = doc.get("action_id")
                if not act_id:
                    continue
                if act_id in activities_map:
                    # Update status if changed
                    activities_map[act_id]["status"] = str(doc.get("status") or "PENDING").upper()
                    continue

                status_val = str(doc.get("status") or "PENDING").upper()
                action_type = str(doc.get("action_type") or "MUTATION").upper()
                draft = doc.get("draft") or {}
                card_title = draft.get("title") or doc.get("command") or "Task Action"
                created_dt = _parse_dt(doc.get("created_at")) or datetime.now(timezone.utc)
                updated_dt = _parse_dt(doc.get("updated_at")) or created_dt

                exec_res = doc.get("execution_result", {})
                card_obj = exec_res.get("result", {}).get("card", {}) if isinstance(exec_res, dict) else {}
                card_url = card_obj.get("url") or doc.get("card_url") or draft.get("card_url")

                desc = draft.get("description") or f"Action {action_type} for '{card_title}'"

                item = {
                    "id": act_id,
                    "action_id": act_id,
                    "action_type": action_type,
                    "tool_name": doc.get("tool_name") or (doc.get("tool_id", "").replace("_", " ").title() or "Trello Operation"),
                    "user_email": doc.get("user_email") or (current_user.email if current_user else "admin@example.com"),
                    "user_name": (current_user.full_name if current_user else "System"),
                    "title": card_title,
                    "status": status_val,
                    "created_at": created_dt.isoformat(),
                    "updated_at": updated_dt.isoformat(),
                    "card_url": card_url,
                    "description": desc,
                    "priority": draft.get("priority", "MEDIUM"),
                    "board_name": draft.get("board_name") or doc.get("board_name"),
                }
                activities_map[act_id] = item

                # Auto-persist into activity_logs so it survives any clearing of pending_actions
                await cls.log_activity(
                    db=db,
                    event_type=action_type,
                    title=card_title,
                    description=desc,
                    user_email=item["user_email"],
                    user_name=item["user_name"],
                    status=status_val,
                    tool_name=item["tool_name"],
                    action_id=act_id,
                    card_url=card_url,
                    board_name=item["board_name"],
                )
        except Exception as e:
            logger.warning(f"Error reading pending_actions in activity service: {e}")

        # 3. Ingest task assignment history (Started, Completed, Assigned, Due Date Updated)
        try:
            cursor = db["task_assignment_history"].find().sort("timestamp", -1).limit(limit)
            async for h_doc in cursor:
                h_id = f"hist_{str(h_doc.get('_id', uuid.uuid4().hex[:6]))}"
                if h_id in activities_map:
                    continue

                assign_id = h_doc.get("assignment_id")
                action = str(h_doc.get("action") or "updated").lower()
                h_dt = _parse_dt(h_doc.get("timestamp")) or datetime.now(timezone.utc)

                # Look up parent assignment
                assign_doc = None
                if assign_id:
                    try:
                        assign_doc = await db["task_assignments"].find_one({"id": str(assign_id)})
                    except Exception:
                        pass

                task_title = (assign_doc.get("task_title") if assign_doc else None) or "Task Assignment"
                card_url = assign_doc.get("trello_card_url") if assign_doc else None
                emp_name = assign_doc.get("employee_name") if assign_doc else "Team Member"
                board_name = assign_doc.get("board_name") if assign_doc else None

                if action == "assigned":
                    title = f"Task '{task_title}' assigned to {emp_name}"
                    desc = f"New task assignment created on board {board_name or 'Trello'}."
                    status_val = "EXECUTED"
                    tool_name = "Task Assignment Engine"
                    event_type = "TASK_ASSIGNED"
                elif action == "started":
                    title = f"Task '{task_title}' started by {emp_name}"
                    desc = f"Work started on task; active timer initiated."
                    status_val = "EXECUTED"
                    tool_name = "Task Progression"
                    event_type = "TASK_STARTED"
                elif action == "completed":
                    title = f"Task '{task_title}' completed by {emp_name}"
                    desc = f"Task successfully marked as completed."
                    status_val = "EXECUTED"
                    tool_name = "Task Completion"
                    event_type = "TASK_COMPLETED"
                elif action == "due_date_updated":
                    new_due = h_doc.get("new_due_date")
                    title = f"Due date updated for '{task_title}'"
                    desc = f"New deadline established: {new_due or 'No deadline'}."
                    status_val = "EXECUTED"
                    tool_name = "Schedule Adjustment"
                    event_type = "DUE_DATE_UPDATED"
                else:
                    title = f"Task '{task_title}' {action}"
                    desc = f"Task lifecycle transition: {action}."
                    status_val = "EXECUTED"
                    tool_name = "Task Lifecycle"
                    event_type = "TASK_LIFECYCLE"

                item = {
                    "id": h_id,
                    "action_id": h_id,
                    "action_type": event_type,
                    "tool_name": tool_name,
                    "user_email": (assign_doc.get("employee_email") if assign_doc else None) or (current_user.email if current_user else "employee@enterprise.com"),
                    "user_name": emp_name,
                    "title": title,
                    "status": status_val,
                    "created_at": h_dt.isoformat(),
                    "updated_at": h_dt.isoformat(),
                    "card_url": card_url,
                    "description": desc,
                    "priority": assign_doc.get("priority", "MEDIUM") if assign_doc else "MEDIUM",
                    "board_name": board_name,
                }
                activities_map[h_id] = item

                # Auto-persist into activity_logs
                await cls.log_activity(
                    db=db,
                    event_type=event_type,
                    title=title,
                    description=desc,
                    user_email=item["user_email"],
                    user_name=item["user_name"],
                    status=status_val,
                    tool_name=tool_name,
                    action_id=h_id,
                    card_url=card_url,
                    board_name=board_name,
                )
        except Exception as e:
            logger.warning(f"Error reading task_assignment_history in activity service: {e}")

        # 4. Ingest live Trello board actions if available
        try:
            from app.mcp_server import trello_tools
            active_bid = board_id
            if not active_bid or active_bid == "all":
                from app.services.board_service import get_active_board_id
                active_bid = await get_active_board_id(db)

            if active_bid:
                actions_res = await trello_tools.trello_list_board_actions(board_id=active_bid, limit=30)
                for tr_act in actions_res.get("actions", []):
                    tr_id = f"trl_{tr_act.get('id')}"
                    if tr_id in activities_map:
                        continue

                    tr_type = tr_act.get("type", "updateCard")
                    tr_date = _parse_dt(tr_act.get("date")) or datetime.now(timezone.utc)
                    tr_member = tr_act.get("memberCreator", {})
                    m_name = tr_member.get("fullName") or tr_member.get("username") or "Trello User"
                    data_obj = tr_act.get("data", {})
                    c_info = data_obj.get("card", {})
                    c_name = c_info.get("name") or "Trello Card"
                    c_short_link = c_info.get("shortLink")
                    c_url = f"https://trello.com/c/{c_short_link}" if c_short_link else None

                    if tr_type == "createCard":
                        ev_type = "CARD_CREATED"
                        ev_title = f"Card '{c_name}' created on Trello"
                        ev_desc = f"Created on list '{data_obj.get('list', {}).get('name', 'To Do')}'."
                    elif tr_type == "updateCard":
                        if "listAfter" in data_obj:
                            ev_type = "CARD_MOVED"
                            l_before = data_obj.get("listBefore", {}).get("name", "List")
                            l_after = data_obj.get("listAfter", {}).get("name", "List")
                            ev_title = f"Card '{c_name}' moved to {l_after}"
                            ev_desc = f"Moved from '{l_before}' to '{l_after}'."
                        else:
                            ev_type = "CARD_UPDATED"
                            ev_title = f"Card '{c_name}' updated"
                            ev_desc = "Card details or deadline synchronized."
                    elif tr_type == "commentCard":
                        ev_type = "CARD_COMMENT"
                        ev_title = f"Comment added to '{c_name}'"
                        ev_desc = data_obj.get("text") or "New discussion note on card."
                    else:
                        ev_type = "TRELLO_ACTIVITY"
                        ev_title = f"Card '{c_name}' activity"
                        ev_desc = f"Trello event {tr_type} processed."

                    item = {
                        "id": tr_id,
                        "action_id": tr_id,
                        "action_type": ev_type,
                        "tool_name": "Trello Live Sync",
                        "user_email": f"{tr_member.get('username', 'trello')}@trello.com",
                        "user_name": m_name,
                        "title": ev_title,
                        "status": "EXECUTED",
                        "created_at": tr_date.isoformat(),
                        "updated_at": tr_date.isoformat(),
                        "card_url": c_url,
                        "description": ev_desc,
                        "priority": "MEDIUM",
                        "board_name": data_obj.get("board", {}).get("name"),
                    }
                    activities_map[tr_id] = item

                    # Auto-persist into activity_logs
                    await cls.log_activity(
                        db=db,
                        event_type=ev_type,
                        title=ev_title,
                        description=ev_desc,
                        user_email=item["user_email"],
                        user_name=item["user_name"],
                        status="EXECUTED",
                        tool_name="Trello Live Sync",
                        action_id=tr_id,
                        card_url=c_url,
                        board_name=item["board_name"],
                    )
        except Exception as e:
            logger.debug(f"Live Trello actions skipped in activity service: {e}")

        # Sort all aggregated activities by created_at descending
        results = list(activities_map.values())
        results.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return results[:limit]

