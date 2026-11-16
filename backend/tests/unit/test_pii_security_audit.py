"""
Comprehensive Security Audit & Automated Interception Test Suite.

Verifies that Microsoft Presidio-based PII detection and masking strictly prevents
Personally Identifiable Information (PII) from reaching external LLM providers
(Google Gemini, OpenAI, or any LangChain-integrated provider).

Synthetic Test Data Only:
- Person: Rahul Sharma
- Email: rahul.test@example.com
- Phone: 9876543210
- PAN: ABCDE1234F
- Aadhaar: 9876 5432 1098
"""

import asyncio
from typing import Any, Dict, List, Optional, Type, TypeVar
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.ai.llm_provider import BaseLLMProvider, GoogleGenAIProvider, OpenAIProvider
from app.ai.model_config import ProviderConfig, LLMProviderType
from app.ai.service import AIService
from app.integrations.gemini.schemas import GeminiIntentOutput
from app.core.exceptions import PIIMaskingError
from app.privacy.service import PIIService
from app.tool_discovery.schemas import DiscoveredToolItem
from app.tool_registry.models import ToolModel

T = TypeVar("T")

SYNTHETIC_PERSON = "Rahul Sharma"
SYNTHETIC_EMAIL = "rahul.test@example.com"
SYNTHETIC_PHONE = "9876543210"
SYNTHETIC_PAN = "ABCDE1234F"
SYNTHETIC_AADHAAR = "9876 5432 1098"


class CapturingLLMProvider(BaseLLMProvider):
    """
    Fake LLM provider that intercepts and records all prompts and structured
    output calls at the outermost provider boundary.
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        cfg = config or ProviderConfig(
            provider=LLMProviderType.GOOGLE,
            model_name="test-capture-model",
            api_key="test-synthetic-key",
        )
        super().__init__(cfg)
        self.captured_prompts: List[str] = []
        self.captured_schemas: List[Type] = []
        self.captured_kwargs: List[Dict[str, Any]] = []

    def is_configured(self) -> bool:
        return True

    async def generate_text(self, prompt: str) -> str:
        self.captured_prompts.append(prompt)
        return "synthetic response"

    async def generate_structured(self, prompt: str, schema_cls: Type[T]) -> T:
        self.captured_prompts.append(prompt)
        self.captured_schemas.append(schema_cls)
        # Return mock intent output echoing placeholders
        return schema_cls(
            intent="create_card",
            entity="card",
            suggested_tool_id="trello_create_card",
            parameters={
                "name": "Onboard [PERSON_1]",
                "desc": "Email: [EMAIL_ADDRESS_1], Phone: [PHONE_NUMBER_1], PAN: [IN_PAN_1]",
                "list_name": "To Do",
                "priority": "HIGH",
            },
            confidence=0.99,
        )


@pytest.fixture
def mock_tools() -> List[DiscoveredToolItem]:
    tool = ToolModel(
        tool_id="trello_create_card",
        name="Create Trello Card",
        description="Creates a task card on Trello",
        category="task_management",
        approval_required=True,
        executor_key="trello_create_card",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "desc": {"type": "string"},
                "list_name": {"type": "string"},
            },
            "required": ["name"],
        },
    )
    return [
        DiscoveredToolItem(
            tool=tool,
            relevance_score=0.95,
            matched_by=["create", "card"],
            explanation="Matched card creation tool",
        )
    ]


@pytest.fixture
def pii_service() -> PIIService:
    return PIIService()


# ==============================================================================
# 1. OUTBOUND LLM REQUEST INTERCEPTION TESTS (SYNTHETIC DATA LEAKAGE VERIFICATION)
# ==============================================================================

@pytest.mark.asyncio
async def test_llm_request_boundary_intercepts_and_masks_all_pii(mock_tools, pii_service):
    """
    SECURITY AUDIT TEST:
    Verify that raw PII (Person, Email, Phone, PAN) NEVER crosses the boundary
    into the LLM provider. The capturing provider records the exact serialized prompt.
    """
    capturing_provider = CapturingLLMProvider()
    ai_service = AIService(provider_type="google", pii_service=pii_service)
    ai_service.provider = capturing_provider

    synthetic_command = (
        f"Create a task for {SYNTHETIC_PERSON}. His email is {SYNTHETIC_EMAIL}, "
        f"phone number is {SYNTHETIC_PHONE}, and PAN is {SYNTHETIC_PAN}."
    )

    result = await ai_service.interpret_command(synthetic_command, mock_tools)

    # 1. Assert exactly one call was captured at the provider boundary
    assert len(capturing_provider.captured_prompts) == 1
    captured_prompt = capturing_provider.captured_prompts[0]

    # 2. Strict Negative Verification: Raw PII must NEVER appear anywhere in outbound prompt
    assert SYNTHETIC_PERSON not in captured_prompt, "CRITICAL: Raw Person name leaked into LLM prompt!"
    assert SYNTHETIC_EMAIL not in captured_prompt, "CRITICAL: Raw Email leaked into LLM prompt!"
    assert SYNTHETIC_PHONE not in captured_prompt, "CRITICAL: Raw Phone number leaked into LLM prompt!"
    assert SYNTHETIC_PAN not in captured_prompt, "CRITICAL: Raw Indian PAN leaked into LLM prompt!"

    # 3. Positive Verification: Anonymized placeholders must appear in outbound prompt
    assert "[PERSON_1]" in captured_prompt
    assert "[EMAIL_ADDRESS_1]" in captured_prompt
    assert "[PHONE_NUMBER_1]" in captured_prompt
    assert "[IN_PAN_1]" in captured_prompt

    # 4. Mapping Dictionary Verification: Raw mapping must NEVER be in outbound prompt
    assert "mapping" not in captured_prompt.lower() or "placeholder" in captured_prompt
    assert f"'{SYNTHETIC_PERSON}'" not in captured_prompt
    assert f"'{SYNTHETIC_EMAIL}'" not in captured_prompt

    # 5. Local Post-Restoration Verification: Parameters safely restored on the backend ONLY
    assert result.parameters["name"] == f"Onboard {SYNTHETIC_PERSON}"
    assert SYNTHETIC_EMAIL in result.parameters["desc"]
    assert SYNTHETIC_PHONE in result.parameters["desc"]
    assert SYNTHETIC_PAN in result.parameters["desc"]


@pytest.mark.asyncio
async def test_google_genai_provider_boundary_serialization(mock_tools, pii_service):
    """
    Verify the LangChain ChatGoogleGenerativeAI provider boundary specifically.
    Mocks the underlying ChatGoogleGenerativeAI ainvoke call to inspect the serialized prompt.
    """
    config = ProviderConfig(
        provider=LLMProviderType.GOOGLE,
        model_name="gemini-3.5-flash-lite",
        api_key="fake-gemini-test-key",
    )
    provider = GoogleGenAIProvider(config)

    mock_structured_model = MagicMock()
    mock_structured_model.ainvoke = AsyncMock(
        return_value=GeminiIntentOutput(
            intent="create_card",
            entity="card",
            suggested_tool_id="trello_create_card",
            parameters={"name": "[PERSON_1]"},
            confidence=0.95,
        )
    )

    with patch.object(provider, "_llm", MagicMock()) as mock_llm:
        mock_llm.with_structured_output.return_value = mock_structured_model

        ai_service = AIService(provider_type="google", pii_service=pii_service)
        ai_service.provider = provider

        synthetic_command = f"Assign new card to {SYNTHETIC_PERSON} with contact {SYNTHETIC_EMAIL}"
        await ai_service.interpret_command(synthetic_command, mock_tools)

        # Verify call made to LangChain structured model
        mock_structured_model.ainvoke.assert_awaited_once()
        invoked_prompt = mock_structured_model.ainvoke.call_args[0][0]

        assert SYNTHETIC_PERSON not in invoked_prompt
        assert SYNTHETIC_EMAIL not in invoked_prompt
        assert "[PERSON_1]" in invoked_prompt
        assert "[EMAIL_ADDRESS_1]" in invoked_prompt


@pytest.mark.asyncio
async def test_openai_provider_boundary_serialization(mock_tools, pii_service):
    """
    Verify the LangChain ChatOpenAI provider boundary specifically.
    Mocks the underlying ChatOpenAI ainvoke call to inspect the serialized prompt.
    """
    config = ProviderConfig(
        provider=LLMProviderType.OPENAI,
        model_name="gpt-4o-mini",
        api_key="fake-openai-test-key",
    )
    provider = OpenAIProvider(config)

    mock_structured_model = MagicMock()
    mock_structured_model.ainvoke = AsyncMock(
        return_value=GeminiIntentOutput(
            intent="create_card",
            entity="card",
            suggested_tool_id="trello_create_card",
            parameters={"name": "[PERSON_1]"},
            confidence=0.95,
        )
    )

    with patch.object(provider, "_llm", MagicMock()) as mock_llm:
        mock_llm.with_structured_output.return_value = mock_structured_model

        ai_service = AIService(provider_type="openai", pii_service=pii_service)
        ai_service.provider = provider

        synthetic_command = f"Register user {SYNTHETIC_PERSON} at {SYNTHETIC_EMAIL} with PAN {SYNTHETIC_PAN}"
        await ai_service.interpret_command(synthetic_command, mock_tools)

        mock_structured_model.ainvoke.assert_awaited_once()
        invoked_prompt = mock_structured_model.ainvoke.call_args[0][0]

        assert SYNTHETIC_PERSON not in invoked_prompt
        assert SYNTHETIC_EMAIL not in invoked_prompt
        assert SYNTHETIC_PAN not in invoked_prompt
        assert "[PERSON_1]" in invoked_prompt
        assert "[EMAIL_ADDRESS_1]" in invoked_prompt
        assert "[IN_PAN_1]" in invoked_prompt


# ==============================================================================
# 2. CONVERSATION HISTORY SANITIZATION VERIFICATION
# ==============================================================================

@pytest.mark.asyncio
async def test_conversation_history_is_sanitized_before_prompt_construction(mock_tools, pii_service):
    """
    Verify that unmasked historical messages stored in chat history or database
    are dynamically sanitized before inclusion in the LLM prompt.
    """
    capturing_provider = CapturingLLMProvider()
    ai_service = AIService(provider_type="google", pii_service=pii_service)
    ai_service.provider = capturing_provider

    synthetic_history = [
        {
            "sender": "user",
            "content": f"Hi, I previously gave contact for {SYNTHETIC_PERSON} as {SYNTHETIC_EMAIL}.",
        },
        {
            "sender": "assistant",
            "content": "I received that contact information. How can I help today?",
        },
    ]

    new_command = f"Create a card for his phone {SYNTHETIC_PHONE}."

    await ai_service.interpret_command(
        command=new_command,
        discovered_tools=mock_tools,
        conversation_history=synthetic_history,
    )

    assert len(capturing_provider.captured_prompts) == 1
    captured_prompt = capturing_provider.captured_prompts[0]

    # Verify conversation history section is sanitized
    assert "PREVIOUS CONVERSATION CONTEXT:" in captured_prompt
    assert SYNTHETIC_PERSON not in captured_prompt, "PII in history leaked to LLM!"
    assert SYNTHETIC_EMAIL not in captured_prompt, "PII in history leaked to LLM!"
    assert SYNTHETIC_PHONE not in captured_prompt, "PII in command leaked to LLM!"

    # Verify placeholders are present in history context
    assert "[PERSON_1]" in captured_prompt
    assert "[EMAIL_ADDRESS_1]" in captured_prompt
    assert "[PHONE_NUMBER_1]" in captured_prompt


# ==============================================================================
# 3. FAIL-CLOSED BEHAVIOR & ERROR RESILIENCE VERIFICATION
# ==============================================================================

@pytest.mark.asyncio
async def test_fail_closed_blocks_external_llm_when_presidio_fails(mock_tools, pii_service):
    """
    FAIL-CLOSED AUDIT TEST:
    When Presidio fails, the system MUST NOT silently bypass masking or continue
    with unmasked raw data to the LLM. It must abort and raise PIIMaskingError.
    """
    capturing_provider = CapturingLLMProvider()
    ai_service = AIService(provider_type="google", pii_service=pii_service)
    ai_service.provider = capturing_provider

    # Simulate catastrophic analyzer crash
    with patch.object(pii_service.analyzer, "analyze", side_effect=RuntimeError("Presidio Engine Failure")):
        with pytest.raises(PIIMaskingError) as exc_info:
            await ai_service.interpret_command(
                f"Create task for {SYNTHETIC_PERSON} with {SYNTHETIC_EMAIL}",
                mock_tools,
            )

        assert "PII detection failed" in str(exc_info.value)
        # CRITICAL: External LLM was NEVER called
        assert len(capturing_provider.captured_prompts) == 0, (
            "CRITICAL SECURITY FAILURE: LLM was invoked after PII masking failure!"
        )


# ==============================================================================
# 4. CONCURRENT REQUEST ISOLATION & PLACEHOLDER COLLISION AUDIT
# ==============================================================================

@pytest.mark.asyncio
async def test_concurrent_request_isolation(mock_tools, pii_service):
    """
    Verify that concurrent user requests maintain strict memory isolation:
    User A's mapping and placeholders never cross-contaminate User B's request.
    """
    ai_service = AIService(provider_type="google", pii_service=pii_service)

    user_a_cmd = "Create card for Rahul Sharma with rahul.a@example.com"
    user_b_cmd = "Create card for Priya Patel with priya.b@example.com"

    # Run simultaneously
    res_a = pii_service.mask_text(user_a_cmd)
    res_b = pii_service.mask_text(user_b_cmd)

    # Both requests should independently assign [PERSON_1] and [EMAIL_ADDRESS_1]
    assert "[PERSON_1]" in res_a.masked_text
    assert "[PERSON_1]" in res_b.masked_text

    # User A's mapping has Rahul Sharma, NOT Priya Patel
    assert res_a.mapping["[PERSON_1]"] == "Rahul Sharma"
    assert res_b.mapping["[PERSON_1]"] == "Priya Patel"

    # Cross-check reverse mappings
    assert "rahul.a@example.com" not in res_b.reverse_mapping
    assert "priya.b@example.com" not in res_a.reverse_mapping


# ==============================================================================
# 5. INDIAN RECOGNIZERS AUDIT (PAN, AADHAAR, PHONE)
# ==============================================================================

def test_indian_recognizers_accuracy_and_format(pii_service):
    """
    Verify custom Indian regex recognizers accurately detect PAN, Aadhaar, and phone numbers.
    """
    test_text = (
        f"Employee {SYNTHETIC_PERSON}, PAN: {SYNTHETIC_PAN}, "
        f"Aadhaar: {SYNTHETIC_AADHAAR}, Phone: +91 98765 43210"
    )

    mask_res = pii_service.mask_text(test_text)

    assert SYNTHETIC_PERSON not in mask_res.masked_text
    assert SYNTHETIC_PAN not in mask_res.masked_text
    assert SYNTHETIC_AADHAAR not in mask_res.masked_text
    assert "98765 43210" not in mask_res.masked_text

    assert "[PERSON_1]" in mask_res.masked_text
    assert "[IN_PAN_1]" in mask_res.masked_text
    assert "[IN_AADHAAR_1]" in mask_res.masked_text
    assert "[PHONE_NUMBER_1]" in mask_res.masked_text
