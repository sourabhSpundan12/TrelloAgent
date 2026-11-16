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

