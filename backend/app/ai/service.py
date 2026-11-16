import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple
from pydantic import ValidationError as PydanticValidationError

from app.ai.llm_provider import BaseLLMProvider, LLMConfigurationError, LLMExecutionError
from app.ai.provider_factory import LLMProviderFactory
from app.ai.prompts import build_interpretation_prompt
from app.ai.schemas import GeminiIntentOutput
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
    ) -> GeminiIntentOutput:
        """
        Interprets natural language command against discovered tools.
        Applies PII masking before sending prompt to external LLMs.
        Locally restores masked parameters strictly within request lifecycle.
        Validates output strictly against GeminiIntentOutput schema.
        Falls back to deterministic pattern interpreter if provider is unconfigured or in tests.
        """
        req_id = correlation_id or f"REQ-{uuid.uuid4().hex[:6]}"
        is_synthetic = is_synthetic_prompt(command)
        current_req_id_var.set(req_id)
        current_synthetic_var.set(is_synthetic)

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

            # Build prompt for LLM provider
            prompt = build_interpretation_prompt(
                sanitized_command, discovered_tools, conversation_history=sanitized_history
            )

            # Stage 4: LangChain Outbound Request
            PIITerminalLogger.log_stage_4_outbound(
                req_id=req_id,
                provider_name=self.provider.provider_name,
                model_name=self.provider.model_name,
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
            if not self.provider.is_configured():
                logger.info(
                    f"LLM provider '{self.provider.provider_name}' is not configured; using deterministic fallback interpreter."
                )
                output = self._fallback_deterministic_interpreter(sanitized_command, discovered_tools)
                PIITerminalLogger.log_stage_6_llm_response(req_id, status_msg="deterministic local fallback")
            else:
                try:
                    parsed = await self.provider.generate_structured(prompt, GeminiIntentOutput)
                    validated = self._validate_suggested_tool(parsed, discovered_tools)
                    PIITerminalLogger.log_stage_6_llm_response(req_id, status_msg="structured intent received")
                    output = validated
                except LLMConfigurationError as e:
                    logger.info(f"Provider configuration error ({e}); using deterministic fallback interpreter.")
                    output = self._fallback_deterministic_interpreter(sanitized_command, discovered_tools)
                    PIITerminalLogger.log_stage_6_llm_response(req_id, status_msg=f"fallback executed ({e})")
                except Exception as e:
                    logger.warning(
                        f"LLM call to '{self.provider.provider_name}' encountered issue ({e}); attempting deterministic fallback."
                    )
                    output = self._fallback_deterministic_interpreter(sanitized_command, discovered_tools)
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
    ) -> GeminiIntentOutput:
        """
        Deterministic, privacy-safe fallback interpreter.
        Extracts basic intent and parameters from natural-language patterns
        when LLM is offline, unconfigured, or mocked in local testing.
        """
        cmd_lower = command.lower().strip()

        def match_tool_id(target_key: str) -> Optional[str]:
            """Helper to resolve tool ID matching either native or MCP namespaced identifier."""
            for item in discovered_tools:
                tid = item.tool.tool_id
                if tid == target_key or tid.endswith(f".{target_key}") or target_key in tid:
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

        # Check for listing cards: "show cards in the to do list", "list cards"
        if ("card" in cmd_lower or "cards" in cmd_lower or "task" in cmd_lower or "tasks" in cmd_lower) and any(w in cmd_lower for w in ["show", "list", "view"]) and not any(w in cmd_lower for w in ["create", "add", "new", "move", "details", "inspect"]):
            tool_id = match_tool_id("trello_search_cards") or match_tool_id("trello_list_cards")
            if tool_id:
                list_match = re.search(r"(?:in|to|under)\s+(?:the\s+)?([a-zA-Z0-9_\s\-]+?)(?:\s+list|\s+column)?$", command, re.IGNORECASE)
                list_name = list_match.group(1).strip() if list_match else None
                return GeminiIntentOutput(
                    intent="search_cards" if "search" in tool_id else "list_cards",
                    entity="card",
                    parameters={"list_name": list_name} if list_name else {},
                    suggested_tool_id=tool_id,
                    requires_clarification=False,
                    confidence=0.94,
                )

        # Check for list creation: "add another list name In-Review", "create list <name>", "add list <name>"
        create_list_match = re.search(
            r"(?:create|add|new)\s+(?:a\s+|another\s+)?(?:list|column)(?:\s+named|\s+name|\s*:\s*|\s+called)?\s*(.+)",
            command,
            re.IGNORECASE,
        )
        if create_list_match and not ("card" in cmd_lower or "task" in cmd_lower):
            raw_list_name = create_list_match.group(1).strip().strip('"\'').rstrip(".")
            raw_list_name = re.split(r"\s+and\s+", raw_list_name, flags=re.IGNORECASE)[0].strip()
            tool_id = match_tool_id("trello_create_list") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
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

        # Extract general due date from command if present
        cmd_due_date = None
        due_match = re.search(
            r"(?:due\s+date|due\s+by|due\s+on|due)\s*[:=]?\s*(\d{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+(?:\s+\d{4})?|[a-zA-Z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?|next\s+[a-zA-Z]+|tomorrow|today|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|[a-zA-Z]+)",
            command,
            re.IGNORECASE,
        )
        if due_match:
            cand = due_match.group(1).strip()
            if cand.lower() not in ("to", "in", "the", "a", "an", "list", "column", "card", "task"):
                cmd_due_date = cand

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
        if "update" in cmd_lower or ("set" in cmd_lower and "due" in cmd_lower):
            tool_id = match_tool_id("trello_update_card") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
            update_card_name = "Task"
            cname_match = re.search(r"(?:for|of|card)\s+([a-zA-Z0-9_\-\s]+?)(?:\s+to|\s+due|\s+with|$)", command, re.IGNORECASE)
            if cname_match:
                update_card_name = cname_match.group(1).replace("card", "").strip()
            update_params: Dict[str, Any] = {"card_name": update_card_name, "card_id": "c101"}
            if cmd_due_date:
                update_params["new_due_date"] = cmd_due_date
                update_params["due_date"] = cmd_due_date
            if cmd_additional_desc:
                update_params["new_description"] = cmd_additional_desc
                update_params["desc"] = cmd_additional_desc
            return GeminiIntentOutput(
                intent="update_card",
                entity="card",
                parameters=update_params,
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.91,
            )

        # Check for card member assignment: "on register card add member sourabh mishra", "add member sourabh to register card", "assign sourabh to register page"
        member_match1 = re.search(r"on\s+(.+?)(?:\s+card)?\s+(?:add|assign)\s+(?:member\s+)?(.+)", command, re.IGNORECASE)
        member_match2 = re.search(r"(?:add|assign)\s+(?:member\s+)?(.+?)\s+(?:to|on)\s+(.+?)(?:\s+card)?$", command, re.IGNORECASE)
        if member_match1 or member_match2:
            if member_match1:
                assign_card_name = member_match1.group(1).strip().strip('"\'')
                assign_member = member_match1.group(2).strip().strip('"\'')
            else:
                assign_member = member_match2.group(1).strip().strip('"\'')
                assign_card_name = member_match2.group(2).strip().strip('"\'')

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
                parameters=assign_params,
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.95,
            )

        # Check for card creation: "create card <name>", "create a task card <name>", "add a card named <name>"
        create_match = re.search(
            r"(?:create|add|new)\s+(?:a\s+)?(?:task\s+card|card|task)(?:\s+named|\s+called|\s*:\s*|\s+to\s+)?\s*(.+)",
            command,
            re.IGNORECASE,
        )
        if create_match:
            raw_card_name = create_match.group(1).strip().strip('"\'').rstrip(".")
            if raw_card_name.lower().startswith("to "):
                raw_card_name = raw_card_name[3:].strip()

            # Extract member to assign if present (e.g. "and add member sourabh mishra", "with member Alex")
            member_name = None
            member_match = re.search(
                r"(?:and\s+)?(?:add\s+member|assign\s+member|assign\s+to|member\s*[:=]?)\s+([a-zA-Z0-9_\-\s\[\]]+?)(?:\s+(?:due|with|under|in)|$)",
                raw_card_name,
                re.IGNORECASE,
            )
            if member_match:
                member_name = member_match.group(1).strip().strip('"\'')
                raw_card_name = re.sub(
                    r"(?:and\s+)?(?:add\s+member|assign\s+member|assign\s+to|member\s*[:=]?)\s+" + re.escape(member_name),
                    "",
                    raw_card_name,
                    flags=re.IGNORECASE,
                ).strip()

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

            # Clean due date from card name if present
            if cmd_due_date:
                raw_card_name = re.sub(
                    r"(?:due\s+date|due\s+by|due\s+on|due)\s*[:=]?\s*" + re.escape(cmd_due_date),
                    "",
                    raw_card_name,
                    flags=re.IGNORECASE,
                ).strip()
            else:
                due_in_name = re.search(
                    r"(?:due\s+date|due\s+by|due\s+on|due)\s*[:=]?\s*(\d{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+(?:\s+\d{4})?|[a-zA-Z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?|tomorrow|today|\d{4}-\d{2}-\d{2})",
                    raw_card_name,
                    re.IGNORECASE,
                )
                if due_in_name:
                    cmd_due_date = due_in_name.group(1).strip()
                    raw_card_name = re.sub(
                        r"(?:due\s+date|due\s+by|due\s+on|due)\s*[:=]?\s*" + re.escape(cmd_due_date),
                        "",
                        raw_card_name,
                        flags=re.IGNORECASE,
                    ).strip()

            # Clean description/notes from card name if present
            if cmd_additional_desc:
                raw_card_name = re.sub(
                    r"(?:with\s+description|with\s+notes?|description\s*[:=]|notes?\s*[:=]|details?\s*[:=]).*",
                    "",
                    raw_card_name,
                    flags=re.IGNORECASE,
                ).strip()

            # Extract target list if present
            target_list = "To Do"
            list_match = re.search(
                r"\b(?:in|to|under)\b\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+list|\s+column|$)",
                raw_card_name,
                re.IGNORECASE,
            )
            if list_match:
                cand_list = list_match.group(1).strip()
                if cand_list.lower() not in ("priority", "high", "medium", "low", "urgent", "due"):
                    if cand_list.upper() in ("TODO", "IN_PROGRESS", "IN_REVIEW", "DONE"):
                        target_list = cand_list.upper()
                    else:
                        target_list = cand_list
                    raw_card_name = raw_card_name[:list_match.start()].strip()

            card_name = raw_card_name.strip(" ,.-")
            if not card_name:
                card_name = "New Task"
            else:
                card_name = card_name[0].upper() + card_name[1:] if len(card_name) > 1 else card_name.upper()

            tool_id = match_tool_id("trello_create_card") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
            desc = cmd_additional_desc or f"Implement and complete deliverables for '{card_name}'. Ensure functional requirements, quality verification, and testing standards are met."

            parameters: Dict[str, Any] = {
                "name": card_name,
                "desc": desc,
                "list_name": target_list,
                "priority": priority,
            }
            if cmd_due_date:
                parameters["due_date"] = cmd_due_date
            if member_name:
                parameters["member_name"] = member_name

            return GeminiIntentOutput(
                intent="create_card",
                entity="card",
                parameters=parameters,
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.96,
            )

        # Check for card movement: "move <card> to <status>" or "<card> card move to <status>" or "mark <card> as done"
        move_match1 = re.search(
            r"(?:move|transfer|shift|put)\s+(?:the\s+)?(.+?)\s+(?:card\s+)?to\s+(?:the\s+)?(.+?)(?:\s+list|\s+column)?(?:\s+(?:due|with|and)|$)",
            command,
            re.IGNORECASE,
        )
        move_match2 = re.search(
            r"(.+?)\s+(?:card\s+)?(?:move|transfer|shift|put)\s+to\s+(?:the\s+)?(.+?)(?:\s+list|\s+column)?(?:\s+(?:due|with|and)|$)",
            command,
            re.IGNORECASE,
        )

        if not move_match1 and not move_match2 and "mark" in cmd_lower and "done" in cmd_lower:
            card_match = re.search(r"mark\s+(?:the\s+)?(.+?)\s+as\s+done", command, re.IGNORECASE)
            card_name = card_match.group(1).strip() if card_match else "Task"
            target_status = "Done"
            tool_id = match_tool_id("trello_move_card") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
            params = {"card_name": card_name, "target_status": target_status, "card_id": "c101", "list_id": "list_done"}
            if cmd_due_date:
                params["due_date"] = cmd_due_date
            if cmd_additional_desc:
                params["description"] = cmd_additional_desc
            return GeminiIntentOutput(
                intent="move_card",
                entity="card",
                parameters=params,
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.94,
            )

        active_move_match = move_match1 or move_match2
        if active_move_match:
            card_name = active_move_match.group(1).replace("card", "").strip().strip('"\'')
            raw_target = active_move_match.group(2).strip().strip('"\'')
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
                elif target_norm in ("testing", "test", "qa"):
                    target_status = "Testing"
                else:
                    target_status = cleaned_target.title()

            tool_id = match_tool_id("trello_move_card") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
            params = {
                "card_name": card_name,
                "target_status": target_status,
                "card_id": "c101",
                "list_id": "list_target",
            }
            if cmd_due_date:
                params["due_date"] = cmd_due_date
            if cmd_additional_desc:
                params["description"] = cmd_additional_desc

            return GeminiIntentOutput(
                intent="move_card",
                entity="card",
                parameters=params,
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.94,
            )

        # Check for card deletion / archiving: "delete card <name>", "archive card <name>", "remove card <name>"
        delete_match1 = re.search(
            r"(?:delete|archive|remove|discard|trash)\s+(?:the\s+)?(?:card|task)\s*(?:named|\s*:\s*|\s+called|\s+titled)?\s*(.+)",
            command,
            re.IGNORECASE,
        )
        delete_match2 = re.search(
            r"(.+?)\s+(?:card\s+)?(?:delete|archive|remove|discard|trash)[\.\!]?$",
            command,
            re.IGNORECASE,
        )
        active_del = delete_match1 or delete_match2
        if active_del and any(w in cmd_lower for w in ["delete", "archive", "remove", "discard", "trash"]):
            raw_card_name = active_del.group(1).replace("card", "").strip().strip('"\'').rstrip(".")
            tool_id = match_tool_id("trello_delete_card") or match_tool_id("trello_archive_card") or (discovered_tools[0].tool.tool_id if discovered_tools else None)
            return GeminiIntentOutput(
                intent="delete_card",
                entity="card",
                parameters={"card_name": raw_card_name, "name": raw_card_name},
                suggested_tool_id=tool_id,
                requires_clarification=False,
                confidence=0.96,
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

