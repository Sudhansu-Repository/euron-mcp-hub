"""Weather: deterministic forecasts over stdio, behind an API key in the environment.

The gateway launches this server as a subprocess and injects WEATHER_API_KEY from an
encrypted secret, which is the point of the demo: the key never appears in a config
file. Forecasts longer than ten days crash the process on purpose, to show how the
gateway reports a dead stdio server and starts a fresh one on the next call.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

VERSION = "0.9.1"
CITIES = (
    "Amsterdam",
    "Bengaluru",
    "Berlin",
    "Cape Town",
    "Lisbon",
    "London",
    "Mumbai",
    "New York",
    "Pune",
    "San Francisco",
    "Singapore",
    "Sydney",
    "Tokyo",
    "Toronto",
)
_CONDITIONS = ("clear", "partly cloudy", "cloudy", "light rain", "showers", "windy", "fog")


def _sample(city: str, day: date) -> dict[str, Any]:
    seed = int.from_bytes(hashlib.sha256(f"{city.lower()}|{day.isoformat()}".encode()).digest()[:8])
    base = 8 + (seed % 23)
    return {
        "date": day.isoformat(),
        "condition": _CONDITIONS[seed % len(_CONDITIONS)],
        "high_c": base + (seed >> 8) % 7,
        "low_c": base - (seed >> 16) % 6,
        "chance_of_rain": (seed >> 24) % 100,
        "wind_kph": 5 + (seed >> 32) % 35,
    }


def _require_key() -> None:
    if not os.environ.get("WEATHER_API_KEY"):
        raise ToolError("WEATHER_API_KEY is not set for this server.")


def build_weather_server() -> MCPServer:
    server = MCPServer(
        "weather",
        title="Weather",
        description="Current conditions and forecasts for major cities.",
        version=VERSION,
        log_level="WARNING",
    )
    read_only = ToolAnnotations(read_only_hint=True, open_world_hint=True)

    @server.tool(description="Current weather in a city.", annotations=read_only)
    def current_weather(city: Annotated[str, Field(min_length=2, max_length=80)]) -> dict[str, Any]:
        _require_key()
        sample = _sample(city, datetime.now(UTC).date())
        return {"city": city, **sample}

    @server.tool(description="Daily forecast for up to ten days.", annotations=read_only)
    def forecast(
        city: Annotated[str, Field(min_length=2, max_length=80)],
        days: Annotated[int, Field(ge=1, le=30)] = 3,
    ) -> list[dict[str, Any]]:
        _require_key()
        if days > 10:
            # A deliberate crash: the process exits mid-request, as buggy servers do.
            os._exit(3)
        start = datetime.now(UTC).date()
        return [{"city": city, **_sample(city, start + timedelta(days=i))} for i in range(days)]

    @server.resource("weather://cities", description="Cities with forecasts.")
    def cities() -> str:
        return "\n".join(CITIES)

    return server
