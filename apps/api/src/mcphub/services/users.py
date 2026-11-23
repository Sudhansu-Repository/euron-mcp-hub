"""Dashboard accounts, managed by admins (and by the CLI and the demo seed)."""

from __future__ import annotations

import uuid

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from mcphub.core.errors import ConflictError, NotFoundError, UnprocessableError
from mcphub.core.security import hash_password, temporary_password, validate_password
from mcphub.models import User
from mcphub.models.enums import Role
from mcphub.repositories.users import UserRepository
from mcphub.services import audit
from mcphub.services.actor import Actor


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def page(self, *, limit: int, offset: int) -> tuple[list[User], int]:
        return await self.users.page(limit=limit, offset=offset)

    async def create(
        self,
        actor: Actor,
        *,
        email: str,
        name: str,
        role: Role,
        password: str | None = None,
    ) -> tuple[User, str | None]:
        """Create an account; without a password, a one-time password is returned once."""
        if await self.users.by_email(email):
            raise ConflictError("An account with that email already exists.")
        generated = None
        if password is None:
            password = generated = temporary_password()
        else:
            validate_password(password, email=email)
        user = await self.users.add(
            User(
                email=email.strip().lower(),
                name=name.strip(),
                password_hash=await anyio.to_thread.run_sync(hash_password, password),
                role=role.value,
            )
        )
        await audit.record(
            self.session,
            actor,
            action="user.created",
            target_type="user",
            target_id=user.id,
            target_name=user.email,
            details={"role": role.value},
        )
        await self.session.commit()
        return user, generated

    async def update(
        self,
        actor: Actor,
        user_id: uuid.UUID,
        *,
        name: str | None,
        role: Role | None,
        is_active: bool | None,
    ) -> User:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        demoting = role is not None and role != Role.ADMIN and user.role == Role.ADMIN
        deactivating = is_active is False and user.is_active and user.role == Role.ADMIN
        if (demoting or deactivating) and await self.users.count_active_admins() <= 1:
            raise UnprocessableError(
                "This deployment needs at least one active admin.", code="last_admin"
            )
        changed: dict[str, object] = {}
        if name is not None and name.strip() != user.name:
            user.name = changed["name"] = name.strip()
        if role is not None and role.value != user.role:
            user.role = changed["role"] = role.value
        if is_active is not None and is_active != user.is_active:
            user.is_active = changed["is_active"] = is_active
            # Deactivation ends every session at once.
            user.session_version += 1
        if changed:
            await audit.record(
                self.session,
                actor,
                action="user.updated",
                target_type="user",
                target_id=user.id,
                target_name=user.email,
                details=changed,
            )
            await self.session.commit()
        return user
