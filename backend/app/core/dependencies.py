from typing import Callable, List
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import decode_access_token
from app.database.mongodb import get_database
from app.models.user import UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService
from app.services.user_service import UserService

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    auth: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> UserResponse:
    """Validates JWT access token and returns authenticated active user."""
    if not auth or not auth.credentials:
        raise AuthenticationError("Missing Authorization Header. Bearer token required.")

    raw_token = auth.credentials.strip()
    if raw_token.lower().startswith("bearer "):
        raw_token = raw_token[7:].strip()

    payload = decode_access_token(raw_token)
    user_id = payload.get("sub")

    if not user_id:
        raise AuthenticationError("Invalid token: Subject claim is missing.")

    repo = UserRepository(db)
    user_data = await repo.get_by_id(user_id)

    if not user_data:
        raise AuthenticationError("User associated with this token does not exist.")

    if not user_data.get("is_active", True):
        raise AuthenticationError("User account has been deactivated.")

    return UserResponse(**user_data)


def require_roles(allowed_roles: List[UserRole]) -> Callable:
    """Dependency factory checking if current user possesses one of the allowed roles."""
    async def role_checker(
        current_user: UserResponse = Depends(get_current_user),
    ) -> UserResponse:
        user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
        allowed_str = [r.value if hasattr(r, "value") else str(r) for r in allowed_roles]

        if user_role_str not in allowed_str:
            raise AuthorizationError(
                f"Role '{user_role_str}' is not authorized to access this resource. Allowed: {', '.join(allowed_str)}"
            )
        return current_user

    return role_checker


async def get_auth_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> AuthService:
    return AuthService(db)


async def get_user_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> UserService:
    return UserService(db)

