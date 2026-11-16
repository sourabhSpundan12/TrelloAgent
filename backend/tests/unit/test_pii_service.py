import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from presidio_analyzer import RecognizerResult

from app.core.exceptions import PIIMaskingError
from app.privacy.service import PIIService
from app.privacy.schemas import PIIMaskResult
from app.ai.service import AIService
from app.ai.schemas import GeminiIntentOutput
from app.tool_discovery.schemas import DiscoveredToolItem
from app.tool_registry.schemas import ToolResponse


@pytest.fixture(scope="module")
def pii_service():
    """Initializes shared PIIService instance for test suite."""
    return PIIService()


class TestStandardEntityDetection:
    def test_detect_person_and_preserve_relative_dates(self, pii_service):
        text = "Schedule sync with Alice Smith tomorrow afternoon"
        result = pii_service.mask_text(text)
        assert "[PERSON_1]" in result.masked_text
        assert "tomorrow" in result.masked_text
        assert result.mapping["[PERSON_1]"] == "Alice Smith"
        restored = pii_service.restore_text(result.masked_text, result.mapping)
        assert restored == text

    def test_detect_email(self, pii_service):
        text = "Contact support at test.user@enterprise.org regarding the server"
        result = pii_service.mask_text(text)
        assert "[EMAIL_ADDRESS_1]" in result.masked_text
        assert result.mapping["[EMAIL_ADDRESS_1]"] == "test.user@enterprise.org"
        assert pii_service.restore_text(result.masked_text, result.mapping) == text

    def test_detect_ip_address(self, pii_service):
        text = "Database host is at 10.0.4.15 and port 5432"
        result = pii_service.mask_text(text)
        assert "[IP_ADDRESS_1]" in result.masked_text
        assert result.mapping["[IP_ADDRESS_1]"] == "10.0.4.15"
        assert pii_service.restore_text(result.masked_text, result.mapping) == text

    def test_detect_url(self, pii_service):
        text = "View deployment metrics at https://monitoring.internal.net/dashboards/12"
        result = pii_service.mask_text(text)
        assert "[URL_1]" in result.masked_text
        assert result.mapping["[URL_1]"] == "https://monitoring.internal.net/dashboards/12"
        assert pii_service.restore_text(result.masked_text, result.mapping) == text

    def test_detect_credit_card(self, pii_service):
        # Valid Luhn test card number (Visa standard test)
        text = "Process transaction using card 4111-1111-1111-1111"
        result = pii_service.mask_text(text)
        assert "[CREDIT_CARD_1]" in result.masked_text
        assert result.mapping["[CREDIT_CARD_1]"] == "4111-1111-1111-1111"
        assert pii_service.restore_text(result.masked_text, result.mapping) == text

    def test_detect_iban(self, pii_service):
        text = "Remit payment to account GB33BUKB20201555555555"
        result = pii_service.mask_text(text)
        assert "[IBAN_CODE_1]" in result.masked_text
        assert result.mapping["[IBAN_CODE_1]"] == "GB33BUKB20201555555555"
        assert pii_service.restore_text(result.masked_text, result.mapping) == text

    def test_detect_us_ssn(self, pii_service):
        text = "Employee social security number is 219-45-7819"
        result = pii_service.mask_text(text)
        assert "[US_SSN_1]" in result.masked_text
        assert result.mapping["[US_SSN_1]"] == "219-45-7819"
        assert pii_service.restore_text(result.masked_text, result.mapping) == text

    def test_detect_location(self, pii_service):
        text = "Ship inventory to warehouse in Berlin"
        result = pii_service.mask_text(text)
        assert "[LOCATION_1]" in result.masked_text
        assert result.mapping["[LOCATION_1]"] == "Berlin"
        assert pii_service.restore_text(result.masked_text, result.mapping) == text


class TestIndianCustomRecognizers:
    def test_indian_phone_with_country_code(self, pii_service):
        text = "Contact support on +91 9876543210 for urgent assistance"
        result = pii_service.mask_text(text)
        assert "[PHONE_NUMBER_1]" in result.masked_text
        assert result.mapping["[PHONE_NUMBER_1]"] == "+91 9876543210"
        assert pii_service.restore_text(result.masked_text, result.mapping) == text

    def test_indian_phone_bare_with_context(self, pii_service):
        text = "Call 9876543210 regarding the task status"
        result = pii_service.mask_text(text)
        assert "[PHONE_NUMBER_1]" in result.masked_text
        assert result.mapping["[PHONE_NUMBER_1]"] == "9876543210"

    def test_indian_phone_bare_without_context_is_not_masked(self, pii_service):
        text = "Task item ID 9876543210 completed successfully"
        result = pii_service.mask_text(text)
        # Should not falsely mask an arbitrary 10-digit ID as phone number
        assert "9876543210" in result.masked_text
        assert not any(e.entity_type == "PHONE_NUMBER" for e in result.detected_entities)

    def test_pan_number_detection(self, pii_service):
        text = "Taxpayer PAN card number is ABCDE1234F"
        result = pii_service.mask_text(text)
        assert "[IN_PAN_1]" in result.masked_text
        assert result.mapping["[IN_PAN_1]"] == "ABCDE1234F"
        assert pii_service.restore_text(result.masked_text, result.mapping) == text

    def test_aadhaar_number_detection(self, pii_service):
        text = "Customer Aadhaar identity is 2345 6789 0123"
        result = pii_service.mask_text(text)
        assert "[IN_AADHAAR_1]" in result.masked_text
        assert result.mapping["[IN_AADHAAR_1]"] == "2345 6789 0123"
        assert pii_service.restore_text(result.masked_text, result.mapping) == text

    def test_aadhaar_does_not_falsely_mask_credit_card(self, pii_service):
        text = "Pay using card 4111-1111-1111-1111 on checkout"
        result = pii_service.mask_text(text)
        # Should not be masked as Aadhaar
        assert not any(e.entity_type == "IN_AADHAAR" for e in result.detected_entities)

    def test_indian_passport_detection(self, pii_service):
        text = "Travel passport number is Z1234567 for onboarding"
        result = pii_service.mask_text(text)
        assert "[IN_PASSPORT_1]" in result.masked_text
        assert result.mapping["[IN_PASSPORT_1]"] == "Z1234567"
        assert pii_service.restore_text(result.masked_text, result.mapping) == text


class TestPlaceholderConsistencyAndDeduplication:
    def test_repeated_entity_receives_identical_placeholder(self, pii_service):
        text = "Assign task to Vikram Verma and confirm Vikram Verma is notified"
        result = pii_service.mask_text(text)
        assert result.masked_text.count("[PERSON_1]") == 2
        assert "[PERSON_2]" not in result.masked_text
        assert len(result.mapping) == 1
        assert result.mapping["[PERSON_1]"] == "Vikram Verma"
        assert pii_service.restore_text(result.masked_text, result.mapping) == text


class TestRequestIsolation:
    def test_separate_requests_maintain_isolated_mappings(self, pii_service):
        req_a_text = "Notify Alice Cooper at alice@wonder.com"
        req_b_text = "Notify Bob Dylan at bob@music.org"

        res_a = pii_service.mask_text(req_a_text)
        res_b = pii_service.mask_text(req_b_text)

        # Mappings must be distinct objects
        assert res_a.mapping != res_b.mapping
        assert res_a.mapping.get("[EMAIL_ADDRESS_1]") == "alice@wonder.com"
        assert res_b.mapping.get("[EMAIL_ADDRESS_1]") == "bob@music.org"

        # Cross-restoration safety
        restored_a = pii_service.restore_text(res_a.masked_text, res_a.mapping)
        assert "Alice" in restored_a
        assert "Bob" not in restored_a


class TestDictAndTextRestoration:
    def test_restore_nested_dictionary(self, pii_service):
        mapping = {
            "[PERSON_1]": "John Doe",
            "[EMAIL_ADDRESS_1]": "john@doe.com",
            "[PHONE_NUMBER_1]": "+91 9988776655",
        }
        nested_data = {
            "title": "Onboard [PERSON_1]",
            "contact": {
                "email": "[EMAIL_ADDRESS_1]",
                "phone": "[PHONE_NUMBER_1]",
            },
            "tags": ["employee", "[PERSON_1]"],
            "count": 42,
        }
        restored = pii_service.restore_dict(nested_data, mapping)
        assert restored["title"] == "Onboard John Doe"
        assert restored["contact"]["email"] == "john@doe.com"
        assert restored["contact"]["phone"] == "+91 9988776655"
        assert restored["tags"] == ["employee", "John Doe"]
        assert restored["count"] == 42


class TestFailClosedBehavior:
    def test_masking_failure_raises_pii_masking_error(self, pii_service):
        with patch.object(pii_service.analyzer, "analyze", side_effect=RuntimeError("Presidio crashed")):
            with pytest.raises(PIIMaskingError) as exc_info:
                pii_service.mask_text("Check user at test@example.com")
            assert "PII detection failed" in str(exc_info.value.message)

    def test_analyzer_uninitialized_raises_pii_masking_error(self):
        broken_service = PIIService()
        broken_service.analyzer = None
        with pytest.raises(PIIMaskingError) as exc_info:
            broken_service.mask_text("Some text")
        assert "Presidio Analyzer is not initialized" in str(exc_info.value.message)


class TestDisabledConfiguration:
    def test_disabled_pii_masking_returns_original_text(self, pii_service):
        with patch.object(pii_service, "enabled", False):
            text = "Send credentials to confidential@company.com"
            result = pii_service.mask_text(text)
            assert result.masked_text == text
            assert result.detected_entities == []
            assert result.mapping == {}


@pytest.mark.asyncio
class TestAIServicePromptSanitization:
    async def test_ai_service_sends_only_masked_prompt_to_llm(self, pii_service):
        mock_provider = MagicMock()
        mock_provider.is_configured.return_value = True
        mock_provider.provider_name = "mock_provider"
        mock_provider.model_name = "mock_model"

        # Mock LLM returning structured output referencing the masked entity
        mock_intent_output = GeminiIntentOutput(
            intent="create_card",
            entity="card",
            parameters={
                "name": "Meeting with [PERSON_1]",
                "desc": "Email him at [EMAIL_ADDRESS_1]",
            },
            suggested_tool_id="trello_create_card",
            requires_clarification=False,
            confidence=0.98,
        )
        mock_provider.generate_structured = AsyncMock(return_value=mock_intent_output)

        ai_service = AIService(provider=mock_provider, pii_service=pii_service)

        dummy_tool = DiscoveredToolItem(
            tool=ToolResponse(
                tool_id="trello_create_card",
                name="Create Card",
                description="Creates a Trello card",
                category="trello",
                keywords=["card", "create"],
                synonyms=[],
                capabilities=["create_card"],
                input_schema={},
                permissions=["EMPLOYEE"],
                executor_type="trello",
                executor_key="trello_create_card",
                version="1.0.0",
                enabled=True,
                approval_required=True,
                created_at="2026-11-12T00:00:00Z",
                updated_at="2026-11-12T00:00:00Z",
            ),
            relevance_score=0.95,
            matched_by=["keyword:card"],
            explanation="Matched card creation tool",
        )

        user_cmd = "Create a card to sync with Rahul Verma and email rahul.verma@example.com"
        result = await ai_service.interpret_command(user_cmd, [dummy_tool])

        # 1. Verify what was passed to generate_structured
        called_prompt = mock_provider.generate_structured.call_args[0][0]
        # Must contain placeholders
        assert "[PERSON_1]" in called_prompt
        assert "[EMAIL_ADDRESS_1]" in called_prompt
        # Must NEVER contain original sensitive values
        assert "Rahul Verma" not in called_prompt
        assert "rahul.verma@example.com" not in called_prompt

        # 2. Verify returned output parameters were restored locally
        assert result.parameters["name"] == "Meeting with Rahul Verma"
        assert result.parameters["desc"] == "Email him at rahul.verma@example.com"

    async def test_technical_card_title_not_falsely_masked_as_person(self, pii_service):
        cmd = "create a task card Full Stack due date 21 novemeber 2026 and add member sourabh mishra"
        res = pii_service.mask_text(cmd)
        assert "Full Stack" in res.masked_text
        assert "[PERSON_1]" not in res.masked_text or res.mapping.get("[PERSON_1]") != "Full Stack"

    async def test_robust_restore_handles_llm_placeholder_normalization(self, pii_service):
        mapping = {"[PERSON_1]": "Full Stack"}
        # Tests case where LLM strips square brackets or changes casing
        assert pii_service.restore_text("Person 1", mapping) == "Full Stack"
        assert pii_service.restore_text("[Person 1]", mapping) == "Full Stack"
        assert pii_service.restore_text("Task card for Person 1, deliverables", mapping) == "Task card for Full Stack, deliverables"
