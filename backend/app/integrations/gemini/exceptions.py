from typing import Any, Dict, Optional
from app.core.exceptions import AppException


class GeminiBaseError(AppException):
    def __init__(
        self,
        message: str = "Gemini integration encountered an error.",
        status_code: int = 502,
        error_code: str = "GEMINI_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message=message, status_code=status_code, error_code=error_code, details=details)


class GeminiNotConfiguredError(GeminiBaseError):
    def __init__(self, message: str = "GEMINI_API_KEY is not configured on the backend."):
        super().__init__(message=message, status_code=503, error_code="GEMINI_NOT_CONFIGURED")


class GeminiAPIError(GeminiBaseError):
    def __init__(self, message: str = "Google Gemini API call failed.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=502, error_code="GEMINI_API_FAILURE", details=details)


class GeminiTimeoutError(GeminiBaseError):
    def __init__(self, message: str = "Google Gemini API request timed out."):
        super().__init__(message=message, status_code=504, error_code="GEMINI_TIMEOUT")


class GeminiRateLimitError(GeminiBaseError):
    def __init__(self, message: str = "Google Gemini API rate limit or quota exceeded."):
        super().__init__(message=message, status_code=429, error_code="GEMINI_RATE_LIMITED")


class GeminiParsingError(GeminiBaseError):
    def __init__(self, message: str = "Failed to parse structured JSON intent from Gemini response.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=502, error_code="GEMINI_PARSING_ERROR", details=details)

