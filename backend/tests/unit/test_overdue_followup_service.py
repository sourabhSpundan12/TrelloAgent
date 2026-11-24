import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from mongomock_motor import AsyncMongoMockClient

from app.services.one_hour_reminder_service import OneHourReminderService
from app.models.task_assignment import TaskAssignmentStatus


@pytest.fixture
def mock_db():
    client = AsyncMongoMockClient()
    return client["test_database"]


@pytest.mark.asyncio
async def test_generate_pm_reply_fallback():
    reply = await OneHourReminderService.generate_pm_reply_to_employee(
        task_title="Authentication Module",
        employee_name="Rohit Sharma",
        employee_reply="Facing issue with OAuth redirect, will fix by tonight.",
        previous_reminder="Reminder: task due in 1 hour.",
    )
    assert "Rohit" in reply
    assert "Authentication Module" in reply
    assert "update" in reply.lower() or "eta" in reply.lower()


@pytest.mark.asyncio
async def test_generate_pm_overdue_unanswered_fallback():
    comment = await OneHourReminderService.generate_pm_overdue_unanswered_comment(
        task_title="Database Migration",
        employee_name="Pooja Patel",
        hours_overdue=1,
    )
    assert "Pooja" in comment
    assert "Database Migration" in comment
    assert "overdue" in comment.lower()


@pytest.mark.asyncio
async def test_overdue_followup_when_employee_replied(mock_db):
    now = datetime.now(timezone.utc)
    due_date = now - timedelta(hours=1, minutes=15)  # 1 hour 15 minutes overdue
    reminder_sent_at = now - timedelta(hours=2, minutes=15)  # Sent 1 hour before due date

    # 1. Seed task assignment
    assign_doc = {
        "task_title": "Fix Payment Gateway",
        "trello_card_id": "card_pay_123",
        "employee_id": "emp_001",
        "employee_name": "Aman Verma",
        "employee_email": "aman@company.com",
        "status": TaskAssignmentStatus.IN_PROGRESS.value,
        "due_date": due_date,
        "due_date_version": 1,
    }
    await mock_db["task_assignments"].insert_one(assign_doc)

    # 2. Seed initial reminder_logs entry (1-hour reminder was sent)
    await mock_db["reminder_logs"].insert_one({
        "assignment_id": str(assign_doc["_id"]),
        "trello_card_id": "card_pay_123",
        "employee_id": "emp_001",
        "due_date": due_date,
        "due_date_version": 1,
        "email_sent": True,
        "trello_comment_sent": True,
        "trello_comment_sent_at": reminder_sent_at,
        "generated_comment": "Hi Aman, your task is due in one hour.",
    })

    # 3. Setup mock mailer & Trello client with employee comment
    mock_mailer = MagicMock()
    mock_mailer.send_email = AsyncMock(return_value=None)

    mock_trello = MagicMock()
    mock_trello.add_comment = AsyncMock(return_value={"id": "comm_pm_1"})

    # Employee replied 30 mins after reminder
    employee_comment_time = (reminder_sent_at + timedelta(minutes=30)).isoformat()
    mock_trello.get_card_comments = AsyncMock(return_value=[
        {
            "id": "c_act_emp",
            "date": employee_comment_time,
            "data": {
                "text": "Stuck in 3D secure validation, need 1 extra hour to wrap it up.",
            },
            "memberCreator": {"fullName": "Aman Verma", "username": "amanv"},
        },
        {
            "id": "c_act_bot",
            "date": reminder_sent_at.isoformat(),
            "data": {
                "text": "Hi Aman, your task is due in one hour.",
            },
            "memberCreator": {"fullName": "PM Hooks Bot", "username": "pmbot"},
        }
    ])

    # First run: should detect employee reply, generate PM reply, post comment & email
    res1 = await OneHourReminderService.process_overdue_followups(
        db=mock_db,
        email_service=mock_mailer,
        trello_client=mock_trello,
    )

    assert res1["checked_tasks"] == 1
    assert res1["replied_followups"] == 1
    assert res1["unanswered_followups"] == 0
    assert res1["comments_posted"] == 1
    assert res1["emails_sent"] == 1

    # Verify Trello add_comment was called
    mock_trello.add_comment.assert_called_once()
    posted_text = mock_trello.add_comment.call_args[1]["text"]
    assert "Aman" in posted_text

    # Verify email was dispatched
    mock_mailer.send_email.assert_called_once()
    assert mock_mailer.send_email.call_args[1]["to_email"] == "aman@company.com"

    # Verify reminder_logs document state
    log = await mock_db["reminder_logs"].find_one({"assignment_id": str(assign_doc["_id"])})
    assert log["overdue_1hr_checked"] is True
    assert log["employee_replied"] is True
    assert "3D secure validation" in log["employee_reply_text"]
    assert log["pm_comment_sent"] is True

    # Second run immediately after: must be idempotent and skip
    mock_trello.add_comment.reset_mock()
    mock_mailer.send_email.reset_mock()

    res2 = await OneHourReminderService.process_overdue_followups(
        db=mock_db,
        email_service=mock_mailer,
        trello_client=mock_trello,
    )
    assert res2["checked_tasks"] == 0
    assert res2["comments_posted"] == 0
    mock_trello.add_comment.assert_not_called()


@pytest.mark.asyncio
async def test_overdue_followup_when_employee_did_not_reply(mock_db):
    now = datetime.now(timezone.utc)
    due_date = now - timedelta(hours=1, minutes=10)  # 1 hour 10 mins overdue
    reminder_sent_at = now - timedelta(hours=2, minutes=10)

    # 1. Seed task assignment
    assign_doc = {
        "task_title": "Setup Docker Compose",
        "trello_card_id": "card_dock_456",
        "employee_id": "emp_002",
        "employee_name": "Karan Mehra",
        "employee_email": "karan@company.com",
        "status": TaskAssignmentStatus.ASSIGNED.value,
        "due_date": due_date,
        "due_date_version": 1,
    }
    await mock_db["task_assignments"].insert_one(assign_doc)

    # 2. Seed initial reminder_logs entry (no employee reply on card)
    await mock_db["reminder_logs"].insert_one({
        "assignment_id": str(assign_doc["_id"]),
        "trello_card_id": "card_dock_456",
        "due_date_version": 1,
        "trello_comment_sent_at": reminder_sent_at,
        "generated_comment": "Hi Karan, your task is due in one hour.",
    })

    # 3. Setup mock mailer & Trello client (only bot comment exists)
    mock_mailer = MagicMock()
    mock_mailer.send_email = AsyncMock(return_value=None)

    mock_trello = MagicMock()
    mock_trello.add_comment = AsyncMock(return_value={"id": "comm_pm_2"})
    mock_trello.get_card_comments = AsyncMock(return_value=[
        {
            "id": "c_act_bot_only",
            "date": reminder_sent_at.isoformat(),
            "data": {
                "text": "Hi Karan, your task is due in one hour.",
            },
        }
    ])

    res = await OneHourReminderService.process_overdue_followups(
        db=mock_db,
        email_service=mock_mailer,
        trello_client=mock_trello,
    )

    assert res["checked_tasks"] == 1
    assert res["replied_followups"] == 0
    assert res["unanswered_followups"] == 1
    assert res["comments_posted"] == 1
    assert res["emails_sent"] == 1

    # Verify posted comment notes lack of update / 1 hour overdue
    posted_text = mock_trello.add_comment.call_args[1]["text"]
    assert "Karan" in posted_text
    assert "overdue" in posted_text.lower()

    # Verify reminder_logs
    log = await mock_db["reminder_logs"].find_one({"assignment_id": str(assign_doc["_id"])})
    assert log["overdue_1hr_checked"] is True
    assert log["employee_replied"] is False
    assert log["pm_comment_sent"] is True


@pytest.mark.asyncio
async def test_overdue_followup_skips_when_less_than_1hr_overdue(mock_db):
    now = datetime.now(timezone.utc)
    due_date = now - timedelta(minutes=20)  # Only 20 minutes overdue (under 1 hour)

    assign_doc = {
        "task_title": "Write API Docs",
        "trello_card_id": "card_doc_789",
        "employee_id": "emp_003",
        "employee_name": "Sneha Roy",
        "status": TaskAssignmentStatus.IN_PROGRESS.value,
        "due_date": due_date,
        "due_date_version": 1,
    }
    await mock_db["task_assignments"].insert_one(assign_doc)

    mock_mailer = MagicMock()
    mock_trello = MagicMock()

    res = await OneHourReminderService.process_overdue_followups(
        db=mock_db,
        email_service=mock_mailer,
        trello_client=mock_trello,
    )

    # Must skip because 1 hour has not elapsed yet
    assert res["checked_tasks"] == 0
    mock_trello.add_comment.assert_not_called()

