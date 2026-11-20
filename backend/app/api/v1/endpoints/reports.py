import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_current_user
from app.database.mongodb import get_database
from app.mcp_server import trello_tools
from app.schemas.user import UserResponse
from app.services.board_service import get_active_board_id

logger = logging.getLogger(__name__)

router = APIRouter()


def _format_overdue(due_iso: Optional[str], is_completed: bool, now_utc: datetime) -> tuple[bool, str]:
    """Calculate if a task is overdue and format human-readable duration."""
    if is_completed or not due_iso:
        return False, "—"

    try:
        clean_due = due_iso.replace("Z", "+00:00")
        due_dt = datetime.fromisoformat(clean_due)
        if due_dt.tzinfo is None:
            due_dt = due_dt.replace(tzinfo=timezone.utc)
    except Exception:
        return False, "—"

    if now_utc > due_dt:
        delta = now_utc - due_dt
        days = delta.days
        hours = delta.seconds // 3600
        mins = (delta.seconds % 3600) // 60
        if days > 0:
            return True, f"Overdue by {days}d {hours}h"
        elif hours > 0:
            return True, f"Overdue by {hours}h {mins}m"
        else:
            return True, f"Overdue by {max(1, mins)}m"

    return False, "On Time"


def _extract_card_date(card: Dict[str, Any]) -> datetime:
    """Extract due date or fallback to creation date embedded in Trello card ObjectId."""
    due_iso = card.get("due")
    if due_iso:
        try:
            clean_due = due_iso.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_due)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass

    # Trello IDs encode a 32-bit timestamp in their first 8 hex characters
    cid = str(card.get("id", ""))
    if len(cid) >= 8:
        try:
            ts = int(cid[:8], 16)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            pass

    return datetime.now(timezone.utc)


@router.get(
    "/workload",
    status_code=status.HTTP_200_OK,
    summary="Get real workload report metrics",
    description="Computes workload distribution and task velocity from live Trello board cards.",
)
async def get_workload_report(
    board_id: Optional[str] = Query(None, description="Optional target Trello board ID"),
    refresh: bool = Query(False, description="Force refresh from Trello API, bypassing cache"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    active_board_id = board_id
    if not active_board_id and db is not None:
        try:
            active_board_id = await get_active_board_id(db, board_id)
        except Exception:
            active_board_id = None

    cards_res, lists_res = await asyncio.gather(
        trello_tools.trello_list_cards(board_id=active_board_id, force_refresh=refresh),
        trello_tools.trello_list_lists(board_id=active_board_id, force_refresh=refresh),
    )

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
        if "done" in l_lower or "completed" in l_lower:
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


@router.get(
    "/board-tasks",
    status_code=status.HTTP_200_OK,
    summary="Get board-wise task report and employee availability",
    description="Returns live Trello board cards with assigned employees, status, overdue durations, KPIs, and today's availability.",
)
async def get_board_task_report(
    board_id: Optional[str] = Query(None, description="Optional target Trello board ID"),
    from_date: Optional[str] = Query(None, description="Optional ISO start date filter"),
    to_date: Optional[str] = Query(None, description="Optional ISO end date filter"),
    refresh: bool = Query(False, description="Force refresh from Trello API, bypassing cache"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    try:
        active_board_id = board_id
        if not active_board_id and db is not None:
            try:
                active_board_id = await get_active_board_id(db, board_id)
            except Exception:
                active_board_id = None

        cards_res, lists_res, members_res = await asyncio.gather(
            trello_tools.trello_list_cards(board_id=active_board_id, force_refresh=refresh),
            trello_tools.trello_list_lists(board_id=active_board_id, force_refresh=refresh),
            trello_tools.trello_list_board_members(board_id=active_board_id, force_refresh=refresh),
        )

        cards = cards_res.get("cards", [])
        lists = lists_res.get("lists", [])
        trello_members = members_res.get("members", [])
        list_map = {l["id"]: l["name"] for l in lists}

        # Build comprehensive team member directory
        team_members_map: Dict[str, Dict[str, Any]] = {}

        for tm in trello_members:
            m_id = str(tm.get("id"))
            m_name = tm.get("fullName") or tm.get("username") or "Board Member"
            username = tm.get("username") or m_name.lower().replace(" ", "_")
            team_members_map[m_id] = {
                "id": m_id,
                "name": m_name,
                "username": username,
                "email": f"{username}@trello.board",
                "role": "Trello Collaborator",
                "avatar": tm.get("avatarUrl") or f"https://api.dicebear.com/7.x/initials/svg?seed={m_name}",
                "assigned_cards": [],
                "active_cards": [],
                "completed_cards": [],
                "busy_cards_today": [],
            }

        # Merge MongoDB users
        if db is not None:
            try:
                async for u in db["users"].find():
                    u_name = u.get("full_name") or u.get("email", "User").split("@")[0]
                    already_exists = any(
                        m["name"].lower() == u_name.lower() or u_name.lower() in m["name"].lower()
                        for m in team_members_map.values()
                    )
                    if not already_exists:
                        u_id = str(u.get("_id"))
                        team_members_map[u_id] = {
                            "id": u_id,
                            "name": u_name,
                            "username": u.get("email", "").split("@")[0],
                            "email": u.get("email", ""),
                            "role": u.get("role", "EMPLOYEE"),
                            "avatar": f"https://api.dicebear.com/7.x/initials/svg?seed={u_name}",
                            "assigned_cards": [],
                            "active_cards": [],
                            "completed_cards": [],
                            "busy_cards_today": [],
                        }
            except Exception as db_err:
                logger.warning(f"Could not load users from database: {db_err}")

        # Fallback to current user if empty
        if not team_members_map:
            u_name = current_user.full_name or "Project Manager"
            team_members_map["current_user"] = {
                "id": "current_user",
                "name": u_name,
                "username": current_user.email.split("@")[0],
                "email": current_user.email,
                "role": current_user.role,
                "avatar": f"https://api.dicebear.com/7.x/initials/svg?seed={u_name}",
                "assigned_cards": [],
                "active_cards": [],
                "completed_cards": [],
                "busy_cards_today": [],
            }

        # Build platform assignments map from database
        db_assignment_map: Dict[str, Dict[str, Any]] = {}
        if db is not None:
            try:
                async for assign in db["task_assignments"].find():
                    trello_cid = assign.get("trello_card_id") or assign.get("card_id")
                    if trello_cid:
                        db_assignment_map[str(trello_cid)] = assign
            except Exception as exc:
                logger.debug(f"Could not query task_assignments: {exc}")

        now_utc = datetime.now(timezone.utc)

        # Parse date filters
        from_dt: Optional[datetime] = None
        to_dt: Optional[datetime] = None
        if from_date:
            try:
                from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
                if from_dt.tzinfo is None:
                    from_dt = from_dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass
        if to_date:
            try:
                to_dt = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
                if to_dt.tzinfo is None:
                    to_dt = to_dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass

        all_board_tasks: List[Dict[str, Any]] = []

        total_cards_count = 0
        overdue_cards_count = 0
        completed_cards_count = 0
        pending_cards_count = 0
        in_progress_cards_count = 0

        for c in cards:
            c_id = str(c.get("id"))
            c_name = c.get("name") or "Untitled Card"
            c_desc = c.get("desc") or ""
            c_list = list_map.get(c.get("idList"), "To Do")
            c_list_lower = c_list.lower()
            c_due = c.get("due")
            c_members = c.get("idMembers", [])
            c_url = c.get("url") or c.get("shortUrl") or ""

            # Check db assignment fallback if due is missing
            if not c_due and c_id in db_assignment_map:
                c_due = db_assignment_map[c_id].get("due_date")

            is_completed = "done" in c_list_lower or "completed" in c_list_lower or c.get("closed", False)
            is_in_progress = "doing" in c_list_lower or "progress" in c_list_lower or "in-progress" in c_list_lower
            is_pending = not is_completed

            is_overdue, overdue_text = _format_overdue(c_due, is_completed, now_utc)

            # Assignee resolution
            assigned_names: List[str] = []
            assigned_member_objs: List[Dict[str, Any]] = []

            # 1. Match by Trello member ID
            for m_id, m_data in team_members_map.items():
                if m_id in c_members:
                    assigned_names.append(m_data["name"])
                    assigned_member_objs.append(m_data)

            # 2. Match by MongoDB task assignment
            if not assigned_names and c_id in db_assignment_map:
                assign_doc = db_assignment_map[c_id]
                emp_name = assign_doc.get("employee_name")
                emp_id = assign_doc.get("employee_id")
                if emp_name:
                    assigned_names.append(emp_name)
                    # Find or attach
                    for m_id, m_data in team_members_map.items():
                        if m_data["name"].lower() == emp_name.lower() or m_data["id"] == str(emp_id):
                            assigned_member_objs.append(m_data)
                            break

            # 3. Match by name regex in card title/desc
            if not assigned_names:
                for m_id, m_data in team_members_map.items():
                    m_name = m_data["name"].strip()
                    if m_data.get("role") == "ADMIN" and "admin" in m_name.lower():
                        continue
                    m_lower = m_name.lower()
                    first_name = m_lower.split()[0]
                    pattern = re.compile(
                        r"\b(?:assigned\s+to|assignee\s*[:=]|member\s*[:=]|for)\s+" + re.escape(first_name) + r"\b|"
                        + r"\b" + re.escape(m_lower) + r"\b",
                        re.IGNORECASE,
                    )
                    if pattern.search(c_name) or pattern.search(c_desc):
                        assigned_names.append(m_name)
                        assigned_member_objs.append(m_data)
                        break

            employee_display = ", ".join(assigned_names) if assigned_names else "Unassigned"

            card_date = _extract_card_date(c)

            task_item = {
                "id": c_id,
                "card": c_name,
                "description": c_desc,
                "employee": employee_display,
                "employee_count": len(assigned_names),
                "list": c_list,
                "status": "Completed" if is_completed else "Pending",
                "in_progress": is_in_progress,
                "is_overdue": is_overdue,
                "overdue": overdue_text,
                "due_date": c_due,
                "date": card_date.isoformat(),
                "created_at": card_date.isoformat(),
                "url": c_url,
            }

            # Update summary metrics (calculated from all board's actual Trello cards)
            total_cards_count += 1
            if is_completed:
                completed_cards_count += 1
            else:
                pending_cards_count += 1
            if is_in_progress:
                in_progress_cards_count += 1
            if is_overdue:
                overdue_cards_count += 1

            # Update employee availability tracking
            for m_data in assigned_member_objs:
                m_data["assigned_cards"].append(task_item)
                if is_completed:
                    m_data["completed_cards"].append(task_item)
                else:
                    m_data["active_cards"].append(task_item)
                    # Busy employee requirement:
                    # At least one assigned Trello card whose due date has not yet arrived (or active card due today/future)
                    # If card has due date and due_dt >= now_utc, or active task without past deadline
                    if not is_overdue:
                        m_data["busy_cards_today"].append(task_item)

            # Date range filtering for table records
            include_in_table = True
            if from_dt and card_date < from_dt:
                include_in_table = False
            if to_dt and card_date > to_dt:
                include_in_table = False

            if include_in_table:
                all_board_tasks.append(task_item)

        # Calculate Employee Availability
        busy_employees: List[Dict[str, Any]] = []
        free_employees: List[Dict[str, Any]] = []

        for m_id, m_data in team_members_map.items():
            busy_cards = m_data["busy_cards_today"]
            active_cards = m_data["active_cards"]
            # Busy: has at least one assigned Trello card whose due date has not yet arrived
            # Or active card assigned
            is_busy = len(busy_cards) > 0 or len(active_cards) > 0

            member_summary = {
                "id": m_data["id"],
                "name": m_data["name"],
                "email": m_data["email"],
                "role": m_data["role"],
                "avatar": m_data["avatar"],
                "busy_cards_count": len(busy_cards),
                "active_cards_count": len(active_cards),
                "total_assigned_cards": len(m_data["assigned_cards"]),
                "completed_cards_count": len(m_data["completed_cards"]),
                "is_busy": is_busy,
                "current_tasks": [t["card"] for t in (busy_cards if busy_cards else active_cards)[:3]],
                "working_hours_allocated": 8 if is_busy else 0,
                "working_hours_total": 8,
            }

            if is_busy:
                busy_employees.append(member_summary)
            else:
                free_employees.append(member_summary)

        # Sort busy employees descending by workload
        busy_employees.sort(key=lambda x: (x["active_cards_count"], x["busy_cards_count"]), reverse=True)
        # Sort free employees by name
        free_employees.sort(key=lambda x: x["name"])

        board_name = "Trello Board"
        try:
            boards_res = await trello_tools.trello_list_boards()
            for b in boards_res.get("boards", []):
                if b.get("id") == active_board_id:
                    board_name = b.get("name", board_name)
                    break
        except Exception:
            pass

        return {
            "status": "SUCCESS",
            "board_id": active_board_id,
            "board_name": board_name,
            "summary": {
                "total_cards": total_cards_count,
                "overdue_cards": overdue_cards_count,
                "completed_cards": completed_cards_count,
                "pending_cards": pending_cards_count,
                "in_progress_cards": in_progress_cards_count,
            },
            "availability": {
                "busy_count": len(busy_employees),
                "free_count": len(free_employees),
                "total_employees": len(busy_employees) + len(free_employees),
                "working_period": "Today's 8-hour working period",
                "working_period_hours": 8,
                "busiest_employees": busy_employees,
                "free_employees": free_employees,
            },
            "total_filtered_cards": len(all_board_tasks),
            "cards": all_board_tasks,
        }
    except Exception as e:
        logger.error(f"Failed to generate board task report: {e}")
        return {
            "status": "ERROR",
            "board_id": board_id or "",
            "board_name": "",
            "summary": {
                "total_cards": 0,
                "overdue_cards": 0,
                "completed_cards": 0,
                "pending_cards": 0,
                "in_progress_cards": 0,
            },
            "availability": {
                "busy_count": 0,
                "free_count": 0,
                "total_employees": 0,
                "working_period": "Today's 8-hour working period",
                "working_period_hours": 8,
                "busiest_employees": [],
                "free_employees": [],
            },
            "total_filtered_cards": 0,
            "cards": [],
            "error": str(e),
        }
