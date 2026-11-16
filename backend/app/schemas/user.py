from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field
from app.models.user import UserRole


class UserResponse(BaseModel):
    id: str = Field(..., description="Unique user identifier")
    email: EmailStr = Field(..., description="User email address")
    full_name: str = Field(..., description="Full display name")
    role: UserRole = Field(..., description="Assigned role")
    department: Optional[str] = Field(None, description="Department")
    is_active: bool = Field(..., description="Active account status")
    created_at: datetime = Field(..., description="Registration timestamp")

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    department: Optional[str] = Field(None, max_length=100)


class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    page: int
    page_size: int

