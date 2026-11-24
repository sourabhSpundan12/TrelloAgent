import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple
from pydantic import ValidationError as PydanticValidationError

from app.ai.llm_provider import BaseLLMProvider, LLMConfigurationError, LLMExecutionError
from app.ai.provider_factory import LLMProviderFactory
from app.ai.prompts import build_interpretation_prompt
from app.ai.schemas import GeminiIntentOutput
from app.ai.guardrails import LLMGuardrails, PromptInjectionError, GuardrailValidationError
from app.approvals.service import ApprovalService
from app.core.exceptions import PIIMaskingError
from app.core.logging import logger
from app.privacy.service import PIIService
from app.privacy.terminal_logger import (
    PIITerminalLogger,
    current_mapping_var,
    current_req_id_var,
    current_synthetic_var,
    is_synthetic_prompt,
    is_terminal_logging_enabled,
)
from app.tool_discovery.schemas import DiscoveredToolItem


class AIService:
    """
    Provider-agnostic AI intent interpretation service using LangChain.
    Supports switching between Google Gemini, OpenAI, and future LLM providers.
    Includes deterministic fallback for offline environments and automated test suites.
    """

    def __init__(
        self,
        provider: Optional[BaseLLMProvider] = None,
        provider_type: Optional[str] = None,
        pii_service: Optional[PIIService] = None,
    ):
        self.pii_service = pii_service or PIIService()
        if provider is not None:
            self.provider = provider
        else:
            try:
                self.provider = LLMProviderFactory.create_provider(provider_type)
            except Exception as e:
                logger.warning(
                    f"Could not initialize provider '{provider_type}': {e}. Creating fallback provider instance."
                )
                from app.ai.model_config import ProviderConfig
                self.provider = LLMProviderFactory.create_provider(
                    config=ProviderConfig.from_settings("google")
                )

    def switch_provider(self, provider_type: str) -> None:
        """Dynamically switches active LLM provider at runtime."""
        self.provider = LLMProviderFactory.create_provider(provider_type)
        logger.info(f"Switched AIService provider to: {self.provider.provider_name} ({self.provider.model_name})")

    async def interpret_command(
        self,
        command: str,
        discovered_tools: List[DiscoveredToolItem],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        correlation_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> GeminiIntentOutput:
        """
        Interprets natural language command against discovered tools.
        Enforces template-based LLM guardrails (input validation, token optimization, output safety).
        Applies PII masking before sending prompt to external LLMs.
        Locally restores masked parameters strictly within request lifecycle.
        Validates output strictly against GeminiIntentOutput schema.
        Falls back to deterministic pattern interpreter if provider is unconfigured or in tests.
        """
        req_id = correlation_id or f"REQ-{uuid.uuid4().hex[:6]}"
        is_synthetic = is_synthetic_prompt(command)
        current_req_id_var.set(req_id)
        current_synthetic_var.set(is_synthetic)

        # Stage 0: Template-based Input Guardrail (Prompt Injection, Policy Violations, Length Limits)
        try:
            LLMGuardrails.validate_input(command)
        except PromptInjectionError as pie:
            logger.warning(f"[{req_id}] Input Guardrail: Prompt injection blocked: {pie}")
            return GeminiIntentOutput(
                intent="unknown",
                entity="general",
                confidence=0.0,
                requires_clarification=True,
                clarification_message="Security assertion: Request blocked by safety guardrails due to policy violation or prompt injection pattern.",
                parameters={},
            )
        except GuardrailValidationError as gve:
            logger.warning(f"[{req_id}] Input Guardrail: Validation error: {gve}")
            return GeminiIntentOutput(
                intent="unknown",
                entity="general",
                confidence=0.0,
                requires_clarification=True,
                clarification_message=f"Guardrail check failed: {gve}",
                parameters={},
            )

        # Stage 1: Incoming User Prompt
        PIITerminalLogger.log_stage_1_incoming(req_id, is_synthetic=is_synthetic)

        try:
            # 1. PII Detection & Masking (Fail-closed on errors)
            mask_result = self.pii_service.mask_text(command, correlation_id=req_id)
            sanitized_command = mask_result.masked_text
            combined_mapping = dict(mask_result.mapping)
            current_mapping_var.set(combined_mapping)

            # Stage 2: PII Detection
            PIITerminalLogger.log_stage_2_detection(req_id, mask_result.detected_entities)

            # Stage 3: PII Masking
            PIITerminalLogger.log_stage_3_masking(
                req_id=req_id,
                masked_text=sanitized_command,
                placeholders=list(mask_result.mapping.keys()),
                entity_count=mask_result.entity_count,
                is_synthetic=is_synthetic,
            )

            # 1b. Sanitize Conversation History if present (Ensures history never leaks PII to external LLM)
            sanitized_history: Optional[List[Dict[str, Any]]] = None
            has_history = False
            if conversation_history:
                has_history = True
                sanitized_history = []
                for msg in conversation_history:
                    msg_copy = dict(msg)
                    raw_content = str(msg.get("content", ""))
                    h_mask = self.pii_service.mask_text(raw_content, correlation_id=req_id)
                    msg_copy["content"] = h_mask.masked_text
                    combined_mapping.update(h_mask.mapping)
                    sanitized_history.append(msg_copy)

                # Cross-sanitize all history messages against all accumulated mappings (case-insensitively)
                # Guarantees that earlier turn messages (e.g. lowercase 'sourabh mishra') are fully sanitized
                for msg_item in sanitized_history:
                    content_str = msg_item["content"]
                    for ph, orig_val in combined_mapping.items():
                        if orig_val and len(orig_val.strip()) > 1:
                            pattern = re.compile(r"\b" + re.escape(orig_val.strip()) + r"\b", re.IGNORECASE)
                            content_str = pattern.sub(ph, content_str)
                    msg_item["content"] = content_str

                # Update context mapping with complete set
                current_mapping_var.set(combined_mapping)

                if is_terminal_logging_enabled():
                    logger.info(
                        f"[{req_id}] Conversation history sanitized: {len(sanitized_history)} messages processed."
                    )

            if mask_result.has_pii:
                logger.info(
                    "Masked %d PII entities before LLM invocation: %s",
                    mask_result.entity_count,
                    [e.entity_type for e in mask_result.detected_entities],
                )

            # 1c. Token Optimization Guardrail: Prune candidate tools and compact history footprint
            (
                sanitized_command,
                discovered_tools,
                sanitized_history,
                token_metrics,
            ) = LLMGuardrails.optimize_token_footprint(
                sanitized_command,
                discovered_tools,
                conversation_history=sanitized_history,
            )
            logger.info(
                f"[{req_id}] Guardrails token footprint: original={token_metrics['estimated_original_tokens']}, "
                f"optimized={token_metrics['estimated_optimized_tokens']}, saved={token_metrics['savings_percentage']}%"
            )

            # Build prompt for LLM provider
            prompt = build_interpretation_prompt(
                sanitized_command, discovered_tools, conversation_history=sanitized_history
            )

            # Dynamic Model Provider Selection
            active_provider = self.provider
            if model_id:
                try:
                    active_provider = LLMProviderFactory.create_provider(model_name=model_id)
                except Exception as e:
                    logger.warning(
                        f"[{req_id}] Could not instantiate provider for model '{model_id}': {e}. Using default provider."
                    )
                    active_provider = self.provider

            # Stage 4: LangChain Outbound Request
            PIITerminalLogger.log_stage_4_outbound(
                req_id=req_id,
                provider_name=active_provider.provider_name,
                model_name=active_provider.model_name,
                has_history=has_history,
            )

            # Stage 5: Security Verification
            security_passed = PIITerminalLogger.log_stage_5_security_verification(
                req_id=req_id,
                serialized_prompt=prompt,
                mapping=combined_mapping,
                history_sanitized=True,
            )
            if not security_passed:
                logger.error(f"[{req_id}] Outbound LLM request blocked due to security verification failure.")
                raise PIIMaskingError("Outbound request blocked: unmasked PII detected in serialized prompt.")

            # LLM Invocation or Deterministic Fallback
            if not active_provider.is_configured():
                logger.info(
                    f"LLM provider '{active_provider.provider_name}' is not configured; using deterministic fallback interpreter."
                )
                output = self._fallback_deterministic_interpreter(sanitized_command, discovered_tools, conversation_history=sanitized_history)
                PIITerminalLogger.log_stage_6_llm_response(req_id, status_msg="deterministic local fallback")
            else:
                try:
                    parsed = await active_provider.generate_structured(prompt, GeminiIntentOutput)
                    validated = self._validate_suggested_tool(parsed, discovered_tools)
                    PIITerminalLogger.log_stage_6_llm_response(req_id, status_msg="structured intent received")
                    output = validated
                except LLMConfigurationError as e:
                    logger.info(f"Provider configuration error ({e}); using deterministic fallback interpreter.")
                    output = self._fallback_deterministic_interpreter(sanitized_command, discovered_tools, conversation_history=sanitized_history)
                    PIITerminalLogger.log_stage_6_llm_response(req_id, status_msg=f"fallback executed ({e})")
                except Exception as e:
                    logger.warning(
                        f"LLM call to '{active_provider.provider_name}' encountered issue ({e}); attempting deterministic fallback."
                    )
                    output = self._fallback_deterministic_interpreter(sanitized_command, discovered_tools, conversation_history=sanitized_history)
                    PIITerminalLogger.log_stage_6_llm_response(req_id, status_msg=f"fallback executed ({type(e).__name__})")

            # Stage 7: Local Restoration
            restored_count = 0
            if combined_mapping:
                PIITerminalLogger.log_stage_7_restoration_start(req_id, len(combined_mapping))
                output.parameters, restored_count = self._restore_parameters_with_count(
                    output.parameters, combined_mapping
                )
                PIITerminalLogger.log_stage_7_restoration_complete(req_id, restored_count)
            else:
                if is_terminal_logging_enabled():
                    PIITerminalLogger.log_stage_7_restoration_start(req_id, 0)
                    PIITerminalLogger.log_stage_7_restoration_complete(req_id, 0)

            # Stage 7a: Deterministic Intent Correction Guardrail
            # Prevent read queries ("show card...", "list tasks...") from being wrongly classified as mutations
            cmd_lower = command.lower().strip()
            is_explicit_read = (
                any(cmd_lower.startswith(prefix) for prefix in ["show ", "list ", "view ", "display ", "get "])
                or ("show" in cmd_lower and any(w in cmd_lower for w in ["card", "cards", "task", "tasks", "list", "lists"]))
            )
            if is_explicit_read and not any(w in cmd_lower for w in ["create", "add new", "move to", "shift to", "transfer to"]):
                if output.intent in ("move_card", "create_card", "update_card", "create_list"):
                    logger.info(f"Corrected misclassified read command '{command}' from {output.intent} to search_cards")
                    output = self._fallback_deterministic_interpreter(command, discovered_tools)

            # Stage 7b: Output Guardrails (Anti-hallucination, Confidence Clamping, Parameter Sanitization)
            output = LLMGuardrails.validate_output(output, discovered_tools)

            # Stage 7c: Task title & date/time parameter boundary sanitization
            if output.parameters and isinstance(output.parameters, dict):
                # Defensive check for leaked prepositions in due_date / new_due_date (e.g. 'of')
                for due_key in ("new_due_date", "due_date"):
                    cur_d = output.parameters.get(due_key)
                    if cur_d and isinstance(cur_d, str) and cur_d.strip().lower() in ("of", "for", "is", "as", "at", "on", "from", "by", "with", "date", "due", "ue", "in"):
                        spec_m = re.search(r"(?:due\s*date|ue\s*date|due)\s+(?:of|for)?\s*(?:.+?)\s+(?:to|as)\s+(.+)$", command, re.IGNORECASE)
                        if spec_m:
                            real_d = spec_m.group(1).strip().strip('"\'')
                            output.parameters[due_key] = real_d
                        else:
                            output.parameters.pop(due_key, None)
                raw_n = output.parameters.get("name")
                if raw_n and isinstance(raw_n, str):
                    cleaned_n = raw_n
                    # Comprehensive leaked time detection (e.g. "and time is 12:00 PM", "time 11:00 AM", "at 5pm", "@ 3:30")
                    time_phrase_match = re.search(
                        r"(?:and\s+)?(?:(?:at\s+(?:the\s+)?time\s+(?:of\s+)?|at\s+|time\s*(?:is|was|will\s+be|should\s+be|[:=])?\s*|timing\s*(?:is|[:=])?\s*|by\s+|@\s*))?(?:\b\d{1,2}(?::\d{2})?(?::\d{2})?\s*(?:am|pm)\b|\b(?:[01]?\d|2[0-3]):[0-5]\d\b)",
                        cleaned_n,
                        re.IGNORECASE,
                    )
                    # Check if there is an explicit time phrase in cleaned_n
                    explicit_time_phrase = re.search(
                        r"(?:and\s+)?(?:at\s+(?:the\s+)?time\s+(?:of\s+)?|at\s+|time\s*(?:is|was|will\s+be|should\s+be|[:=])?\s*|timing\s*(?:is|[:=])?\s*|by\s+|@\s*)(?:\b\d{1,2}(?::\d{2})?(?::\d{2})?\s*(?:am|pm)\b|\b(?:[01]?\d|2[0-3]):[0-5]\d\b)",
                        cleaned_n,
                        re.IGNORECASE,
                    )
                    time_match_to_use = explicit_time_phrase or (time_phrase_match if re.search(r"\b(?:am|pm)\b", cleaned_n, re.IGNORECASE) else None)

                    if time_match_to_use:
                        matched_segment = time_match_to_use.group(0)
                        t_val = re.search(r"(\b\d{1,2}(?::\d{2})?(?::\d{2})?\s*(?:am|pm)\b|\b(?:[01]?\d|2[0-3]):[0-5]\d\b)", matched_segment, re.IGNORECASE)
                        exp_t = t_val.group(1).strip() if t_val else ""

                        cleaned_n = cleaned_n.replace(matched_segment, " ").strip()

                        if exp_t:
                            cur_due = output.parameters.get("due_date")
                            if cur_due and isinstance(cur_due, str) and not re.search(r"(?:\d{1,2}:\d{2}|am|pm)", cur_due, re.IGNORECASE):
                                output.parameters["due_date"] = f"{cur_due} {exp_t}"
                            elif not cur_due:
                                cur_start = output.parameters.get("start_date")
                                if cur_start and isinstance(cur_start, str) and not re.search(r"(?:\d{1,2}:\d{2}|am|pm)", cur_start, re.IGNORECASE):
                                    output.parameters["start_date"] = f"{cur_start} {exp_t}"
                                else:
                                    output.parameters["due_date"] = exp_t

                    # Clean remaining dates, members, conjunctions, and conversational filler
                    hindi_m_m = re.search(
                        r"(?:(?:aur|or|and|usme|isme)\s+)?([a-zA-Z0-9_\-\[\]]+(?:\s+[a-zA-Z0-9_\-\[\]]+){0,2})\s+ko\s+(?:assign\s+karo|assign\s+kardo|assign\s+kar\s+do|de\s+do|jod\s+do|add\s+karo|add\s+kardo|assign\b)",
                        cleaned_n,
                        re.IGNORECASE,
                    )
                    if hindi_m_m:
                        if not output.parameters.get("member_name"):
                            cand_m_g = hindi_m_m.group(1).strip()
                            if cand_m_g.lower() not in ("it", "the", "this", "that", "a", "an", "card", "task"):
                                output.parameters["member_name"] = cand_m_g
                        cleaned_n = cleaned_n[:hindi_m_m.start()] + " " + cleaned_n[hindi_m_m.end():]

                    cleaned_n = re.sub(r"(?:and\s+)?(?:due\s+date|due\s+by|due\s+on|due)\s*[:=]?\s*.*", "", cleaned_n, flags=re.IGNORECASE).strip()
                    cleaned_n = re.sub(r"(?:and\s+)?(?:start\s+date|starting\s+(?:on|from)?|starts?\s+(?:on|from)?|start)\s*[:=]?\s*.*", "", cleaned_n, flags=re.IGNORECASE).strip()
                    cleaned_n = re.sub(r"(?:and\s+)?(?:add\s+member|assign\s+member|assign\s+(?:it\s+)?to|member\s*[:=]?)\s+.*", "", cleaned_n, flags=re.IGNORECASE).strip()
                    cleaned_n = re.sub(r"\btime\s+(?:is|was|will\s+be|should\s+be)\b", "", cleaned_n, flags=re.IGNORECASE).strip()

                    # Handle 'naam ka' pattern: "Fullstack naam ka" -> "Fullstack"
                    naam_g = re.search(r"(.+?)\s+naam\s+(?:ka|ki|ke)\b", cleaned_n, re.IGNORECASE)
                    if naam_g:
                        cleaned_n = naam_g.group(1).strip()

                    cleaned_n = re.sub(r"^(?:and|with|to|is|for)\s+", "", cleaned_n, flags=re.IGNORECASE).strip()
                    cleaned_n = re.sub(r"\b(?:usme|isme|iski|uski|rakho|rakhna|karo|kardo|ka|ki|ke)\b", " ", cleaned_n, flags=re.IGNORECASE).strip()
                    cleaned_n = re.sub(r"\s+(?:and|with|at|time|is|ka|ki|ke|or|aur)$", "", cleaned_n, flags=re.IGNORECASE).strip()
                    cleaned_n = re.sub(r"\s+", " ", cleaned_n).strip()

                    if cleaned_n:
                        output.parameters["name"] = cleaned_n

                    # Also sanitize description so it doesn't echo the leaked time phrase
                    if raw_n != cleaned_n and "desc" in output.parameters and isinstance(output.parameters["desc"], str):
                        output.parameters["desc"] = output.parameters["desc"].replace(raw_n, cleaned_n)
                        output.parameters["desc"] = re.sub(
                            r"\s+(?:and\s+)?(?:at\s+(?:the\s+)?time\s+(?:of\s+)?|at\s+|time\s*(?:is|was|will\s+be|should\s+be|[:=])?\s*|timing\s*(?:is|[:=])?\s*|by\s+|@\s*)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?",
                            "",
                            output.parameters["desc"],
                            flags=re.IGNORECASE,
                        )

                raw_cn = output.parameters.get("card_name")
                if raw_cn and isinstance(raw_cn, str):
                    cleaned_cn = re.sub(
                        r"(?:and\s+)?(?:at\s+(?:the\s+)?time\s+(?:of\s+)?|at\s+|time\s*(?:is|was|will\s+be|should\s+be|[:=])?\s*|timing\s*(?:is|[:=])?\s*|by\s+|@\s*)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b",
                        "",
                        raw_cn,
                        flags=re.IGNORECASE,
                    ).strip()
                    cleaned_cn = re.sub(r"\btime\s+(?:is|was|will\s+be|should\s+be)\b", "", cleaned_cn, flags=re.IGNORECASE).strip()
                    cleaned_cn = re.sub(r"^(?:and|with|to|is|for)\s+", "", cleaned_cn, flags=re.IGNORECASE).strip()
                    cleaned_cn = re.sub(r"\s+(?:and|with|at|time|is)$", "", cleaned_cn, flags=re.IGNORECASE).strip()
                    cleaned_cn = re.sub(r"\s+", " ", cleaned_cn).strip()
                    if cleaned_cn:
                        output.parameters["card_name"] = cleaned_cn

            # Stage 7d: Multilingual Automatic Template Selection & Missing Fields
            if output.intent == "create_card":
                task_name = (output.parameters.get("name") or "").strip()
                member_n = (output.parameters.get("member_name") or "").strip()

                if not task_name or task_name.lower() in ("task", "card", "new task"):
                    output.missing_fields = ["name"]
                    output.requires_clarification = True
                    if member_n:
                        output.clarification_message = f"Please specify the title or deliverables for the task you want to create for {member_n}."
                    else:
                        output.clarification_message = "Please specify the task title or deliverables to create."
                else:
                    if not output.selected_template:
                        from app.services.template_service import BUILTIN_TEMPLATES
                        c_low = task_name.lower()
                        for b_tmpl in BUILTIN_TEMPLATES:
                            if b_tmpl["id"] == "tmpl_general":
                                continue
                            if any(re.search(r"\b" + re.escape(k) + r"\b", c_low) or (len(k) > 3 and k in c_low) for k in b_tmpl.get("keywords", [])):
                                output.selected_template = b_tmpl["id"]
                                cur_desc = output.parameters.get("desc", "")
                                if not cur_desc or cur_desc.lower() in ("task created via assistant", "new task", task_name.lower()):
                                    output.parameters["desc"] = b_tmpl["description_template"].replace("{title}", task_name)
                                break
                    elif output.selected_template and not output.parameters.get("desc"):
                        from app.services.template_service import BUILTIN_TEMPLATES
                        for b_tmpl in BUILTIN_TEMPLATES:
                            if b_tmpl["id"] == output.selected_template:
                                output.parameters["desc"] = b_tmpl["description_template"].replace("{title}", task_name)
                                break
            else:
                output.selected_template = None

            # Sync entities and action_parameters
            output.action_parameters = dict(output.parameters)
            if not output.entities:
                output.entities = {}
                if output.parameters.get("name"):
                    output.entities["card"] = output.parameters.get("name")
                elif output.parameters.get("card_name"):
                    output.entities["card"] = output.parameters.get("card_name")
                if output.parameters.get("member_name"):
                    output.entities["person"] = output.parameters.get("member_name")
                if output.parameters.get("target_status"):
                    output.entities["list"] = output.parameters.get("target_status")

            # Stage 8: Final Summary
            PIITerminalLogger.log_stage_8_summary(
                req_id=req_id,
                detection_ok=True,
                masking_ok=True,
                outbound_sanitized=True,
                restoration_ok=True,
            )
            return output

        except PIIMaskingError as exc:
            PIITerminalLogger.log_fail_closed(req_id, str(exc))
            PIITerminalLogger.log_stage_8_summary(
                req_id=req_id,
                detection_ok=False,
                masking_ok=False,
                outbound_sanitized=False,
                restoration_ok=False,
            )
            raise

    def _restore_parameters_with_count(
        self,
        parameters: Dict[str, Any],
        mapping: Dict[str, str],
    ) -> Tuple[Dict[str, Any], int]:
        """Restores parameters using request-scoped mapping and counts restored placeholders."""
        if not parameters or not mapping:
            return parameters, 0

        raw_json = json.dumps(parameters)
        restored_count = 0
        for ph in mapping.keys():
            if ph in raw_json:
                restored_count += 1
            else:
                m = re.match(r"\[([A-Za-z_]+)_(\d+)\]", ph)
                if m and re.search(r"\b" + re.escape(m.group(1)) + r"[ _]" + re.escape(m.group(2)) + r"\b", raw_json, re.I):
                    restored_count += 1

        restored_params = self.pii_service.restore_dict(parameters, mapping)
        return restored_params, (restored_count if restored_count > 0 else len(mapping))

    def _validate_suggested_tool(
        self,
        parsed: GeminiIntentOutput,
        discovered_tools: List[DiscoveredToolItem],
    ) -> GeminiIntentOutput:
        """Validates suggested_tool_id against discovered tools."""
        if parsed.suggested_tool_id:
            valid_ids = {item.tool.tool_id for item in discovered_tools}
            if parsed.suggested_tool_id not in valid_ids:
                logger.warning(
                    f"LLM suggested tool_id '{parsed.suggested_tool_id}' which was not in discovered tools."
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
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> GeminiIntentOutput:
        """
        Deterministic, privacy-safe fallback interpreter.
        Extracts basic intent and parameters from natural-language patterns
        when LLM is offline, unconfigured, or mocked in local testing.
        Incorporates conversation history to resolve follow-ups, confirmations, and missing fields.
        """
        cmd_lower = command.lower().strip()

        # Follow-up context resolution from conversation history
        pending_member = None
        pending_action_type = None
        if conversation_history:
            # Check if recent assistant turn asked for a task title or clarification
            for prev_msg in reversed(conversation_history):
                raw_prev_content = str(prev_msg.get("content", ""))
                prev_content = raw_prev_content.lower()
                prev_sender = prev_msg.get("sender") or prev_msg.get("role")
                if prev_sender in ("assistant", "system"):
                    # Check if asked for task title or deliverables for a member
                    clarif_m = re.search(r"(?:task you (?:want|would like) to create for|task title or deliverables to create|what should the task be about|specify the title|specify the task title)\s*(?:for\s+([a-zA-Z0-9_\-\s\[\]]+?))?[\.\?!:]?$", raw_prev_content, re.IGNORECASE)
                    if clarif_m:
                        pending_action_type = "create_card"
                        if clarif_m.group(1):
                            pending_member = clarif_m.group(1).strip()
                            if pending_member and not pending_member.isupper():
                                pending_member = pending_member.title()
                        break
                elif prev_sender == "user":
                    # Check if user previously said "create a task for X"
                    prev_cmd_m = re.search(r"(?:create|banao|add)\s+(?:a\s+)?task\s+for\s+([a-zA-Z0-9_\-\s\[\]]+)", raw_prev_content, re.IGNORECASE)
                    prev_cmd_hi = re.search(r"([a-zA-Z0-9_\-\s\[\]]+?)\s+ke\s+liye\s+task\s*(?:bana\s+do|banao|dalo)", raw_prev_content, re.IGNORECASE)
                    if prev_cmd_m:
                        pending_member = prev_cmd_m.group(1).strip()
                        if pending_member and not pending_member.isupper():
                            pending_member = pending_member.title()
                        pending_action_type = "create_card"
                        break
                    elif prev_cmd_hi:
                        pending_member = prev_cmd_hi.group(1).strip()
                        if pending_member and not pending_member.isupper():
                            pending_member = pending_member.title()
                        pending_action_type = "create_card"
                        break
        # Clean polite and conversational prefixes so natural requests parse cleanly:
        # e.g., "please", "can you", "could you", "i want to", "help me", "kripya", "zara", "bhai"
        command = re.sub(
            r"^(?:please\s+|can\s+you\s+(?:please\s+)?|could\s+you\s+(?:please\s+)?|i\s+want\s+to\s+|would\s+you\s+|help\s+me\s+(?:to\s+)?|kripya\s+|zara\s+|bhai\s+)+",
            "",
            command.strip(),
            flags=re.IGNORECASE,
        ).strip().rstrip(".!?")
        cmd_lower = command.lower().strip()

        def match_tool_id(target_key: str) -> Optional[str]:
            """Helper to resolve tool ID matching either native or MCP namespaced identifier."""
            for item in discovered_tools:
                if hasattr(item, "tool") and hasattr(item.tool, "tool_id"):
                    tid = item.tool.tool_id
                elif hasattr(item, "tool_id"):
                    tid = item.tool_id
                elif isinstance(item, dict):
                    tid = item.get("tool_id") or (item.get("tool", {}).get("tool_id") if isinstance(item.get("tool"), dict) else None)
                else:
                    tid = None
                if tid and (tid == target_key or tid.endswith(f".{target_key}") or target_key in tid):
                    return tid
            return None

        # Check for listing Trello boards: "show my trello boards", "list boards", "get boards"
        if ("board" in cmd_lower or "boards" in cmd_lower) and any(w in cmd_lower for w in ["show", "list", "get", "view", "my"]):
            tool_id = match_tool_id("trello_list_boards")
            if tool_id:
                return GeminiIntentOutput(
                    intent="list_boards",
                    entity="board",
                    parameters={},
                    suggested_tool_id=tool_id,
                    requires_clarification=False,
                    confidence=0.95,
                )

        # Check for date-range task filtering: "give me tasks from X to Y", "show tasks between A and B", "filter tasks from X to Y"
        date_range_match = re.search(
            r"(?:show|give|list|get|find|filter)\s+(?:me\s+)?(?:all\s+)?(?:active\s+and\s+completed\s+|completed\s+and\s+active\s+)?(?:tasks?|cards?)\s+(?:from|between|after)\s+([0-9\-\/a-zA-Z\s]+?)\s+(?:to|and|until)\s+([0-9\-\/a-zA-Z\s]+)",
            command,
            re.IGNORECASE,
        )
        if date_range_match:
            tool_id = match_tool_id("trello_search_cards") or match_tool_id("trello_list_cards")
            from_d = date_range_match.group(1).strip()
            to_d = date_range_match.group(2).strip()
            return GeminiIntentOutput(
                intent="search_cards",
                entity="card",
                parameters={"from_date": from_d, "to_date": to_d},
                suggested_tool_id=tool_id or "trello_search_cards",
                requires_clarification=False,
                confidence=0.96,
            )

        # Check for listing cards: "show cards in the to do list", "show card of Doing list", "show Doing tasks", "list cards"
        is_show_query = (
            any(cmd_lower.startswith(w) for w in ["show", "list ", "view ", "display ", "get "])
            or any(w in cmd_lower for w in ["show ", "view ", "display "])
        )
        if is_show_query and not any(w in cmd_lower for w in ["create", "add", "new", "move", "delete", "archive", "remove", "clear", "trash", "empty"]):
            tool_id = match_tool_id("trello_search_cards") or match_tool_id("trello_list_cards") or "trello_search_cards"
            list_name = None
            list_match = re.search(r"\b(?:in|under|of|from)\s+(?:the\s+)?([a-zA-Z0-9_\s\-]+?)(?:\s+list|\s+column)?$", command, re.IGNORECASE)
            if list_match:
                list_name = list_match.group(1).strip()
            if not list_name:
                list_match2 = re.search(
                    r"(?:show|list|view|get|display)\s+(?:the\s+)?([a-zA-Z0-9_\s\-]+?)\s+(?:tasks?|cards?)\b",
                    command,
                    re.IGNORECASE,
                )
                if list_match2:
                    cand = list_match2.group(1).strip()
                    if cand.lower() not in ("all", "my", "live", "trello", "all the", "me", "card", "cards", "task", "tasks"):
                        list_name = cand
            if not list_name:
                list_match3 = re.search(
                    r"(?:show|list|view|get|display)\s+(?:the\s+)?([a-zA-Z0-9_\s\-]+?)\s+(?:list|column)$",
                    command,
                    re.IGNORECASE,
                )
                if list_match3:
                    cand = list_match3.group(1).strip()
                    if cand.lower() not in ("all", "my", "live", "trello", "all the"):
                        list_name = cand
            if list_name:
                list_name = re.sub(r"\s+list$", "", list_name, flags=re.IGNORECASE).strip()

            return GeminiIntentOutput(
                intent="search_cards",
                entity="card",
                parameters={"list_name": list_name} if list_name else {},
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.96,
            )

        # Check for list creation: "add another list name In-Review", "create list <name>", "create lists A, B, C", "add multiple lists X, Y and Z"
        create_list_match = re.search(
            r"(?:create|add|new)\s+(?:multiple\s+)?(?:a\s+|another\s+)?(?:lists?|columns?)(?:\s+named|\s+name|\s*:\s*|\s+called)?\s*(.+)",
            command,
            re.IGNORECASE,
        )
        if create_list_match and not ("card" in cmd_lower or "task" in cmd_lower):
            raw_target = create_list_match.group(1).strip().strip('"\'').rstrip(".")
            parts = re.split(r"[,;]|\s+and\s+", raw_target, flags=re.IGNORECASE)
            clean_names = []
            for p in parts:
                cleaned = p.strip().strip('"\'').rstrip(".")
                if cleaned and cleaned.lower() not in ("list", "lists", "column", "columns", "a", "an", "the"):
                    clean_names.append(cleaned)

            tool_id = match_tool_id("trello_create_list") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
            if len(clean_names) > 1:
                return GeminiIntentOutput(
                    intent="create_list",
                    entity="list",
                    parameters={"names": clean_names, "name": ", ".join(clean_names)},
                    suggested_tool_id=tool_id,
                    requires_clarification=False,
                    confidence=0.96,
                )
            else:
                raw_list_name = clean_names[0] if clean_names else raw_target
                return GeminiIntentOutput(
                    intent="create_list",
                    entity="list",
                    parameters={"name": raw_list_name},
                    suggested_tool_id=tool_id,
                    requires_clarification=False,
                    confidence=0.96,
                )

        # Check for listing lists/columns: "show all lists in my board", "list lists", "show lists"
        if ("list" in cmd_lower or "lists" in cmd_lower or "columns" in cmd_lower) and not ("card" in cmd_lower or "cards" in cmd_lower or "task" in cmd_lower) and any(w in cmd_lower for w in ["show", "list", "get", "view", "all"]):
            tool_id = match_tool_id("trello_list_lists")
            if tool_id:
                return GeminiIntentOutput(
                    intent="list_lists",
                    entity="list",
                    parameters={},
                    suggested_tool_id=tool_id,
                    requires_clarification=False,
                    confidence=0.94,
                )

        # Check for card archiving: "archive card <name>", "close card <name>"
        if "archive" in cmd_lower or "close card" in cmd_lower:
            card_match = re.search(r"(?:archive|close)\s+(?:the\s+)?(?:card|task)?\s*(.+)", command, re.IGNORECASE)
            card_id = card_match.group(1).strip().strip('"\'') if card_match else "card"
            tool_id = match_tool_id("trello_archive_card")
            if tool_id:
                return GeminiIntentOutput(
                    intent="archive_card",
                    entity="card",
                    parameters={"card_id": card_id},
                    suggested_tool_id=tool_id,
                    requires_clarification=False,
                    confidence=0.93,
                )

        # Extract general start date from command if present
        cmd_start_date = None
        start_match = re.search(
            r"(?:(?:aur|or|and|iski|uski)\s+)?(?:start\s+date|starting\s+(?:on|from)?|starts?\s+(?:on|from)?|start)\s*[:=]?\s*(?:rakho|rakhna)?\s*(in\s+\d+\s+(?:days?|hours?|weeks?|months?)|\d{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+(?:\s+\d{4})?|[a-zA-Z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?|next\s+[a-zA-Z]+|tomorrow|today|\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?|\d{1,2}/\d{1,2}/\d{4})(?:\s+(?:(?:and\s+)?(?:at\s+|time\s*[:=]?\s*)?)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?(?:\s+(?:rakho|rakhna|honi\s+chahiye))?",
            command,
            re.IGNORECASE,
        )
        if start_match:
            cand_start = start_match.group(1).strip()
            # If the match also had trailing time, include it
            full_start = start_match.group(0)
            time_part = re.search(r"(?:(?:and\s+)?(?:at\s+|time\s*[:=]?\s*)?)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?$", full_start, re.IGNORECASE)
            if time_part and time_part.group(0).strip():
                clean_time = re.sub(r"^(?:and\s+)?(?:at\s+|time\s*[:=]?\s*)", "", time_part.group(0).strip(), flags=re.IGNORECASE).strip()
                if clean_time and clean_time not in cand_start:
                    cand_start = f"{cand_start} {clean_time}"
            if cand_start.lower() not in ("to", "in", "the", "a", "an", "list", "column", "card", "task", "of", "for", "is", "as", "at", "on", "from", "by", "with", "date", "due", "ue"):
                cmd_start_date = cand_start

        # Extract general due date from command if present
        cmd_due_date = None
        due_match = re.search(
            r"(?:(?:aur|or|and|iski|uski)\s+)?(?:due\s+date|due\s+by|due\s+on|due)\s*[:=]?\s*(?:rakho|rakhna)?\s*(in\s+\d+\s+(?:days?|hours?|weeks?|months?)|\d{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+(?:\s+\d{4})?|[a-zA-Z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?|next\s+[a-zA-Z]+|tomorrow|today|\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?|\d{1,2}/\d{1,2}/\d{4})(?:\s+(?:(?:and\s+)?(?:at\s+|time\s*[:=]?\s*)?)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?(?:\s+(?:rakho|rakhna|honi\s+chahiye))?",
            command,
            re.IGNORECASE,
        )
        if due_match:
            cand = due_match.group(1).strip()
            full_due = due_match.group(0)
            time_part = re.search(r"(?:(?:and\s+)?(?:at\s+|time\s*[:=]?\s*)?)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?$", full_due, re.IGNORECASE)
            if time_part and time_part.group(0).strip():
                clean_time = re.sub(r"^(?:and\s+)?(?:at\s+|time\s*[:=]?\s*)", "", time_part.group(0).strip(), flags=re.IGNORECASE).strip()
                if clean_time and clean_time not in cand:
                    cand = f"{cand} {clean_time}"
            if cand.lower() not in ("to", "in", "the", "a", "an", "list", "column", "card", "task", "of", "for", "is", "as", "at", "on", "from", "by", "with", "date", "due", "ue"):
                cmd_due_date = cand

        # Standalone or explicit time clause check:
        # e.g. "and time is 12:00 PM", "and time 11:00 AM", "time: 11:00 AM", "at 11:00 AM", "timing 12:00 PM" anywhere in command
        explicit_time_match = re.search(
            r"(?:(?:and\s+)?(?:at\s+(?:the\s+)?time\s+(?:of\s+)?|at\s+|time\s*(?:is|was|will\s+be|should\s+be|[:=])?\s*|timing\s*(?:is|[:=])?\s*|by\s+|@\s*))(\b\d{1,2}(?::\d{2})?(?::\d{2})?\s*(?:am|pm)\b|\b(?:[01]?\d|2[0-3]):[0-5]\d\b)",
            command,
            re.IGNORECASE,
        )
        if not explicit_time_match:
            explicit_time_match = re.search(
                r"\b(?:and\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b",
                command,
                re.IGNORECASE,
            )
        if explicit_time_match:
            exp_time = explicit_time_match.group(1).strip()
            if cmd_due_date and not re.search(r"(?:\d{1,2}:\d{2}|am|pm)", cmd_due_date, re.IGNORECASE):
                cmd_due_date = f"{cmd_due_date} {exp_time}"
            elif not cmd_due_date and cmd_start_date and not re.search(r"(?:\d{1,2}:\d{2}|am|pm)", cmd_start_date, re.IGNORECASE):
                cmd_start_date = f"{cmd_start_date} {exp_time}"
            elif not cmd_due_date:
                cmd_due_date = exp_time

        # Extract general additional description or notes from command if present
        cmd_additional_desc = None
        desc_match = re.search(
            r"(?:with\s+description|with\s+notes?|description\s*[:=]|notes?\s*[:=]|details?\s*[:=])\s*(.+)",
            command,
            re.IGNORECASE,
        )
        if desc_match:
            cmd_additional_desc = desc_match.group(1).strip().strip('"\'')

        # Check for card update: "update card <name>", "update description", "set due date for <card> to <due>"
        # e.g., "update due date of Register Page to 29 nov 2026", "change due date of Features to tomorrow 4pm"
        if not any(w in cmd_lower for w in ["create", "add new", "add task", "add card", "bana do", "banao", "dalo"]) and ("update" in cmd_lower or ("set" in cmd_lower and ("due" in cmd_lower or "deadline" in cmd_lower)) or ("change" in cmd_lower and "due" in cmd_lower) or "ue date" in cmd_lower):
            tool_id = match_tool_id("trello_update_card") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
            update_card_name = "Task"
            update_due_target = cmd_due_date

            # Dedicated regex for 'update due date of <Card> to <Date>'
            specific_due_match1 = re.search(
                r"(?:update|change|set)\s+(?:the\s+)?(?:due\s*date|ue\s*date|due|deadline)\s+(?:of|for)\s+(?:the\s+)?(?:card\s+|task\s+)?(.+?)\s+(?:to|as)\s+(.+)$",
                command,
                re.IGNORECASE,
            )
            specific_due_match2 = re.search(
                r"(?:update|change|set)\s+(?:the\s+)?(?:card\s+|task\s+)?(.+?)\s+(?:due\s*date|ue\s*date|due|deadline)\s+(?:to|as)\s+(.+)$",
                command,
                re.IGNORECASE,
            )
            active_spec_due = specific_due_match1 or specific_due_match2
            if active_spec_due:
                update_card_name = active_spec_due.group(1).strip().strip('"\'')
                cand_due_tgt = active_spec_due.group(2).strip().strip('"\'')
                if cand_due_tgt.lower() not in ("of", "for", "is", "as", "at", "on", "from", "by", "with", "date", "due", "ue"):
                    update_due_target = cand_due_tgt
            else:
                cname_match = re.search(r"(?:for|of|card)\s+([a-zA-Z0-9_\-\s]+?)(?:\s+to|\s+due|\s+with|$)", command, re.IGNORECASE)
                if cname_match:
                    update_card_name = cname_match.group(1).replace("card", "").strip()

            update_card_name = re.sub(r"^(?:card|task)\s+", "", update_card_name, flags=re.IGNORECASE).strip()
            update_card_name = re.sub(r"\s+(?:card|task)$", "", update_card_name, flags=re.IGNORECASE).strip()

            update_params: Dict[str, Any] = {"card_name": update_card_name, "card_id": "c101"}
            if update_due_target:
                update_params["new_due_date"] = update_due_target
                update_params["due_date"] = update_due_target
            if cmd_additional_desc:
                update_params["new_description"] = cmd_additional_desc
                update_params["desc"] = cmd_additional_desc
            return GeminiIntentOutput(
                intent="update_card",
                entity="card",
                parameters=update_params,
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.95,
            )

        # Check for card creation FIRST: "create card <name>", "create a task card <name>", "create task card <name> and assign it to <member>",
        # or natural Hindi/conversational: "bana do card <name>", "naya task dalo <name>", "in Doing list create task <name>", "for Alex create task <name>"
        # or Hindi subject-first: "Rahul ke liye task banao", "Rahul ke liye API integration task banao"
        list_prefix_override = None
        raw_remainder = None
        hindi_preset_member = None

        # Check Hindi/Hinglish subject-first creation: e.g. "Rahul ke liye task banao", "Rahul ke liye API integration task banao"
        hindi_subj_match = re.search(
            r"^([a-zA-Z0-9_\-\s\[\]]+?)\s+ke\s+liye\s+(?:ek\s+)?(?:naya\s+)?(?:task|card)\s*(?:bana\s+do|banao|dalo|create\s+karo)(?:\s+(.+))?$",
            command,
            re.IGNORECASE,
        )
        hindi_subj_match2 = re.search(
            r"^([a-zA-Z0-9_\-\s\[\]]+?)\s+ke\s+liye\s+(.+?)\s+(?:task|card)\s*(?:bana\s+do|banao|dalo|create\s+karo)$",
            command,
            re.IGNORECASE,
        )

        # Natural Hindi title-first and 'naam ka' patterns:
        # e.g. "full stack naam ka card banao", "ek card banao fullStack naam ka", "full stack ka card bana do"
        hindi_title_first_m1 = re.search(
            r"^(.+?)\s+naam\s+(?:ka|ki|ke)\s+(?:ek\s+)?(?:naya\s+)?(?:task|card)\s*(?:bana\s+do|banao|dalo|create\s+karo|khol|banaye)?$",
            command,
            re.IGNORECASE,
        )
        hindi_title_first_m2 = re.search(
            r"^(?:ek\s+)?(?:naya\s+)?(?:task|card)\s*(?:bana\s+do|banao|dalo|create\s+karo)\s+(.+?)(?:\s+naam\s+(?:ka|ki|ke))?$",
            command,
            re.IGNORECASE,
        )
        hindi_title_first_m3 = re.search(
            r"^(.+?)\s+(?:ka|ki|ke)\s+(?:ek\s+)?(?:naya\s+)?(?:task|card)\s*(?:bana\s+do|banao|dalo|create\s+karo)$",
            command,
            re.IGNORECASE,
        )

        if hindi_subj_match:
            create_match = hindi_subj_match
            hindi_preset_member = hindi_subj_match.group(1).strip()
            raw_remainder = (hindi_subj_match.group(2) or "").strip()
        elif hindi_subj_match2:
            create_match = hindi_subj_match2
            hindi_preset_member = hindi_subj_match2.group(1).strip()
            raw_remainder = hindi_subj_match2.group(2).strip()
        elif hindi_title_first_m1:
            create_match = hindi_title_first_m1
            raw_remainder = hindi_title_first_m1.group(1).strip()
        elif hindi_title_first_m2 and not any(w in cmd_lower for w in ["move", "delete", "archive", "details", "directory", "report", "who"]):
            create_match = hindi_title_first_m2
            raw_remainder = hindi_title_first_m2.group(1).strip()
        elif hindi_title_first_m3:
            create_match = hindi_title_first_m3
            raw_remainder = hindi_title_first_m3.group(1).strip()
        else:
            # Check list-first creation FIRST: "in Doing list create card Code Review", "under To Do add task X"
            list_first_match = re.search(
                r"(?:in|under)\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)\s+(?:list|column)\s+(?:create|add|make|dalo|banao)\s+(?:a\s+)?(?:task\s+card|card|task)(?:\s+named|\s+called|\s*:\s*|\s+to\s+)?\s*(.+)",
                command,
                re.IGNORECASE,
            )
            if list_first_match:
                create_match = list_first_match
                list_prefix_override = list_first_match.group(1).strip()
                raw_remainder = list_first_match.group(2).strip()
            else:
                create_match = re.search(
                    r"(?:create|add|new|make|schedule|draft|insert|bana\s+do|banao|dalo|create\s+karo)\s+(?:ek\s+)?(?:naya\s+)?(?:a\s+)?(?:task\s+card|card|task)(?:\s+named|\s+called|\s*:\s*|\s+to\s+)?\s*(.+)",
                    command,
                    re.IGNORECASE,
                )
                if not create_match and pending_action_type == "create_card" and pending_member:
                    # User is answering the follow-up question with just the task title!
                    # e.g. User: "Full stack development." or "API integration"
                    raw_remainder = command
                    create_match = True
                    hindi_preset_member = pending_member
        if create_match:
            raw_card_name = (raw_remainder if raw_remainder is not None else create_match.group(1)).strip().strip('"\'').rstrip(".")
            if raw_card_name.lower().startswith("to "):
                raw_card_name = raw_card_name[3:].strip()

            member_name = hindi_preset_member

            # Hindi assignment pattern: e.g. "usme sourabh mishra ko assign karo", "sourabh mishra ko assign kardo", "rahul ko de do"
            hindi_assign_match = re.search(
                r"(?:(?:aur|or|and|usme|isme)\s+)?([a-zA-Z0-9_\-\[\]]+(?:\s+[a-zA-Z0-9_\-\[\]]+){0,2})\s+ko\s+(?:assign\s+karo|assign\s+kardo|assign\s+kar\s+do|de\s+do|jod\s+do|add\s+karo|add\s+kardo|assign\b)",
                raw_card_name,
                re.IGNORECASE,
            )
            if hindi_assign_match:
                cand_m = hindi_assign_match.group(1).strip().strip('"\'')
                if cand_m.lower() not in ("it", "the", "this", "that", "a", "an", "card", "task"):
                    if not member_name:
                        member_name = cand_m
                    raw_card_name = raw_card_name[:hindi_assign_match.start()] + " " + raw_card_name[hindi_assign_match.end():]

            member_match = re.search(
                r"(?:and\s+)?(?:add\s+member|assign\s+member|assign\s+(?:it\s+)?to|member\s*[:=]?)\s+([a-zA-Z0-9_\-\s\[\]]+?)(?:\s+(?:and\s+)?(?:start\s+date|starting|starts?|start|due\s+date|due|with|under|in|priority)|$)",
                raw_card_name,
                re.IGNORECASE,
            )
            if member_match:
                cand_member = member_match.group(1).strip().strip('"\'')
                cand_member = re.sub(r"\s+and$", "", cand_member, flags=re.IGNORECASE).strip()
                if cand_member.lower() not in ("it", "the", "this", "that", "a", "an"):
                    member_name = cand_member
                    raw_card_name = re.sub(
                        r"(?:and\s+)?(?:add\s+member|assign\s+member|assign\s+(?:it\s+)?to|member\s*[:=]?)\s+" + re.escape(member_match.group(1)),
                        "",
                        raw_card_name,
                        flags=re.IGNORECASE,
                    ).strip()

            # Handle pattern: "create a task for <Member> ... ask him/her to <Action>"
            for_member_match = re.search(
                r"^for\s+([a-zA-Z0-9_\-\s\[\]]+?)(?:\s*\.|\s+and|\s+his|\s+her|\s+email|\s+phone|\s+ask|$)",
                raw_card_name,
                re.IGNORECASE,
            )
            if for_member_match:
                cand_member = for_member_match.group(1).strip().strip('"\'')
                if not member_name and cand_member:
                    member_name = cand_member

            ask_action_match = re.search(
                r"(?:ask|tell)\s+(?:him|her|them)?\s+(?:to\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+(?:by|due|on|before|\.|$))",
                command,
                re.IGNORECASE,
            )
            if ask_action_match:
                action_name = ask_action_match.group(1).strip().strip('"\'')
                if action_name and len(action_name) > 1 and action_name.lower() not in ("the", "a", "an", "this", "that"):
                    raw_card_name = action_name

            # Extract priority if present
            priority = "MEDIUM"
            prio_match = re.search(
                r"(?:with\s+)?(?:priority\s*[:=]?\s*|priority\s+)(high|urgent|medium|low)|(?:with\s+)?(high|urgent|medium|low)\s+priority",
                command,
                re.IGNORECASE,
            )
            if prio_match:
                extracted_prio = (prio_match.group(1) or prio_match.group(2)).upper()
                priority = extracted_prio
                raw_card_name = re.sub(
                    r"(?:with\s+)?(?:priority\s*[:=]?\s*|priority\s+)(?:high|urgent|medium|low)|(?:with\s+)?(?:high|urgent|medium|low)\s+priority",
                    "",
                    raw_card_name,
                    flags=re.IGNORECASE,
                ).strip()

            # Clean start date from card name if present
            if cmd_start_date:
                raw_card_name = re.sub(
                    r"(?:(?:aur|or|and|iski|uski)\s+)?(?:start\s+date|starting\s+(?:on|from)?|starts?\s+(?:on|from)?|start)\s*[:=]?\s*(?:rakho|rakhna)?\s*" + re.escape(cmd_start_date) + r"(?:\s+(?:rakho|rakhna|honi\s+chahiye))?",
                    "",
                    raw_card_name,
                    flags=re.IGNORECASE,
                ).strip()
            raw_card_name = re.sub(
                r"(?:(?:aur|or|and|iski|uski)\s+)?(?:start\s+date|starting\s+(?:on|from)?|starts?\s+(?:on|from)?|start)\s*[:=]?\s*(?:rakho|rakhna)?\s*(?:in\s+\d+\s+(?:days?|hours?|weeks?|months?)|\d{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+(?:\s+\d{4})?|[a-zA-Z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?|next\s+[a-zA-Z]+|tomorrow|today|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})(?:\s+(?:(?:and\s+)?(?:at\s+|time\s*[:=]?\s*)?)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?(?:\s+(?:rakho|rakhna|honi\s+chahiye))?",
                "",
                raw_card_name,
                flags=re.IGNORECASE,
            ).strip()

            # Clean due date from card name if present
            if cmd_due_date:
                raw_card_name = re.sub(
                    r"(?:(?:aur|or|and|iski|uski)\s+)?(?:due\s+date|due\s+by|due\s+on|due)\s*[:=]?\s*(?:rakho|rakhna)?\s*" + re.escape(cmd_due_date) + r"(?:\s+(?:rakho|rakhna|honi\s+chahiye))?",
                    "",
                    raw_card_name,
                    flags=re.IGNORECASE,
                ).strip()
            else:
                due_in_name = re.search(
                    r"(?:(?:aur|or|and|iski|uski)\s+)?(?:due\s+date|due\s+by|due\s+on|due)\s*[:=]?\s*(?:rakho|rakhna)?\s*(\d{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+(?:\s+\d{4})?|[a-zA-Z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?|tomorrow|today|\d{4}-\d{2}-\d{2})(?:\s+(?:(?:and\s+)?(?:at\s+|time\s*[:=]?\s*)?)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?(?:\s+(?:rakho|rakhna|honi\s+chahiye))?",
                    raw_card_name,
                    re.IGNORECASE,
                )
                if due_in_name:
                    cand = due_in_name.group(1).strip()
                    full_due = due_in_name.group(0)
                    time_part = re.search(r"(?:(?:and\s+)?(?:at\s+|time\s*[:=]?\s*)?)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?$", full_due, re.IGNORECASE)
                    if time_part and time_part.group(0).strip():
                        clean_time = re.sub(r"^(?:and\s+)?(?:at\s+|time\s*[:=]?\s*)", "", time_part.group(0).strip(), flags=re.IGNORECASE).strip()
                        if clean_time and clean_time not in cand:
                            cand = f"{cand} {clean_time}"
                    cmd_due_date = cand
                    raw_card_name = re.sub(
                        r"(?:(?:aur|or|and|iski|uski)\s+)?(?:due\s+date|due\s+by|due\s+on|due)\s*[:=]?\s*(?:rakho|rakhna)?\s*" + re.escape(due_in_name.group(1)),
                        "",
                        raw_card_name,
                        flags=re.IGNORECASE,
                    ).strip()

            raw_card_name = re.sub(
                r"(?:(?:aur|or|and|iski|uski)\s+)?(?:due\s+date|due\s+by|due\s+on|due)\s*[:=]?\s*(?:rakho|rakhna)?\s*(?:in\s+\d+\s+(?:days?|hours?|weeks?|months?)|\d{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+(?:\s+\d{4})?|[a-zA-Z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?|next\s+[a-zA-Z]+|tomorrow|today|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|[a-zA-Z]+)(?:\s+(?:(?:and\s+)?(?:at\s+|time\s*[:=]?\s*)?)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?(?:\s+(?:rakho|rakhna|honi\s+chahiye))?",
                "",
                raw_card_name,
                flags=re.IGNORECASE,
            ).strip()

            # Clean any remaining time clauses from raw_card_name (e.g. "and time is 12:00 PM", "time 11:00 AM", "at 5pm")
            raw_card_name = re.sub(
                r"(?:and\s+)?(?:at\s+(?:the\s+)?time\s+(?:of\s+)?|at\s+|time\s*(?:is|was|will\s+be|should\s+be|[:=])?\s*|timing\s*(?:is|[:=])?\s*|by\s+|@\s*)?(?:\b\d{1,2}(?::\d{2})?(?::\d{2})?\s*(?:am|pm)\b|\b(?:[01]?\d|2[0-3]):[0-5]\d\b)",
                "",
                raw_card_name,
                flags=re.IGNORECASE,
            ).strip()
            raw_card_name = re.sub(r"\btime\s+(?:is|was|will\s+be|should\s+be)\b", "", raw_card_name, flags=re.IGNORECASE).strip()

            # Check naam ka pattern in raw_card_name: "fullstack naam ka" -> "fullstack"
            naam_m = re.search(r"(.+?)\s+naam\s+(?:ka|ki|ke)\b", raw_card_name, re.IGNORECASE)
            if naam_m:
                raw_card_name = naam_m.group(1).strip()

            # Strip leading/trailing conjunctions, prepositions, and Hindi conversational particles
            raw_card_name = re.sub(r"^(?:and|with|to|is|for)\s+", "", raw_card_name, flags=re.IGNORECASE).strip()
            raw_card_name = re.sub(r"\b(?:usme|isme|iski|uski|rakho|rakhna|karo|kardo|ka|ki|ke)\b", " ", raw_card_name, flags=re.IGNORECASE).strip()
            raw_card_name = re.sub(r"\s+(?:and|with|at|time|is|ka|ki|ke|or|aur)$", "", raw_card_name, flags=re.IGNORECASE).strip()
            raw_card_name = re.sub(r"\s+", " ", raw_card_name).strip()

            # Clean description/notes from card name if present
            if cmd_additional_desc:
                raw_card_name = re.sub(
                    r"(?:with\s+description|with\s+notes?|description\s*[:=]|notes?\s*[:=]|details?\s*[:=]).*",
                    "",
                    raw_card_name,
                    flags=re.IGNORECASE,
                ).strip()

            # Extract target list if present
            target_list = list_prefix_override if list_prefix_override else "To Do"
            list_match = re.search(
                r"\b(?:in|to|under)\b\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+list|\s+column|$)",
                raw_card_name,
                re.IGNORECASE,
            )
            if list_match:
                cand_list = list_match.group(1).strip()
                if cand_list.lower() not in ("priority", "high", "medium", "low", "urgent", "due", "start"):
                    if cand_list.upper() in ("TODO", "IN_PROGRESS", "IN_REVIEW", "DONE"):
                        target_list = cand_list.upper()
                    else:
                        target_list = cand_list
                    raw_card_name = raw_card_name[:list_match.start()].strip()

            card_name = raw_card_name.strip(" ,.-")
            missing_fields = []
            requires_clarification = False
            clarification_msg = None

            if not card_name or card_name.lower() in ("new task", "task", "card") or (member_name and card_name.lower() in (f"for {member_name.lower()}", member_name.lower())):
                if member_name:
                    missing_fields = ["name"]
                    requires_clarification = True
                    clarification_msg = f"Please specify the title or deliverables for the task you want to create for {member_name}."
                    card_name = ""
                else:
                    missing_fields = ["name"]
                    requires_clarification = True
                    clarification_msg = "Please specify the task title or deliverables to create."
                    card_name = ""
            else:
                card_name = card_name[0].upper() + card_name[1:] if len(card_name) > 1 else card_name.upper()

            tool_id = match_tool_id("trello_create_card") or (discovered_tools[0].tool.tool_id if discovered_tools else None)

            # Automatic Template Selection
            selected_template = None
            desc = ""
            if card_name:
                from app.services.template_service import BUILTIN_TEMPLATES
                c_low = card_name.lower()
                for b_tmpl in BUILTIN_TEMPLATES:
                    if b_tmpl["id"] == "tmpl_general":
                        continue
                    if any(re.search(r"\b" + re.escape(k) + r"\b", c_low) or (len(k) > 3 and k in c_low) for k in b_tmpl.get("keywords", [])):
                        selected_template = b_tmpl["id"]
                        desc = b_tmpl["description_template"].replace("{title}", card_name)
                        break
                if not desc:
                    desc = ApprovalService._generate_related_description(card_name, command, cmd_additional_desc)

            parameters: Dict[str, Any] = {
                "name": card_name,
                "desc": desc,
                "list_name": target_list,
                "priority": priority,
            }
            if cmd_start_date:
                parameters["start_date"] = cmd_start_date
            if cmd_due_date:
                parameters["due_date"] = cmd_due_date
            if member_name:
                parameters["member_name"] = member_name

            entities: Dict[str, Any] = {}
            if card_name:
                entities["card"] = card_name
            if member_name:
                entities["person"] = member_name

            return GeminiIntentOutput(
                intent="create_card",
                entity="card",
                entities=entities,
                parameters=parameters,
                action_parameters=dict(parameters),
                selected_template=selected_template,
                missing_fields=missing_fields,
                suggested_tool_id=tool_id,
                requires_clarification=requires_clarification,
                clarification_message=clarification_msg,
                confidence=0.96 if not requires_clarification else 0.5,
            )

        # Check for card member assignment on existing cards: "on register card add member sourabh mishra", "add member sourabh to register card", "assign sourabh to register page"
        # or natural Hindi/conversational: "assign sourabh to card Register", "give card Register to sourabh", "sourabh ko card Register assign kardo", "sourabh ko task Register de do", "Rahul ko API integration assign kar do"
        member_match1 = re.search(r"^on\s+(.+?)(?:\s+card)?\s+(?:add|assign)\s+(?:member\s+)?(.+)", command, re.IGNORECASE)
        member_match2 = re.search(r"^(?:please\s+)?(?:add|assign)\s+(?:member\s+)?(.+?)\s+(?:to|on)\s+(.+?)(?:\s+card)?$", command, re.IGNORECASE)
        member_match3 = re.search(r"^(?:give|assign)\s+(?:card|task\s+)?(.+?)\s+to\s+(?:member\s+)?(.+)", command, re.IGNORECASE)
        member_match4 = re.search(r"^([a-zA-Z0-9_\-]+)\s+ko\s+(?:card|task\s+)?(.+?)\s+(?:assign\s+kardo|assign\s+karo|de\s+do|assign\s+kar\s+do|assign)", command, re.IGNORECASE)
        member_match5 = re.search(r"^(?:card\s+|task\s+)?(.+?)\s+([a-zA-Z0-9_\-]+)\s+ko\s+(?:card\s+|task\s+)?(?:assign\s+kardo|assign\s+karo|de\s+do|assign\s+kar\s+do|assign)", command, re.IGNORECASE)

        if member_match1 or member_match2 or member_match3 or member_match4 or member_match5:
            if member_match1:
                assign_card_name = member_match1.group(1).strip().strip('"\'')
                assign_member = member_match1.group(2).strip().strip('"\'')
            elif member_match2:
                assign_member = member_match2.group(1).strip().strip('"\'')
                assign_card_name = member_match2.group(2).strip().strip('"\'')
            elif member_match3:
                assign_card_name = member_match3.group(1).strip().strip('"\'')
                assign_member = member_match3.group(2).strip().strip('"\'')
            elif member_match4:
                assign_member = member_match4.group(1).strip().strip('"\'')
                assign_card_name = member_match4.group(2).strip().strip('"\'')
            else:
                assign_card_name = member_match5.group(1).strip().strip('"\'')
                assign_member = member_match5.group(2).strip().strip('"\'')

            assign_card_name = re.sub(r"^(?:card|task)\s+", "", assign_card_name, flags=re.IGNORECASE).strip()
            assign_member = re.sub(r"^(?:member)\s+", "", assign_member, flags=re.IGNORECASE).strip()

            if assign_member.lower() not in ("it", "the", "this", "that", "a", "an"):
                tool_id = match_tool_id("trello_update_card") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
                assign_params: Dict[str, Any] = {
                    "card_name": assign_card_name,
                    "member_name": assign_member,
                    "card_id": "c101",
                }
                if cmd_due_date:
                    assign_params["due_date"] = cmd_due_date
                if cmd_additional_desc:
                    assign_params["new_description"] = cmd_additional_desc
                return GeminiIntentOutput(
                    intent="update_card",
                    entity="card",
                    entities={"card": assign_card_name, "person": assign_member},
                    parameters=assign_params,
                    action_parameters=dict(assign_params),
                    selected_template=None,
                    missing_fields=[],
                    suggested_tool_id=tool_id,
                    requires_clarification=False,
                    confidence=0.95,
                )

        # Check for card movement: "move <card> to <status>" or "<card> card move to <status>" or "mark <card> as done"
        # or natural Hindi/conversational: "push Features to Doing", "send Auth to In-Review", "Features ho gaya", "Features card Done me bhej do", "Is card ko Doing mein move karo"
        # Hinglish move match FIRST: e.g. "Features card Done me bhej do", "Login Doing me daal do", "Features ko Done me shift kardo", "Is card ko Doing mein move karo"
        move_hinglish = re.search(
            r"['\"]?(.+?)['\"]?\s+(?:card|task\s+)?(?:ko\s+)?(.+?)\s+(?:list|column)?\s*(?:me|mai|mein)\s*(?:bhej\s+do|daal\s+do|move\s+kardo|shift\s+kardo|transfer\s+kardo|move\s+karo|shift\s+karo|move|shift)",
            command,
            re.IGNORECASE,
        )
        move_match1 = None
        move_match2 = None
        if not move_hinglish:
            move_match1 = re.search(
                r"(?:move|transfer|shift|put|push|send|drag)\s+(?:the\s+)?(?:card|task\s+)?['\"]?(.+?)['\"]?\s+(?:from\s+(?:the\s+)?(.+?)\s+)?(?:to|into|in)\s+(?:the\s+)?(.+?)(?:\s+list|\s+column)?(?:\s+(?:due|with|and)|$)",
                command,
                re.IGNORECASE,
            )
            move_match2 = re.search(
                r"['\"]?(.+?)['\"]?\s+(?:card|task\s+)?(?:move|transfer|shift|put|push|send|drag)\s+(?:from\s+(?:the\s+)?(.+?)\s+)?(?:to|into|in)\s+(?:the\s+)?(.+?)(?:\s+list|\s+column)?(?:\s+(?:due|with|and)|$)",
                command,
                re.IGNORECASE,
            )
        # Completion phrases: "mark <card> as done", "mark <card> done", "complete task <card>", "finish <card>", "<card> ho gaya", "Ye card complete kar do"
        completion_match = None
        if not move_match1 and not move_match2 and not move_hinglish:
            if "mark" in cmd_lower and "done" in cmd_lower:
                completion_match = re.search(r"mark\s+(?:the\s+)?(?:card|task\s+)?['\"]?(.+?)['\"]?\s+(?:as\s+)?done", command, re.IGNORECASE)
            elif any(cmd_lower.startswith(w) for w in ["complete ", "finish "]):
                completion_match = re.search(r"(?:complete|finish)\s+(?:the\s+)?(?:card|task\s+)?['\"]?(.+?)['\"]?$", command, re.IGNORECASE)
            elif "ho gaya" in cmd_lower or "ho gya" in cmd_lower:
                completion_match = re.search(r"['\"]?(.+?)['\"]?\s+(?:card|task\s+)?(?:ho\s+gaya|ho\s+gya)", command, re.IGNORECASE)
            elif "complete" in cmd_lower and any(w in cmd_lower for w in ["kar do", "kardo", "karo", "karna"]):
                completion_match = re.search(r"['\"]?(.+?)['\"]?\s+(?:card|task\s+)?(?:ko\s+)?(?:complete|completed)\s*(?:kar\s+do|kardo|karo)", command, re.IGNORECASE)

        if completion_match:
            card_name = completion_match.group(1).strip().strip('"\'')
            card_name = re.sub(r"^(?:the\s+)?(?:card|task)\s+", "", card_name, flags=re.IGNORECASE).strip()
            target_status = "Done"
            tool_id = match_tool_id("trello_move_card") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
            params = {"card_name": card_name, "name": card_name, "target_status": target_status, "card_id": "c101", "list_id": "list_done"}
            if cmd_due_date:
                params["due_date"] = cmd_due_date
            if cmd_additional_desc:
                params["description"] = cmd_additional_desc
            return GeminiIntentOutput(
                intent="move_card",
                entity="card",
                entities={"card": card_name, "status": "Done"},
                parameters=params,
                action_parameters=dict(params),
                selected_template=None,
                missing_fields=[],
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.94,
            )

        active_move_match = move_hinglish or move_match1 or move_match2
        if active_move_match:
            if active_move_match == move_hinglish:
                raw_cname = move_hinglish.group(1).strip().strip('"\'')
                raw_target = move_hinglish.group(2).strip().strip('"\'')
            else:
                raw_cname = active_move_match.group(1).strip().strip('"\'')
                raw_target = active_move_match.group(3).strip().strip('"\'') if active_move_match.group(3) else active_move_match.group(2).strip().strip('"\'')

            raw_target = re.sub(r"^ko\s+", "", raw_target, flags=re.IGNORECASE).strip()
            raw_cname = re.sub(r"^(?:the\s+)?(?:card|task)\s+", "", raw_cname, flags=re.IGNORECASE).strip()
            raw_cname = re.sub(r"\s+(?:card|task)$", "", raw_cname, flags=re.IGNORECASE).strip()
            card_name = raw_cname if raw_cname else "Task Card"

            cleaned_target = re.sub(r"\s+(?:list|column)$", "", raw_target, flags=re.IGNORECASE).strip()

            # Preserve uppercase enum format if provided, else normalize or keep custom name
            if cleaned_target.upper() in ("IN_PROGRESS", "IN_REVIEW", "TODO", "DONE"):
                target_status = cleaned_target.upper()
            else:
                target_norm = cleaned_target.lower()
                if target_norm in ("todo", "to do", "backlog"):
                    target_status = "To Do"
                elif target_norm in ("doing", "in progress", "in_progress", "inprogress"):
                    target_status = "Doing"
                elif target_norm in ("done", "completed"):
                    target_status = "Done"
                elif target_norm in ("in-review", "in review", "in_review", "review"):
                    target_status = "In-Review"
                elif target_norm in ("testing", "qa"):
                    target_status = "Testing"
                else:
                    target_status = cleaned_target

            tool_id = match_tool_id("trello_move_card") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
            params = {
                "card_name": card_name,
                "name": card_name,
                "target_status": target_status,
                "card_id": "c101",
                "list_id": f"list_{target_status.lower().replace(' ', '_')}",
            }
            if cmd_due_date:
                params["due_date"] = cmd_due_date
            if cmd_additional_desc:
                params["description"] = cmd_additional_desc

            return GeminiIntentOutput(
                intent="move_card",
                entity="card",
                entities={"card": card_name, "list": target_status},
                parameters=params,
                action_parameters=dict(params),
                selected_template=None,
                missing_fields=[],
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.96,
            )

        # Check for bulk list deletion / clearing:
        # e.g., "delete all tasks of to do list", "delete all cards in doing", "clear to do list", "delete all tasks from to do"
        bulk_del_match1 = re.search(
            r"(?:delete|archive|remove|clear|trash|discard)\s+all\s+(?:the\s+)?(?:cards?|tasks?)\s+(?:of|in|from|under)?\s*(.+?)(?:\s+(?:list|column))?[\.\!]?$",
            cmd_lower,
            re.IGNORECASE,
        )
        bulk_del_match2 = re.search(
            r"(?:delete|clear|empty|trash)\s+(?:all\s+)?(?:the\s+)?(?:cards?|tasks?\s+(?:of|in|from)\s+)?(.+?)\s+(?:list|column)(?:\s+tasks?|\s+cards?)?[\.\!]?$",
            cmd_lower,
            re.IGNORECASE,
        )
        bulk_del_active = bulk_del_match1 or bulk_del_match2
        if bulk_del_active and any(w in cmd_lower for w in ["delete", "archive", "remove", "clear", "trash", "discard", "empty"]):
            raw_list = bulk_del_active.group(1).strip()
            raw_list = re.sub(r"^(?:of|in|from|under)\s+", "", raw_list, flags=re.IGNORECASE).strip()
            raw_list = re.sub(r"\s+(?:list|column)$", "", raw_list, flags=re.IGNORECASE).strip()
            if raw_list and raw_list not in ("card", "task"):
                tool_id = match_tool_id("trello_delete_card") or match_tool_id("trello_archive_card") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
                return GeminiIntentOutput(
                    intent="delete_list_cards",
                    entity="list",
                    parameters={
                        "list_name": raw_list,
                        "card_name": raw_list,
                        "name": raw_list,
                        "is_bulk_delete": True,
                        "action_type": "DELETE_LIST_CARDS",
                    },
                    suggested_tool_id=tool_id,
                    requires_clarification=False,
                    confidence=0.98,
                )

        # Check for card deletion / archiving: "delete card <name>", "delete Trello Starter Guide tasks", "archive card <name>", "remove card <name>",
        # or natural Hindi/conversational: "<name> card delete kardo", "<name> card hata do", "card <name> hatao"
        delete_match1 = re.search(
            r"(?:delete|archive|remove|discard|trash|hata\s+do|hatao)\s+(?:all\s+)?(?:the\s+)?(?:cards?|tasks?)?(?:\s+(?:in|from|under))?\s*(?:named|\s*:\s*|\s+called|\s+titled)?\s*(.+?)(?:\s+(?:cards?|tasks?))?[\.\!]?$",
            command,
            re.IGNORECASE,
        )
        delete_match2 = re.search(
            r"(.+?)\s+(?:cards?|tasks?\s+)?(?:delete|archive|remove|discard|trash|delete\s+kardo|delete\s+karo|hata\s+do|hatao)[\.\!]?$",
            command,
            re.IGNORECASE,
        )
        active_del = delete_match1 or delete_match2
        if active_del and any(w in cmd_lower for w in ["delete", "archive", "remove", "discard", "trash", "hata do", "hatao", "delete kardo"]):
            raw_card_name = active_del.group(1).replace("card", "").replace("task", "").strip().strip('"\'').rstrip(".")
            tool_id = match_tool_id("trello_delete_card") or match_tool_id("trello_archive_card") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
            return GeminiIntentOutput(
                intent="delete_card",
                entity="card",
                parameters={"card_name": raw_card_name, "name": raw_card_name},
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.96,
            )

        # Check for intelligent employee recommendation:
        # e.g., "Who should I assign this task to?", "Which employee is currently free?", "Rahul has fewer tasks. Can he handle this task?",
        # "Mujhe ye task kis employee ko dena chahiye?", "who can take this task", "recommend someone for task X"
        is_recommend_query = (
            any(w in cmd_lower for w in ["who should i assign", "which employee is free", "which employee is currently free", "who is free", "who can handle", "who can take", "recommend an employee", "recommend employee", "who should do", "which employee should"])
            or ("which employee" in cmd_lower and any(w in cmd_lower for w in ["handle", "assign", "take", "free", "do", "work", "give"]))
            or ("kis employee" in cmd_lower and any(w in cmd_lower for w in ["dena", "assign", "de", "du", "chahiye"]))
            or ("kaun" in cmd_lower and any(w in cmd_lower for w in ["free", "handle", "karega", "kare"]))
            or (any(w in cmd_lower for w in ["fewer tasks", "less tasks", "can he handle", "can she handle", "can they handle"]))
        )
        if is_recommend_query:
            tool_id = match_tool_id("employee_recommend_assignment") or "employee_recommend_assignment"
            rec_params: Dict[str, Any] = {}
            target_emp = None
            emp_q_match = re.search(r"([a-zA-Z0-9_\-\[\]]+?)\s+(?:has\s+fewer\s+tasks|has\s+less\s+tasks|free\s+hai|handle\s+kar\s+sakta)", command, re.IGNORECASE)
            if emp_q_match:
                target_emp = emp_q_match.group(1).strip()
            task_name_m = re.search(r"(?:for|assign|handle|take)\s+(?:this\s+)?(?:task|card)?\s*['\"]?([a-zA-Z0-9_\-\s]+?)['\"]?(?:\?|\.|$)", command, re.IGNORECASE)
            if task_name_m and task_name_m.group(1).lower() not in ("this", "the", "a", "an", "task", "card"):
                rec_params["task_name"] = task_name_m.group(1).strip()
            if target_emp:
                rec_params["target_employee"] = target_emp

            return GeminiIntentOutput(
                intent="recommend_employee",
                entity="employee",
                entities={"person": target_emp} if target_emp else {},
                parameters=rec_params,
                action_parameters=dict(rec_params),
                selected_template=None,
                missing_fields=[],
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.95,
            )

        # Check for workload reports: "show workload", "report", "analytics"
        if "workload" in cmd_lower or "report" in cmd_lower or "analytics" in cmd_lower:
            tool_id = match_tool_id("report_get_workload") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
            return GeminiIntentOutput(
                intent="get_workload",
                entity="report",
                parameters={"report_type": "daily"},
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.85,
            )

        # Check for card details: "details of card <name>", "get card details <name>"
        if "details" in cmd_lower or "inspect" in cmd_lower:
            card_match = re.search(r"(?:details|inspect|info)\s+(?:of\s+|for\s+)?(?:card\s+)?(.+)", command, re.IGNORECASE)
            card_name = card_match.group(1).strip().strip('"\'') if card_match else "Card"
            tool_id = match_tool_id("trello_get_card") or match_tool_id("trello_get_card_details") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
            return GeminiIntentOutput(
                intent="get_card_details",
                entity="card",
                parameters={"card_name": card_name, "card_id": "c101"},
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.88,
            )

        # Check for employee directory / staff roster
        if ("employee" in cmd_lower or "staff" in cmd_lower or "team" in cmd_lower) and ("directory" in cmd_lower or "list" in cmd_lower or "roster" in cmd_lower or "members" in cmd_lower):
            tool_id = match_tool_id("employee_list_directory") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
            return GeminiIntentOutput(
                intent="list_employees",
                entity="employee",
                parameters={},
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.86,
            )

        # Check for card search: "search cards <query>", "find <query>"
        search_match = re.search(r"(?:search|find|lookup|show)\s+(?:cards?\s+(?:for\s+)?)?(.+)", command, re.IGNORECASE)
        if search_match and any("search" in t.tool.tool_id for t in discovered_tools):
            search_query = search_match.group(1).strip().strip('"\'')
            return GeminiIntentOutput(
                intent="search_cards",
                entity="card",
                parameters={"query": search_query},
                suggested_tool_id="trello_search_cards",
                requires_clarification=False,
                confidence=0.88,
            )

        # If matching tool found in discovered tools
        if discovered_tools:
            top_tool = discovered_tools[0].tool
            return GeminiIntentOutput(
                intent=f"invoke_{top_tool.tool_id}",
                entity="task",
                parameters={},
                suggested_tool_id=top_tool.tool_id,
                requires_clarification=False,
                confidence=round(discovered_tools[0].relevance_score, 2),
            )

        # Ambiguous command
        return GeminiIntentOutput(
            intent="unknown",
            entity="none",
            parameters={},
            suggested_tool_id=None,
            requires_clarification=True,
            clarification_message=f"I could not identify a registered tool for '{command}'. Could you please rephrase or specify the action?",
            confidence=0.2,
        )

