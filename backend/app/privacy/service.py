import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
try:
    import tldextract
    # Ensure tldextract uses local package snapshot and doesn't make network calls
    _offline_extractor = tldextract.TLDExtract(suffix_list_urls=None)
    tldextract.extract = _offline_extractor
except Exception:
    pass

from app.core.config import settings
from app.core.exceptions import PIIMaskingError
from app.privacy.schemas import DetectedEntity, PIIMaskResult
from app.privacy.recognizers.indian_recognizers import (
    IndianPhoneRecognizer,
    IndianPanRecognizer,
    IndianAadhaarRecognizer,
    IndianPassportRecognizer,
    TaskMemberNameRecognizer,
)

logger = logging.getLogger(__name__)


class PIIService:
    """
    Service responsible for detecting and masking Personally Identifiable Information (PII)
    prior to sending prompts/context to external LLMs, and locally restoring values when needed.

    Guarantees:
    1. Request-scoped isolation: mappings are never stored globally or shared across requests.
    2. Zero LLM exposure: original PII and mapping dictionaries are never sent to external LLMs.
    3. Fail-closed: raises PIIMaskingError if detection or masking fails when masking is enabled.
    4. Deterministic placeholder deduplication: repeated values receive the identical placeholder.
    """

    def __init__(
        self,
        analyzer: Optional[AnalyzerEngine] = None,
        anonymizer: Optional[AnonymizerEngine] = None,
    ):
        self.enabled = settings.PII_MASKING_ENABLED
        self.threshold = settings.PII_MASKING_THRESHOLD
        self.supported_entities = list(settings.PII_MASKING_ENTITIES)

        try:
            if analyzer is not None:
                self.analyzer = analyzer
            else:
                nlp_config = {
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]
                }
                nlp_provider = NlpEngineProvider(nlp_configuration=nlp_config)
                nlp_engine = nlp_provider.create_engine()
                self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
                self._register_custom_recognizers()

            self.anonymizer = anonymizer or AnonymizerEngine()
            logger.info(
                "PIIService initialized successfully. Enabled=%s, Threshold=%s, Entities=%s",
                self.enabled,
                self.threshold,
                len(self.supported_entities),
            )
        except Exception as exc:
            logger.error("Failed to initialize PIIService: %s", exc)
            self.analyzer = None
            self.anonymizer = None

    def _register_custom_recognizers(self) -> None:
        """Register Indian-specific and customized recognizers to Presidio registry."""
        if not self.analyzer:
            return

        registry = self.analyzer.registry
        registry.add_recognizer(IndianPhoneRecognizer())
        registry.add_recognizer(IndianPanRecognizer())
        registry.add_recognizer(IndianAadhaarRecognizer())
        registry.add_recognizer(IndianPassportRecognizer())
        registry.add_recognizer(TaskMemberNameRecognizer())

    def mask_text(
        self,
        text: str,
        entities: Optional[List[str]] = None,
        score_threshold: Optional[float] = None,
        correlation_id: Optional[str] = None,
    ) -> PIIMaskResult:
        """
        Detect and mask PII entities in the input text with unique, deterministic placeholders.

        Returns a request-scoped PIIMaskResult containing:
        - original_text
        - masked_text
        - detected_entities
        - mapping: Dict[placeholder -> original_value] (REQUEST-SCOPED ONLY)
        - reverse_mapping: Dict[original_value -> placeholder]

        Fail-closed: If masking fails when enabled, raises PIIMaskingError.
        """
        if not self.enabled:
            return PIIMaskResult(
                original_text=text,
                masked_text=text,
                detected_entities=[],
                mapping={},
                reverse_mapping={},
            )

        if not text or not text.strip():
            return PIIMaskResult(
                original_text=text,
                masked_text=text,
                detected_entities=[],
                mapping={},
                reverse_mapping={},
            )

        if self.analyzer is None:
            raise PIIMaskingError(
                "PII Masking is enabled but Presidio Analyzer is not initialized"
            )

        try:
            target_entities = entities or self.supported_entities
            threshold = score_threshold if score_threshold is not None else self.threshold

            # 1. Analyze text for PII
            results: List[RecognizerResult] = self.analyzer.analyze(
                text=text,
                entities=target_entities,
                language="en",
                score_threshold=threshold,
            )

            # Filter out overlapping/conflicting recognitions and sort by start position
            results = self._filter_results(results, text)

            if not results:
                return PIIMaskResult(
                    original_text=text,
                    masked_text=text,
                    detected_entities=[],
                    mapping={},
                    reverse_mapping={},
                )

            # 2. Build deterministic entity placeholders and mappings
            # e.g., [PERSON_1], [EMAIL_1]
            # If the exact same text appears multiple times, assign it the identical placeholder
            entity_counters: Dict[str, int] = {}
            reverse_map: Dict[Tuple[str, str], str] = {}  # (entity_type, text_lower) -> placeholder
            placeholder_to_original: Dict[str, str] = {}
            detected_entities_list: List[DetectedEntity] = []

            # Assign placeholders
            for res in results:
                raw_val = text[res.start:res.end]
                key = (res.entity_type, raw_val.strip().lower())

                if key in reverse_map:
                    placeholder = reverse_map[key]
                else:
                    curr_count = entity_counters.get(res.entity_type, 0) + 1
                    entity_counters[res.entity_type] = curr_count
                    placeholder = f"[{res.entity_type}_{curr_count}]"
                    reverse_map[key] = placeholder
                    placeholder_to_original[placeholder] = raw_val

                detected_entities_list.append(
                    DetectedEntity(
                        entity_type=res.entity_type,
                        start=res.start,
                        end=res.end,
                        score=round(res.score, 3),
                        text=f"<{res.entity_type} masked>",  # Don't store raw PII in public logs/objects
                    )
                )

            # 3. Construct masked string from back to front to preserve string indices
            sorted_results = sorted(results, key=lambda r: r.start, reverse=True)
            masked_chars = list(text)

            for res in sorted_results:
                raw_val = text[res.start:res.end]
                key = (res.entity_type, raw_val.strip().lower())
                placeholder = reverse_map[key]
                masked_chars[res.start:res.end] = list(placeholder)

            masked_text = "".join(masked_chars)

            # Build simple reverse mapping (original_val -> placeholder) for convenience
            simple_reverse_map = {orig: ph for ph, orig in placeholder_to_original.items()}

            return PIIMaskResult(
                original_text=text,
                masked_text=masked_text,
                detected_entities=detected_entities_list,
                mapping=placeholder_to_original,
                reverse_mapping=simple_reverse_map,
            )

        except PIIMaskingError:
            raise
        except Exception as exc:
            logger.error("PII detection and masking failed (fail-closed triggered): %s", exc)
            try:
                from app.privacy.terminal_logger import PIITerminalLogger, is_terminal_logging_enabled
                if is_terminal_logging_enabled():
                    PIITerminalLogger.log_fail_closed(correlation_id or "REQ-FAIL", str(exc))
            except Exception:
                pass
            raise PIIMaskingError(f"PII detection failed: {str(exc)}") from exc

    def _filter_results(
        self,
        results: List[RecognizerResult],
        text: str,
    ) -> List[RecognizerResult]:
        """
        Filter out overlapping or spurious recognitions:
        - If two recognitions overlap, keep the one with higher score or longer span.
        - Suppress common relative task terms (e.g., 'tomorrow', 'next week') if DATE_TIME.
        """
        if not results:
            return []

        # Sort primarily by score desc, then span length desc
        sorted_by_score = sorted(
            results,
            key=lambda r: (r.score, (r.end - r.start)),
            reverse=True,
        )

        accepted: List[RecognizerResult] = []

        for r in sorted_by_score:
            # Check overlap with already accepted results
            overlaps = False
            for acc in accepted:
                if max(r.start, acc.start) < min(r.end, acc.end):
                    overlaps = True
                    break

            if overlaps:
                continue

            span_text = text[r.start:r.end].strip().lower()
            tokens = span_text.split()

            # Task management safety: If entity is PERSON, LOCATION, GPE, ORGANIZATION, or NRP, do not falsely mask standard action verbs or technical objects
            if r.entity_type in ("PERSON", "LOCATION", "GPE", "ORGANIZATION", "NRP"):
                pronouns_and_non_names = {
                    "it", "this", "that", "them", "me", "us", "you", "him", "her", "his",
                    "their", "its", "which", "what", "where", "when", "why", "how",
                    "all", "some", "any", "none", "each", "both", "my", "our", "your"
                }
                if span_text in pronouns_and_non_names or any(t in pronouns_and_non_names for t in tokens if len(tokens) == 1):
                    continue

                action_verbs = {
                    "create", "email", "send", "call", "move", "add", "delete",
                    "remove", "update", "edit", "list", "review", "assign",
                    "notify", "check", "get", "post", "put", "close", "open",
                    "schedule", "start", "stop", "run", "make", "view", "show",
                    "login", "logout", "signin", "signup", "sign in", "sign up", "log in", "log out"
                }
                technical_terms = {
                    "api", "card", "board", "task", "list", "login", "logout", "signin", "signup",
                    "sign-in", "sign-up", "log-in", "log-out", "repo", "db",
                    "app", "ui", "server", "code", "database", "frontend", "backend",
                    "auth", "authentication", "endpoint", "workflow", "pipeline", "bug", "feature",
                    "test", "deploy", "release", "doc", "docs", "stack", "fullstack",
                    "full stack", "devops", "qa", "react", "python", "node", "java",
                    "spring", "docker", "k8s", "kubernetes", "aws", "gcp", "azure",
                    "ci/cd", "ci", "cd", "jira", "trello", "git", "github", "gitlab",
                    "sql", "nosql", "postgres", "mongodb", "redis", "kafka", "oauth",
                    "jwt", "microservice", "microservices", "unit test", "integration test",
                    "architecture", "service", "system", "client", "website", "portal",
                    "page", "screen", "button", "modal", "table", "view",
                    "onboard", "onboarding", "offboarding", "training", "meeting",
                    "sync", "standup", "deliverable", "deliverables", "requirement",
                    "requirements", "scope", "design", "wireframe", "milestone",
                    "sprint", "backlog", "client onboarding", "client onboard", "guide", "starter"
                }
                if span_text in action_verbs:
                    continue
                if tokens and tokens[0] in action_verbs:
                    continue
                if span_text in technical_terms or any(t in technical_terms for t in tokens):
                    continue

                # Context check: Check if span immediately follows card creation prefix
                # e.g. "create a task card Full Stack" or "create a task card Logout"
                prefix_text = text[:r.start].lower().strip()
                if re.search(
                    r"(?:create|add|new|update|move|delete)\s+(?:a\s+)?(?:task\s+card|card|task)(?:\s+named|\s+called|\s*:\s*)?\s*$",
                    prefix_text,
                ):
                    continue

            # Task management safety: If entity is DATE_TIME, do not mask relative task deadlines
            if r.entity_type == "DATE_TIME":
                relative_task_terms = {
                    "today", "tomorrow", "yesterday", "next week", "this week",
                    "next month", "monday", "tuesday", "wednesday", "thursday",
                    "friday", "saturday", "sunday", "asap", "urgent"
                }
                if span_text in relative_task_terms:
                    continue

            accepted.append(r)

        # Re-sort accepted results by start position ascending
        return sorted(accepted, key=lambda r: r.start)

    def restore_text(self, text: str, mapping: Dict[str, str]) -> str:
        """
        Locally restores masked placeholders in text using the provided request-scoped mapping.
        Replaces only placeholders present in mapping.
        Resilient to LLM formatting variations (e.g. [PERSON_1], Person 1, [Person 1], PERSON_1).
        """
        if not text or not mapping:
            return text

        restored = text
        # 1. Exact string substitution first (sorted by placeholder length descending)
        for placeholder, original in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
            restored = restored.replace(placeholder, original)

        # 2. Resilient regex replacement for LLM normalization variations
        # (e.g., LLM stripping brackets or normalizing [PERSON_1] -> Person 1 or [Person 1])
        for placeholder, original in mapping.items():
            m = re.match(r"\[([A-Za-z_]+)_(\d+)\]", placeholder)
            if m:
                entity_type, num = m.groups()
                pattern = re.compile(
                    r"\[?\b" + re.escape(entity_type) + r"[ _]" + re.escape(num) + r"\b\]?",
                    re.IGNORECASE,
                )
                restored = pattern.sub(original, restored)

        return restored

    def restore_dict(self, data: Any, mapping: Dict[str, str]) -> Any:
        """
        Recursively traverses dictionaries, lists, or strings and restores placeholders
        using the request-scoped mapping.
        """
        if not mapping:
            return data

        if isinstance(data, str):
            return self.restore_text(data, mapping)
        elif isinstance(data, dict):
            return {k: self.restore_dict(v, mapping) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.restore_dict(item, mapping) for item in data]
        else:
            return data
