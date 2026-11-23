"""Sign-in, first-run setup, the current user, password and profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from mcphub.api.deps import ActorDep, ContainerDep, SessionDep, UserDep, login_rate_limit
from mcphub.core.security import SessionClaims
from mcphub.schemas.auth import (
    LoginRequest,
    PasswordChange,
    ProfileUpdate,
    SessionOut,
    SetupRequest,
    UserOut,
)
from mcphub.services.auth import SESSION_COOKIE, AuthService
from mcphub.services.container import Container

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _set_cookie(response: Response, container: Container, token: str, _: SessionClaims) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=container.settings.session_ttl_hours * 3600,
        httponly=True,
        secure=container.settings.cookie_secure,
        samesite="lax",
        domain=container.settings.cookie_domain,
        path="/",
    )


@router.post("/login", summary="Sign in", dependencies=[Depends(login_rate_limit())])
async def login(
    body: LoginRequest, response: Response, container: ContainerDep, session: SessionDep
) -> SessionOut:
    user, token, claims = await AuthService(container, session).login(body.email, body.password)
    _set_cookie(response, container, token, claims)
    return SessionOut(user=UserOut.model_validate(user), token=token, expires_at=claims.expires_at)


@router.post(
    "/setup",
    summary="Create the first account (an admin); refused once any account exists",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(login_rate_limit())],
)
async def setup(
    body: SetupRequest, response: Response, container: ContainerDep, session: SessionDep
) -> SessionOut:
    auth = AuthService(container, session)
    await auth.setup(body.email, body.name, body.password)
    user, token, claims = await auth.login(body.email, body.password)
    _set_cookie(response, container, token, claims)
    return SessionOut(user=UserOut.model_validate(user), token=token, expires_at=claims.expires_at)


@router.post("/logout", summary="Sign out", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    actor: ActorDep, response: Response, container: ContainerDep, session: SessionDep
) -> None:
    if actor.session is not None:
        await AuthService(container, session).logout(actor.session)
    response.delete_cookie(SESSION_COOKIE, path="/", domain=container.settings.cookie_domain)


@router.get("/me", summary="The signed-in user")
async def me(user: UserDep) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", summary="Update your profile")
async def update_me(
    body: ProfileUpdate, user: UserDep, container: ContainerDep, session: SessionDep
) -> UserOut:
    return UserOut.model_validate(
        await AuthService(container, session).update_profile(user, body.name)
    )


@router.post("/password", summary="Change your password (signs out every other session)")
async def change_password(
    body: PasswordChange,
    user: UserDep,
    response: Response,
    container: ContainerDep,
    session: SessionDep,
) -> SessionOut:
    token, claims = await AuthService(container, session).change_password(
        user, body.current_password, body.new_password
    )
    _set_cookie(response, container, token, claims)
    return SessionOut(user=UserOut.model_validate(user), token=token, expires_at=claims.expires_at)
