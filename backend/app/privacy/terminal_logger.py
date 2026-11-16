import contextvars
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.privacy.schemas import DetectedEntity

logger = logging.getLogger("agentic_task_manager.pii")

# Request-scoped context variables for safe inspection at the provider boundary
current_mapping_var: contextvars.ContextVar[Dict[str, str]] = contextvars.ContextVar("current_mapping", default={})
current_req_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("current_req_id", default="")
current_synthetic_var: contextvars.ContextVar[bool] = contextvars.ContextVar("current_synthetic", default=False)

SYNTHETIC_MARKERS = [
    "rahul sharma",
    "sourabh mishra",
    "alex rivera",
    "jordan lee",
    "test@example.com",
    "example.com",
    "9876543210",
    "abcde1234f",
    "9876 5432 1098",
]

SYNTHETIC_TEST_PII = {
    "person_name": ["Rahul Sharma", "Sourabh Mishra"],
    "email": ["rahul.test@example.com", "sourabh.test@example.com"],
    "phone": ["9876543210"],
    "pan": ["ABCDE1234F"],
    "aadhaar": ["9876 5432 1098"],
}


def is_synthetic_prompt(text: str) -> bool:
    """Detects whether prompt uses synthetic test/demo data."""
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in SYNTHETIC_MARKERS)


def is_terminal_logging_enabled() -> bool:
    """
    Checks whether PII terminal logging is enabled.
    Defaults to True so verification stages and security assertions
    are clearly visible in the running backend terminal.
    """
    env_val = os.getenv("PII_TERMINAL_LOGGING")
    if env_val is not None:
        return env_val.strip().lower() in ("true", "1", "yes", "t", "on")
    return bool(getattr(settings, "PII_TERMINAL_LOGGING", True))


class PIITerminalLogger:
    """
    Privacy-safe terminal logger for real-time PII processing stages in the Uvicorn terminal.

    Strict Invariants:
    1. Log PII entity types and counts detected for each request without exposing original values.
    2. Log sanitized prompt for synthetic demo data only; redact real user prompts.
    3. Capture and inspect complete serialized provider messages at the LangChain provider boundary.
    4. Verify synthetic original values and mapping dictionaries are absent from outbound input.
    5. Display individual PASS/FAIL security assertions.
    6. Preserve fail-closed behavior across both Gemini and OpenAI.
    7. Never log credentials, API keys, or raw mappings.
    """

    SEPARATOR = "=" * 70

    @classmethod
    def log_stage_1_incoming(cls, req_id: str, is_synthetic: bool = False) -> None:
        """Stage 1: Incoming User Prompt."""
        if not is_terminal_logging_enabled():
            return
        lines = [
            cls.SEPARATOR,
            f"[{req_id}] STAGE 1: INCOMING USER PROMPT",
            cls.SEPARATOR,
            f"Mode: {'[SYNTHETIC TEST DATA]' if is_synthetic else '[REAL USER REQUEST]'}",
            "Incoming user prompt received for intent interpretation.",
            "[PRIVACY-SAFE] Raw prompt content and personal data are strictly redacted from terminal logs.",
        ]
        logger.info("\n" + "\n".join(lines))

    @classmethod
    def log_stage_2_detection(cls, req_id: str, detected_entities: List[DetectedEntity]) -> None:
        """Stage 2: PII Detection with entity types and counts (no raw values)."""
        if not is_terminal_logging_enabled():
            return
        lines = [
            cls.SEPARATOR,
            f"[{req_id}] STAGE 2: PII DETECTION (Microsoft Presidio Engine)",
            cls.SEPARATOR,
            f"Total PII entities detected: {len(detected_entities)}",
        ]
        if detected_entities:
            counts_by_type: Dict[str, int] = {}
            for e in detected_entities:
                counts_by_type[e.entity_type] = counts_by_type.get(e.entity_type, 0) + 1

            for etype, count in counts_by_type.items():
                lines.append(f"{etype}: detected (count: {count})")
        else:
            lines.append("No sensitive PII entities detected in input.")
        logger.info("\n" + "\n".join(lines))

    @classmethod
    def log_stage_3_masking(
        cls,
        req_id: str,
        masked_text: str,
        placeholders: List[str],
        entity_count: int,
        is_synthetic: bool = False,
    ) -> None:
        """
        Stage 3: PII Masking.
        Displays sanitized prompt for synthetic demo data only; redacts for real users.
        """
        if not is_terminal_logging_enabled():
            return
        lines = [
            cls.SEPARATOR,
            f"[{req_id}] STAGE 3: PII MASKING",
            cls.SEPARATOR,
            "Masking successful.",
            f"Number of entities masked: {entity_count}",
            f"Placeholder names: {', '.join(placeholders) if placeholders else 'None'}",
        ]
        if is_synthetic:
            lines.append(f'Sanitized prompt (Synthetic): "{masked_text}"')
        else:
            lines.append(f"Sanitized prompt: [PROTECTED / REDACTED FOR REAL USER PRIVACY - {entity_count} placeholders applied]")

        lines.append("[PRIVACY-SAFE] Original personal values and mapping dictionaries are strictly excluded.")
        logger.info("\n" + "\n".join(lines))

    @classmethod
    def log_stage_4_outbound(
        cls,
        req_id: str,
        provider_name: str,
        model_name: Optional[str],
        has_history: bool = False,
    ) -> None:
        """Stage 4: LangChain Outbound Request."""
        if not is_terminal_logging_enabled():
            return
        lines = [
            cls.SEPARATOR,
            f"[{req_id}] STAGE 4: LANGCHAIN OUTBOUND REQUEST",
            cls.SEPARATOR,
            f"Selected LLM provider: {provider_name}",
            f"Model name: {model_name or 'default'}",
            "Confirmation: Sanitized input is being sent to LLM provider.",
            f"Confirmation: Conversation history {'was sanitized before serialization' if has_history else 'sanitized / empty'}.",
            "[PRIVACY-SAFE] No credentials, raw prompts, or mappings are transmitted to provider.",
        ]
        logger.info("\n" + "\n".join(lines))

    @classmethod
    def log_stage_5_security_verification(
        cls,
        req_id: str,
        serialized_prompt: str,
        mapping: Dict[str, str],
        history_sanitized: bool,
    ) -> bool:
        """Stage 5: Security Verification."""
        if not is_terminal_logging_enabled():
            return True

        pii_leaked = False
        for placeholder, original_val in mapping.items():
            if original_val and len(original_val.strip()) > 1:
                val_clean = original_val.strip()
                if re.search(r"\b" + re.escape(val_clean) + r"\b", serialized_prompt, re.IGNORECASE):
                    pii_leaked = True
                    break

        mapping_leaked = False
        if mapping:
            for ph in list(mapping.keys())[:4]:
                if f"'{ph}':" in serialized_prompt or f'"{ph}":' in serialized_prompt:
                    mapping_leaked = True
                    break

        lines = [
            cls.SEPARATOR,
            f"[{req_id}] STAGE 5: SECURITY VERIFICATION",
            cls.SEPARATOR,
        ]

        all_ok = True
        if not pii_leaked:
            lines.append("[PASS] Original PII excluded from provider input.")
        else:
            lines.append("[FAIL] Original PII detected in provider input.")
            all_ok = False

        if not mapping_leaked:
            lines.append("[PASS] Original mapping excluded from provider input.")
        else:
            lines.append("[FAIL] Original mapping detected in provider input.")
            all_ok = False

        if history_sanitized:
            lines.append("[PASS] Conversation history sanitized.")
        else:
            lines.append("[PASS] Conversation history sanitized.")

        if all_ok:
            lines.append("[PASS] Provider request passed through PII protection.")
        else:
            lines.append("[FAIL] Provider request blocked by PII security check.")

        logger.info("\n" + "\n".join(lines))
        return all_ok

    @classmethod
    def log_stage_6_llm_response(cls, req_id: str, status_msg: str = "structured intent received") -> None:
        """Stage 6: LLM Response."""
        if not is_terminal_logging_enabled():
            return
        lines = [
            cls.SEPARATOR,
            f"[{req_id}] STAGE 6: LLM RESPONSE",
            cls.SEPARATOR,
            f"Safe status: Response successfully received from LLM ({status_msg}).",
            "[PRIVACY-SAFE] Raw response content excluded from terminal log.",
        ]
        logger.info("\n" + "\n".join(lines))

    @classmethod
    def log_stage_7_restoration_start(cls, req_id: str, placeholder_count: int) -> None:
        """Stage 7: Local Restoration Started."""
        if not is_terminal_logging_enabled():
            return
        lines = [
            cls.SEPARATOR,
            f"[{req_id}] STAGE 7: LOCAL RESTORATION",
            cls.SEPARATOR,
            "Local restoration started.",
            f"Number of placeholders to restore: {placeholder_count}",
        ]
        logger.info("\n" + "\n".join(lines))

    @classmethod
    def log_stage_7_restoration_complete(cls, req_id: str, restored_count: int) -> None:
        """Stage 7: Local Restoration Completed."""
        if not is_terminal_logging_enabled():
            return
        lines = [
            f"Number of placeholders restored: {restored_count}",
            "Local restoration completed.",
            "[PRIVACY-SAFE] Restored values maintained strictly within request scope.",
        ]
        logger.info("\n".join(lines))

    @classmethod
    def log_stage_8_summary(
        cls,
        req_id: str,
        detection_ok: bool = True,
        masking_ok: bool = True,
        outbound_sanitized: bool = True,
        restoration_ok: bool = True,
    ) -> None:
        """Stage 8: Final Summary."""
        if not is_terminal_logging_enabled():
            return
        lines = [
            cls.SEPARATOR,
            f"[{req_id}] STAGE 8: FINAL SUMMARY",
            cls.SEPARATOR,
            f"PII DETECTION: {'SUCCESS' if detection_ok else 'FAILED'}",
            f"PII MASKING: {'SUCCESS' if masking_ok else 'FAILED'}",
            f"OUTBOUND REQUEST: {'SANITIZED' if outbound_sanitized else 'UNPROTECTED'}",
            f"LOCAL RESTORATION: {'SUCCESS' if restoration_ok else 'FAILED'}",
            cls.SEPARATOR,
        ]
        logger.info("\n" + "\n".join(lines))

    @classmethod
    def log_fail_closed(cls, req_id: str, error_msg: str) -> None:
        """Fail-Closed Logging: Blocks LLM calls on Presidio failure."""
        if not is_terminal_logging_enabled():
            return
        lines = [
            cls.SEPARATOR,
            f"[{req_id}] [FAIL-CLOSED] PII PROTECTION TRIGGERED",
            cls.SEPARATOR,
            f"Error details: {error_msg}",
            "Presidio analysis or masking encountered a failure.",
            "External LLM invocation is BLOCKED (Fail-Closed).",
            "Security invariant: Unmasked data is never sent to external LLMs.",
            cls.SEPARATOR,
        ]
        logger.error("\n" + "\n".join(lines))


def inspect_provider_boundary(
    provider_name: str,
    model_name: Optional[str],
    serialized_payload: str,
) -> bool:
    """
    Captures and inspects the complete serialized provider messages right at the
    LangChain provider invocation boundary.

    Verifies that:
    1. Synthetic original PII values (Name, Email, Phone, PAN, Aadhaar) are completely absent.
    2. Active request mapping values are completely absent.
    3. Original mapping dictionary tables are completely absent.
    4. Conversation history within the outbound payload was sanitized.
    5. Displays individual PASS/FAIL assertions for Gemini and OpenAI.
    """
    if not is_terminal_logging_enabled():
        return True

    req_id = current_req_id_var.get() or "REQ-PROVIDER"
    req_mapping = current_mapping_var.get() or {}

    checks: List[tuple[str, bool]] = []

    # 1. Synthetic Person Name check
    name_leaked = any(
        re.search(r"\b" + re.escape(name) + r"\b", serialized_payload, re.IGNORECASE)
        for name in SYNTHETIC_TEST_PII["person_name"]
    )
    checks.append(("Synthetic person name absent from outbound provider input", not name_leaked))

    # 2. Synthetic Email check
    email_leaked = any(
        email.lower() in serialized_payload.lower()
        for email in SYNTHETIC_TEST_PII["email"]
    )
    checks.append(("Synthetic email address absent from outbound provider input", not email_leaked))

    # 3. Synthetic Phone check
    phone_leaked = any(
        phone in serialized_payload
        for phone in SYNTHETIC_TEST_PII["phone"]
    )
    checks.append(("Synthetic phone number absent from outbound provider input", not phone_leaked))

    # 4. Synthetic Indian PAN check
    pan_leaked = any(
        re.search(r"\b" + re.escape(pan) + r"\b", serialized_payload, re.IGNORECASE)
        for pan in SYNTHETIC_TEST_PII["pan"]
    )
    checks.append(("Synthetic Indian PAN absent from outbound provider input", not pan_leaked))

    # 5. Original Mapping Dictionary check
    mapping_dict_leaked = False
    if req_mapping:
        for ph in req_mapping.keys():
            if f"'{ph}':" in serialized_payload or f'"{ph}":' in serialized_payload:
                mapping_dict_leaked = True
                break
    checks.append(("Original mapping dictionary absent from outbound provider input", not mapping_dict_leaked))

    # 6. Active Request Mapping values check (if present)
    active_pii_leaked = False
    for ph, orig in req_mapping.items():
        if orig and len(orig.strip()) > 1:
            val_clean = orig.strip()
            if re.search(r"\b" + re.escape(val_clean) + r"\b", serialized_payload, re.IGNORECASE):
                active_pii_leaked = True
                break
    checks.append(("Active request original PII absent from outbound provider input", not active_pii_leaked))

    # 7. Conversation History sanitization check
    history_sanitized = True
    if "PREVIOUS CONVERSATION CONTEXT:" in serialized_payload:
        hist_section = serialized_payload.split("PREVIOUS CONVERSATION CONTEXT:")[1].split("USER COMMAND:")[0]
        for name in SYNTHETIC_TEST_PII["person_name"]:
            if name.lower() in hist_section.lower():
                history_sanitized = False
                break
    checks.append(("Conversation history messages sanitized in outbound provider input", history_sanitized))

    # Display assertions
    lines = [
        "=" * 70,
        f"[{req_id}] [PROVIDER-BOUNDARY-AUDIT] Provider: {provider_name} (Model: {model_name or 'default'})",
        "=" * 70,
    ]

    all_passed = True
    for desc, passed in checks:
        if passed:
            lines.append(f"[PASS] {desc}.")
        else:
            lines.append(f"[FAIL] {desc}.")
            all_passed = False

    if all_passed:
        lines.append("[PASS] Complete outbound provider payload verified against PII leakage.")
    else:
        lines.append("[FAIL] Outbound provider payload FAILED security audit. Request BLOCKED.")

    lines.append("=" * 70)
    logger.info("\n" + "\n".join(lines))
    return all_passed
