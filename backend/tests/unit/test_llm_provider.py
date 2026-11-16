import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel

from app.ai.llm_provider import (
    BaseLLMProvider,
    GoogleGenAIProvider,
    OpenAIProvider,
    LLMConfigurationError,
    LLMExecutionError,
)
from app.ai.model_config import ProviderConfig, LLMProviderType
from app.ai.provider_factory import LLMProviderFactory
from app.ai.prompts import build_interpretation_prompt, get_langchain_prompt_template
from app.ai.schemas import GeminiIntentOutput
from app.ai.service import AIService
from app.tool_discovery.schemas import DiscoveredToolItem
from app.tool_registry.schemas import ToolResponse


def create_sample_tools():
    tool = ToolResponse(
        tool_id="trello_create_card",
        name="Create Trello Card",
        description="Creates a card on Trello.",
        category="trello",
        keywords=["card", "create"],
        synonyms=[],
        capabilities=["create_card"],
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
        permissions=["EMPLOYEE"],
        executor_type="trello",
        executor_key="trello_create_card",
        version="1.0.0",
        enabled=True,
        approval_required=True,
        created_at="2026-11-12T00:00:00Z",
        updated_at="2026-11-12T00:00:00Z",
    )
    return [DiscoveredToolItem(tool=tool, relevance_score=0.9, matched_by=["keyword:card"], explanation="Matched")]


def test_provider_config_google_default():
    config = ProviderConfig.from_settings("google")
    assert config.provider == LLMProviderType.GOOGLE
    assert config.model_name is not None


def test_provider_config_openai():
    config = ProviderConfig.from_settings("openai")
    assert config.provider == LLMProviderType.OPENAI
    assert "gpt" in config.model_name or config.model_name == "gpt-4o-mini"


def test_provider_config_invalid():
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        ProviderConfig.from_settings("unsupported_provider_xyz")


def test_provider_factory_google():
    provider = LLMProviderFactory.create_provider("google")
    assert isinstance(provider, GoogleGenAIProvider)
    assert provider.provider_name == "google"


def test_provider_factory_openai():
    provider = LLMProviderFactory.create_provider("openai")
    assert isinstance(provider, OpenAIProvider)
    assert provider.provider_name == "openai"


def test_provider_configuration_status():
    unconf_google = GoogleGenAIProvider(ProviderConfig(provider=LLMProviderType.GOOGLE, model_name="gemini-3.5-flash-lite", api_key=""))
    assert unconf_google.is_configured() is False

    conf_google = GoogleGenAIProvider(ProviderConfig(provider=LLMProviderType.GOOGLE, model_name="gemini-3.5-flash-lite", api_key="fake-key"))
    assert conf_google.is_configured() is True

    unconf_openai = OpenAIProvider(ProviderConfig(provider=LLMProviderType.OPENAI, model_name="gpt-4o-mini", api_key=""))
    assert unconf_openai.is_configured() is False

    conf_openai = OpenAIProvider(ProviderConfig(provider=LLMProviderType.OPENAI, model_name="gpt-4o-mini", api_key="sk-fake"))
    assert conf_openai.is_configured() is True


@pytest.mark.asyncio
async def test_unconfigured_providers_raise_configuration_error():
    unconf_google = GoogleGenAIProvider(ProviderConfig(provider=LLMProviderType.GOOGLE, model_name="gemini-3.5-flash-lite", api_key=""))
    with pytest.raises(LLMConfigurationError):
        await unconf_google.generate_text("Hello")

    with pytest.raises(LLMConfigurationError):
        await unconf_google.generate_structured("Hello", GeminiIntentOutput)

    unconf_openai = OpenAIProvider(ProviderConfig(provider=LLMProviderType.OPENAI, model_name="gpt-4o-mini", api_key=""))
    with pytest.raises(LLMConfigurationError):
        await unconf_openai.generate_text("Hello")

    with pytest.raises(LLMConfigurationError):
        await unconf_openai.generate_structured("Hello", GeminiIntentOutput)


@pytest.mark.asyncio
async def test_ai_service_fallback_on_unconfigured_provider():
    unconf_provider = GoogleGenAIProvider(ProviderConfig(provider=LLMProviderType.GOOGLE, model_name="gemini-3.5-flash-lite", api_key=""))
    service = AIService(provider=unconf_provider)
    tools = create_sample_tools()

    result = await service.interpret_command("Create a card named Setup Database in TODO", tools)
    assert result.intent == "create_card"
    assert "Setup Database" in result.parameters["name"]
    assert result.parameters["list_name"] == "TODO"
    assert result.suggested_tool_id == "trello_create_card"


@pytest.mark.asyncio
async def test_ai_service_with_structured_provider():
    mock_provider = MagicMock(spec=BaseLLMProvider)
    mock_provider.is_configured.return_value = True
    mock_provider.provider_name = "google"
    mock_provider.model_name = "gemini-3.5-flash-lite"

    expected_output = GeminiIntentOutput(
        intent="create_card",
        entity="card",
        parameters={"name": "LangChain Migration Task", "list_name": "To Do"},
        suggested_tool_id="trello_create_card",
        requires_clarification=False,
        confidence=0.99,
    )
    mock_provider.generate_structured = AsyncMock(return_value=expected_output)

    service = AIService(provider=mock_provider)
    tools = create_sample_tools()

    result = await service.interpret_command("Create task LangChain Migration Task", tools)
    assert result.intent == "create_card"
    assert result.parameters["name"] == "LangChain Migration Task"
    assert result.suggested_tool_id == "trello_create_card"
    assert result.confidence == 0.99


@pytest.mark.asyncio
async def test_ai_service_invalid_suggested_tool_rectification():
    mock_provider = MagicMock(spec=BaseLLMProvider)
    mock_provider.is_configured.return_value = True
    mock_provider.provider_name = "openai"
    mock_provider.model_name = "gpt-4o-mini"

    # Model returned a nonexistent tool ID
    invalid_tool_output = GeminiIntentOutput(
        intent="create_card",
        entity="card",
        parameters={"name": "Test Tool Fallback"},
        suggested_tool_id="nonexistent_tool_xyz",
        requires_clarification=False,
        confidence=0.9,
    )
    mock_provider.generate_structured = AsyncMock(return_value=invalid_tool_output)

    service = AIService(provider=mock_provider)
    tools = create_sample_tools()

    result = await service.interpret_command("Create task", tools)
    # Rectified to first available discovered tool
    assert result.suggested_tool_id == "trello_create_card"


def test_ai_service_runtime_provider_switching():
    service = AIService(provider_type="google")
    assert service.provider.provider_name == "google"

    service.switch_provider("openai")
    assert service.provider.provider_name == "openai"


def test_langchain_prompt_template_generation():
    template = get_langchain_prompt_template()
    messages = template.format_messages(command="List all tasks", tools_context="[]")
    assert len(messages) == 2
    assert "intent interpretation engine" in messages[0].content
    assert "List all tasks" in messages[1].content

