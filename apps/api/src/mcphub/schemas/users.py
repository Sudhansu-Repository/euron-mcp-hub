from __future__ import annotations

from typing import Literal

from pydantic import EmailStr, Field

from mcphub.schemas.auth import UserOut
from mcphub.schemas.common import ApiModel

RoleName = Literal["admin", "operator", "viewer"]


class UserCreate(ApiModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    role: RoleName = "viewer"


class UserCreated(ApiModel):
    user: UserOut
    temporary_password: str = Field(
        description="Shown once. The person changes it after signing in."
    )


class UserUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: RoleName | None = None
    is_active: bool | None = None
