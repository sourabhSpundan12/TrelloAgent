from fastapi import APIRouter, Depends, status
from app.core.dependencies import get_auth_service, get_current_user
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    MessageResponse,
    RefreshTokenRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
)
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    description="Registers a new platform user with Argon2 password hashing and duplicate email checks.",
)
async def register(
    payload: UserRegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    return await auth_service.register(payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User authentication and token generation",
    description="Verifies credentials using Argon2 and issues a JWT access token and rotating refresh token.",
)
async def login(
    payload: UserLoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return await auth_service.login(payload)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    description="Returns the profile and role of the currently authenticated user based on JWT bearer token.",
)
async def get_me(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    return current_user


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token and issue new token pair",
    description="Validates the provided refresh token hash against MongoDB, revokes it, and issues a new pair.",
)
async def refresh_token(
    payload: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return await auth_service.refresh_tokens(payload.refresh_token)


@router.post(
    "/change-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change user password",
    description="Validates current password and updates to new password with Argon2 hashing.",
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: UserResponse = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    return await auth_service.change_password(current_user.id, payload)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Request password reset verification code",
    description="Generates a 6-digit verification code and dispatches email via SMTP.",
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    return await auth_service.request_password_reset(payload)


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset password using verification code",
    description="Validates the 6-digit verification code sent via SMTP and updates the account password.",
)
async def reset_password(
    payload: ResetPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    return await auth_service.reset_password(payload)


