from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from app.core.dependencies import get_current_user, get_user_service, require_roles
from app.models.user import UserRole
from app.schemas.user import UserListResponse, UserResponse, UserUpdateRequest
from app.services.user_service import UserService

router = APIRouter()


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user details",
    description="Returns profile details for the currently authenticated user.",
)
async def get_current_user_profile(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    return current_user


@router.patch(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update current user profile",
    description="Allows updating non-sensitive profile attributes (full_name, department) for current user.",
)
async def update_current_user_profile(
    payload: UserUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    return await user_service.update_profile(current_user.id, payload)


@router.get(
    "",
    response_model=UserListResponse,
    status_code=status.HTTP_200_OK,
    summary="List users (Restricted to ADMIN, HR, and MANAGER)",
    description="Paginated retrieval of user records. Accessible only by users holding ADMIN, HR, or MANAGER roles.",
)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size limit"),
    role: Optional[UserRole] = Query(None, description="Optional role filter"),
    _: UserResponse = Depends(require_roles([UserRole.ADMIN, UserRole.HR, UserRole.MANAGER])),
    user_service: UserService = Depends(get_user_service),
) -> UserListResponse:
    return await user_service.list_users(page=page, page_size=page_size, role=role)

