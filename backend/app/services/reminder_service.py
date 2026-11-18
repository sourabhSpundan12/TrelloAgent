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

            target_board_id = await get_active_board_id(db, board_id)
            cards_res = await trello_tools.trello_list_cards(board_id=target_board_id)
            lists_res = await trello_tools.trello_list_lists(board_id=target_board_id)
            members_res = await trello_tools.trello_list_board_members(board_id=target_board_id)

            cards = cards_res.get("cards", [])
            lists = lists_res.get("lists", [])
            list_map = {l["id"]: l["name"] for l in lists}

            # Build member profile lookup
            user_docs = await db["users"].find().to_list(100)
            user_lookup = {str(u["_id"]): u for u in user_docs}
            if current_user and str(current_user.id) not in user_lookup:
                user_lookup[str(current_user.id)] = current_user.model_dump()

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

                # If no specific user matched, assign to current_user
                if not assigned_users and current_user:
                    assigned_users.append({
                        "user_id": str(current_user.id),
                        "email": current_user.email,
                        "name": current_user.full_name or "Operator",
                    })

                for assignee in assigned_users:
                    u_id = assignee["user_id"]
                    stage = stage_info["stage"]

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
                        "created_at": now_utc,
                    }

                    await db["task_deadline_reminders"].insert_one(reminder_record)
                    reminders_generated.append(reminder_record)

                    # Send Email Alert if configured
                    if self.email_service.is_configured() and assignee.get("email"):
                        try:
                            subject = f"[{stage_info['label']}] Deadline Reminder for '{card_title}'"
                            text_body = f"{msg_text}\n\nDue Date: {due_dt.strftime('%d %b %Y, %I:%M %p UTC')}\nView in Trello: {card_url}"
                            html_body = f"""
                            <div style="font-family: Arial, sans-serif; padding: 20px; color: #1e293b;">
                                <h2 style="color: #0f172a; margin-bottom: 8px;">{stage_info['title']}</h2>
                                <p style="font-size: 14px; line-height: 1.5; color: #334155;">{msg_text}</p>
                                <div style="margin: 16px 0; padding: 12px; background: #f8fafc; border-left: 4px solid #10b981; border-radius: 4px;">
                                    <strong>Task:</strong> {card_title}<br/>
                                    <strong>Due:</strong> {due_dt.strftime('%d %b %Y, %I:%M %p UTC')}
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
                            logger.info(f"Dispatched deadline reminder email ({stage}) to {assignee['email']}")
                        except Exception as em_err:
                            logger.warning(f"Could not send reminder email to {assignee.get('email')}: {em_err}")

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

