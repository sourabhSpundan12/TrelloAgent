import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.dependencies import get_current_user
from app.core.logging import logger
from app.database.mongodb import get_database
from app.integrations.trello.client import parse_due_date_for_trello
from app.mcp_server import trello_tools
from app.schemas.user import UserResponse
from app.services.board_service import get_active_board_id

router = APIRouter()


@router.get(
    "/trello",
    status_code=status.HTTP_200_OK,
    summary="Get live Trello board cards and lists",
    description="Fetches live tasks directly from the configured Trello board via MCP tools.",
)
async def get_trello_tasks(
    board_id: Optional[str] = Query(None, description="Optional target Trello board ID"),
    refresh: bool = Query(False, description="Force refresh from Trello API, bypassing cache"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    try:
        active_board_id = await get_active_board_id(db, board_id)
        cards_res, lists_res = await asyncio.gather(
            trello_tools.trello_list_cards(board_id=active_board_id, force_refresh=refresh),
            trello_tools.trello_list_lists(board_id=active_board_id, force_refresh=refresh),
        )

        lists = lists_res.get("lists", [])
        cards = cards_res.get("cards", [])

        list_map = {l["id"]: l["name"] for l in lists}

        # Build fallback map of known due dates from platform actions for cards where Trello due is missing
        executed_due_map: Dict[str, str] = {}
        try:
            executed_actions = await db["pending_actions"].find(
                {"draft.due_date": {"$exists": True, "$ne": None}}
            ).to_list(100)
            for act in executed_actions:
                d = act.get("draft", {})
                d_due = d.get("due_date")
                if not d_due:
                    continue
                parsed_d_due = parse_due_date_for_trello(d_due)
                if not parsed_d_due:
                    continue
                t_key = (d.get("title") or "").strip().lower()
                if t_key:
                    executed_due_map[t_key] = parsed_d_due
                cid = act.get("card_id")
                if not cid and isinstance(act.get("execution_result"), dict):
                    res_inner = act["execution_result"]
                    if isinstance(res_inner.get("result"), dict):
                        cid = res_inner["result"].get("card", {}).get("id") or res_inner["result"].get("id")
                if cid:
                    executed_due_map[str(cid)] = parsed_d_due
        except Exception as e:
            logger.debug(f"Could not query pending_actions for due dates: {e}")

        formatted_cards = []
        for c in cards:
            list_name = list_map.get(c.get("idList"), "To Do")
            card_id = c.get("id")
            card_name = c.get("name") or ""
            card_due = c.get("due")

            # If missing from Trello, reconcile with platform action draft
            if not card_due:
                matched_due = executed_due_map.get(str(card_id)) or executed_due_map.get(card_name.strip().lower())
                if matched_due:
                    card_due = matched_due
                    try:
                        client = trello_tools.get_trello_client()
                        asyncio.create_task(client.update_card(card_id=card_id, due=matched_due))
                    except Exception as exc:
                        logger.debug(f"Async Trello due date sync skipped: {exc}")

            formatted_cards.append({
                "id": card_id,
                "name": card_name,
                "desc": c.get("desc") or "",
                "list_id": c.get("idList"),
                "list_name": list_name,
                "url": c.get("url"),
                "short_url": c.get("shortUrl"),
                "due": card_due,
                "closed": c.get("closed", False),
                "members": c.get("idMembers", []),
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


@router.get(
    "/team",
    status_code=status.HTTP_200_OK,
    summary="Get live team members and their assigned workload",
    description="Fetches live Trello board members and platform users, computing real assigned task counts from Trello cards.",
)
async def get_team_workload(
    board_id: Optional[str] = Query(None, description="Optional target Trello board ID"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    try:
        active_board_id = await get_active_board_id(db, board_id)
        cards_res = await trello_tools.trello_list_cards(board_id=active_board_id)
        lists_res = await trello_tools.trello_list_lists(board_id=active_board_id)
        members_res = await trello_tools.trello_list_board_members(board_id=active_board_id)

        cards = cards_res.get("cards", [])
        lists = lists_res.get("lists", [])
        trello_members = members_res.get("members", [])
        list_map = {l["id"]: l["name"] for l in lists}

        # Build list of member profiles
        team_members_map: Dict[str, Dict[str, Any]] = {}

        # 1. Registered platform users from MongoDB are designated as ADMIN role
        admin_emails = set()
        admin_names = set()
        if db is not None:
            try:
                async for u in db["users"].find():
                    u_name = u.get("full_name") or u.get("email", "User").split("@")[0]
                    u_email = u.get("email", "").lower().strip()
                    admin_names.add(u_name.lower().strip())
                    if u_email:
                        admin_emails.add(u_email)
                    u_id = str(u.get("_id"))
                    team_members_map[u_id] = {
                        "id": u_id,
                        "empId": f"ADM-{u_id[:6].upper()}",
                        "name": u_name,
                        "username": u.get("email", "").split("@")[0],
                        "email": u.get("email", ""),
                        "role": "ADMIN",
                        "department": u.get("department", "Platform Administration"),
                        "avatar": f"https://api.dicebear.com/7.x/initials/svg?seed={u_name}",
                        "status": "ACTIVE" if u.get("is_active", True) else "AWAY",
                        "assignedTasksCount": 0,
                        "todoCount": 0,
                        "inProgressCount": 0,
                        "inReviewCount": 0,
                        "completedCount": 0,
                        "overdueCount": 0,
                        "tasks": [],
                    }
            except Exception as db_err:
                logger.warning(f"Could not load users from database: {db_err}")

        # 2. Add active Trello board members (designated as MEMBER role)
        for tm in trello_members:
            m_id = str(tm.get("id"))
            m_name = (tm.get("fullName") or tm.get("username") or "Board Member").strip()
            username = tm.get("username") or m_name.lower().replace(" ", "_")
            m_lower = m_name.lower()
            u_lower = username.lower()

            # If this member matches an existing Admin registered in DB, ensure they retain ADMIN role
            matched_admin_id = None
            for adm_id, adm_data in team_members_map.items():
                if adm_data.get("role") == "ADMIN":
                    if adm_data["name"].lower() == m_lower or m_lower in adm_data["name"].lower() or adm_data["name"].lower() in m_lower:
                        matched_admin_id = adm_id
                        break

            if matched_admin_id:
                # Update Trello ID reference on the admin so Trello tasks correlate correctly
                team_members_map[matched_admin_id]["trello_id"] = m_id
                team_members_map[matched_admin_id]["username"] = username
                if tm.get("avatarUrl"):
                    team_members_map[matched_admin_id]["avatar"] = tm.get("avatarUrl")
            else:
                team_members_map[m_id] = {
                    "id": m_id,
                    "empId": f"MBR-{m_id[:6].upper()}",
                    "name": m_name,
                    "username": username,
                    "email": f"{username}@trello.board",
                    "role": "MEMBER",
                    "department": "Board Member",
                    "avatar": tm.get("avatarUrl") or f"https://api.dicebear.com/7.x/initials/svg?seed={m_name}",
                    "status": "ACTIVE",
                    "assignedTasksCount": 0,
                    "todoCount": 0,
                    "inProgressCount": 0,
                    "inReviewCount": 0,
                    "completedCount": 0,
                    "overdueCount": 0,
                    "tasks": [],
                }

        # If still no members found, add current logged in user
        if not team_members_map:
            u_name = current_user.full_name or "Sourabh Mishra"
            team_members_map["current_user"] = {
                "id": "current_user",
                "empId": "EMP-001",
                "name": u_name,
                "username": current_user.email.split("@")[0],
                "email": current_user.email,
                "role": current_user.role,
                "department": current_user.department or "Engineering",
                "avatar": f"https://api.dicebear.com/7.x/initials/svg?seed={u_name}",
                "status": "ACTIVE",
                "assignedTasksCount": 0,
                "todoCount": 0,
                "inProgressCount": 0,
                "inReviewCount": 0,
                "completedCount": 0,
                "overdueCount": 0,
                "tasks": [],
            }

        # 3. Correlate cards to team members
        now_utc = datetime.now(timezone.utc)
        unassigned_cards: List[Dict[str, Any]] = []

        for c in cards:
            c_name = c.get("name", "")
            c_desc = c.get("desc", "")
            c_due = c.get("due")
            c_list = list_map.get(c.get("idList"), "To Do")
            c_list_lower = c_list.lower()
            c_url = c.get("url") or c.get("shortUrl")
            c_members = c.get("idMembers", [])

            is_done = "done" in c_list_lower or "completed" in c_list_lower
            is_review = "review" in c_list_lower or "testing" in c_list_lower or "qa" in c_list_lower
            is_progress = "doing" in c_list_lower or "progress" in c_list_lower or "in-progress" in c_list_lower
            is_todo = not (is_done or is_review or is_progress)

            is_overdue = False
            if c_due and not is_done:
                try:
                    due_dt = datetime.fromisoformat(c_due.replace("Z", "+00:00"))
                    if due_dt < now_utc:
                        is_overdue = True
                except Exception:
                    pass

            formatted_task = {
                "id": c.get("id"),
                "title": c_name,
                "description": c_desc,
                "status": "DONE" if is_done else ("IN_REVIEW" if is_review else ("IN_PROGRESS" if is_progress else "TODO")),
                "list_name": c_list,
                "due_date": c_due,
                "is_overdue": is_overdue,
                "url": c_url,
            }

            matched_any = False
            # Check Trello member ID match (either directly or via trello_id)
            for m_id, member_data in team_members_map.items():
                if m_id in c_members or member_data.get("trello_id") in c_members:
                    member_data["assignedTasksCount"] += 1
                    if is_done:
                        member_data["completedCount"] += 1
                    elif is_review:
                        member_data["inReviewCount"] += 1
                    elif is_progress:
                        member_data["inProgressCount"] += 1
                    else:
                        member_data["todoCount"] += 1
                    if is_overdue:
                        member_data["overdueCount"] += 1
                    member_data["tasks"].append(formatted_task)
                    matched_any = True

            # If not assigned by Trello idMembers, check explicit name mention in card title or desc
            if not matched_any:
                for m_id, member_data in team_members_map.items():
                    m_name = member_data["name"].strip()
                    # Skip generic system accounts from fuzzy name matching
                    if member_data.get("role") == "ADMIN" and "admin" in m_name.lower():
                        continue
                    m_lower = m_name.lower()
                    first_name = m_lower.split()[0]
                    pattern = re.compile(
                        r"\b(?:assigned\s+to|assignee\s*[:=]|member\s*[:=]|for)\s+" + re.escape(first_name) + r"\b|"
                        + r"\b" + re.escape(m_lower) + r"\b",
                        re.IGNORECASE,
                    )
                    if pattern.search(c_name) or pattern.search(c_desc):
                        member_data["assignedTasksCount"] += 1
                        if is_done:
                            member_data["completedCount"] += 1
                        elif is_review:
                            member_data["inReviewCount"] += 1
                        elif is_progress:
                            member_data["inProgressCount"] += 1
                        else:
                            member_data["todoCount"] += 1
                        if is_overdue:
                            member_data["overdueCount"] += 1
                        member_data["tasks"].append(formatted_task)
                        matched_any = True
                        break

            if not matched_any:
                unassigned_cards.append(formatted_task)

        members_list = list(team_members_map.values())
        return {
            "status": "SUCCESS",
            "total_members": len(members_list),
            "members": members_list,
            "unassigned_count": len(unassigned_cards),
            "unassigned_tasks": unassigned_cards,
        }
    except Exception as e:
        logger.error(f"Failed to calculate team workload: {e}")
        return {
            "status": "ERROR",
            "total_members": 0,
            "members": [],
            "error": str(e),
        }


@router.post(
    "/reminders/check",
    status_code=status.HTTP_200_OK,
    summary="Trigger 3-stage deadline reminder checks for assigned members",
    description="Evaluates pending tasks for 1 day, 4 hours, and 1 hour deadlines, issuing email and in-app alerts.",
)
async def trigger_deadline_reminders(
    board_id: Optional[str] = Query(None, description="Optional target Trello board ID"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    from app.services.reminder_service import TaskReminderService
    from app.services.one_hour_reminder_service import OneHourReminderService

    service = TaskReminderService()
    reminders = await service.scan_and_generate_reminders(db, current_user=current_user, board_id=board_id)

    one_hr_res = await OneHourReminderService.process_due_reminders(db)
    overdue_res = await OneHourReminderService.process_overdue_followups(db)

    return {
        "status": "SUCCESS",
        "reminders_dispatched": len(reminders),
        "reminders": reminders,
        "one_hour_reminders": one_hr_res,
        "overdue_followups": overdue_res,
    }

