import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.ai.service import AIService
from app.integrations.trello.client import parse_due_date_for_trello
from app.services.reminder_service import TaskReminderService
from app.tool_executor.interfaces import ExecutionContext
from app.tool_executor.registry import MockTrelloArchiveCardExecutor, MockTrelloSearchExecutor


def test_determine_reminder_stage_three_levels():
    """Verify the 3-stage reminder thresholds: 1 Day, 4 Hours, 1 Hour."""
    now = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)

    # 1. First reminder: 1 Day left (between 4h and 24h, e.g., 18h left)
    due_1_day = now + timedelta(hours=18)
    res_1 = TaskReminderService.determine_reminder_stage(due_1_day, now)
    assert res_1 is not None
    assert res_1["stage"] == "1_DAY"
    assert res_1["label"] == "1 Day Left"
    assert res_1["urgency"] == "MEDIUM"

    # 2. Second reminder: 4 Hours left (between 1h and 4h, e.g., 3h left)
    due_4_hours = now + timedelta(hours=3)
    res_2 = TaskReminderService.determine_reminder_stage(due_4_hours, now)
    assert res_2 is not None
    assert res_2["stage"] == "4_HOURS"
    assert res_2["label"] == "4 Hours Left"
    assert res_2["urgency"] == "HIGH"

    # 3. Third reminder: 1 Hour left (between 0 and 1h, e.g., 30 mins left)
    due_1_hour = now + timedelta(minutes=30)
    res_3 = TaskReminderService.determine_reminder_stage(due_1_hour, now)
    assert res_3 is not None
    assert res_3["stage"] == "1_HOUR"
    assert res_3["label"] == "1 Hour Left"
    assert res_3["urgency"] == "URGENT"
    assert res_3["mins_left"] == 30

    # Outside thresholds: > 24 hours left -> None
    due_far = now + timedelta(hours=36)
    assert TaskReminderService.determine_reminder_stage(due_far, now) is None

    # Past due: <= 0 seconds -> None
    due_past = now - timedelta(minutes=10)
    assert TaskReminderService.determine_reminder_stage(due_past, now) is None


def test_reminder_service_parse_due_date():
    """Verify various due date parsing formats."""
    # ISO 8601
    dt_iso = TaskReminderService._parse_due_date("2026-11-20T18:00:00.000Z")
    assert dt_iso is not None
    assert dt_iso.year == 2026 and dt_iso.month == 11 and dt_iso.day == 20

    # Date string
    dt_dash = TaskReminderService._parse_due_date("2026-12-01")
    assert dt_dash is not None
    assert dt_dash.year == 2026 and dt_dash.month == 12 and dt_dash.day == 1

    # Empty / invalid
    assert TaskReminderService._parse_due_date(None) is None
    assert TaskReminderService._parse_due_date("") is None
    assert TaskReminderService._parse_due_date("invalid-date-format") is None


def test_mock_trello_search_executor_date_parsing():
    """Test date parsing in MockTrelloSearchExecutor."""
    parsed1 = MockTrelloSearchExecutor._parse_date("2026-11-18")
    assert parsed1 is not None
    assert parsed1.year == 2026 and parsed1.month == 11 and parsed1.day == 18

    parsed2 = MockTrelloSearchExecutor._parse_date("18/11/2026")
    assert parsed2 is not None
    assert parsed2.year == 2026 and parsed2.month == 11 and parsed2.day == 18

    assert MockTrelloSearchExecutor._parse_date("") is None
    assert MockTrelloSearchExecutor._parse_date(None) is None


@pytest.mark.asyncio
async def test_mock_trello_search_executor_date_filtering():
    """Test that date range filtering returns both active and completed cards tagged correctly."""
    executor = MockTrelloSearchExecutor()
    tool = {
        "tool_id": "trello_search_cards",
    }
    parameters = {
        "from_date": "2026-11-01",
        "to_date": "2026-11-30",
    }
    context = ExecutionContext(user_id="u1", user_role="ADMIN")

    # Execute without MCP client (fallback to mocked cards)
    result = await executor.execute(tool=tool, parameters=parameters, context=context)
    assert result.status == "SUCCESS"
    assert "cards" in result.result
    cards = result.result["cards"]
    assert isinstance(cards, list)

    # Check that cards are annotated with is_completed and status_category
    for card in cards:
        assert "is_completed" in card
        assert card["status_category"] in ("Active", "Completed")

    assert "active_count" in result.result
    assert "completed_count" in result.result
    assert result.result["active_count"] + result.result["completed_count"] == len(cards)


def test_parse_due_date_for_trello_formats():
    """Verify that parse_due_date_for_trello correctly parses natural language & month names."""
    # Month name formats like 'Nov 19, 2026'
    res1 = parse_due_date_for_trello("Nov 19, 2026")
    assert res1 is not None
    assert res1.startswith("2026-11-19")

    # Day month year formats
    res2 = parse_due_date_for_trello("19 Nov 2026")
    assert res2 is not None
    assert res2.startswith("2026-11-19")

    # Ordinal formats
    res3 = parse_due_date_for_trello("19th November 2026")
    assert res3 is not None
    assert res3.startswith("2026-11-19")

    # ISO format
    res4 = parse_due_date_for_trello("2026-11-19")
    assert res4 is not None
    assert res4.startswith("2026-11-19")

    # Tomorrow / relative
    res5 = parse_due_date_for_trello("tomorrow")
    assert res5 is not None

    # Invalid / empty
    assert parse_due_date_for_trello(None) is None
    assert parse_due_date_for_trello("") is None
    assert parse_due_date_for_trello("No due date") is None


def test_bulk_delete_recognition():
    """Verify that 'delete all tasks of to do list' is classified as bulk delete with clean list name."""
    service = AIService()
    tools = [{"tool_id": "trello_delete_card"}]

    res1 = service._fallback_deterministic_interpreter("delete all tasks of to do list", tools)
    assert res1.intent == "delete_list_cards"
    assert res1.parameters["list_name"] == "to do"
    assert res1.parameters["is_bulk_delete"] is True

    res2 = service._fallback_deterministic_interpreter("clear to do list", tools)
    assert res2.intent == "delete_list_cards"
    assert res2.parameters["list_name"] == "to do"
    assert res2.parameters["is_bulk_delete"] is True

    res3 = service._fallback_deterministic_interpreter("delete all cards in Doing list", tools)
    assert res3.intent == "delete_list_cards"
    assert res3.parameters["list_name"] == "doing"
    assert res3.parameters["is_bulk_delete"] is True


@pytest.mark.asyncio
async def test_mock_trello_archive_card_executor_bulk_delete():
    """Verify that MockTrelloArchiveCardExecutor correctly processes bulk delete in safe mode."""
    executor = MockTrelloArchiveCardExecutor()
    tool = {"tool_id": "trello_delete_card"}
    parameters = {
        "list_name": "To Do",
        "cards_count": 3,
        "card_names": ["Task 1", "Task 2", "Task 3"],
        "is_bulk_delete": True,
        "action_type": "DELETE_LIST_CARDS",
    }
    context = ExecutionContext(user_id="u1", user_role="ADMIN", confirmed=True)

    result = await executor.execute(tool=tool, parameters=parameters, context=context)
    assert result.status == "SUCCESS"
    assert result.result["status"] == "SUCCESS"
    assert result.result["total_deleted"] == 3
    assert result.result["list_name"] == "To Do"


def test_show_card_of_list_recognition():
    """Verify that commands asking to show or list cards from a list are classified as search_cards, never mutations."""
    service = AIService()
    tools = [{"tool_id": "trello_search_cards"}, {"tool_id": "trello_move_card"}]

    res1 = service._fallback_deterministic_interpreter("show card of Doing list", tools)
    assert res1.intent == "search_cards"
    assert res1.parameters.get("list_name") == "Doing"
    assert res1.suggested_tool_id == "trello_search_cards"

    res2 = service._fallback_deterministic_interpreter("show Doing cards", tools)
    assert res2.intent == "search_cards"
    assert res2.parameters.get("list_name") == "Doing"

    res3 = service._fallback_deterministic_interpreter("show cards in To Do", tools)
    assert res3.intent == "search_cards"
    assert res3.parameters.get("list_name") == "To Do"


@pytest.mark.asyncio
async def test_get_employee_tasks_date_range_filtering():
    """Verify that get_employee_tasks strictly filters tasks within date bounds and returns empty on future ranges."""
    from app.services.task_assignment_service import TaskAssignmentService

    mock_db = MagicMock()
    mock_user = {"_id": "u123", "full_name": "Sourabh Mishra", "email": "sourabh@example.com"}
    mock_db["users"].find_one = AsyncMock(return_value=mock_user)

    # Task assigned on Nov 19, 2026 and due Nov 20, 2026
    sample_task = {
        "_id": "t1",
        "employee_id": "u123",
        "employee_name": "Sourabh Mishra",
        "task_title": "TrelloAgent",
        "status": "in_progress",
        "due_date": datetime(2026, 11, 20, 15, 57, tzinfo=timezone.utc),
        "assigned_at": datetime(2026, 11, 19, 17, 27, tzinfo=timezone.utc),
        "created_at": datetime(2026, 11, 19, 17, 27, tzinfo=timezone.utc),
    }

    mock_cursor = MagicMock()
    # Mock find().sort().to_list()
    mock_cursor.to_list = AsyncMock(return_value=[dict(sample_task)])
    mock_sort = MagicMock(return_value=mock_cursor)
    mock_db["task_assignments"].find = MagicMock(return_value=MagicMock(sort=mock_sort))

    # 1. Future date range where no task belongs (Nov 25 - Nov 30, 2026) -> must return []
    future_tasks = await TaskAssignmentService.get_employee_tasks(
        db=mock_db,
        employee_id="u123",
        from_date=datetime(2026, 11, 25, 0, 0, tzinfo=timezone.utc),
        to_date=datetime(2026, 11, 30, 0, 0, tzinfo=timezone.utc),
    )
    assert len(future_tasks) == 0

    # 2. Matching date range (Nov 19 - Nov 21, 2026) -> must return the task
    mock_cursor.to_list = AsyncMock(return_value=[dict(sample_task)])
    matching_tasks = await TaskAssignmentService.get_employee_tasks(
        db=mock_db,
        employee_id="u123",
        from_date=datetime(2026, 11, 19, 0, 0, tzinfo=timezone.utc),
        to_date=datetime(2026, 11, 21, 0, 0, tzinfo=timezone.utc),
    )
    assert len(matching_tasks) == 1
    assert matching_tasks[0]["task_title"] == "TrelloAgent"




