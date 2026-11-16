from typing import Any, Dict, Optional


class TrelloError(Exception):
    """Base exception for all Trello integration failures."""

    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class TrelloConfigError(TrelloError):
    """Raised when Trello API credentials or board ID are not configured."""

    def __init__(self, message: str = "Trello API credentials are missing or unconfigured.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=500, details=details)


class TrelloAuthenticationError(TrelloError):
    """Raised when Trello API key or token is invalid (401 Unauthorized)."""

    def __init__(self, message: str = "Invalid Trello API credentials or unauthorized access.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=401, details=details)


class TrelloResourceNotFoundError(TrelloError):
    """Raised when a requested board, list, or card does not exist (404 Not Found)."""

    def __init__(self, message: str = "Requested Trello resource was not found.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=404, details=details)


class TrelloValidationError(TrelloError):
    """Raised when an operation parameter fails validation."""

    def __init__(self, message: str = "Invalid parameters for Trello operation.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=400, details=details)


class TrelloAPIError(TrelloError):
    """Raised when Trello returns an unexpected HTTP error."""

    def __init__(self, message: str, status_code: int = 502, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=status_code, details=details)

