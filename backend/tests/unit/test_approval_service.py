from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.approvals.exceptions import (
    ApprovalAlreadyProcessedError,
    ApprovalExecutionError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
    ApprovalUnauthorizedError,
)
from app.approvals.models import ApprovalStatus
from app.approvals.schemas import ApprovalEditRequest
from app.approvals.service import ApprovalService
from app.tool_executor.interfaces import ExecutionResult
from app.tool_registry.service import ToolRegistryService


@pytest.mark.asyncio
async def test_create_task_draft(mock_db):
    service = ApprovalService(mock_db)
    preview = await service.create_task_draft(
        user_id="user_123",
        user_email="user@example.com",
        command="Create a task to implement JWT authentication in Spring Boot with high priority due next Friday",
        intent="create_card",
        tool_id="trello_create_card",
        tool_name="Create Trello Card",
        category="TRELLO",
        parameters={
            "name": "Implement JWT authentication in Spring Boot",
            "desc": "Implement JWT authentication filter and endpoints",
            "list_name": "To Do",
            "priority": "HIGH",
            "due_date": "next Friday",
        },
    )

    assert preview.action_id.startswith("ACT-PREV-")
    assert preview.status == ApprovalStatus.PENDING.value
    assert preview.tool_id == "trello_create_card"
    assert preview.draft.title == "Implement JWT authentication in Spring Boot"
    assert preview.draft.priority == "HIGH"
    assert preview.draft.due_date == "next Friday"
    assert preview.draft.list_name == "To Do"
    assert preview.payload_hash is not None
    assert preview.expires_at > preview.created_at

    # Verify persisted in mock_db
    persisted = await mock_db["pending_actions"].find_one({"action_id": preview.action_id})
    assert persisted is not None
    assert persisted["user_id"] == "user_123"


@pytest.mark.asyncio
async def test_get_action_preview(mock_db):
    service = ApprovalService(mock_db)
    created = await service.create_task_draft(
        user_id="user_123",
        user_email="user@example.com",
        command="Create task to configure SSL",
        intent="create_card",
        tool_id="trello_create_card",
        tool_name="Create Trello Card",
        category="TRELLO",
        parameters={"name": "Configure SSL", "list_name": "To Do"},
    )

    # Authorized owner
    fetched = await service.get_action(created.action_id, user_id="user_123", user_role="EMPLOYEE")
    assert fetched.action_id == created.action_id
    assert fetched.draft.title == "Configure SSL"

    # Admin access allowed
    admin_fetched = await service.get_action(created.action_id, user_id="admin_999", user_role="ADMIN")
    assert admin_fetched.action_id == created.action_id

    # Unauthorized access rejected
    with pytest.raises(ApprovalUnauthorizedError):
        await service.get_action(created.action_id, user_id="attacker_456", user_role="EMPLOYEE")

    # Nonexistent ID
    with pytest.raises(ApprovalNotFoundError):
        await service.get_action("ACT-NONEXISTENT", user_id="user_123", user_role="EMPLOYEE")


@pytest.mark.asyncio
async def test_confirm_action_success(mock_db):
    # Seed tool registry so tool exists
    tool_reg = ToolRegistryService(mock_db)
    await tool_reg.seed_default_tools()

    service = ApprovalService(mock_db)
    created = await service.create_task_draft(
        user_id="user_123",
        user_email="user@example.com",
        command="Create a task to implement JWT authentication in Spring Boot",
        intent="create_card",
        tool_id="trello_create_card",
        tool_name="Create Trello Card",
        category="TRELLO",
        parameters={"name": "Implement JWT authentication in Spring Boot", "desc": "Setup auth filters"},
    )

    # Mock tool executor output
    mock_exec_result = ExecutionResult(
        tool_id="trello_create_card",
        status="SUCCESS",
        is_mutation=True,
        result={
            "action": "CREATED",
            "card": {
                "id": "card_jwt_789",
                "name": "Implement JWT authentication in Spring Boot",
                "url": "https://trello.com/c/mockJwtCard",
                "shortUrl": "https://trello.com/c/mockJwtCard",
            },
        },
        message="Card created",
    )
    service.tool_executor.execute = AsyncMock(return_value=mock_exec_result)

    confirm_res = await service.confirm_action(
        action_id=created.action_id,
        user_id="user_123",
        user_role="EMPLOYEE",
    )

    assert confirm_res.status == ApprovalStatus.EXECUTED.value
    assert confirm_res.card_id == "card_jwt_789"
    assert confirm_res.card_url == "https://trello.com/c/mockJwtCard"

    # Verify updated in database
    doc = await mock_db["pending_actions"].find_one({"action_id": created.action_id})
    assert doc["status"] == ApprovalStatus.EXECUTED.value
    assert doc["execution_result"] is not None


@pytest.mark.asyncio
async def test_duplicate_confirm_race_condition(mock_db):
    service = ApprovalService(mock_db)
    created = await service.create_task_draft(
        user_id="user_123",
        user_email="user@example.com",
        command="Create a card",
        intent="create_card",
        tool_id="trello_create_card",
        tool_name="Create Trello Card",
        category="TRELLO",
        parameters={"name": "Test Card"},
    )

    service.tool_executor.execute = AsyncMock(
        return_value=ExecutionResult(
            tool_id="trello_create_card",
            status="SUCCESS",
            is_mutation=True,
            result={"card": {"id": "c1", "url": "https://trello.com/c/c1"}},
            message="Done",
        )
    )

    # First confirmation succeeds
    await service.confirm_action(created.action_id, user_id="user_123", user_role="EMPLOYEE")

    # Second confirmation attempts race condition / double click -> raises ApprovalAlreadyProcessedError
    with pytest.raises(ApprovalAlreadyProcessedError) as exc_info:
        await service.confirm_action(created.action_id, user_id="user_123", user_role="EMPLOYEE")
    assert "cannot be re-confirmed" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_expired_action_rejection(mock_db):
    service = ApprovalService(mock_db)
    created = await service.create_task_draft(
        user_id="user_123",
        user_email="user@example.com",
        command="Create an expired card",
        intent="create_card",
        tool_id="trello_create_card",
        tool_name="Create Trello Card",
        category="TRELLO",
        parameters={"name": "Old Card"},
    )

    # Backdate expiration time to 10 minutes ago
    past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    await mock_db["pending_actions"].update_one(
        {"action_id": created.action_id},
        {"$set": {"expires_at": past_time}},
    )

    # Confirm should reject with 410 ApprovalExpiredError
    with pytest.raises(ApprovalExpiredError):
        await service.confirm_action(created.action_id, user_id="user_123", user_role="EMPLOYEE")

    # Get preview should also detect expiration
    with pytest.raises(ApprovalExpiredError):
        await service.get_action(created.action_id, user_id="user_123", user_role="EMPLOYEE")


@pytest.mark.asyncio
async def test_unauthorized_user_rejection(mock_db):
    service = ApprovalService(mock_db)
    created = await service.create_task_draft(
        user_id="user_owner",
        user_email="owner@example.com",
        command="Create card",
        intent="create_card",
        tool_id="trello_create_card",
        tool_name="Create Card",
        category="TRELLO",
        parameters={"name": "Owner Card"},
    )

    # Attacker cannot confirm
    with pytest.raises(ApprovalUnauthorizedError):
        await service.confirm_action(created.action_id, user_id="user_attacker", user_role="EMPLOYEE")

    # Attacker cannot edit
    with pytest.raises(ApprovalUnauthorizedError):
        await service.edit_action(
            created.action_id,
            user_id="user_attacker",
            user_role="EMPLOYEE",
            edit_data=ApprovalEditRequest(title="Hacked"),
        )

    # Attacker cannot cancel
    with pytest.raises(ApprovalUnauthorizedError):
        await service.cancel_action(created.action_id, user_id="user_attacker", user_role="EMPLOYEE")


@pytest.mark.asyncio
async def test_edit_pending_action(mock_db):
    service = ApprovalService(mock_db)
    created = await service.create_task_draft(
        user_id="user_123",
        user_email="user@example.com",
        command="Create task to build search",
        intent="create_card",
        tool_id="trello_create_card",
        tool_name="Create Trello Card",
        category="TRELLO",
        parameters={"name": "Build search", "desc": "Initial spec", "list_name": "To Do"},
    )

    old_hash = created.payload_hash

    # Edit title, description, priority, and list
    edit_req = ApprovalEditRequest(
        title="Build ElasticSearch Indexing Pipeline",
        description="Updated detailed acceptance criteria with full test suite",
        list_name="In Progress",
        priority="HIGH",
        due_date="2026-12-01",
    )

    updated = await service.edit_action(
        action_id=created.action_id,
        user_id="user_123",
        user_role="EMPLOYEE",
        edit_data=edit_req,
    )

    assert updated.draft.title == "Build ElasticSearch Indexing Pipeline"
    assert updated.draft.description == "Updated detailed acceptance criteria with full test suite"
    assert updated.draft.list_name == "In Progress"
    assert updated.draft.priority == "HIGH"
    assert updated.draft.due_date == "2026-12-01"
    assert updated.payload_hash != old_hash
    assert updated.status == ApprovalStatus.PENDING.value


@pytest.mark.asyncio
async def test_cannot_edit_non_pending_action(mock_db):
    service = ApprovalService(mock_db)
    created = await service.create_task_draft(
        user_id="user_123",
        user_email="user@example.com",
        command="Create task",
        intent="create_card",
        tool_id="trello_create_card",
        tool_name="Create Card",
        category="TRELLO",
        parameters={"name": "Task"},
    )

    # Cancel action
    await service.cancel_action(created.action_id, user_id="user_123", user_role="EMPLOYEE")

    # Editing a cancelled action should fail with 409
    with pytest.raises(ApprovalAlreadyProcessedError):
        await service.edit_action(
            created.action_id,
            user_id="user_123",
            user_role="EMPLOYEE",
            edit_data=ApprovalEditRequest(title="Attempted edit"),
        )


@pytest.mark.asyncio
async def test_cancel_action(mock_db):
    service = ApprovalService(mock_db)
    created = await service.create_task_draft(
        user_id="user_123",
        user_email="user@example.com",
        command="Create task to cancel",
        intent="create_card",
        tool_id="trello_create_card",
        tool_name="Create Card",
        category="TRELLO",
        parameters={"name": "Task to cancel"},
    )

    cancel_res = await service.cancel_action(
        action_id=created.action_id,
        user_id="user_123",
        user_role="EMPLOYEE",
    )
    assert cancel_res.status == ApprovalStatus.REJECTED.value

    # Verify status in database
    doc = await mock_db["pending_actions"].find_one({"action_id": created.action_id})
    assert doc["status"] == ApprovalStatus.REJECTED.value

    # Cannot cancel again
    with pytest.raises(ApprovalAlreadyProcessedError):
        await service.cancel_action(created.action_id, user_id="user_123", user_role="EMPLOYEE")


def test_generate_related_description_cleans_prompt_echo():
    # Prompt echo should be discarded in favor of rich domain description
    desc = ApprovalService._generate_related_description(
        title="backend",
        command="create a card backend by thursday add member",
        raw_desc="Create backend card with due date Thursday and assigned to sourabh mishra.",
    )
    assert "backend architecture" in desc.lower() or "api endpoints" in desc.lower()
    assert "sourabh mishra" not in desc.lower()
    assert "create backend card with due date" not in desc.lower()


def test_generate_related_description_categories():
    frontend_desc = ApprovalService._generate_related_description("UI Redesign", "create card UI Redesign")
    assert "user interface" in frontend_desc.lower() or "client-side" in frontend_desc.lower()

    auth_desc = ApprovalService._generate_related_description("Login Auth", "create card Login Auth")
    assert "authentication" in auth_desc.lower() or "token" in auth_desc.lower()

    db_desc = ApprovalService._generate_related_description("MongoDB Schema", "create card MongoDB Schema")
    assert "data models" in db_desc.lower() or "persistence" in db_desc.lower()


def test_generate_related_description_preserves_custom_notes():
    custom_desc = "Special note: ensure backward compatibility with v1 API clients."
    desc = ApprovalService._generate_related_description(
        title="v2 Release",
        command='create card v2 Release with description "Special note: ensure backward compatibility with v1 API clients."',
        raw_desc=custom_desc,
    )
    assert desc == custom_desc


@pytest.mark.asyncio
async def test_move_card_preserves_existing_description(mock_db):
    """Verify that moving a card retains the card's existing description and does NOT overwrite it with a move command string."""
    service = ApprovalService(db=mock_db)

    # Seed an existing task with an original description in mock_db
    await mock_db["task_assignments"].insert_one({
        "task_title": "Hr-atlas",
        "task_description": "Configure authorization checks and access controls across systems.",
    })

    preview = await service.create_task_draft(
        user_id="user123",
        user_email="user@example.com",
        command="move card Hr-atlas to DONE",
        intent="move_card",
        tool_id="trello_move_card",
        tool_name="Move Trello Card",
        category="TRELLO",
        action_type="MOVE_CARD",
        parameters={"card_name": "Hr-atlas", "target_status": "DONE", "card_id": "c101", "list_id": "l_done"},
    )

    # Description must be the existing card's description, NOT "Move card 'Hr-atlas' to DONE."
    assert preview.draft.description == "Configure authorization checks and access controls across systems."
    # Parameters sent to execution must NOT overwrite the description on Trello
    assert "desc" not in preview.draft.parameters
    assert "description" not in preview.draft.parameters


