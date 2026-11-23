"""Request dependencies: infrastructure, the signed-in person, roles and rate limits."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from mcphub.core.config import Settings
from mcphub.core.errors import ForbiddenError, RateLimitedError, UnauthorizedError
from mcphub.core.security import API_KEY_PREFIX
from mcphub.models import User
from mcphub.models.enums import Role
from mcphub.services.actor import Actor
from mcphub.services.auth import SESSION_COOKIE, AuthService
from mcphub.services.container import Container

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    async with container.db.session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _origin_allowed(request: Request, settings: Settings) -> bool:
    """CSRF defence for cookie sessions: unsafe methods must come from the dashboard."""
    origin = request.headers.get("origin")
    if origin is None and (referer := request.headers.get("referer")):
        parts = urlsplit(referer)
        origin = f"{parts.scheme}://{parts.netloc}"
    allowed = {*settings.cors_origins, settings.web_url.rstrip("/")}
    return origin in allowed


async def get_actor(request: Request, container: ContainerDep, session: SessionDep) -> Actor:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token.startswith(f"{API_KEY_PREFIX}_"):
            raise ForbiddenError(
                "Client API keys work only at the MCP gateway (/mcp), not the management API.",
                code="client_key_not_allowed",
            )
        user, claims = await AuthService(container, session).resolve(token)
        return Actor(user=user, session=claims)
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        user, claims = await AuthService(container, session).resolve(cookie)
        if request.method not in _SAFE_METHODS and not _origin_allowed(request, container.settings):
            raise ForbiddenError("Cross-site request blocked.", code="csrf")
        return Actor(user=user, session=claims, via_cookie=True)
    raise UnauthorizedError()


ActorDep = Annotated[Actor, Depends(get_actor)]


def get_user(actor: ActorDep) -> User:
    if actor.user is None:
        raise UnauthorizedError()
    return actor.user


UserDep = Annotated[User, Depends(get_user)]


class RequireRole:
    """At least `minimum` role (admin > operator > viewer)."""

    def __init__(self, minimum: Role) -> None:
        self.minimum = minimum

    def __call__(self, actor: ActorDep) -> Actor:
        if not actor.role.allows(self.minimum):
            raise ForbiddenError(
                f"This needs the {self.minimum.value} role.", code="forbidden_role"
            )
        return actor


ViewerDep = Annotated[Actor, Depends(RequireRole(Role.VIEWER))]
OperatorDep = Annotated[Actor, Depends(RequireRole(Role.OPERATOR))]
AdminDep = Annotated[Actor, Depends(RequireRole(Role.ADMIN))]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def login_rate_limit() -> Callable[..., Awaitable[None]]:
    async def dependency(request: Request, response: Response, container: ContainerDep) -> None:
        result = await container.limiter.hit(
            f"login:{client_ip(request)}", container.settings.rate_limit_login
        )
        response.headers.update(result.headers())
        if not result.allowed:
            raise RateLimitedError("Too many sign-in attempts. Wait a minute and try again.")

    return dependency
