import pytest
from app.tool_executor.exceptions import (
    ApprovalRequiredError,
    ToolDisabledError,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolPermissionError,
    UnregisteredExecutorError,
)
from app.tool_executor.interfaces import ExecutionContext
from app.tool_executor.service import ToolExecutorService
from app.tool_registry.repository import ToolRepository


@pytest.mark.asyncio
async def test_tool_executor_policies(mock_db):
    repo = ToolRepository(mock_db)
    executor_service = ToolExecutorService(mock_db)

    # Seed test tool
    tool_doc = {
        "tool_id": "test_mutation_tool",
        "name": "Mutation Tool",
        "description": "Mutates data and requires approval.",
        "category": "trello",
        "keywords": ["mutate"],
        "synonyms": [],
        "capabilities": ["mutate"],
        "input_schema": {
            "type": "object",
            "properties": {
                "item_name": {"type": "string"},
                "priority": {"type": "string", "enum": ["LOW", "HIGH"]},
            },
            "required": ["item_name"],
        },
        "permissions": ["MANAGER", "ADMIN"],
        "executor_type": "mock",
        "executor_key": "trello_create_card",
        "version": "1.0.0",
        "enabled": True,
        "approval_required": True,
    }
    await repo.create(tool_doc)

    # 1. Unknown Tool Rejection
    with pytest.raises(ToolNotFoundError):
        await executor_service.execute(
            tool_id="completely_unknown_tool",
            parameters={"item_name": "Task"},
            context=ExecutionContext(user_id="u1", user_role="ADMIN"),
        )

    # 2. Unauthorized Execution Rejection (EMPLOYEE not in MANAGER, ADMIN)
    with pytest.raises(ToolPermissionError):
        await executor_service.execute(
            tool_id="test_mutation_tool",
            parameters={"item_name": "Task"},
            context=ExecutionContext(user_id="u1", user_role="EMPLOYEE"),
        )

    # 3. Invalid Input Parameter Rejection (fails schema)
    with pytest.raises(ToolInputValidationError):
        await executor_service.execute(
            tool_id="test_mutation_tool",
            parameters={"priority": "INVALID_ENUM_VALUE"},  # missing required 'item_name'
            context=ExecutionContext(user_id="u1", user_role="ADMIN"),
        )

    # 4. Approval Required Check (Unconfirmed invocation returns REQUIRES_APPROVAL)
    unconfirmed_result = await executor_service.execute(
        tool_id="test_mutation_tool",
        parameters={"item_name": "New Task", "priority": "HIGH"},
        context=ExecutionContext(user_id="u1", user_role="ADMIN", confirmed=False),
    )
    assert unconfirmed_result.status == "REQUIRES_APPROVAL"
    assert unconfirmed_result.payload_hash is not None
    assert unconfirmed_result.preview is not None

    # 5. Confirmed invocation executes successfully
    confirmed_result = await executor_service.execute(
        tool_id="test_mutation_tool",
        parameters={"item_name": "New Task", "priority": "HIGH"},
        context=ExecutionContext(user_id="u1", user_role="ADMIN", confirmed=True),
    )
    assert confirmed_result.status == "SUCCESS"
    assert confirmed_result.result is not None

    # 6. Disabled Tool Rejection
    await repo.set_enabled("test_mutation_tool", False)
    with pytest.raises(ToolDisabledError):
        await executor_service.execute(
            tool_id="test_mutation_tool",
            parameters={"item_name": "New Task"},
            context=ExecutionContext(user_id="u1", user_role="ADMIN"),
        )

    # 7. Unregistered Executor Rejection
    bad_executor_tool = {
        "tool_id": "bad_executor_tool",
        "name": "Bad Executor Tool",
        "description": "Tool pointing to non-existent executor.",
        "category": "system",
        "input_schema": {"type": "object"},
        "permissions": ["ADMIN"],
        "executor_type": "unknown",
        "executor_key": "non_existent_executor_key",
        "version": "1.0.0",
        "enabled": True,
        "approval_required": False,
    }
    await repo.create(bad_executor_tool)

    with pytest.raises(UnregisteredExecutorError):
        await executor_service.execute(
            tool_id="bad_executor_tool",
            parameters={},
            context=ExecutionContext(user_id="u1", user_role="ADMIN"),
        )


@pytest.mark.asyncio
async def test_trello_search_executor_list_name_matching():
    from unittest.mock import AsyncMock, patch
    from app.tool_executor.registry import MockTrelloSearchExecutor

    executor = MockTrelloSearchExecutor()
    mock_lists = {
        "status": "SUCCESS",
        "lists": [
            {"id": "list_guide_1", "name": "Trello Starter Guide"},
            {"id": "list_today_2", "name": "Today"},
        ]
    }
    mock_cards = {
        "status": "SUCCESS",
        "cards": [
            {"id": "c1", "name": "Manage your team's projects", "desc": "", "idList": "list_guide_1", "url": "https://trello.com/c/1"},
            {"id": "c2", "name": "backend", "desc": "Backend dev", "idList": "list_guide_1", "url": "https://trello.com/c/2"},
            {"id": "c3", "name": "frontend", "desc": "UI components", "idList": "list_guide_1", "url": "https://trello.com/c/3"},
            {"id": "c4", "name": "MCP", "desc": "MCP server", "idList": "list_today_2", "url": "https://trello.com/c/4"},
        ]
    }

    with patch("app.mcp_server.trello_tools.trello_list_lists", new=AsyncMock(return_value=mock_lists)), \
         patch("app.mcp_server.trello_tools.trello_list_cards", new=AsyncMock(return_value=mock_cards)), \
         patch("app.core.config.settings.TRELLO_API_KEY", "mock_key"), \
         patch("app.core.config.settings.TRELLO_TOKEN", "mock_token"):

        # 1. User passes query="Trello Starter Guide"
        res = await executor.execute(
            tool={"tool_id": "trello_search_cards"},
            parameters={"query": "Trello Starter Guide"},
            context=ExecutionContext(user_id="u1", user_role="EMPLOYEE", confirmed=True),
        )
        assert res.status == "SUCCESS"
        assert res.result["total"] == 3
        card_names = [c["name"] for c in res.result["cards"]]
        assert "Manage your team's projects" in card_names
        assert "backend" in card_names
        assert "frontend" in card_names
        assert "MCP" not in card_names

        # 2. User typo "trello started guide"
        res2 = await executor.execute(
            tool={"tool_id": "trello_search_cards"},
            parameters={"query": "trello started guide"},
            context=ExecutionContext(user_id="u1", user_role="EMPLOYEE", confirmed=True),
        )
        assert res2.result["total"] == 3


@pytest.mark.asyncio
async def test_trello_delete_executor_list_deletion():
    from unittest.mock import AsyncMock, patch
    from app.tool_executor.registry import MockTrelloArchiveCardExecutor

    executor = MockTrelloArchiveCardExecutor()
    mock_lists = {
        "status": "SUCCESS",
        "lists": [
            {"id": "list_guide_1", "name": "Trello Starter Guide"},
            {"id": "list_today_2", "name": "Today"},
        ]
    }
    mock_cards = {
        "status": "SUCCESS",
        "cards": [
            {"id": "c1", "name": "Manage your team's projects", "desc": "", "idList": "list_guide_1"},
            {"id": "c2", "name": "backend", "desc": "Backend dev", "idList": "list_guide_1"},
            {"id": "c3", "name": "frontend", "desc": "UI components", "idList": "list_guide_1"},
        ]
    }
    mock_delete = AsyncMock(return_value={"status": "SUCCESS"})

    with patch("app.mcp_server.trello_tools.trello_list_lists", new=AsyncMock(return_value=mock_lists)), \
         patch("app.mcp_server.trello_tools.trello_list_cards", new=AsyncMock(return_value=mock_cards)), \
         patch("app.mcp_server.trello_tools.trello_delete_card", new=mock_delete), \
         patch("app.core.config.settings.TRELLO_API_KEY", "mock_key"), \
         patch("app.core.config.settings.TRELLO_TOKEN", "mock_token"):

        res = await executor.execute(
            tool={"tool_id": "trello_delete_card"},
            parameters={"card_name": "Trello Starter Guide tasks"},
            context=ExecutionContext(user_id="u1", user_role="EMPLOYEE", confirmed=True),
        )
        assert res.status == "SUCCESS"
        assert res.result["total_deleted"] == 3
        assert len(res.result["deleted_cards"]) == 3
        assert mock_delete.call_count == 3

