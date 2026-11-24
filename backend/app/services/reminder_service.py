import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.logging import logger
from app.schemas.user import UserResponse
from app.services.email_service import EmailService


class TaskReminderService:
    """
    3-Stage Automated Deadline Reminder Engine for Assigned Task Members.
    1st Reminder: 1 Day (24h) before due date (4h < T <= 24h)
    2nd Reminder: 4 Hours before due date (1h < T <= 4h)
    3rd Reminder: 1 Hour before due date (0 < T <= 1h)
    Delivers persistent in-app notifications and SMTP email alerts.
    """

    def __init__(self, email_service: Optional[EmailService] = None):
        self.email_service = email_service or EmailService()

    @staticmethod
    def _parse_due_date(due_val: Any) -> Optional[datetime]:
        if not due_val:
            return None
        if isinstance(due_val, datetime):
            return due_val if due_val.tzinfo else due_val.replace(tzinfo=timezone.utc)
        s = str(due_val).strip()
        if not s:
            return None
        clean_s = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean_s)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            except Exception:
                continue
        return None

    @classmethod
    def determine_reminder_stage(cls, due_dt: datetime, now_utc: datetime) -> Optional[Dict[str, Any]]:
        """
        Calculates remaining seconds and determines which of the 3 deadline reminder stages applies:
        - 1_DAY: 4 hours < remaining <= 24 hours
        - 4_HOURS: 1 hour < remaining <= 4 hours
        - 1_HOUR: 0 < remaining <= 1 hour
        """
        remaining_seconds = (due_dt - now_utc).total_seconds()
        if remaining_seconds <= 0:
            return None

        hours_left = remaining_seconds / 3600.0

        if 4.0 < hours_left <= 24.0:
            return {
                "stage": "1_DAY",
                "label": "1 Day Left",
                "urgency": "MEDIUM",
                "hours_left": round(hours_left, 1),
                "title": "Task Ending Soon: 1 Day Left",
                "message_template": 'Reminder: Your assigned task "{title}" is due in approximately {time_str}.',
            }
        elif 1.0 < hours_left <= 4.0:
            return {
                "stage": "4_HOURS",
                "label": "4 Hours Left",
                "urgency": "HIGH",
                "hours_left": round(hours_left, 1),
                "title": "Urgent Reminder: 4 Hours Left",
                "message_template": 'Urgent: Your assigned task "{title}" is due in less than {time_str}!',
            }
        elif 0 < hours_left <= 1.0:
            mins_left = max(1, int(remaining_seconds / 60.0))
            return {
                "stage": "1_HOUR",
                "label": "1 Hour Left",
                "urgency": "URGENT",
                "hours_left": round(hours_left, 2),
                "title": "Final Notice: 1 Hour Left",
                "message_template": 'Final Notice: Your assigned task "{title}" is due in {mins} minutes!',
                "mins_left": mins_left,
            }
        return None

    async def scan_and_generate_reminders(
        self,
        db: AsyncIOMotorDatabase,
        current_user: Optional[UserResponse] = None,
        board_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Scans active cards with due dates across configured boards.
        Identifies assigned team members and issues deadline alerts across the 3 stages.
        Guarantees that each stage is dispatched exactly once per assigned member.
        """
        now_utc = datetime.now(timezone.utc)
        reminders_generated: List[Dict[str, Any]] = []

        if not (settings.TRELLO_API_KEY and settings.TRELLO_TOKEN):
            return reminders_generated

        try:
            from app.mcp_server import trello_tools
            from app.services.board_service import get_active_board_id

            target_board_ids: List[str] = []
            if board_id:
                target_board_ids.append(await get_active_board_id(db, board_id))
            else:
                # Scan all configured boards in database
                b_cursor = db["boards"].find({})
                async for b_doc in b_cursor:
                    bid = str(b_doc.get("board_id") or b_doc.get("id") or "").strip()
                    if bid and bid not in target_board_ids:
                        target_board_ids.append(bid)
                if not target_board_ids:
                    target_board_ids.append(await get_active_board_id(db, None))

            # Build member profile lookup
            user_docs = await db["users"].find().to_list(100)
            user_lookup = {str(u["_id"]): u for u in user_docs}
            if current_user and str(current_user.id) not in user_lookup:
                user_lookup[str(current_user.id)] = current_user.model_dump()

            for target_board_id in target_board_ids:
                try:
                    cards_res = await trello_tools.trello_list_cards(board_id=target_board_id)
                    lists_res = await trello_tools.trello_list_lists(board_id=target_board_id)
                    cards = cards_res.get("cards", [])
                    lists = lists_res.get("lists", [])
                    list_map = {l["id"]: l["name"] for l in lists}
                except Exception as b_err:
                    logger.debug(f"Could not load cards for board {target_board_id}: {b_err}")
                    continue

                # Fetch board members for resolving Trello member IDs to actual names
                board_members: List[Dict[str, Any]] = []
                try:
                    trello_client = trello_tools.get_trello_client()
                    board_members = await trello_client.list_board_members(board_id=target_board_id)
                except Exception as bm_err:
                    logger.debug(f"Could not load board members for {target_board_id}: {bm_err}")

                for c in cards:
                    c_due_raw = c.get("due")
                    if not c_due_raw:
                        continue

                    c_list = list_map.get(c.get("idList"), "To Do").lower()
                    # Skip completed/archived cards
                    if "done" in c_list or "completed" in c_list or c.get("closed"):
                        continue

                    due_dt = self._parse_due_date(c_due_raw)
                    if not due_dt:
                        continue

                    stage_info = self.determine_reminder_stage(due_dt, now_utc)
                    if not stage_info:
                        continue

                    card_id = str(c.get("id"))
                    card_title = c.get("name") or "Task"
                    card_desc = c.get("desc") or ""
                    card_url = c.get("url") or c.get("shortUrl") or f"https://trello.com/c/{card_id}"
                    c_members = [str(m) for m in c.get("idMembers", [])]

                    # Identify which platform users are assigned to this card
                    assigned_users: List[Dict[str, Any]] = []

                    # 1. Primary lookup: Check linked local task_assignments document
                    ass_doc = await db["task_assignments"].find_one({"trello_card_id": card_id})
                    if ass_doc and ass_doc.get("employee_email"):
                        assigned_users.append({
                            "user_id": str(ass_doc.get("employee_id") or "unassigned"),
                            "email": ass_doc.get("employee_email"),
                            "name": ass_doc.get("employee_name") or "Assigned Member",
                        })

                    # 2. Secondary lookup: Match Trello members from board_members
                    if not assigned_users and c_members and board_members:
                        for bm in board_members:
                            bm_id = str(bm.get("id", ""))
                            if bm_id in c_members:
                                bm_name = (bm.get("fullName") or bm.get("username") or "").strip()
                                # Try matching Mongo user by full name
                                matched_u = None
                                for uid, udata in user_lookup.items():
                                    uname = (udata.get("full_name") or udata.get("name") or "").strip()
                                    if uname and uname.lower() == bm_name.lower():
                                        matched_u = (uid, udata)
                                        break
                                if matched_u:
                                    assigned_users.append({
                                        "user_id": matched_u[0],
                                        "email": matched_u[1].get("email"),
                                        "name": matched_u[1].get("full_name") or bm_name,
                                    })
                                else:
                                    assigned_users.append({
                                        "user_id": bm_id,
                                        "email": None,
                                        "name": bm_name,
                                    })

                    # 3. Tertiary lookup: Match mentions or member IDs against registered users
                    if not assigned_users:
                        for uid, udata in user_lookup.items():
                            u_email = (udata.get("email") or "").lower()
                            u_name = (udata.get("full_name") or udata.get("name") or "").strip()
                            first_name = u_name.split()[0].lower() if u_name else ""

                            is_assigned = False
                            # Check trello member ID match
                            if c_members and any(m in c_members for m in [uid, udata.get("trello_member_id")]):
                                is_assigned = True
                            # Check name or email mentioned in card
                            elif u_name and (u_name.lower() in card_title.lower() or u_name.lower() in card_desc.lower()):
                                is_assigned = True
                            elif first_name and len(first_name) > 2 and re.search(r"\b" + re.escape(first_name) + r"\b", card_title + " " + card_desc, re.IGNORECASE):
                                is_assigned = True

                            if is_assigned:
                                assigned_users.append({
                                    "user_id": uid,
                                    "email": udata.get("email"),
                                    "name": u_name or "Team Member",
                                })

                    # Filter out System/Administrator if real employees are present
                    real_assignees = [
                        a for a in assigned_users
                        if not any(k in (a.get("name") or "").lower() for k in ("system administrator", "system admin"))
                    ]
                    if real_assignees:
                        assigned_users = real_assignees

                    # 4. Fallback only if no users could be identified
                    if not assigned_users:
                        if current_user and not any(k in (current_user.full_name or "").lower() for k in ("system administrator", "system admin")):
                            assigned_users.append({
                                "user_id": str(current_user.id),
                                "email": current_user.email,
                                "name": current_user.full_name or "Operator",
                            })
                        else:
                            admin_doc = await db["users"].find_one({"role": "ADMIN", "is_active": True})
                            if admin_doc and admin_doc.get("email"):
                                assigned_users.append({
                                    "user_id": str(admin_doc["_id"]),
                                    "email": admin_doc.get("email"),
                                    "name": admin_doc.get("full_name") or "Administrator",
                                })

                    # Deduplicate assigned users by email / user_id
                    unique_assignees: List[Dict[str, Any]] = []
                    seen_keys = set()
                    for a in assigned_users:
                        key = a.get("email") or a.get("user_id")
                        if key and key not in seen_keys:
                            seen_keys.add(key)
                            unique_assignees.append(a)
                    assigned_users = unique_assignees or assigned_users

                    stage = stage_info["stage"]

                    # Convert due datetime to IST for human presentation
                    from datetime import timedelta
                    ist_tz = timezone(timedelta(hours=5, minutes=30), name="IST")
                    due_ist = due_dt.astimezone(ist_tz) if due_dt.tzinfo else due_dt.replace(tzinfo=timezone.utc).astimezone(ist_tz)
                    due_formatted_ist = due_ist.strftime('%d %b %Y, %I:%M %p IST')

                    for assignee in assigned_users:
                        u_id = assignee["user_id"]

                        # Check deduplication record in MongoDB
                        already_sent = await db["task_deadline_reminders"].find_one({
                            "card_id": card_id,
                            "user_id": u_id,
                            "stage": stage,
                        })
                        if already_sent:
                            continue

                        # Format human message
                        if stage == "1_HOUR":
                            msg_text = stage_info["message_template"].format(
                                title=card_title, mins=stage_info.get("mins_left", 30)
                            )
                        else:
                            hours_str = f"{stage_info['hours_left']} hours"
                            msg_text = stage_info["message_template"].format(title=card_title, time_str=hours_str)

                        reminder_record = {
                            "card_id": card_id,
                            "card_name": card_title,
                            "card_url": card_url,
                            "user_id": u_id,
                            "user_email": assignee.get("email"),
                            "stage": stage,
                            "stage_label": stage_info["label"],
                            "urgency": stage_info["urgency"],
                            "title": stage_info["title"],
                            "message": msg_text,
                            "due_date": due_dt.isoformat(),
                            "due_date_ist": due_formatted_ist,
                            "created_at": now_utc,
                            "email_sent": False,
                            "comment_posted": False,
                        }

                        # Send Email Alert for 1_DAY, 4_HOURS, and 1_HOUR
                        if self.email_service.is_configured() and assignee.get("email"):
                            try:
                                if stage == "1_DAY":
                                    subject = f"Deadline Reminder: '{card_title}' is due in 24 hours"
                                elif stage == "4_HOURS":
                                    subject = f"Urgent Reminder: '{card_title}' is due in 4 hours"
                                else:
                                    subject = f"Final Notice: '{card_title}' is due in 1 hour"

                                text_body = f"{msg_text}\n\nDue Date: {due_formatted_ist}\nView in Trello: {card_url}"
                                html_body = f"""
                                <div style="font-family: Arial, sans-serif; padding: 20px; color: #1e293b;">
                                    <h2 style="color: #0f172a; margin-bottom: 8px;">{stage_info['title']}</h2>
                                    <p style="font-size: 14px; line-height: 1.5; color: #334155;">{msg_text}</p>
                                    <div style="margin: 16px 0; padding: 12px; background: #f8fafc; border-left: 4px solid #10b981; border-radius: 4px;">
                                        <strong>Task:</strong> {card_title}<br/>
                                        <strong>Due Date:</strong> {due_formatted_ist}
                                    </div>
                                    <a href="{card_url}" style="display: inline-block; padding: 10px 18px; background: #10b981; color: #ffffff; text-decoration: none; border-radius: 8px; font-weight: bold;">View Task in Trello</a>
                                </div>
                                """
                                await self.email_service.send_email(
                                    to_email=assignee["email"],
                                    subject=subject,
                                    html_content=html_body,
                                    text_content=text_body,
                                )
                                reminder_record["email_sent"] = True
                                logger.info(f"Dispatched deadline reminder email ({stage}) to {assignee['email']}")
                            except Exception as em_err:
                                logger.warning(f"Could not send reminder email to {assignee.get('email')}: {em_err}")

                        await db["task_deadline_reminders"].insert_one(reminder_record)
                        reminders_generated.append(reminder_record)

                    # STRICT COMMENT RULE:
                    # 1_DAY: ONLY EMAIL. NEVER POST COMMENT.
                    # 4_HOURS: ONLY EMAIL. NEVER POST COMMENT ("4 hours bachte hai tho sirf mail hi bhejna hai ok comment nahi bhejna hai").
                    # 1_HOUR: BOTH EMAIL AND COMMENT ("sirf 1 hour bachega tho mail or comment dono jana chaiye ok").
                    if stage == "1_HOUR":
                        try:
                            # Card-level deduplication: Post at most ONE comment per card for 1_HOUR
                            check1 = db["task_deadline_reminders"].find_one({
                                "card_id": card_id,
                                "stage": "1_HOUR",
                                "comment_posted": True,
                            })
                            already_commented = (await check1) if hasattr(check1, "__await__") else None

                            if not already_commented:
                                check2 = db["reminder_logs"].find_one({
                                    "trello_card_id": card_id,
                                    "trello_comment_sent": True,
                                })
                                already_commented = (await check2) if hasattr(check2, "__await__") else None

                            if not already_commented:
                                # Determine polite recipient name (exclude System/Administrator)
                                target_name = "there"
                                if assigned_users:
                                    raw_n = assigned_users[0].get("name", "")
                                    f_name = raw_n.split()[0] if raw_n else ""
                                    if f_name and not any(k in f_name.lower() for k in ("system", "admin")):
                                        target_name = f_name

                                # Image 3 exact format:
                                # "Hi Sourabh, your task 'Hr-atlas' is approaching its deadline in one hour. Please provide a quick status update and let us know if anything is needed to wrap it up on schedule."
                                comment_text = (
                                    f"Hi {target_name}, your task '{card_title}' is approaching its deadline in one hour. "
                                    f"Please provide a quick status update and let us know if anything is needed to wrap it up on schedule."
                                )
                                await trello_tools.trello_add_comment(card_id=card_id, text=comment_text)
                                logger.info(f"Posted 1_HOUR reminder comment to Trello card {card_id}")

                                # Mark comment_posted = True in database across both tracking collections
                                upd1 = db["task_deadline_reminders"].update_many(
                                    {"card_id": card_id, "stage": "1_HOUR"},
                                    {"$set": {"comment_posted": True}}
                                )
                                if hasattr(upd1, "__await__"):
                                    await upd1

                                upd2 = db["reminder_logs"].update_many(
                                    {"trello_card_id": card_id},
                                    {"$set": {"trello_comment_sent": True}}
                                )
                                if hasattr(upd2, "__await__"):
                                    await upd2
                        except Exception as c_err:
                            logger.warning(f"Could not post reminder comment to Trello card {card_id}: {c_err}")

        except Exception as e:
            logger.error(f"Error during scan_and_generate_reminders: {e}")

        return reminders_generated

    async def get_user_reminders_for_notifications(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        limit: int = 15,
    ) -> List[Dict[str, Any]]:
        """Fetches stored reminders for user and formats them for the notification tray."""
        cursor = db["task_deadline_reminders"].find({"user_id": user_id}).sort("created_at", -1).limit(limit)
        items = []
        async for doc in cursor:
            card_id = doc.get("card_id")
            stage = doc.get("stage")
            created_dt = doc.get("created_at")
            created_str = created_dt.isoformat() if hasattr(created_dt, "isoformat") else str(created_dt or "")
            items.append({
                "id": f"reminder_{card_id}_{stage}",
                "type": "DEADLINE_REMINDER",
                "title": doc.get("title") or f"Task Ending Soon: {doc.get('stage_label')}",
                "message": doc.get("message") or f"Reminder: Task '{doc.get('card_name')}' is ending soon.",
                "created_at": created_str,
                "card_url": doc.get("card_url"),
                "target_tab": "tasks",
                "priority": doc.get("urgency") or "HIGH",
                "stage": stage,
                "stage_label": doc.get("stage_label"),
            })
        return items

