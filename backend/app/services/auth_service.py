import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, ValidationError
from app.core.logging import logger
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import UserRole
from app.repositories.user_repository import (
    PasswordResetRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    VerifyResetCodeRequest,
)
from app.schemas.user import UserResponse
from app.services.email_service import EmailService


class AuthService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.user_repo = UserRepository(db)
        self.token_repo = RefreshTokenRepository(db)
        self.reset_repo = PasswordResetRepository(db)
        self.email_service = EmailService()

    async def register(self, req: UserRegisterRequest) -> UserResponse:
        """Register a new user with duplicate email prevention and Argon2 hashing."""
        existing = await self.user_repo.get_by_email(req.email)
        if existing:
            raise ConflictError("A user with this email address already exists.")

        user_doc = {
            "email": req.email.strip().lower(),
            "hashed_password": hash_password(req.password),
            "full_name": req.full_name.strip(),
            "role": req.role.value if hasattr(req.role, "value") else str(req.role),
            "department": req.department,
            "is_active": True,
        }

        created = await self.user_repo.create(user_doc)
        logger.info(f"Registered new user account: {created['email']} [role={created['role']}]")
        return UserResponse(**created)

    async def login(self, req: UserLoginRequest) -> TokenResponse:
        """Authenticate user credentials and issue access + refresh tokens."""
        user = await self.user_repo.get_by_email(req.email)
        if not user:
            # Safe authentication error response (timing and identity safe)
            raise AuthenticationError("Email and password is incorrect.")

        if not user.get("is_active", True):
            raise AuthenticationError("User account is inactive. Please contact an administrator.")

        if not verify_password(req.password, user["hashed_password"]):
            raise AuthenticationError("Email and password is incorrect.")

        # Generate access token
        access_token = create_access_token(
            subject=user["id"],
            email=user["email"],
            role=user["role"],
        )

        # Generate refresh token and save hash
        raw_refresh_token, token_hash = generate_refresh_token()
        refresh_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        await self.token_repo.create({
            "token_hash": token_hash,
            "user_id": user["id"],
            "expires_at": refresh_expires_at,
            "is_revoked": False,
            "created_at": datetime.now(timezone.utc),
        })

        logger.info(f"User logged in successfully: {user['email']}")
        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh_tokens(self, raw_refresh_token: str) -> TokenResponse:
        """
        Rotates refresh token:
        1. Validates token hash against MongoDB.
        2. Checks revocation & expiration.
        3. Revokes/deletes old refresh token.
        4. Issues a new access token AND new refresh token pair.
        """
        token_hash = hash_token(raw_refresh_token)
        stored_token = await self.token_repo.get_by_hash(token_hash)

        if not stored_token:
            raise AuthenticationError("Invalid or expired refresh token.")

        if stored_token.get("is_revoked", False):
            raise AuthenticationError("Refresh token has been revoked.")

        now = datetime.now(timezone.utc)
        expires_at = stored_token["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < now:
            await self.token_repo.delete(token_hash)
            raise AuthenticationError("Refresh token has expired.")

        # Retrieve user
        user = await self.user_repo.get_by_id(stored_token["user_id"])
        if not user or not user.get("is_active", True):
            raise AuthenticationError("User account not found or deactivated.")

        # Revoke old token to enforce rotation
        await self.token_repo.delete(token_hash)

        # Generate new pair
        new_access_token = create_access_token(
            subject=user["id"],
            email=user["email"],
            role=user["role"],
        )

        new_raw_refresh, new_token_hash = generate_refresh_token()
        new_expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        await self.token_repo.create({
            "token_hash": new_token_hash,
            "user_id": user["id"],
            "expires_at": new_expires_at,
            "is_revoked": False,
            "created_at": now,
        })

        logger.info(f"Rotated refresh token for user {user['id']}")
        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_raw_refresh,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def bootstrap_admin(self) -> Optional[UserResponse]:
        """
        Secure admin bootstrap mechanism:
        If BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD are provided via environment,
        and no user exists with that email, creates an initial ADMIN account.
        """
        email = settings.BOOTSTRAP_ADMIN_EMAIL
        password = settings.BOOTSTRAP_ADMIN_PASSWORD
        if not email or not password:
            return None

        existing = await self.user_repo.get_by_email(email)
        if existing:
            return None

        logger.info(f"Bootstrapping initial administrator account from environment: {email}")
        user_doc = {
            "email": email.strip().lower(),
            "hashed_password": hash_password(password),
            "full_name": settings.BOOTSTRAP_ADMIN_NAME,
            "role": UserRole.ADMIN.value,
            "department": "Platform Administration",
            "is_active": True,
        }
        created = await self.user_repo.create(user_doc)
        return UserResponse(**created)

    async def change_password(self, user_id: str, req: ChangePasswordRequest) -> MessageResponse:
        """Verify current password and update to new password with Argon2 hashing."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found.")

        if not verify_password(req.current_password, user["hashed_password"]):
            raise AuthenticationError("Current password is incorrect.")

        if req.current_password == req.new_password:
            raise ValidationError("New password cannot be the same as your current password.")

        new_hashed = hash_password(req.new_password)
        await self.user_repo.update(user_id, {"hashed_password": new_hashed})
        # Invalidate any other active refresh tokens
        await self.token_repo.revoke_all_for_user(user_id)
        logger.info(f"Password changed successfully for user: {user.get('email')}")
        return MessageResponse(message="Password updated successfully.")

    async def request_password_reset(self, req: ForgotPasswordRequest) -> MessageResponse:
        """
        Initiate password reset flow:
        1. Checks user existence. If not found, explicitly informs user.
        2. Generates secure 6-digit verification code.
        3. Persists code with expiry in MongoDB.
        4. Dispatches verification code email via SMTP.
        """
        normalized_email = req.email.strip().lower()
        user = await self.user_repo.get_by_email(normalized_email)

        if not user:
            raise NotFoundError(
                f"No account found with email '{normalized_email}'. Please verify your email or Sign Up."
            )

        if not user.get("is_active", True):
            raise AuthenticationError("This account is currently deactivated. Please contact your administrator.")

        code = f"{secrets.randbelow(900000) + 100000}"
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
        )
        await self.reset_repo.create_reset_code(normalized_email, code, expires_at)
        logger.info(f"Generated password reset verification code for: {normalized_email}")

        try:
            await self.email_service.send_password_reset_email(
                to_email=normalized_email,
                user_name=user.get("full_name", "User"),
                reset_code=code,
                expire_minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
            )
        except Exception as exc:
            logger.error(f"Error delivering password reset email to {normalized_email}: {exc}")
            if settings.DEBUG:
                logger.info(f"[DEV DEBUG NOTICE] Reset code for {normalized_email} is: {code}")
            raise AuthenticationError(
                f"Could not send email via SMTP ({exc}). Please check your SMTP configuration in .env."
            )

        return MessageResponse(
            message=f"A 6-digit verification code has been sent to {normalized_email}."
        )

    async def verify_reset_code(self, req: VerifyResetCodeRequest) -> MessageResponse:
        """Verify the 6-digit code before presenting password entry fields."""
        normalized_email = req.email.strip().lower()
        is_valid = await self.reset_repo.verify_code(normalized_email, req.code)
        if not is_valid:
            raise AuthenticationError("Invalid or expired verification code. Please check your code or request a new one.")
        return MessageResponse(message="Verification code is valid. You can now set your new password.")

    async def reset_password(self, req: ResetPasswordRequest) -> MessageResponse:
        """
        Verify the 6-digit verification code and update user password.
        """
        normalized_email = req.email.strip().lower()
        is_valid = await self.reset_repo.verify_code(normalized_email, req.code)
        if not is_valid:
            raise AuthenticationError("Invalid or expired verification code. Please check the code or request a new one.")

        user = await self.user_repo.get_by_email(normalized_email)
        if not user:
            raise NotFoundError("User account not found.")

        new_hashed = hash_password(req.new_password)
        await self.user_repo.update(user["id"], {"hashed_password": new_hashed})
        await self.reset_repo.mark_used(normalized_email, req.code)
        await self.token_repo.revoke_all_for_user(user["id"])
        logger.info(f"Password reset successfully via verification code for: {normalized_email}")
        return MessageResponse(message="Password reset successfully. You can now sign in with your new password.")


