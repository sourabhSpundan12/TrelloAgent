import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from app.ai.service import AIService
from app.services.board_service import resolve_active_board
from app.mcp_server.trello_tools import trello_create_list, trello_create_card
from app.services.reminder_service import TaskReminderService
from app.integrations.trello.client import parse_due_date_for_trello
from app.tool_executor.registry import find_best_matching_card, MockTrelloArchiveCardExecutor, MockTrelloMoveCardExecutor
from app.tool_executor.interfaces import ExecutionContext


def test_ai_fallback_multi_list_parsing():
    """Test AI fallback deterministic parser correctly parses multiple lists."""
    service = AIService()
    cmd = "create lists: Backlog, QA, In-Progress and Done"
    res = service._fallback_deterministic_interpreter(
        command=cmd,
        discovered_tools=[],
    )
    assert res.intent in ("create_list", "trello_create_list")
    assert res.parameters.get("names") == ["Backlog", "QA", "In-Progress", "Done"]
    assert "Backlog" in res.parameters.get("name")


def test_ai_fallback_start_and_due_date_with_time_parsing():
    """Test AI fallback parser correctly extracts start date and due date with time."""
    service = AIService()
    cmd = "create a card API Integration start tomorrow at 9am and due in 3 days at 5pm"
    res = service._fallback_deterministic_interpreter(
        command=cmd,
        discovered_tools=[],
    )
    assert res.intent in ("create_card", "trello_create_card")
    assert "API Integration" in res.parameters.get("name")
    assert res.parameters.get("start_date") is not None
    assert "tomorrow" in res.parameters.get("start_date").lower()
    assert res.parameters.get("due_date") is not None
    assert "in 3 days" in res.parameters.get("due_date").lower()


def test_parse_due_date_for_trello_with_time():
    """Test parse_due_date_for_trello correctly handles dates with time in Indian Standard Time (IST)."""
    # 1. tomorrow at 3pm IST -> in UTC is 09:30 UTC
    parsed_3pm = parse_due_date_for_trello("tomorrow at 3pm")
    assert parsed_3pm is not None
    assert "T09:30:00.000Z" in parsed_3pm

    # 2. specific date with 24-hr time in IST (14:30 IST -> 09:00 UTC)
    parsed_date_time = parse_due_date_for_trello("2026-11-25 14:30")
    assert parsed_date_time is not None
    assert "2026-11-25T09:00:00.000Z" == parsed_date_time

    # 3. specific date with am/pm in IST (10:15 AM IST -> 04:45 UTC)
    parsed_ampm = parse_due_date_for_trello("25 Nov 2026 10:15 AM")
    assert parsed_ampm is not None
    assert "2026-11-25T04:45:00.000Z" == parsed_ampm


def test_move_card_fallback_parsing():
    """Test move card intent parsing for various natural prompt formats."""
    service = AIService()

    # Format 1: move card X to Y
    res1 = service._fallback_deterministic_interpreter(
        command="move card Features to Done",
        discovered_tools=[],
    )
    assert res1.intent == "move_card"
    assert res1.parameters.get("card_name") == "Features"
    assert res1.parameters.get("target_status") in ("Done", "DONE")

    # Format 2: move card X from ListA to ListB
    res2 = service._fallback_deterministic_interpreter(
        command="move card Features from To Do to In Progress",
        discovered_tools=[],
    )
    assert res2.intent == "move_card"
    assert res2.parameters.get("card_name") == "Features"
    assert res2.parameters.get("target_status") == "Doing"  # In Progress canonical status is Doing

    # Format 3: mark card as done
    res3 = service._fallback_deterministic_interpreter(
        command="mark card 'Auth Service' as done",
        discovered_tools=[],
    )
    assert res3.intent == "move_card"
    assert "Auth Service" in res3.parameters.get("card_name")
    assert res3.parameters.get("target_status") == "Done"


def test_delete_card_single_does_not_pass_list_name():
    """Test single card delete prompt only extracts card_name and does NOT set list_name."""
    service = AIService()
    res = service._fallback_deterministic_interpreter(
        command="delete card Features",
        discovered_tools=[],
    )
    assert res.intent == "delete_card"
    assert res.parameters.get("card_name") == "Features"
    assert "list_name" not in res.parameters


def test_user_prompt_with_sre_member_start_due_dates():
    """Test full command from user screenshot parses cleanly without capturing start date in member name."""
    service = AIService()
    cmd = "create task SRE and add member sourabh mishra and start date 26 november 2026 and due date 27 november 2026"
    res = service._fallback_deterministic_interpreter(
        command=cmd,
        discovered_tools=[],
    )
    assert res.intent in ("create_card", "trello_create_card")
    assert res.parameters.get("name") == "SRE"
    assert res.parameters.get("member_name") == "sourabh mishra"
    assert "26 november 2026" in res.parameters.get("start_date")
    assert "27 november 2026" in res.parameters.get("due_date")


@pytest.mark.asyncio
async def test_resolve_active_board_precedence():
    """Test that requested_board_id from UI takes precedence over stale parameters."""
    mock_db = MagicMock()
    class AsyncBoardsCursor:
        def __init__(self, items):
            self.items = list(items)
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    boards = [
        {"board_id": "board_old_stale", "name": "Old Board"},
        {"board_id": "board_new_selection", "name": "New Board Selection"},
        {"board_id": "board_sre", "name": "SRE"},
    ]
    mock_db.__getitem__.return_value.find.return_value = AsyncBoardsCursor(boards)

    # 1. Parameter precedence
    active = await resolve_active_board(
        db=mock_db,
        requested_board_id="board_new_selection",
        parameters={"board_id": "board_old_stale"},
    )
    assert active.get("board_id") == "board_new_selection"

    # 2. Task name 'SRE' does NOT switch away from requested_board_id
    mock_db.__getitem__.return_value.find.return_value = AsyncBoardsCursor(boards)
    active2 = await resolve_active_board(
        db=mock_db,
        requested_board_id="board_new_selection",
        command="create task SRE and add member sourabh mishra",
    )
    assert active2.get("board_id") == "board_new_selection"
    assert active2.get("name") == "New Board Selection"


@pytest.mark.asyncio
async def test_trello_create_multi_list_tool():
    """Test trello_create_list tool accepts list of names and creates each list."""
    with patch("app.mcp_server.trello_tools.get_trello_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.create_list = AsyncMock(side_effect=[
            {"id": "list_1", "name": "Sprint Backlog"},
            {"id": "list_2", "name": "In Review"},
        ])
        mock_client_factory.return_value = mock_client

        res = await trello_create_list(
            board_id="board_123",
            names=["Sprint Backlog", "In Review"],
        )
        assert res["created_count"] == 2
        assert len(res["lists"]) == 2
        assert res["lists"][0]["name"] == "Sprint Backlog"
        assert res["lists"][1]["name"] == "In Review"


@pytest.mark.asyncio
async def test_trello_create_card_with_start_date():
    """Test trello_create_card tool passes start date to client."""
    with patch("app.mcp_server.trello_tools.get_trello_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.create_card = AsyncMock(return_value={
            "id": "card_test_1",
            "name": "Feature X",
            "start": "2026-11-25T09:00:00.000Z",
            "due": "2026-11-28T18:00:00.000Z",
        })
        mock_client_factory.return_value = mock_client

        res = await trello_create_card(
            name="Feature X",
            list_id="list_todo",
            start_date="2026-11-25",
            due_date="2026-11-28",
        )
        mock_client.create_card.assert_called_once()
        _, kwargs = mock_client.create_card.call_args
        assert kwargs.get("start") == "2026-11-25"
        assert kwargs.get("due") == "2026-11-28"
        assert res["card"]["id"] == "card_test_1"


@pytest.mark.asyncio
async def test_task_reminder_service_stages_and_comments():
    """Test reminder service stages: 1_DAY, 4_HOURS, and 1_HOUR thresholds with comments & emails."""
    mock_email_svc = MagicMock()
    mock_email_svc.is_configured.return_value = True
    mock_email_svc.send_email = AsyncMock(return_value=True)
    reminder_svc = TaskReminderService(email_service=mock_email_svc)
    now = datetime.now(timezone.utc)

    # 1. Card due in ~23 hours -> Should trigger 1_DAY stage
    due_1d = (now + timedelta(hours=23)).isoformat()
    # 2. Card due in ~3.5 hours -> Should trigger 4_HOURS stage
    due_4h = (now + timedelta(hours=3, minutes=30)).isoformat()
    # 3. Card due in ~45 minutes -> Should trigger 1_HOUR stage
    due_1h = (now + timedelta(minutes=45)).isoformat()

    cards = [
        {"id": "c1", "name": "Task 1 Day", "due": due_1d, "idMembers": ["mem_1"]},
        {"id": "c2", "name": "Task 4 Hours", "due": due_4h, "idMembers": ["mem_1"]},
        {"id": "c3", "name": "Task 1 Hour", "due": due_1h, "idMembers": ["mem_1"]},
    ]

    mock_db = MagicMock()
    # boards collection cursor
    class AsyncBoardsCursor:
        def __init__(self, items):
            self.items = list(items)
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    # users collection cursor
    mock_users_cursor = MagicMock()
    mock_users_cursor.to_list = AsyncMock(return_value=[
        {"_id": "u1", "email": "employee@example.com", "full_name": "Dev Employee", "trello_member_id": "mem_1"}
    ])

    # reminders collection
    mock_reminders = MagicMock()
    mock_reminders.find_one = AsyncMock(return_value=None)
    mock_reminders.insert_one = AsyncMock()
    mock_reminders.update_many = AsyncMock()

    # task_assignments collection
    mock_assignments = MagicMock()
    mock_assignments.find_one = AsyncMock(return_value={
        "employee_email": "employee@example.com",
        "employee_name": "Dev Employee",
        "employee_id": "u1",
    })
    mock_assignments.update_many = AsyncMock()

    def get_coll(name):
        if name == "boards":
            m = MagicMock()
            m.find.return_value = AsyncBoardsCursor([{"id": "b1", "name": "Sprint Board"}])
            return m
        elif name in ("reminders", "task_deadline_reminders", "reminder_logs"):
            return mock_reminders
        elif name == "task_assignments":
            return mock_assignments
        elif name == "users":
            m = MagicMock()
            m.find.return_value = mock_users_cursor
            return m
        return MagicMock()

    mock_db.__getitem__.side_effect = get_coll

    with patch("app.mcp_server.trello_tools.trello_list_cards", new_callable=AsyncMock) as mock_cards, \
         patch("app.mcp_server.trello_tools.trello_list_lists", new_callable=AsyncMock) as mock_lists, \
         patch("app.mcp_server.trello_tools.trello_add_comment", new_callable=AsyncMock) as mock_add_comment:
        mock_cards.return_value = {"cards": cards}
        mock_lists.return_value = {"lists": [{"id": "list_1", "name": "To Do"}]}
        mock_add_comment.return_value = {"status": "SUCCESS"}

        generated = await reminder_svc.scan_and_generate_reminders(mock_db)
        assert len(generated) == 3
        stages = {r["stage"] for r in generated}
        assert "1_DAY" in stages
        assert "4_HOURS" in stages
        assert "1_HOUR" in stages

        # Verified: Email sent to the employee with IST timestamp for all 3 stages
        assert mock_email_svc.send_email.call_count == 3
        to_emails = [call.kwargs.get("to_email") for call in mock_email_svc.send_email.call_args_list]
        assert all(email == "employee@example.com" for email in to_emails)
        first_email_text = mock_email_svc.send_email.call_args_list[0].kwargs.get("text_content")
        assert "IST" in first_email_text

        # Verified: STRICT RULE: 1_DAY and 4_HOURS only send emails; ONLY 1_HOUR posts a comment on Trello!
        assert mock_add_comment.call_count == 1
        comment_text = mock_add_comment.call_args_list[0].kwargs.get("text")
        # Image 3 format verification
        assert "approaching its deadline in one hour" in comment_text
        assert "Hi Dev" in comment_text
        assert "Task 1 Hour" in comment_text


def test_create_task_with_member_due_date_and_time_title_separation():
    """Test user prompt: create task SRH and add member sourabh mishra and due date 26 november 2026 and time 11:00 AM"""
    service = AIService()
    cmd = "create task SRH and add member sourabh mishra and due date 26 november 2026 and time 11:00 AM"
    res = service._fallback_deterministic_interpreter(
        command=cmd,
        discovered_tools=[],
    )
    assert res.intent == "create_card"
    assert res.parameters.get("name") == "SRH"
    assert res.parameters.get("member_name") == "sourabh mishra"
    assert "26 november 2026" in res.parameters.get("due_date").lower()
    assert "11:00 am" in res.parameters.get("due_date").lower()

    # Verify parse_due_date_for_trello accepts it and produces exact UTC time for 11:00 AM IST (05:30 UTC)
    iso_date = parse_due_date_for_trello(res.parameters.get("due_date"))
    assert iso_date == "2026-11-26T05:30:00.000Z"


def test_user_screenshot_register_time_is_title_separation():
    """Test user prompt: create card Register and time is 12:00 PM and add member sourabh mishra and start date 24/11/2026 and due date 24/11/2026"""
    service = AIService()
    cmd = "create card Register and time is 12:00 PM and add member sourabh mishra and start date 24/11/2026 and due date 24/11/2026"
    res = service._fallback_deterministic_interpreter(
        command=cmd,
        discovered_tools=[],
    )
    assert res.intent in ("create_card", "trello_create_card")
    # Title must be strictly "Register", NEVER containing "time is 12:00 PM"
    assert res.parameters.get("name") == "Register"
    assert "time" not in res.parameters.get("name").lower()
    assert res.parameters.get("member_name") == "sourabh mishra"
    assert "24/11/2026" in res.parameters.get("start_date")
    assert "24/11/2026" in res.parameters.get("due_date")
    assert "12:00 pm" in res.parameters.get("due_date").lower()

    # Verify parse_due_date_for_trello correctly parses 24/11/2026 12:00 PM IST -> 2026-11-24T06:30:00.000Z
    iso_due = parse_due_date_for_trello(res.parameters.get("due_date"))
    assert iso_due == "2026-11-24T06:30:00.000Z"


@pytest.mark.asyncio
async def test_create_task_draft_cleans_leaked_time_from_title():
    """Test that create_task_draft defensively strips any leaked time clauses and cleans description."""
    from app.approvals.service import ApprovalService
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__.return_value.insert_one = AsyncMock()

    approval_svc = ApprovalService(db=mock_db)
    draft_res = await approval_svc.create_task_draft(
        user_id="u123",
        user_email="test@example.com",
        command="create card Register and time is 12:00 PM",
        intent="create_card",
        tool_id="trello_create_card",
        tool_name="Create Trello Card",
        category="TRELLO",
        parameters={
            "name": "Register and time is 12:00 PM",
            "due_date": "24/11/2026",
            "member_name": "sourabh mishra",
        },
        board_name="SRE",
    )
    # Draft title must be clean "Register"
    assert draft_res.draft.title == "Register"
    assert "time is" not in draft_res.draft.title.lower()
    # Description must not contain "time is 12:00 PM"
    assert "time is" not in draft_res.draft.description.lower()
    # due_date must now contain 12:00 PM
    assert "12:00 pm" in draft_res.draft.parameters.get("due_date", "").lower()


def test_natural_conversational_and_hinglish_prompts():
    """Test natural human phrasing for creating, moving, updating, and deleting tasks."""
    service = AIService()

    # 1. Polite prefix removal
    res_polite = service._fallback_deterministic_interpreter(
        command="Please can you create card Auth Service with high priority",
        discovered_tools=[],
    )
    assert res_polite.intent in ("create_card", "trello_create_card")
    assert res_polite.parameters.get("name") == "Auth Service"
    assert res_polite.parameters.get("priority") == "HIGH"

    # 2. Hinglish task creation: "bana do card Register and add member sourabh mishra"
    res_create_hinglish = service._fallback_deterministic_interpreter(
        command="bana do card Register and add member sourabh mishra",
        discovered_tools=[],
    )
    assert res_create_hinglish.intent in ("create_card", "trello_create_card")
    assert res_create_hinglish.parameters.get("name") == "Register"
    assert res_create_hinglish.parameters.get("member_name") == "sourabh mishra"

    # 3. List-first task creation: "in Doing list create card Code Review"
    res_list_first = service._fallback_deterministic_interpreter(
        command="in Doing list create card Code Review",
        discovered_tools=[],
    )
    assert res_list_first.intent in ("create_card", "trello_create_card")
    assert res_list_first.parameters.get("name") == "Code Review"
    assert res_list_first.parameters.get("list_name") == "Doing"

    # 4. Natural move synonyms: "push Features to Doing"
    res_push = service._fallback_deterministic_interpreter(
        command="push Features to Doing",
        discovered_tools=[],
    )
    assert res_push.intent in ("move_card", "trello_move_card")
    assert res_push.parameters.get("card_name") == "Features"
    assert res_push.parameters.get("target_status") == "Doing"

    # 5. Natural completion: "mark Features done"
    res_mark_done = service._fallback_deterministic_interpreter(
        command="mark Features done",
        discovered_tools=[],
    )
    assert res_mark_done.intent in ("move_card", "trello_move_card")
    assert res_mark_done.parameters.get("card_name") == "Features"
    assert res_mark_done.parameters.get("target_status") == "Done"

    # 6. Hinglish move: "Features card Done me bhej do"
    res_move_hinglish = service._fallback_deterministic_interpreter(
        command="Features card Done me bhej do",
        discovered_tools=[],
    )
    assert res_move_hinglish.intent in ("move_card", "trello_move_card")
    assert res_move_hinglish.parameters.get("card_name") == "Features"
    assert res_move_hinglish.parameters.get("target_status").upper() == "DONE"

    # 7. Hinglish completion: "Backend ho gaya"
    res_ho_gaya = service._fallback_deterministic_interpreter(
        command="Backend ho gaya",
        discovered_tools=[],
    )
    assert res_ho_gaya.intent in ("move_card", "trello_move_card")
    assert res_ho_gaya.parameters.get("card_name") == "Backend"
    assert res_ho_gaya.parameters.get("target_status") == "Done"

    # 8. Natural assignment: "assign Sourabh to card Register"
    res_assign = service._fallback_deterministic_interpreter(
        command="assign Sourabh to card Register",
        discovered_tools=[],
    )
    assert res_assign.intent in ("update_card", "trello_update_card")
    assert res_assign.parameters.get("card_name") == "Register"
    assert res_assign.parameters.get("member_name") == "Sourabh"

    # 9. Hinglish assignment: "Sourabh ko card Register assign kardo"
    res_assign_hinglish = service._fallback_deterministic_interpreter(
        command="Sourabh ko card Register assign kardo",
        discovered_tools=[],
    )
    assert res_assign_hinglish.intent in ("update_card", "trello_update_card")
    assert res_assign_hinglish.parameters.get("card_name") == "Register"
    assert res_assign_hinglish.parameters.get("member_name") == "Sourabh"

    # 10. Hinglish card deletion: "Register card hata do"
    res_del_hinglish = service._fallback_deterministic_interpreter(
        command="Register card hata do",
        discovered_tools=[],
    )
    assert res_del_hinglish.intent in ("delete_card", "trello_delete_card")
    assert res_del_hinglish.parameters.get("card_name") == "Register"

    # 11. Natural relative dates/times in Trello client parser: tonight, by eod, in 2 hours
    from app.integrations.trello.client import parse_due_date_for_trello
    iso_tonight = parse_due_date_for_trello("tonight")
    assert iso_tonight is not None and "T14:30:00" in iso_tonight  # 20:00 IST is 14:30 UTC

    iso_eod = parse_due_date_for_trello("by eod")
    assert iso_eod is not None and "T12:30:00" in iso_eod  # 18:00 IST is 12:30 UTC

    iso_hours = parse_due_date_for_trello("in 2 hours")
    assert iso_hours is not None

def test_user_screenshot_update_due_date_register_page():
    """Test user prompt: 'update due date of Register Page to 29 nov 2026' and 'update ue date of Register Page to 29 nov 2026'."""
    service = AIService()

    # 1. Standard phrasing
    res1 = service._fallback_deterministic_interpreter(
        command="update due date of Register Page to 29 nov 2026",
        discovered_tools=[],
    )
    assert res1.intent in ("update_card", "trello_update_card")
    assert res1.parameters.get("card_name") == "Register Page"
    assert res1.parameters.get("new_due_date") == "29 nov 2026"
    assert "of" not in res1.parameters.get("new_due_date").lower()

    # 2. Typos like 'update ue date...'
    res2 = service._fallback_deterministic_interpreter(
        command="update ue date of Register Page to 29 nov 2026",
        discovered_tools=[],
    )
    assert res2.intent in ("update_card", "trello_update_card")
    assert res2.parameters.get("card_name") == "Register Page"
    assert res2.parameters.get("new_due_date") == "29 nov 2026"


@pytest.mark.asyncio
async def test_update_card_draft_does_not_mutate_trello_card_desc_unless_requested():
    """Verify that create_task_draft for UPDATE_CARD does not pass desc to exec_params when only due date is changed."""
    from app.approvals.service import ApprovalService
    from unittest.mock import MagicMock, AsyncMock

    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__.return_value.insert_one = AsyncMock()

    approval_svc = ApprovalService(db=mock_db)
    draft_res = await approval_svc.create_task_draft(
        user_id="u123",
        user_email="test@example.com",
        command="update due date of Register Page to 29 nov 2026",
        intent="update_card",
        tool_id="trello_update_card",
        tool_name="Update Trello Card",
        category="TRELLO",
        parameters={
            "card_name": "Register Page",
            "new_due_date": "29 nov 2026",
            "due_date": "29 nov 2026",
        },
        board_name="Testing",
    )
    assert draft_res.draft.title == "Register Page"
    assert draft_res.draft.due_date == "29 nov 2026"
    # Execution params sent to Trello must NOT have 'desc' or 'description'
    assert "desc" not in draft_res.draft.parameters
    assert "description" not in draft_res.draft.parameters


@pytest.mark.asyncio
async def test_team_workload_distinguishes_admin_vs_member_role():
    """Verify that get_team_workload assigns ADMIN role to registered DB users and MEMBER role to Trello board members."""
    from app.api.v1.endpoints.tasks import get_team_workload
    from app.schemas.user import UserResponse

    mock_db = MagicMock()
    # Mock users in DB as async iterable
    mock_users = [
        {"_id": "user123", "full_name": "Sourabh Mishra", "email": "sourabh@example.com", "role": "ADMIN", "department": "Engineering", "is_active": True},
        {"_id": "user456", "full_name": "Shilu Mishra", "email": "shilumishra9039@gmail.com", "role": "EMPLOYEE", "department": "QA", "is_active": True},
    ]

    class AsyncUserCursor:
        def __init__(self, items):
            self.items = items
        def __aiter__(self):
            self._iter = iter(self.items)
            return self
        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    mock_db.__getitem__.return_value.find.return_value = AsyncUserCursor(mock_users)

    # Mock Trello board members: Sourabh Mishra (matches Admin) and John Doe (new board member)
    mock_trello_members = {
        "members": [
            {"id": "trello_sourabh", "fullName": "Sourabh Mishra", "username": "sourabh_m"},
            {"id": "trello_john", "fullName": "John Doe", "username": "johndoe"},
        ]
    }
    mock_trello_cards = {"cards": []}
    mock_trello_lists = {"lists": []}

    current_user = UserResponse(
        id="user123",
        email="sourabh@example.com",
        full_name="Sourabh Mishra",
        role="ADMIN",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )

    with patch("app.mcp_server.trello_tools.trello_list_board_members", AsyncMock(return_value=mock_trello_members)), \
         patch("app.mcp_server.trello_tools.trello_list_cards", AsyncMock(return_value=mock_trello_cards)), \
         patch("app.mcp_server.trello_tools.trello_list_lists", AsyncMock(return_value=mock_trello_lists)), \
         patch("app.api.v1.endpoints.tasks.get_active_board_id", AsyncMock(return_value="board_123")):
        res = await get_team_workload(
            board_id="board_123",
            current_user=current_user,
            db=mock_db,
        )

    assert res["status"] == "SUCCESS"
    members = {m["name"]: m for m in res["members"]}

    # Registered users are marked as ADMIN
    assert "Sourabh Mishra" in members
    assert members["Sourabh Mishra"]["role"] == "ADMIN"
    assert members["Sourabh Mishra"]["empId"].startswith("ADM-")
    assert members["Sourabh Mishra"]["trello_id"] == "trello_sourabh"

    assert "Shilu Mishra" in members
    assert members["Shilu Mishra"]["role"] == "ADMIN"

    # Trello-only board collaborator is marked as MEMBER
    assert "John Doe" in members
    assert members["John Doe"]["role"] == "MEMBER"
    assert members["John Doe"]["empId"].startswith("MBR-")


