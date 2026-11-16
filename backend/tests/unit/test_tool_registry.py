import pytest
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.tool_registry.schemas import ToolRegisterRequest, ToolUpdateRequest
from app.tool_registry.service import ToolRegistryService
from app.tool_registry.validators import validate_input_schema, validate_tool_metadata


def test_validate_input_schema_valid():
    valid_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "count": {"type": "integer"},
        },
        "required": ["title"],
    }
    # Should not raise
    validate_input_schema(valid_schema)


def test_validate_input_schema_invalid():
    with pytest.raises(ValidationError):
        validate_input_schema({})

    with pytest.raises(ValidationError):
        validate_input_schema({"properties": {}})  # Missing root "type"


def test_validate_tool_metadata():
    # Valid
    validate_tool_metadata("trello_create_card", "Create Card", "1.0.0", "trello_create_card")

    # Invalid ID
    with pytest.raises(ValidationError):
        validate_tool_metadata("INVALID ID WITH SPACES", "Create Card", "1.0.0", "key")

    # Invalid Version
    with pytest.raises(ValidationError):
        validate_tool_metadata("valid_id", "Create Card", "not-a-semver", "key")


@pytest.mark.asyncio
async def test_tool_registry_crud(mock_db):
    service = ToolRegistryService(mock_db)

    # 1. Register a new tool
    req = ToolRegisterRequest(
        tool_id="test_custom_tool",
        name="Custom Test Tool",
        description="A specialized test tool for registry validation.",
        category="testing",
        keywords=["test", "custom", "specialized"],
        synonyms=["run custom", "test action"],
        capabilities=["custom_test"],
        input_schema={
            "type": "object",
            "properties": {"param1": {"type": "string"}},
            "required": ["param1"],
        },
        permissions=["ADMIN", "MANAGER"],
        executor_type="mock",
        executor_key="mock.echo",
        version="1.0.0",
        enabled=True,
        approval_required=False,
    )
    created = await service.register_tool(req)
    assert created.tool_id == "test_custom_tool"
    assert created.enabled is True
    assert created.version == "1.0.0"

    # 2. Reject duplicate tool_id
    with pytest.raises(ConflictError):
        await service.register_tool(req)

    # 3. Reject duplicate name
    dup_name_req = req.model_copy(update={"tool_id": "another_unique_id"})
    with pytest.raises(ConflictError):
        await service.register_tool(dup_name_req)

    # 4. Retrieve tool
    fetched = await service.get_tool("test_custom_tool")
    assert fetched.tool_id == "test_custom_tool"
    assert fetched.name == "Custom Test Tool"

    # Non-existent tool
    with pytest.raises(NotFoundError):
        await service.get_tool("non_existent_tool_xyz")

    # 5. Update tool version and metadata
    update_req = ToolUpdateRequest(
        version="1.1.0",
        description="Updated description for custom test tool.",
    )
    updated = await service.update_tool("test_custom_tool", update_req)
    assert updated.version == "1.1.0"
    assert updated.description == "Updated description for custom test tool."

    # 6. Disable tool
    disabled = await service.disable_tool("test_custom_tool")
    assert disabled.enabled is False

    # 7. Enable tool
    re_enabled = await service.enable_tool("test_custom_tool")
    assert re_enabled.enabled is True

    # 8. List tools pagination
    tool_list = await service.list_tools(page=1, page_size=10)
    assert tool_list.total >= 1
    assert any(t.tool_id == "test_custom_tool" for t in tool_list.tools)

