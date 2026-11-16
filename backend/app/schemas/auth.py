from pydantic import BaseModel, EmailStr, Field
from app.models.user import UserRole


class UserRegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User unique email address")
    password: str = Field(..., min_length=8, max_length=128, description="Password with minimum 8 characters")
    full_name: str = Field(..., min_length=2, max_length=100, description="Full display name")
    role: UserRole = Field(default=UserRole.EMPLOYEE, description="Initial assigned role")
    department: str = Field(default="Engineering", description="Department affiliation")


class UserLoginRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="Plaintext password")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Valid raw refresh token")

