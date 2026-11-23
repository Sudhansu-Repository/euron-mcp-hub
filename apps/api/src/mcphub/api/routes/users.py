"""Dashboard accounts (admins only)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from mcphub.api.deps import AdminDep, SessionDep
from mcphub.models.enums import Role
from mcphub.schemas.auth import UserOut
from mcphub.schemas.common import Page
from mcphub.schemas.users import UserCreate, UserCreated, UserUpdate
from mcphub.services.users import UserService

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("", summary="Accounts")
async def list_users(
    actor: AdminDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[UserOut]:
    users, total = await UserService(session).page(limit=limit, offset=offset)
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in users], total=total, limit=limit, offset=offset
    )


@router.post(
    "",
    summary="Create an account (returns a one-time password)",
    status_code=status.HTTP_201_CREATED,
)
async def create_user(body: UserCreate, actor: AdminDep, session: SessionDep) -> UserCreated:
    user, password = await UserService(session).create(
        actor, email=body.email, name=body.name, role=Role(body.role)
    )
    return UserCreated(user=UserOut.model_validate(user), temporary_password=password or "")


@router.patch("/{user_id}", summary="Rename, change the role, or deactivate an account")
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, actor: AdminDep, session: SessionDep
) -> UserOut:
    user = await UserService(session).update(
        actor,
        user_id,
        name=body.name,
        role=Role(body.role) if body.role else None,
        is_active=body.is_active,
    )
    return UserOut.model_validate(user)
