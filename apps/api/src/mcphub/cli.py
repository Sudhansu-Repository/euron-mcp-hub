"""Operator command line.

mcphub migrate
mcphub user create --email you@example.com --name "You" --role admin
mcphub discover [--server tickets]
mcphub purge
mcphub demo seed
mcphub openapi --out docs/api/openapi.json
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Literal

import typer

from mcphub.core.config import get_settings
from mcphub.core.logging import configure_logging

app = typer.Typer(no_args_is_help=True, help="Euron MCPHub command line.", add_completion=False)
user_app = typer.Typer(no_args_is_help=True, help="Manage dashboard accounts.")
demo_app = typer.Typer(no_args_is_help=True, help="Demo data for local stacks.")
app.add_typer(user_app, name="user")
app.add_typer(demo_app, name="demo")


@app.callback()
def _setup() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, "console")


@app.command()
def migrate() -> None:
    """Apply pending database migrations."""
    from mcphub.db.migrate import migrate as run

    asyncio.run(run(get_settings()))
    typer.echo("migrations applied")


@user_app.command("create")
def create_user(
    email: Annotated[str, typer.Option(help="Sign-in email.")],
    name: Annotated[str, typer.Option(help="Display name.")],
    password: Annotated[str, typer.Option(prompt=True, hide_input=True, confirmation_prompt=True)],
    role: Annotated[Literal["admin", "operator", "viewer"], typer.Option(help="Role.")] = "admin",
) -> None:
    """Create an account."""
    from mcphub.db.session import Database
    from mcphub.models.enums import Role
    from mcphub.services.actor import SYSTEM
    from mcphub.services.users import UserService

    async def run() -> None:
        db = Database(get_settings())
        try:
            async with db.session() as session:
                user, _ = await UserService(session).create(
                    SYSTEM, email=email, name=name, role=Role(role), password=password
                )
                typer.echo(f"created {user.email} ({user.role})")
        finally:
            await db.dispose()

    asyncio.run(run())


@app.command()
def discover(
    server: Annotated[
        str | None, typer.Option(help="Server slug; every server when omitted.")
    ] = None,
) -> None:
    """Discover servers now, instead of waiting for the worker's schedule."""
    from mcphub.repositories.servers import ServerFilters, ServerRepository
    from mcphub.services.container import build_container
    from mcphub.services.discovery import DiscoveryService

    async def run() -> None:
        container = build_container(get_settings())
        try:
            async with container.db.session() as session:
                repo = ServerRepository(session)
                if server:
                    found = await repo.by_slug(server)
                    targets = [found] if found else []
                else:
                    targets, _ = await repo.page(ServerFilters(enabled=True), limit=500, offset=0)
            if not targets:
                raise typer.BadParameter("no matching servers")
            for target in targets:
                outcome = await DiscoveryService(container).discover(target.id)
                status = "ok" if outcome.ok else f"failed: {outcome.error}"
                typer.echo(f"{target.slug:<24} {status}")
        finally:
            await container.close()

    asyncio.run(run())


@app.command()
def purge() -> None:
    """Delete call log rows and health checks past their retention now."""
    from mcphub.services import retention
    from mcphub.services.container import build_container

    async def run() -> None:
        container = build_container(get_settings())
        try:
            purged = await retention.purge(container)
            typer.echo(f"deleted {purged.calls} call(s) and {purged.checks} health check(s)")
        finally:
            await container.close()

    asyncio.run(run())


@demo_app.command("seed")
def seed(
    password: Annotated[
        str | None, typer.Option(envvar="DEMO_PASSWORD", help="Password for every demo account.")
    ] = None,
    servers_host: Annotated[
        str, typer.Option(envvar="DEMO_SERVERS_HOST", help="Where the demo MCP servers listen.")
    ] = "127.0.0.1",
    tickets_token: Annotated[
        str, typer.Option(envvar="DEMO_TICKETS_TOKEN", help="Token the demo tickets server wants.")
    ] = "demo-tickets-token",  # noqa: S107
    weather_key: Annotated[
        str, typer.Option(envvar="DEMO_WEATHER_KEY", help="API key for the demo weather server.")
    ] = "demo-weather-key",
    history: Annotated[bool, typer.Option(help="Run demo traffic through the gateway.")] = True,
) -> None:
    """Demo accounts, servers, clients, policies and two weeks of real gateway traffic."""
    from mcphub.demo.seed import DemoOptions, run

    settings = get_settings()
    if settings.is_production:
        raise typer.BadParameter("refusing to seed demo data with APP_ENV=production")
    secret = password or (
        settings.demo_password.get_secret_value() if settings.demo_password else None
    )
    if not secret:
        raise typer.BadParameter("set DEMO_PASSWORD (make env generates one)")
    options = DemoOptions(
        password=secret,
        servers_host=servers_host,
        tickets_token=tickets_token,
        weather_key=weather_key,
        history=history,
    )
    asyncio.run(run(settings, options))


@app.command()
def openapi(
    out: Annotated[Path, typer.Option(help="Where to write the OpenAPI document.")] = Path(
        "openapi.json"
    ),
) -> None:
    """Export the OpenAPI document generated from the routes."""
    from mcphub.main import create_app

    schema = create_app().openapi()
    out.write_text(json.dumps(schema, indent=2, sort_keys=False) + "\n")
    typer.echo(f"wrote {out}")


if __name__ == "__main__":
    app()
