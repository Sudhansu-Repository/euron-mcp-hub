from __future__ import annotations

import uuid

from sqlalchemy import func, select

from mcphub.models import User
from mcphub.models.enums import Role
from mcphub.repositories.base import Repository


class UserRepository(Repository):
    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email.strip()))
        return result.scalar_one_or_none()

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count()).select_from(User)) or 0)

    async def count_active_admins(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).where(User.role == Role.ADMIN, User.is_active.is_(True))
            )
            or 0
        )

    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def page(self, *, limit: int, offset: int) -> tuple[list[User], int]:
        total = int(await self.session.scalar(select(func.count()).select_from(User)) or 0)
        result = await self.session.execute(
            select(User).order_by(User.created_at).limit(limit).offset(offset)
        )
        return list(result.scalars()), total
