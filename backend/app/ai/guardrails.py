import re
import json
from typing import Any, Dict, List, Optional, Tuple, Type
from pydantic import BaseModel, ValidationError as PydanticValidationError

from app.core.logging import logger
from app.integrations.gemini.schemas import GeminiIntentOutput
from app.tool_discovery.schemas import DiscoveredToolItem


class GuardrailValidationError(Exception):
    """Raised when an LLM input or output violates security or formatting guardrails."""
    pass


class PromptInjectionError(GuardrailValidationError):
    """Raised when a prompt injection or jailbreak attempt is detected."""
    pass


class LLMGuardrails:
    """
    Enterprise-grade template-based guardrails engine.
    Controls LLM input/output safety, prevents prompt injection, and optimizes token consumption.
    """

    MAX_COMMAND_LENGTH = 1000
    MAX_HISTORY_TURNS = 6

    # Comprehensive Jailbreak / Prompt Injection Signatures
    PROMPT_INJECTION_PATTERNS = [
        r"(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|system|above)\s+(?:instructions|rules|prompts|commands|constraints)",
        r"(?:you\s+are\s+now|act\s+as)\s+(?:in\s+)?(?:developer\s+mode|unrestricted|dan|jailbroken|god\s+mode|sudo|root)",
        r"(?:bypass|disable|turn\s+off)\s+(?:all\s+)?(?:guardrails|safety|security|filters|restrictions)",
        r"(?:reveal|print|show|output|leak)\s+(?:your\s+)?(?:system\s+prompt|developer\s+prompt|initial\s+instructions|secret\s+key|api\s+key|token)",
        r"<\|(?:im_start|im_end|endoftext)\|>",
        r"\[(?:system|admin|root)\]\s*:",
        r"\b(?:eval|exec|import\s+os|import\s+sys|__import__|subprocess)\b",
    ]

    @classmethod
    def validate_input(cls, command: str) -> None:
        """
        Input Guardrail: Validates user input length and checks for prompt injection/jailbreak attacks.
        Raises PromptInjectionError or GuardrailValidationError if a violation is detected.
        """
        if not command or not command.strip():
            raise GuardrailValidationError("User command cannot be empty.")

        if len(command) > cls.MAX_COMMAND_LENGTH:
            raise GuardrailValidationError(
                f"Command length ({len(command)} chars) exceeds maximum safety limit ({cls.MAX_COMMAND_LENGTH} chars)."
            )

        cmd_lower = command.lower()
        for pat in cls.PROMPT_INJECTION_PATTERNS:
            if re.search(pat, cmd_lower, re.IGNORECASE):
                logger.warning(f"Prompt injection pattern detected: '{pat}' in command: '{command[:80]}...'")
                raise PromptInjectionError(
                    "Security assertion failed: Outbound request blocked due to prompt injection or policy violation."
                )

    @classmethod
    def optimize_token_footprint(
        cls,
        command: str,
        discovered_tools: List[DiscoveredToolItem],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, List[DiscoveredToolItem], Optional[List[Dict[str, Any]]], Dict[str, Any]]:
        """
        Token Optimization Guardrail:
        1. Compresses whitespace and extraneous conversational filler from command.
        2. Filters discovered tool schemas to only include relevant fields (eliminating schema bloat).
        3. Caps conversation history to the most recent relevant turns.
        Returns: (optimized_command, optimized_tools, optimized_history, metrics)
        """
        # 1. Clean command
        clean_cmd = re.sub(r"\s+", " ", command).strip()

        # 2. Trim and compact conversation history to avoid token accumulation
        optimized_history = None
        if conversation_history:
            trimmed = conversation_history[-cls.MAX_HISTORY_TURNS:]
            optimized_history = []
            for item in trimmed:
                msg_copy = dict(item)
                raw_c = str(msg_copy.get("content", ""))
                # Strip excessive whitespace and repetitive signatures
                cleaned_c = re.sub(r"\s+", " ", raw_c).strip()
                if len(cleaned_c) > 300:
                    cleaned_c = cleaned_c[:297] + "..."
                msg_copy["content"] = cleaned_c
                optimized_history.append(msg_copy)

        # 3. Discovered tools pruning (keep top 4 most relevant tools to save prompt tokens)
        optimized_tools = discovered_tools[:4] if len(discovered_tools) > 4 else list(discovered_tools)

        # 4. Metrics estimation (~4 chars per token rule of thumb)
        raw_chars = len(command) + sum(len(str(t.tool.model_dump())) for t in discovered_tools)
        if conversation_history:
            raw_chars += sum(len(str(m.get("content", ""))) for m in conversation_history)

        opt_chars = len(clean_cmd) + sum(len(str(t.tool.model_dump())) for t in optimized_tools)
        if optimized_history:
            opt_chars += sum(len(str(m.get("content", ""))) for m in optimized_history)

        raw_tokens_est = max(1, raw_chars // 4)
        opt_tokens_est = max(1, opt_chars // 4)
        savings_pct = max(0.0, round(((raw_tokens_est - opt_tokens_est) / raw_tokens_est) * 100, 1))

        metrics = {
            "estimated_original_tokens": raw_tokens_est,
            "estimated_optimized_tokens": opt_tokens_est,
            "tokens_saved": max(0, raw_tokens_est - opt_tokens_est),
            "savings_percentage": savings_pct,
            "history_turns_retained": len(optimized_history) if optimized_history else 0,
            "candidate_tools_count": len(optimized_tools),
        }

        logger.info(
            f"LLM Token Guardrail: Optimized {raw_tokens_est} -> {opt_tokens_est} tokens ({savings_pct}% saved)."
        )

        return clean_cmd, optimized_tools, optimized_history, metrics

    @classmethod
    def validate_output(
        cls,
        output: GeminiIntentOutput,
        discovered_tools: List[DiscoveredToolItem],
    ) -> GeminiIntentOutput:
        """
        Output Guardrail:
        1. Ensures confidence is strictly within [0.0, 1.0].
        2. Validates that suggested_tool_id exists among registered tools (anti-hallucination).
        3. Sanitizes extracted parameters (no code injection, bounds checking).
        """
        # Clamp confidence
        output.confidence = max(0.0, min(1.0, float(output.confidence)))

        # Anti-Hallucination: Verify suggested_tool_id exists
        valid_tool_ids = {item.tool.tool_id for item in discovered_tools}
        # Allow canonical built-in tools
        canonical_ids = {
            "trello_create_card", "trello_move_card", "trello_update_card",
            "trello_delete_card", "trello_archive_card", "trello_search_cards",
            "trello_create_list", "report_get_workload", "report_get_employee_tasks",
            "employee_recommend_assignment", "employee_list_directory"
        }
        all_valid_ids = valid_tool_ids.union(canonical_ids)

        if output.suggested_tool_id and output.suggested_tool_id not in all_valid_ids:
            logger.warning(
                f"Output Guardrail: Rejected hallucinated tool_id '{output.suggested_tool_id}'. Resetting to closest match or None."
            )
            # Find best match or clear
            matched = False
            for valid_id in all_valid_ids:
                if output.intent in valid_id or valid_id in output.intent:
                    output.suggested_tool_id = valid_id
                    matched = True
                    break
            if not matched:
                output.suggested_tool_id = None

        # Sanitize parameters
        sanitized_params: Dict[str, Any] = {}
        for k, v in output.parameters.items():
            if isinstance(v, str):
                # Clamp overly verbose strings (e.g. descriptions > 1000 chars)
                clean_v = v.strip()
                if len(clean_v) > 1000:
                    clean_v = clean_v[:997] + "..."
                # Strip null bytes or control characters
                clean_v = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", clean_v)
                sanitized_params[k] = clean_v
            else:
                sanitized_params[k] = v

        output.parameters = sanitized_params
        output.action_parameters = dict(sanitized_params)

        # Template Validation (Never allow hallucinated or invalid template IDs)
        if output.selected_template:
            from app.services.template_service import BUILTIN_TEMPLATES
            known_ids = {t["id"] for t in BUILTIN_TEMPLATES}
            if output.selected_template not in known_ids and not output.selected_template.startswith("tmpl_custom_"):
                logger.info(f"Output Guardrail: Resetting invalid selected_template '{output.selected_template}' to None.")
                output.selected_template = None

        # Low-Confidence & Ambiguity Guardrail (Never execute low-confidence or ambiguous actions)
        if output.confidence < 0.6 or output.missing_fields:
            output.requires_clarification = True
            if not output.clarification_message:
                if output.missing_fields:
                    output.clarification_message = f"Please clarify the following missing details: {', '.join(output.missing_fields)}."
                else:
                    output.clarification_message = "Your request seems ambiguous. Could you please provide more details?"

        return output

