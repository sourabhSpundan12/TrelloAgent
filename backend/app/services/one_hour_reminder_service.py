import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging import logger
from app.integrations.trello.client import TrelloClient
from app.services.email_service import EmailService
from app.ai.provider_factory import LLMProviderFactory
from app.models.task_assignment import PerformanceLevel, TaskAssignmentStatus


class OneHourReminderService:
    """
    Module 5: Automatic One-Hour Deadline Reminder Service.
    Monitors incomplete tasks approaching their 1-hour deadline window,
    sends SMTP email notifications, and posts AI-generated, performance-level
    tailored comments to Trello cards.
    """

    @classmethod
    def get_fallback_comment(cls, task_title: str, first_name: str, level: str) -> str:
        lvl = (level or "").upper()
        if lvl == PerformanceLevel.LOW.value:
            return (
                f"Hi {first_name}, your task '{task_title}' is due in one hour. "
                f"Are you facing any difficulties or blockers? Please share an update so we can help you complete it on time."
            )
        elif lvl == PerformanceLevel.HIGH.value:
            return (
                f"Hi {first_name}, your task '{task_title}' is due in one hour. "
                f"Please confirm completion before the deadline, or immediately communicate any blockers requiring escalation."
            )
        else:  # MEDIUM or default
            return (
                f"Hi {first_name}, your task '{task_title}' is approaching its deadline in one hour. "
                f"Please provide a quick status update and let us know if anything is needed to wrap it up on schedule."
            )

    @classmethod
    async def generate_ai_comment(
        cls,
        task_title: str,
        employee_name: str,
        performance_level: str,
        time_remaining_str: str = "one hour",
    ) -> str:
        first_name = (employee_name or "there").split()[0]
        lvl = (performance_level or "MEDIUM").upper()

        prompt = (
            f"You are an AI assistant generating a professional, concise deadline reminder comment for a Trello task card.\n"
            f"Task Title: {task_title}\n"
            f"Employee First Name: {first_name}\n"
            f"Employee Performance Level: {lvl}\n"
            f"Time Remaining: {time_remaining_str}\n\n"
            f"Communication rules based on Employee Level:\n"
            f"- LOW: Be supportive, ask about blockers, offer help, encourage progress.\n"
            f"- MEDIUM: Be balanced, emphasize the approaching deadline, request a timely status update.\n"
            f"- HIGH: Be firm but respectful, emphasize deadline accountability, ask for immediate communication if there is a blocker.\n\n"
            f"Strict constraints:\n"
            f"1. Never insult, threaten, or embarrass the employee.\n"
            f"2. Never expose internal performance levels or numerical scores.\n"
            f"3. Never invent task progress or employee problems.\n"
            f"4. Keep the comment between 15 and 35 words.\n"
            f"5. Output ONLY the comment text without any surrounding quotes or markdown markup."
        )

        try:
            provider = LLMProviderFactory.create_provider()
            if provider.is_configured():
                generated = await provider.generate_text(prompt)
                cleaned = generated.strip().strip('"').strip("'")
                if len(cleaned) > 10:
                    return cleaned
        except Exception as e:
            logger.debug(f"LLM comment generation failed ({e}); falling back to deterministic template.")

        return cls.get_fallback_comment(task_title, first_name, lvl)

    @classmethod
    async def process_due_reminders(
        cls,
        db: AsyncIOMotorDatabase,
        email_service: Optional[EmailService] = None,
        trello_client: Optional[TrelloClient] = None,
    ) -> Dict[str, Any]:
        """
        Scans all active, incomplete tasks for 1-hour deadline window and dispatches reminders.
        """
        now = datetime.now(timezone.utc)
        # Find active tasks with a due date
        query = {
            "status": {"$in": [TaskAssignmentStatus.ASSIGNED.value, TaskAssignmentStatus.IN_PROGRESS.value]},
            "due_date": {"$ne": None},
        }

        cursor = db["task_assignments"].find(query)
        tasks = await cursor.to_list(length=500)

        mailer = email_service or EmailService()
        client = trello_client or TrelloClient()

        processed_count = 0
        email_success_count = 0
        trello_success_count = 0

        for task in tasks:
            assignment_id = str(task.get("_id") or task.get("id"))
            due_date = task.get("due_date")
            if not due_date:
                continue

            due_dt = due_date if due_date.tzinfo else due_date.replace(tzinfo=timezone.utc)
            remaining_seconds = (due_dt - now).total_seconds()
            remaining_minutes = remaining_seconds / 60.0

            # Module 5 Trigger Condition:
            # reminderTime = dueDate - 1 hour -> Trigger when remaining is <= 60 minutes and > 0
            if not (0 < remaining_minutes <= 60):
                continue

            due_date_version = task.get("due_date_version", 1)
            trello_card_id = task.get("trello_card_id")
            employee_id = str(task.get("employee_id"))
            employee_name = task.get("employee_name") or "Employee"
            employee_email = task.get("employee_email")
            task_title = task.get("task_title", "Assigned Task")

            # Check reminder_logs for this assignment_id and due_date_version
            log_entry = await db["reminder_logs"].find_one({
                "assignment_id": assignment_id,
                "due_date_version": due_date_version,
            })

            if log_entry and log_entry.get("email_sent") and log_entry.get("trello_comment_sent"):
                # Already completely fulfilled for this deadline version
                continue

            # Fetch employee performance level
            perf_doc = await db["employee_performance"].find_one({"employee_id": employee_id})
            level = perf_doc.get("level", PerformanceLevel.MEDIUM.value) if perf_doc else PerformanceLevel.MEDIUM.value

            # Resolve email address if missing
            if not employee_email:
                try:
                    from bson import ObjectId
                    u = await db["users"].find_one({"_id": ObjectId(employee_id)})
                    if u and u.get("email"):
                        employee_email = u.get("email")
                        employee_name = u.get("full_name") or employee_name
                except Exception:
                    pass

            email_sent = log_entry.get("email_sent", False) if log_entry else False
            email_err = None
            trello_sent = log_entry.get("trello_comment_sent", False) if log_entry else False
            trello_err = None
            generated_comment = log_entry.get("generated_comment") if log_entry else None

            # Action A: Send Email Reminder via SMTP
            if not email_sent and employee_email:
                first_name = employee_name.split()[0]
                subject = f"Task Deadline Reminder – {task_title}"
                text_content = (
                    f"Hi {first_name},\n\n"
                    f"Your task '{task_title}' is due in one hour.\n\n"
                    f"Please review the task and complete it within the deadline. "
                    f"If you are facing any difficulties, please inform your Project Manager.\n\n"
                    f"Regards,\n"
                    f"Project Management Team"
                )
                html_content = f"""<!DOCTYPE html>
<html>
<body style="font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 24px;">
  <div style="max-width: 500px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 24px; border: 1px solid #334155;">
    <h2 style="color: #38bdf8; margin-top: 0;">Task Deadline Reminder</h2>
    <p>Hi <strong>{first_name}</strong>,</p>
    <p>Your task <strong>{task_title}</strong> is due in <strong>one hour</strong>.</p>
    <p style="color: #cbd5e1; line-height: 1.5;">Please review the task and complete it within the deadline. If you are facing any difficulties, please inform your Project Manager.</p>
    <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #334155; font-size: 13px; color: #94a3b8;">
      Regards,<br><strong>Project Management Team</strong>
    </div>
  </div>
</body>
</html>"""
                try:
                    await mailer.send_email(
                        to_email=employee_email,
                        subject=subject,
                        html_content=html_content,
                        text_content=text_content
                    )
                    email_sent = True
                    email_success_count += 1
                except Exception as err:
                    logger.warning(f"Failed to dispatch 1-hour reminder email to {employee_email}: {err}")
                    email_err = str(err)

            # Action B: AI-Generated Trello Comment
            if not trello_sent and trello_card_id:
                if not generated_comment:
                    generated_comment = await cls.generate_ai_comment(
                        task_title=task_title,
                        employee_name=employee_name,
                        performance_level=level,
                    )
                try:
                    await client.add_comment(card_id=trello_card_id, text=generated_comment)
                    trello_sent = True
                    trello_success_count += 1
                except Exception as err:
                    logger.warning(f"Failed to post AI reminder comment to Trello card {trello_card_id}: {err}")
                    trello_err = str(err)

            # Record or update in reminder_logs
            attempt_count = (log_entry.get("attempt_count", 0) + 1) if log_entry else 1
            log_doc = {
                "assignment_id": assignment_id,
                "trello_card_id": trello_card_id,
                "employee_id": employee_id,
                "due_date": due_dt,
                "due_date_version": due_date_version,
                "email_sent": email_sent,
                "email_sent_at": now if email_sent else None,
                "email_error": email_err,
                "trello_comment_sent": trello_sent,
                "trello_comment_sent_at": now if trello_sent else None,
                "trello_comment_error": trello_err,
                "generated_comment": generated_comment,
                "attempt_count": attempt_count,
                "created_at": log_entry.get("created_at") if log_entry else now,
            }

            await db["reminder_logs"].update_one(
                {"assignment_id": assignment_id, "due_date_version": due_date_version},
                {"$set": log_doc},
                upsert=True
            )
            processed_count += 1

        return {
            "processed_tasks": processed_count,
            "emails_sent": email_success_count,
            "trello_comments_posted": trello_success_count,
        }

