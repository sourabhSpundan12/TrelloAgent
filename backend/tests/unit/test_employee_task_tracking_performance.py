import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from fastapi import HTTPException

from app.models.task_assignment import (
    TaskAssignmentStatus,
    PerformanceLevel,
)
from app.services.task_assignment_service import TaskAssignmentService
from app.services.performance_service import PerformanceCalculationService
from app.services.one_hour_reminder_service import OneHourReminderService


# ---------------------------------------------------------------------------
# Test In-Memory MongoDB Fixture
# ---------------------------------------------------------------------------
class AsyncMockCollection:
    def __init__(self, name: str = "coll"):
        self.name = name
        self.docs = []

    async def insert_one(self, doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        self.docs.append(d)
        res = MagicMock()
        res.inserted_id = d["_id"]
        return res

    async def find_one(self, filter_query):
        for d in self.docs:
            matched = True
            for k, v in filter_query.items():
                if k == "_id":
                    if str(d.get("_id")) != str(v):
                        matched = False
                        break
                elif k == "$or":
                    or_matched = any(
                        all(str(d.get(ok)) == str(ov) for ok, ov in cond.items())
                        for cond in v
                    )
                    if not or_matched:
                        matched = False
                        break
                elif d.get(k) != v:
                    matched = False
                    break
            if matched:
                return dict(d)
        return None

    def find(self, filter_query=None):
        filtered = []
        filter_query = filter_query or {}
        for d in self.docs:
            matched = True
            for k, v in filter_query.items():
                if k == "employee_id":
                    if str(d.get("employee_id")) != str(v):
                        matched = False
                        break
                elif k == "status":
                    if isinstance(v, dict) and "$in" in v:
                        if d.get("status") not in v["$in"]:
                            matched = False
                            break
                    elif isinstance(v, dict) and "$ne" in v:
                        if d.get("status") == v["$ne"]:
                            matched = False
                            break
                    elif d.get("status") != v:
                        matched = False
                        break
                elif k == "assignment_id":
                    if isinstance(v, dict) and "$in" in v:
                        if str(d.get("assignment_id")) not in [str(x) for x in v["$in"]]:
                            matched = False
                            break
                    elif str(d.get("assignment_id")) != str(v):
                        matched = False
                        break
            if matched:
                filtered.append(dict(d))

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=filtered)
        return mock_cursor

    async def update_one(self, filter_query, update_spec, upsert=False):
        doc = await self.find_one(filter_query)
        if doc:
            for k, v in update_spec.get("$set", {}).items():
                doc[k] = v
            # update in docs list
            for i, d in enumerate(self.docs):
                if str(d.get("_id")) == str(doc.get("_id")) or (
                    filter_query.get("assignment_id")
                    and d.get("assignment_id") == filter_query.get("assignment_id")
                ):
                    self.docs[i].update(doc)
            res = MagicMock()
            res.modified_count = 1
            return res
        elif upsert:
            new_doc = dict(filter_query)
            for k, v in update_spec.get("$set", {}).items():
                new_doc[k] = v
            await self.insert_one(new_doc)
            res = MagicMock()
            res.upserted_id = new_doc.get("_id")
            return res
        return MagicMock(modified_count=0)


class MockDatabase:
    def __init__(self):
        self.collections = {
            "task_assignments": AsyncMockCollection("task_assignments"),
            "task_assignment_history": AsyncMockCollection("task_assignment_history"),
            "employee_performance": AsyncMockCollection("employee_performance"),
            "employee_level_history": AsyncMockCollection("employee_level_history"),
            "reminder_logs": AsyncMockCollection("reminder_logs"),
            "users": AsyncMockCollection("users"),
        }

    def __getitem__(self, name: str):
        if name not in self.collections:
            self.collections[name] = AsyncMockCollection(name)
        return self.collections[name]


# ---------------------------------------------------------------------------
# MODULE 1 & 2 TESTS: Task Assignment, Due Date Management & Duration Variance
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_task_assignment_lifecycle_and_time_variance():
    db = MockDatabase()
    pm_id = str(ObjectId())
    emp_id = str(ObjectId())
    board_id = "test_board_123"
    card_id = "trello_card_abc"

    now = datetime.now(timezone.utc)
    due_date = now + timedelta(hours=2)  # 120 minutes in future

    # 1. Create task assignment
    assignment = await TaskAssignmentService.create_assignment(
        db=db,
        employee_id=emp_id,
        project_manager_id=pm_id,
        board_id=board_id,
        trello_card_id=card_id,
        task_title="Build Authentication Flow",
        task_description="Implement secure login endpoint with JWT",
        due_date=due_date,
        board_name="Engineering Sprint",
    )
    assignment_id = assignment["id"]
    assert assignment["status"] == TaskAssignmentStatus.ASSIGNED.value
    assert assignment["employee_id"] == emp_id
    assert assignment["due_date_version"] == 1

    # Verify initial history log
    history_logs = db["task_assignment_history"].docs
    assert len(history_logs) == 1
    assert history_logs[0]["action"] == "assigned"

    # 2. Start Task (Employee clicks Start)
    started = await TaskAssignmentService.start_task(
        db=db,
        assignment_id=assignment_id,
        actor_id=emp_id,
        actor_role="EMPLOYEE",
    )
    assert started["status"] == TaskAssignmentStatus.IN_PROGRESS.value
    assert started["started_at"] is not None
    # estimatedDurationMinutes = dueDate - startedAt
    assert started["estimated_duration_minutes"] is not None
    assert 115 <= started["estimated_duration_minutes"] <= 125

    # 3. Duplicate start rejection (Prevent duplicate starts)
    with pytest.raises(HTTPException) as exc:
        await TaskAssignmentService.start_task(
            db=db,
            assignment_id=assignment_id,
            actor_id=emp_id,
            actor_role="EMPLOYEE",
        )
    assert exc.value.status_code == 400
    assert "already been started" in exc.value.detail

    # 4. Due date update (Employee updates deadline with reason)
    extended_due = now + timedelta(hours=3)  # +60 mins
    updated_due = await TaskAssignmentService.update_due_date(
        db=db,
        assignment_id=assignment_id,
        actor_id=emp_id,
        actor_role="EMPLOYEE",
        new_due_date=extended_due,
        reason="Third party API documentation was delayed",
    )
    assert updated_due["due_date_version"] == 2
    # Recalculated estimate should now be ~180 minutes
    assert 170 <= updated_due["estimated_duration_minutes"] <= 185

    # 5. Complete Task (Employee completes task)
    # Simulate started 90 minutes ago by adjusting started_at in db
    simulated_started = datetime.now(timezone.utc) - timedelta(minutes=90)
    db["task_assignments"].docs[0]["started_at"] = simulated_started
    db["task_assignments"].docs[0]["estimated_duration_minutes"] = 180

    completed = await TaskAssignmentService.complete_task(
        db=db,
        assignment_id=assignment_id,
        actor_id=emp_id,
        actor_role="EMPLOYEE",
    )
    assert completed["status"] == TaskAssignmentStatus.COMPLETED.value
    assert completed["completed_at"] is not None
    # actualDurationMinutes = completedAt - startedAt (~90 mins)
    assert 88 <= completed["actual_duration_minutes"] <= 92
    # timeVarianceMinutes = actualDurationMinutes - estimatedDurationMinutes
    # 90 - 180 = -90 mins (Negative = completed prior to estimated time)
    assert -92 <= completed["time_variance_minutes"] <= -88

    # 6. Duplicate completion rejection
    with pytest.raises(HTTPException) as exc:
        await TaskAssignmentService.complete_task(
            db=db,
            assignment_id=assignment_id,
            actor_id=emp_id,
            actor_role="EMPLOYEE",
        )
    assert exc.value.status_code == 400
    assert "already been completed" in exc.value.detail


@pytest.mark.asyncio
async def test_due_date_update_authorization_control():
    db = MockDatabase()
    pm_id = str(ObjectId())
    emp_id = str(ObjectId())
    other_emp_id = str(ObjectId())

    assignment = await TaskAssignmentService.create_assignment(
        db=db,
        employee_id=emp_id,
        project_manager_id=pm_id,
        board_id="board_1",
        trello_card_id="card_1",
        task_title="Database Migration",
        due_date=datetime.now(timezone.utc) + timedelta(days=2),
    )
    assignment_id = assignment["id"]

    # Unauthorized user attempting to change due date must be rejected (403)
    with pytest.raises(HTTPException) as exc:
        await TaskAssignmentService.update_due_date(
            db=db,
            assignment_id=assignment_id,
            actor_id=other_emp_id,
            actor_role="EMPLOYEE",
            new_due_date=datetime.now(timezone.utc) + timedelta(days=3),
        )
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# MODULE 4 TESTS: Automatic Employee Performance Level Calculation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_employee_performance_insufficient_data():
    db = MockDatabase()
    emp_id = str(ObjectId())

    # Only 1 completed task (requires at least 3)
    now = datetime.now(timezone.utc)
    db["task_assignments"].docs.append({
        "_id": ObjectId(),
        "employee_id": emp_id,
        "task_title": "Task 1",
        "status": TaskAssignmentStatus.COMPLETED.value,
        "due_date": now + timedelta(days=1),
        "completed_at": now,
        "estimated_duration_minutes": 60,
        "actual_duration_minutes": 55,
        "created_at": now - timedelta(days=5),
    })

    perf = await PerformanceCalculationService.calculate_employee_performance(
        db=db,
        employee_id=emp_id,
    )
    assert perf["level"] == PerformanceLevel.NOT_ENOUGH_DATA.value
    assert "Insufficient historical completed tasks" in perf["reason"]


@pytest.mark.asyncio
async def test_employee_performance_high_classification_and_history():
    db = MockDatabase()
    emp_id = str(ObjectId())
    now = datetime.now(timezone.utc)

    # 4 completed tasks, all on time, consistent duration
    for i in range(4):
        db["task_assignments"].docs.append({
            "_id": ObjectId(),
            "employee_id": emp_id,
            "task_title": f"Feature {i+1}",
            "status": TaskAssignmentStatus.COMPLETED.value,
            "due_date": now + timedelta(days=1),
            "completed_at": now - timedelta(hours=i),
            "estimated_duration_minutes": 100,
            "actual_duration_minutes": 90,
            "created_at": now - timedelta(days=10),
        })

    perf = await PerformanceCalculationService.calculate_employee_performance(
        db=db,
        employee_id=emp_id,
        employee_name="Alice Engineer",
    )
    # On-time: 100%, Consistency: 100%, Completion: 100%, Reliability: 100% -> Overall Score: 100.0
    assert perf["level"] == PerformanceLevel.HIGH.value
    assert perf["overall_score"] >= 80.0
    assert perf["on_time_rate"] == 100.0

    # Verify history entry was created in employee_level_history
    history_docs = db["employee_level_history"].docs
    assert len(history_docs) == 1
    assert history_docs[0]["employee_id"] == emp_id
    assert history_docs[0]["new_level"] == PerformanceLevel.HIGH.value


# ---------------------------------------------------------------------------
# MODULE 5 TESTS: Automatic One-Hour Deadline Reminders
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_one_hour_reminder_level_tailored_comments():
    task_title = "Login API Integration"
    emp_name = "Rahul Sharma"

    # LOW level: supportive, blocker inquiry, offer help
    comment_low = OneHourReminderService.get_fallback_comment(task_title, "Rahul", "LOW")
    assert "Rahul" in comment_low
    assert "blocker" in comment_low.lower() or "help" in comment_low.lower()
    # Must NOT expose scores or level names
    assert "LOW" not in comment_low
    assert "score" not in comment_low.lower()

    # MEDIUM level: balanced, approaching deadline, timely status update
    comment_med = OneHourReminderService.get_fallback_comment(task_title, "Rahul", "MEDIUM")
    assert "Rahul" in comment_med
    assert "status update" in comment_med.lower() or "approaching" in comment_med.lower()

    # HIGH level: firm, respectful, deadline accountability, immediate escalation
    comment_high = OneHourReminderService.get_fallback_comment(task_title, "Rahul", "HIGH")
    assert "Rahul" in comment_high
    assert "confirm" in comment_high.lower() or "escalation" in comment_high.lower() or "deadline" in comment_high.lower()


@pytest.mark.asyncio
async def test_one_hour_reminder_trigger_and_idempotency():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    emp_id = str(ObjectId())

    # Task due in 45 minutes (within the 1-hour window)
    task_id = str(ObjectId())
    db["task_assignments"].docs.append({
        "_id": ObjectId(task_id),
        "employee_id": emp_id,
        "employee_name": "Rahul Sharma",
        "employee_email": "rahul@example.com",
        "trello_card_id": "card_rem_1",
        "task_title": "Login API Integration",
        "status": TaskAssignmentStatus.IN_PROGRESS.value,
        "due_date": now + timedelta(minutes=45),
        "due_date_version": 1,
    })

    # Set performance level in db
    db["employee_performance"].docs.append({
        "employee_id": emp_id,
        "level": "MEDIUM",
        "overall_score": 72.0,
    })

    mock_mailer = MagicMock()
    mock_mailer.send_email = AsyncMock(return_value=None)
    mock_trello = MagicMock()
    mock_trello.add_comment = AsyncMock(return_value={"id": "comm_123"})

    # First run: should trigger email and Trello comment
    res1 = await OneHourReminderService.process_due_reminders(
        db=db,
        email_service=mock_mailer,
        trello_client=mock_trello,
    )
    assert res1["processed_tasks"] == 1
    assert res1["emails_sent"] == 1
    assert res1["trello_comments_posted"] == 1

    # Verify reminder log entry
    logs = db["reminder_logs"].docs
    assert len(logs) == 1
    assert logs[0]["email_sent"] is True
    assert logs[0]["trello_comment_sent"] is True

    # Second run immediately after: must be idempotent and skip
    res2 = await OneHourReminderService.process_due_reminders(
        db=db,
        email_service=mock_mailer,
        trello_client=mock_trello,
    )
    assert res2["processed_tasks"] == 0
    assert res2["emails_sent"] == 0
    assert res2["trello_comments_posted"] == 0

