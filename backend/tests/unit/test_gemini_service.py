from unittest.mock import AsyncMock, patch
import pytest
from app.integrations.gemini.client import GeminiClient
from app.integrations.gemini.exceptions import (
    GeminiAPIError,
    GeminiNotConfiguredError,
    GeminiParsingError,
    GeminiRateLimitError,
    GeminiTimeoutError,
)
from app.integrations.gemini.schemas import GeminiIntentOutput
from app.integrations.gemini.service import GeminiService
from app.tool_discovery.schemas import DiscoveredToolItem
from app.tool_registry.schemas import ToolResponse


def create_sample_discovered_tool():
    tool = ToolResponse(
        tool_id="trello_create_card",
        name="Create Trello Card",
        description="Creates a new card on the board.",
        category="trello",
        keywords=["card", "create", "new"],
        synonyms=["add a card"],
        capabilities=["create_card"],
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        permissions=["EMPLOYEE", "ADMIN"],
        executor_type="trello",
        executor_key="trello_create_card",
        version="1.0.0",
        enabled=True,
        approval_required=True,
        created_at="2026-11-12T00:00:00Z",
        updated_at="2026-11-12T00:00:00Z",
    )
    return [
        DiscoveredToolItem(
            tool=tool,
            relevance_score=0.95,
            matched_by=["keyword:card"],
            explanation="Selected Create Trello Card",
        )
    ]


@pytest.mark.asyncio
async def test_gemini_valid_structured_response():
    mock_client = AsyncMock(spec=GeminiClient)
    mock_client.generate_structured_content.return_value = """
    {
        "intent": "create_card",
        "entity": "card",
        "parameters": {
            "name": "Implement OAuth2 Flow",
            "list_name": "TODO"
        },
        "suggested_tool_id": "trello_create_card",
        "requires_clarification": false,
        "clarification_message": null,
        "confidence": 0.98
    }
    """

    service = GeminiService(client=mock_client)
    tools = create_sample_discovered_tool()

    result = await service.interpret_command("Create a card named Implement OAuth2 Flow", tools)
    assert isinstance(result, GeminiIntentOutput)
    assert result.intent == "create_card"
    assert result.parameters["name"] == "Implement OAuth2 Flow"
    assert result.suggested_tool_id == "trello_create_card"
    assert result.requires_clarification is False
    assert result.confidence == 0.98


@pytest.mark.asyncio
async def test_gemini_markdown_wrapped_json():
    mock_client = AsyncMock(spec=GeminiClient)
    mock_client.generate_structured_content.return_value = """```json
    {
        "intent": "create_card",
        "entity": "card",
        "parameters": {"name": "Fix Bug 123"},
        "suggested_tool_id": "trello_create_card",
        "requires_clarification": false,
        "confidence": 0.95
    }
    ```"""

    service = GeminiService(client=mock_client)
    tools = create_sample_discovered_tool()

    result = await service.interpret_command("Create card Fix Bug 123", tools)
    assert result.intent == "create_card"
    assert result.parameters["name"] == "Fix Bug 123"


@pytest.mark.asyncio
async def test_gemini_invalid_json_handling():
    mock_client = AsyncMock(spec=GeminiClient)
    mock_client.generate_structured_content.return_value = "This is not valid JSON at all."

    service = GeminiService(client=mock_client)
    tools = create_sample_discovered_tool()

    with pytest.raises(GeminiParsingError):
        await service.interpret_command("Some command", tools)


@pytest.mark.asyncio
async def test_gemini_missing_required_fields():
    mock_client = AsyncMock(spec=GeminiClient)
    # Missing required 'intent' field
    mock_client.generate_structured_content.return_value = """
    {
        "entity": "card",
        "parameters": {}
    }
    """

    service = GeminiService(client=mock_client)
    tools = create_sample_discovered_tool()

    with pytest.raises(GeminiParsingError):
        await service.interpret_command("Some command", tools)


@pytest.mark.asyncio
async def test_gemini_deterministic_fallback_when_unconfigured():
    # Client with no api key raises GeminiNotConfiguredError
    unconfigured_client = GeminiClient(api_key="")
    service = GeminiService(client=unconfigured_client)
    tools = create_sample_discovered_tool()

    # 1. Card creation fallback
    res1 = await service.interpret_command("Create a card named Login API in TODO", tools)
    assert res1.intent == "create_card"
    assert "Login API" in res1.parameters["name"]
    assert res1.parameters["list_name"] == "TODO"
    assert res1.suggested_tool_id == "trello_create_card"

    # 2. Card move fallback
    res2 = await service.interpret_command("Move Login API card to IN_PROGRESS", tools)
    assert res2.intent == "move_card"
    assert "Login API" in res2.parameters["card_name"]
    assert res2.parameters["target_status"] == "IN_PROGRESS"

    # 3. Ambiguous fallback
    res3 = await service.interpret_command("Random nonsense without meaning", [])
    assert res3.requires_clarification is True
    assert res3.intent == "unknown"


@pytest.mark.asyncio
async def test_gemini_client_timeout():
    mock_client = GeminiClient(api_key="mock_key")
    with patch.object(mock_client, "_get_client") as mock_get:
        import time
        from unittest.mock import MagicMock

        def hanging_call(*args, **kwargs):
            time.sleep(0.5)
            mock_res = MagicMock()
            mock_res.text = "{}"
            return mock_res

        mock_model = MagicMock()
        mock_model.generate_content.side_effect = hanging_call
        mock_get.return_value.models = mock_model

        with pytest.raises(GeminiTimeoutError):
            await mock_client.generate_structured_content("Test", timeout_seconds=0.05)
