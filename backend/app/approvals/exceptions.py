from typing import Any, Optional
from fastapi import status
from app.core.exceptions import AppException


class ApprovalError(AppException):
    """Base exception for approval workflow errors."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str = "APPROVAL_ERROR",
        details: Optional[Any] = None,
    ):
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=error_code,
            details=details,
        )


class ApprovalNotFoundError(ApprovalError):
    def __init__(self, message: str = "Pending action not found.", details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="APPROVAL_NOT_FOUND",
            details=details,
        )


class ApprovalExpiredError(ApprovalError):
    def __init__(self, message: str = "Pending action draft has expired.", details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_410_GONE,
            error_code="APPROVAL_EXPIRED",
            details=details,
        )


class ApprovalAlreadyProcessedError(ApprovalError):
    def __init__(
        self,
        message: str = "Action has already been processed or is not in PENDING state.",
        details: Optional[Any] = None,
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code="APPROVAL_ALREADY_PROCESSED",
            details=details,
        )


class ApprovalUnauthorizedError(ApprovalError):
    def __init__(
        self,
        message: str = "You are not authorized to modify or confirm this action.",
        details: Optional[Any] = None,
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="APPROVAL_UNAUTHORIZED",
            details=details,
        )


class ApprovalExecutionError(ApprovalError):
    def __init__(
        self,
        message: str = "Failed to execute approved action via tool executor.",
        details: Optional[Any] = None,
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="APPROVAL_EXECUTION_FAILED",
            details=details,
        )
