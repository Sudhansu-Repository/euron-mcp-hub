"""Who is acting on the dashboard API: a signed-in person, or the system (the worker)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from mcphub.core.security import SessionClaims
from mcphub.models import User
from mcphub.models.enums import Role


@dataclass(frozen=True, slots=True)
class Actor:
    user: User | None = None
    session: SessionClaims | None = None
    via_cookie: bool = False

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.user.id if self.user else None

    @property
    def name(self) -> str:
        return self.user.name if self.user else "system"

    @property
    def role(self) -> Role:
        return Role(self.user.role) if self.user else Role.ADMIN


SYSTEM = Actor()
