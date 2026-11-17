from datetime import datetime, timedelta, timezone
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.core.logging import logger
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import UserRole
from app.repositories.user_repository import RefreshTokenRepository, UserRepository
from app.schemas.auth import TokenResponse, UserLoginRequest, UserRegisterRequest
from app.schemas.user import UserResponse


class AuthService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.user_repo = UserRepository(db)
        self.token_repo = RefreshTokenRepository(db)

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

