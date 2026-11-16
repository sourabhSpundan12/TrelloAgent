import json
import re
from typing import Any, Dict, List, Optional
from pydantic import ValidationError as PydanticValidationError
from app.core.logging import logger
from app.integrations.gemini.client import GeminiClient
from app.integrations.gemini.exceptions import (
    GeminiNotConfiguredError,
    GeminiParsingError,
)
from app.integrations.gemini.prompts import build_interpretation_prompt
from app.integrations.gemini.schemas import GeminiIntentOutput
from app.tool_discovery.schemas import DiscoveredToolItem
from app.ai.service import AIService


class GeminiService:
    """
    Backwards-compatible interface for structured intent interpretation.
    Powered by LangChain provider-agnostic AIService under the hood,
    while fully preserving existing method signatures and testing harnesses.
    """

    def __init__(
        self,
        client: Optional[GeminiClient] = None,
        ai_service: Optional[AIService] = None,
    ):
        self.client = client
        self.ai_service = ai_service or AIService(provider_type="google")

    async def interpret_command(
        self,
        command: str,
        discovered_tools: List[DiscoveredToolItem],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        correlation_id: Optional[str] = None,
    ) -> GeminiIntentOutput:
        """
        Interprets natural language command against discovered tools.
        If a custom client is provided (common in unit tests), uses that client's output.
        Otherwise, routes through provider-agnostic AIService via LangChain.
        """
        if self.client is not None:
            mask_result = self.ai_service.pii_service.mask_text(command)
            sanitized_command = mask_result.masked_text
            combined_mapping = dict(mask_result.mapping)

            sanitized_history: Optional[List[Dict[str, Any]]] = None
            if conversation_history:
                sanitized_history = []
                for msg in conversation_history:
                    msg_copy = dict(msg)
                    raw_content = str(msg.get("content", ""))
                    h_mask = self.ai_service.pii_service.mask_text(raw_content)
                    msg_copy["content"] = h_mask.masked_text
                    combined_mapping.update(h_mask.mapping)
                    sanitized_history.append(msg_copy)

            prompt = build_interpretation_prompt(
                sanitized_command,
                discovered_tools,
                conversation_history=sanitized_history,
            )
            try:
                raw_text = await self.client.generate_structured_content(prompt)
                parsed = self._parse_and_validate(raw_text, discovered_tools)
                if combined_mapping:
                    parsed.parameters = self.ai_service.pii_service.restore_dict(
                        parsed.parameters, combined_mapping
                    )
                return parsed
            except GeminiNotConfiguredError:
                logger.info("Gemini API key not configured; using deterministic fallback interpreter.")
                output = self._fallback_deterministic_interpreter(sanitized_command, discovered_tools)
                if combined_mapping:
                    output.parameters = self.ai_service.pii_service.restore_dict(
                        output.parameters, combined_mapping
                    )
                return output
            except (GeminiParsingError, PydanticValidationError):
                raise
            except Exception as e:
                logger.warning(f"Gemini client call failed ({e}); attempting deterministic fallback.")
                output = self._fallback_deterministic_interpreter(sanitized_command, discovered_tools)
                if combined_mapping:
                    output.parameters = self.ai_service.pii_service.restore_dict(
                        output.parameters, combined_mapping
                    )
                return output

        return await self.ai_service.interpret_command(
            command,
            discovered_tools,
            conversation_history=conversation_history,
            correlation_id=correlation_id,
        )

    def _parse_and_validate(
        self,
        raw_text: str,
        discovered_tools: List[DiscoveredToolItem],
    ) -> GeminiIntentOutput:
        """Extracts JSON and validates against Pydantic schema."""
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as err:
            logger.error(f"Failed to decode JSON response: {cleaned}")
            raise GeminiParsingError(
                f"Invalid JSON returned: {err.msg}",
                details={"raw_response": cleaned[:200]},
            )

        try:
            parsed = GeminiIntentOutput(**data)
        except PydanticValidationError as err:
            logger.error(f"Response failed Pydantic validation: {err}")
            raise GeminiParsingError(
                "Response did not conform to the expected intent schema.",
                details={"validation_errors": err.errors()},
            )

        if parsed.suggested_tool_id:
            valid_ids = {item.tool.tool_id for item in discovered_tools}
            if parsed.suggested_tool_id not in valid_ids:
                logger.warning(
                    f"Suggested tool_id '{parsed.suggested_tool_id}' was not in discovered tools."
                )
                if discovered_tools:
                    parsed.suggested_tool_id = discovered_tools[0].tool.tool_id
                else:
                    parsed.suggested_tool_id = None

        return parsed

    def _fallback_deterministic_interpreter(
        self,
        command: str,
        discovered_tools: List[DiscoveredToolItem],
    ) -> GeminiIntentOutput:
        return self.ai_service._fallback_deterministic_interpreter(command, discovered_tools)
