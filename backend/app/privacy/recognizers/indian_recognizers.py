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
