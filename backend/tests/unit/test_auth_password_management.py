import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

from app.core.exceptions import AuthenticationError, ValidationError
from app.repositories.user_repository import PasswordResetRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.services.auth_service import AuthService
from app.services.email_service import EmailService


@pytest.fixture
def mock_db():
    db = MagicMock()
    # Mock collections
    db["users"] = MagicMock()
    db["refresh_tokens"] = MagicMock()
    db["password_resets"] = MagicMock()
    return db


@pytest.mark.asyncio
async def test_change_password_success(mock_db):
    auth_service = AuthService(mock_db)
    from app.core.security import hash_password, verify_password

    old_hashed = hash_password("OldPassword123!")
    auth_service.user_repo.get_by_id = AsyncMock(return_value={
        "id": "user-1",
        "email": "user@example.com",
        "hashed_password": old_hashed,
    })
    auth_service.user_repo.update = AsyncMock(return_value={})
    auth_service.token_repo.revoke_all_for_user = AsyncMock(return_value=1)

    req = ChangePasswordRequest(
        current_password="OldPassword123!",
        new_password="BrandNewPassword123!",
    )
    res = await auth_service.change_password("user-1", req)
    assert res.message == "Password updated successfully."
    assert auth_service.user_repo.update.called


@pytest.mark.asyncio
async def test_change_password_incorrect_current(mock_db):
    auth_service = AuthService(mock_db)
    from app.core.security import hash_password

    old_hashed = hash_password("CorrectOldPassword123!")
    auth_service.user_repo.get_by_id = AsyncMock(return_value={
        "id": "user-1",
        "email": "user@example.com",
        "hashed_password": old_hashed,
    })

    req = ChangePasswordRequest(
        current_password="WrongPassword123!",
        new_password="BrandNewPassword123!",
    )
    with pytest.raises(AuthenticationError):
        await auth_service.change_password("user-1", req)


@pytest.mark.asyncio
async def test_change_password_same_password(mock_db):
    auth_service = AuthService(mock_db)
    from app.core.security import hash_password

    old_hashed = hash_password("SamePassword123!")
    auth_service.user_repo.get_by_id = AsyncMock(return_value={
        "id": "user-1",
        "email": "user@example.com",
        "hashed_password": old_hashed,
    })

    req = ChangePasswordRequest(
        current_password="SamePassword123!",
        new_password="SamePassword123!",
    )
    with pytest.raises(ValidationError):
        await auth_service.change_password("user-1", req)


@pytest.mark.asyncio
async def test_request_password_reset_user_found(mock_db):
    auth_service = AuthService(mock_db)
    auth_service.user_repo.get_by_email = AsyncMock(return_value={
        "id": "user-1",
        "email": "test@example.com",
        "full_name": "Test User",
        "is_active": True,
    })
    auth_service.reset_repo.create_reset_code = AsyncMock()
    auth_service.email_service.send_password_reset_email = AsyncMock()

    res = await auth_service.request_password_reset(ForgotPasswordRequest(email="test@example.com"))
    assert "sent" in res.message.lower()
    assert auth_service.reset_repo.create_reset_code.called
    assert auth_service.email_service.send_password_reset_email.called


@pytest.mark.asyncio
async def test_reset_password_flow(mock_db):
    auth_service = AuthService(mock_db)
    auth_service.reset_repo.verify_code = AsyncMock(return_value=True)
    auth_service.reset_repo.mark_used = AsyncMock()
    auth_service.user_repo.get_by_email = AsyncMock(return_value={
        "id": "user-1",
        "email": "test@example.com",
        "hashed_password": "old",
    })
    auth_service.user_repo.update = AsyncMock()
    auth_service.token_repo.revoke_all_for_user = AsyncMock()

    req = ResetPasswordRequest(
        email="test@example.com",
        code="123456",
        new_password="NewSecurePassword123!",
    )
    res = await auth_service.reset_password(req)
    assert "reset successfully" in res.message.lower()
    assert auth_service.reset_repo.mark_used.called
    assert auth_service.user_repo.update.called


def test_email_service_unconfigured():
    svc = EmailService()
    svc.user = ""
    svc.password = ""
    assert svc.is_configured() is False
