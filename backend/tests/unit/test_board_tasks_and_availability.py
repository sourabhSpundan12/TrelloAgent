import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from app.api.v1.endpoints.reports import _format_overdue, _extract_card_date, get_board_task_report
from app.schemas.user import UserResponse


def test_format_overdue():
    now = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)

    # Completed card should not be overdue
    is_od, text = _format_overdue("2026-11-19T10:00:00Z", is_completed=True, now_utc=now)
    assert not is_od
    assert text == "—"

    # Card with no due date
    is_od, text = _format_overdue(None, is_completed=False, now_utc=now)
    assert not is_od
    assert text == "—"

    # Card overdue by 2 hours
    past_due = (now - timedelta(hours=2, minutes=15)).isoformat()
    is_od, text = _format_overdue(past_due, is_completed=False, now_utc=now)
    assert is_od
    assert "Overdue by 2h 15m" in text

    # Card overdue by 3 days
    past_due_days = (now - timedelta(days=3, hours=5)).isoformat()
    is_od, text = _format_overdue(past_due_days, is_completed=False, now_utc=now)
    assert is_od
    assert "Overdue by 3d 5h" in text

    # Card on time
    future_due = (now + timedelta(days=1)).isoformat()
    is_od, text = _format_overdue(future_due, is_completed=False, now_utc=now)
    assert not is_od
    assert text == "On Time"


def test_extract_card_date():
    # From due date
    card_with_due = {"id": "673cc0000000000000000000", "due": "2026-11-20T15:30:00Z"}
    dt = _extract_card_date(card_with_due)
    assert dt.year == 2026
    assert dt.month == 11
    assert dt.day == 20

    # Fallback to Trello ObjectId timestamp
    card_no_due = {"id": "673cc0000000000000000000"}
    dt2 = _extract_card_date(card_no_no_due := card_no_due)
    assert dt2.year == 2024
    assert dt2.month == 11


@pytest.mark.asyncio
async def test_get_board_task_report_availability_and_summary():
    mock_current_user = UserResponse(
        id="usr_pm_1",
        email="pm@enterprise.com",
        full_name="Project Manager",
        role="MANAGER",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )

    mock_cards = [
        {
            "id": "c101",
            "name": "Backend Auth Implementation",
            "desc": "assigned to Alice",
            "idList": "list_doing",
            "idMembers": ["m_alice"],
            "due": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "closed": False,
        },
        {
            "id": "c102",
            "name": "Database Migration",
            "desc": "for Bob",
            "idList": "list_done",
            "idMembers": ["m_bob"],
            "due": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "closed": False,
        },
        {
            "id": "c103",
            "name": "Fix Critical Bug",
            "desc": "urgent task",
            "idList": "list_todo",
            "idMembers": ["m_alice"],
            "due": (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat(),
            "closed": False,
        },
    ]

    mock_lists = [
        {"id": "list_todo", "name": "To Do"},
        {"id": "list_doing", "name": "In Progress"},
        {"id": "list_done", "name": "Done"},
    ]

    mock_members = [
        {"id": "m_alice", "fullName": "Alice Smith", "username": "alice", "avatarUrl": ""},
        {"id": "m_bob", "fullName": "Bob Jones", "username": "bob", "avatarUrl": ""},
        {"id": "m_charlie", "fullName": "Charlie Brown", "username": "charlie", "avatarUrl": ""},
    ]

    with patch("app.mcp_server.trello_tools.trello_list_cards", new_callable=AsyncMock) as mock_list_cards, \
         patch("app.mcp_server.trello_tools.trello_list_lists", new_callable=AsyncMock) as mock_list_lists, \
         patch("app.mcp_server.trello_tools.trello_list_board_members", new_callable=AsyncMock) as mock_list_members, \
         patch("app.mcp_server.trello_tools.trello_list_boards", new_callable=AsyncMock) as mock_list_boards, \
         patch("app.services.board_service.get_active_board_id", new_callable=AsyncMock) as mock_get_board:

        mock_get_board.return_value = "board_main"
        mock_list_cards.return_value = {"cards": mock_cards}
        mock_list_lists.return_value = {"lists": mock_lists}
        mock_list_members.return_value = {"members": mock_members}
        mock_list_boards.return_value = {"boards": [{"id": "board_main", "name": "Engineering Board"}]}

        result = await get_board_task_report(
            board_id="board_main",
            from_date=None,
            to_date=None,
            current_user=mock_current_user,
            db=None,
        )

        assert result["status"] == "SUCCESS"
        assert result["board_name"] == "Engineering Board"

        # Verify Summary cards
        summary = result["summary"]
        assert summary["total_cards"] == 3
        assert summary["completed_cards"] == 1  # c102
        assert summary["in_progress_cards"] == 1  # c101
        assert summary["pending_cards"] == 2  # c101 + c103
        assert summary["overdue_cards"] == 1  # c103 is pending and overdue

        # Verify Today's Employee Availability
        avail = result["availability"]
        assert avail["working_period_hours"] == 8
        assert avail["total_employees"] == 3

        # Alice has c101 (future due date) -> Busy
        # Bob has only completed cards -> Free today
        # Charlie has 0 cards -> Free today
        assert avail["busy_count"] >= 1
        assert avail["free_count"] >= 1

        busiest = avail["busiest_employees"]
        assert any(b["name"] == "Alice Smith" for b in busiest)

        free = avail["free_employees"]
        assert any(f["name"] == "Charlie Brown" for f in free)

        # Verify Table Columns for Cards
        cards = result["cards"]
        assert len(cards) == 3
        card_101 = next(c for c in cards if c["id"] == "c101")
        assert card_101["card"] == "Backend Auth Implementation"
        assert "Alice Smith" in card_101["employee"]
        assert card_101["list"] == "In Progress"
        assert card_101["status"] == "Pending"
        assert card_101["overdue"] == "On Time"

        card_102 = next(c for c in cards if c["id"] == "c102")
        assert card_102["status"] == "Completed"
        assert card_102["overdue"] == "—"
