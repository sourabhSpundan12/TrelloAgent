from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.exceptions import NotFoundError
from app.models.user import UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserListResponse, UserResponse, UserUpdateRequest


class UserService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.user_repo = UserRepository(db)

    async def get_by_id(self, user_id: str) -> UserResponse:
        """Fetch user by ID."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found.")
        return UserResponse(**user)

    async def update_profile(self, user_id: str, req: UserUpdateRequest) -> UserResponse:
        """Update user profile fields."""
        update_data = {k: v for k, v in req.model_dump().items() if v is not None}
        if not update_data:
            return await self.get_by_id(user_id)

        updated = await self.user_repo.update(user_id, update_data)
        if not updated:
            raise NotFoundError("User not found.")
        return UserResponse(**updated)

    async def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        role: Optional[UserRole] = None,
    ) -> UserListResponse:
        """List users with pagination."""
        skip = (page - 1) * page_size
        users_raw, total = await self.user_repo.list_users(skip=skip, limit=page_size, role=role)
        users = [UserResponse(**u) for u in users_raw]
        return UserListResponse(
            users=users,
            total=total,
            page=page,
            page_size=page_size,
        )

