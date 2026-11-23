"""`mcphub-demo`: run the demo MCP servers.

mcphub-demo serve      notes on 9150, toolbox on 9151, tickets on 9152 (streamable HTTP)
mcphub-demo weather    the weather server over stdio (the gateway launches this itself)
"""

from __future__ import annotations

import asyncio
import os
from typing import Annotated

import typer
from starlette.types import ASGIApp

from mcphub.demo.servers.common import RequireBearer, mcp_app, mounted, serve_all
from mcphub.demo.servers.notes import build_notes_server
from mcphub.demo.servers.tickets import LATEST, PREVIOUS, Queue, build_tickets_server
from mcphub.demo.servers.toolbox import build_toolbox_server
from mcphub.demo.servers.weather import build_weather_server

cli = typer.Typer(no_args_is_help=True, add_completion=False, help="Euron MCPHub demo MCP servers.")


@cli.command()
def serve(
    host: Annotated[str, typer.Option(help="Interface to bind.")] = "127.0.0.1",
    notes_port: Annotated[int, typer.Option(help="Port for the notes server.")] = 9150,
    toolbox_port: Annotated[int, typer.Option(help="Port for the toolbox server.")] = 9151,
    tickets_port: Annotated[int, typer.Option(help="Port for the tickets server.")] = 9152,
    # A demo default for `uv run`; the compose stack passes a random token instead.
    tickets_token: Annotated[
        str,
        typer.Option(envvar="DEMO_TICKETS_TOKEN", help="Bearer token the tickets server requires."),
    ] = "demo-tickets-token",  # noqa: S107
) -> None:
    """Serve notes, toolbox and tickets over streamable HTTP."""
    queue = Queue()
    tickets = mounted(
        ("/v1", build_tickets_server(queue, version=PREVIOUS)),
        ("", build_tickets_server(queue, version=LATEST)),
    )
    apps: list[tuple[ASGIApp, int]] = [
        (mcp_app(build_notes_server()), notes_port),
        (mcp_app(build_toolbox_server()), toolbox_port),
        (RequireBearer(tickets, tickets_token), tickets_port),
    ]
    ports = f"notes {notes_port}, toolbox {toolbox_port}, tickets {tickets_port}"
    typer.echo(f"demo MCP servers on {host}: {ports}")
    asyncio.run(serve_all(apps, host))


@cli.command()
def weather() -> None:
    """Serve the weather server over stdio (WEATHER_API_KEY must be set by the launcher)."""
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    build_weather_server().run("stdio")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
