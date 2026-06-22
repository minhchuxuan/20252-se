"""Auth/user DTOs."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..domain.enums import Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: Role
    home_id: int | None


class ResidentCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=6, max_length=128)
    unit_name: str = Field(default="New Unit", max_length=120)  # the unit being sold to this resident


TokenResponse.model_rebuild()
