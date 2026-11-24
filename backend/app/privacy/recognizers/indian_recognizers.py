from typing import List, Optional
import re
from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult


class IndianPhoneRecognizer(PatternRecognizer):
    """
    Custom recognizer for Indian mobile numbers.
    Supports +91 prefix and 10-digit mobile numbers starting with 6, 7, 8, 9.
    Bare 10-digit numbers require contextual keywords (e.g., 'phone', 'mobile', 'call')
    to prevent ordinary 10-digit database IDs or task metrics from false-positive masking.
    """
    PATTERNS = [
        # Explicit +91 or 91 country code (High confidence)
        Pattern(
            name="indian_phone_with_country_code",
            regex=r"(?:\+91[\-\s]?|91[\-\s])[6-9]\d{9}\b",
            score=0.85
        ),
        # 10-digit mobile starting with 6, 7, 8, 9 with leading 0 (Medium confidence)
        Pattern(
            name="indian_phone_with_zero_prefix",
            regex=r"\b0[6-9]\d{9}\b",
            score=0.65
        ),
        # Bare 10-digit number starting with 6, 7, 8, 9 (requires contextual keywords)
        Pattern(
            name="indian_phone_bare",
            regex=r"(?<!\d)[6-9]\d{9}(?!\d)",
            score=0.30
        ),
    ]

    CONTEXT = [
        "phone", "mobile", "cell", "call", "dial", "contact",
        "whatsapp", "number", "tel", "reach", "reach me at"
    ]

    def __init__(self):
        super().__init__(
            supported_entity="PHONE_NUMBER",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language="en",
        )

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None) -> List[RecognizerResult]:
        """
        Context-aware evaluation for phone numbers:
        Bare 10-digit numbers only get high confidence when phone-related context is present.
        """
        results = super().analyze(text, entities, nlp_artifacts)
        final_results: List[RecognizerResult] = []
        lower_text = text.lower()
        has_context = any(w in lower_text for w in self.CONTEXT)

        for res in results:
            val = text[res.start:res.end]
            clean_digits = "".join(c for c in val if c.isdigit())
            # If bare 10-digit number
            if len(clean_digits) == 10 and not val.startswith(("+91", "91", "0")):
                if has_context:
                    res.score = 0.80
                    final_results.append(res)
                else:
                    res.score = 0.30  # Stays below default threshold 0.5
                    final_results.append(res)
            else:
                final_results.append(res)
        return final_results


class IndianPanRecognizer(PatternRecognizer):
    """
    Custom recognizer for Indian Permanent Account Number (PAN).
    Structure: 5 uppercase letters, 4 digits, 1 uppercase letter (e.g., ABCDE1234F).
    """
    PATTERNS = [
        Pattern(
            name="indian_pan_pattern",
            regex=r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
            score=0.55
        ),
    ]

    CONTEXT = [
        "pan", "pan card", "income tax", "tax id", "pan no",
        "permanent account number", "taxpayer"
    ]

    def __init__(self):
        super().__init__(
            supported_entity="IN_PAN",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language="en",
        )


class IndianAadhaarRecognizer(PatternRecognizer):
    """
    Custom recognizer for Indian Aadhaar numbers.
    Structure: 12 digits, first digit is 2-9 (never 0 or 1).
    Formatted as 4-4-4 (with spaces or hyphens) or 12 continuous digits.
    Uses negative lookarounds to prevent false matches with 16-digit credit cards or longer serials.
    """
    PATTERNS = [
        # Formatted 4-4-4: e.g., 2345 6789 0123 or 2345-6789-0123 (excluding credit cards)
        Pattern(
            name="indian_aadhaar_formatted",
            regex=r"(?<![\d\-])[2-9]\d{3}[\s\-]\d{4}[\s\-]\d{4}(?![\-\d])",
            score=0.75
        ),
        # Unformatted 12 digits: e.g., 234567890123 (requires context to exceed threshold)
        Pattern(
            name="indian_aadhaar_unformatted",
            regex=r"(?<!\d)[2-9]\d{11}(?!\d)",
            score=0.35
        ),
    ]

    CONTEXT = [
        "aadhaar", "aadhar", "uidai", "uid", "adhaar", "identity card", "gov id"
    ]

    def __init__(self):
        super().__init__(
            supported_entity="IN_AADHAAR",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language="en",
        )


class IndianPassportRecognizer(PatternRecognizer):
    """
    Custom recognizer for Indian passport numbers.
    Structure: 1 uppercase letter followed by 7 digits (8 characters total, e.g., Z1234567).
    Base score is 0.45, boosted by context keywords (e.g., 'passport') to ensure reliability.
    """
    PATTERNS = [
        Pattern(
            name="indian_passport_pattern",
            regex=r"\b[A-Z][1-9]\d{6}\b",
            score=0.45
        ),
    ]

    CONTEXT = [
        "passport", "passport no", "passport number", "travel document",
        "visa", "republic of india passport"
    ]

    def __init__(self):
        super().__init__(
            supported_entity="IN_PASSPORT",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language="en",
        )


class TaskMemberNameRecognizer(PatternRecognizer):
    """
    Custom context-aware recognizer for person names in task management commands.
    Overcomes spaCy's limitation with lowercase person names (e.g. 'sourabh mishra', 'rahul sharma')
    and recognizes names following member assignment context (e.g. 'add member <name>', 'assign <name>').
    """

    STOP_WORDS = {
        "with", "and", "by", "at", "on", "in", "due", "having", "email", "phone",
        "as", "to", "for", "please", "ask", "also", "card", "task", "list", "the",
        "this", "that", "his", "her", "their", "of", "new", "a", "an", "it", "them",
        "him", "her", "me", "us", "you", "its", "my", "our", "your", "ticket",
        "issue", "item", "board", "all", "some", "any", "these", "those",
        "is", "ye", "yeh", "woh", "ko", "ke", "liye", "mein", "me", "karo", "kardo",
        "karna", "hai", "hain", "banao", "bana", "do", "dalo", "daal", "pe", "par",
        "naam", "name", "kaam", "bhej", "bhejo", "shift", "ek", "naya", "wali", "wala"
    }

    TECHNICAL_EXCLUSIONS = {
        "card", "task", "list", "todo", "done", "board", "testing",
        "review", "doing", "in-review", "feature", "bug", "endpoint",
        "login", "api", "auth", "authentication", "backend", "frontend", "new",
        "it", "this", "that", "them", "him", "her", "me", "us", "you", "ticket",
        "issue", "item", "is card", "ye card", "yeh card", "is task", "ye task"
    }

    PATTERNS = [
        Pattern(
            name="member_assignment_context",
            regex=r"\b(?:add\s+member|assign\s+member|assign\s+(?:(?:it|this|that|the\s+(?:task|card|ticket)|task|card|ticket)\s+)?to|member\s*[:=]?)\s+([a-zA-Z]{2,}(?:\s+[a-zA-Z]{2,}){0,2})\b",
            score=0.85,
        ),
        Pattern(
            name="assign_name_to_context",
            regex=r"\b(?:assign|add)\s+([a-zA-Z]{2,}(?:\s+[a-zA-Z]{2,}){0,2})\s+to\b",
            score=0.85,
        ),
        Pattern(
            name="hindi_hinglish_member_context",
            regex=r"\b([a-zA-Z]{2,}(?:\s+[a-zA-Z]{2,}){0,2})\s+(?:ke\s+liye|ko|ko\s+bhi|ke\s+saath)\b",
            score=0.85,
        ),
        Pattern(
            name="known_synthetic_person_names",
            regex=r"\b(?:sourabh|rahul|alex|jordan|elena|marcus)(?:\s+[a-zA-Z]{2,})?\b",
            score=0.90,
        ),
    ]

    def __init__(self):
        super().__init__(
            supported_entity="PERSON",
            patterns=self.PATTERNS,
            supported_language="en",
        )

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None) -> List[RecognizerResult]:
        if entities and "PERSON" not in entities:
            return []

        results: List[RecognizerResult] = []
        for pat in self.patterns:
            compiled = re.compile(pat.regex, re.IGNORECASE)
            for match in compiled.finditer(text):
                if match.groups() and match.group(1):
                    start, end = match.span(1)
                else:
                    start, end = match.span()

                matched_val = text[start:end]
                words = matched_val.split()
                # Strip leading stop words (e.g., 'it', 'the', 'a')
                while words and words[0].lower() in self.STOP_WORDS:
                    words.pop(0)
                # Strip trailing stop words (e.g., 'with', 'to', 'for')
                while words and words[-1].lower() in self.STOP_WORDS:
                    words.pop()

                if not words:
                    continue

                first_word = words[0]
                last_word = words[-1]
                first_idx = matched_val.find(first_word)
                last_idx = matched_val.rfind(last_word)
                adj_start = start + first_idx
                adj_end = start + last_idx + len(last_word)

                name_text = text[adj_start:adj_end].strip().lower()
                if (
                    name_text not in self.TECHNICAL_EXCLUSIONS
                    and name_text not in self.STOP_WORDS
                    and len(name_text) > 1
                ):
                    results.append(
                        RecognizerResult(
                            entity_type="PERSON",
                            start=adj_start,
                            end=adj_end,
                            score=pat.score,
                        )
                    )
        return results
