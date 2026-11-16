import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.dependencies import get_current_user
from app.core.logging import logger
from app.database.mongodb import get_database
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
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    try:
        cards_res = await trello_tools.trello_list_cards()
        lists_res = await trello_tools.trello_list_lists()
        members_res = await trello_tools.trello_list_board_members()

        cards = cards_res.get("cards", [])
        lists = lists_res.get("lists", [])
        trello_members = members_res.get("members", [])
        list_map = {l["id"]: l["name"] for l in lists}

        # Build list of member profiles
        team_members_map: Dict[str, Dict[str, Any]] = {}

        # 1. Add Trello board members
        for tm in trello_members:
            m_id = str(tm.get("id"))
            m_name = tm.get("fullName") or tm.get("username") or "Board Member"
            username = tm.get("username") or m_name.lower().replace(" ", "_")
            team_members_map[m_id] = {
                "id": m_id,
                "empId": f"TRL-{m_id[:6].upper()}",
                "name": m_name,
                "username": username,
                "email": f"{username}@trello.board",
                "role": "Trello Collaborator",
                "department": "Engineering & Operations",
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

        # 2. Add registered users from MongoDB if not already present
        if db is not None:
            try:
                async for u in db["users"].find():
                    u_name = u.get("full_name") or u.get("email", "User").split("@")[0]
                    # Check if already covered by trello name
                    already_exists = any(
                        m["name"].lower() == u_name.lower() or u_name.lower() in m["name"].lower()
                        for m in team_members_map.values()
                    )
                    if not already_exists:
                        u_id = str(u.get("_id"))
                        team_members_map[u_id] = {
                            "id": u_id,
                            "empId": f"USR-{u_id[:6].upper()}",
                            "name": u_name,
                            "username": u.get("email", "").split("@")[0],
                            "email": u.get("email", ""),
                            "role": u.get("role", "EMPLOYEE"),
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
            # Check Trello member ID match
            for m_id, member_data in team_members_map.items():
                if m_id in c_members:
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

