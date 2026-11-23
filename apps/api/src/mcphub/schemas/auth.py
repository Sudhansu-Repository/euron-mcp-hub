from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field

from mcphub.schemas.common import ApiModel


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class SetupRequest(ApiModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(ApiModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class ProfileUpdate(ApiModel):
    name: str = Field(min_length=1, max_length=120)


class UserOut(ApiModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class SessionOut(ApiModel):
    user: UserOut
    token: str = Field(description="Also set as an httpOnly cookie for the dashboard.")
    expires_at: datetime
