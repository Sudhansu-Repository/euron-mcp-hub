"""Toolbox: a calculator, unit and time zone conversion, and a deliberately slow tool."""

from __future__ import annotations

import ast
import asyncio
import math
import operator
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

VERSION = "1.2.0"

_BINARY: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "log": math.log,
    "exp": math.exp,
}
_CONSTANTS = {"pi": math.pi, "e": math.e}


def evaluate(expression: str) -> float:
    """Arithmetic only: numbers, operators, parentheses and a few named functions."""

    def walk(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return node.value
        if isinstance(node, ast.Name) and node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
            value = walk(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ToolError("Exponents above 100 are not supported.")
            return _BINARY[type(node.op)](left, right)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCTIONS
            and not node.keywords
        ):
            return _FUNCTIONS[node.func.id](*(walk(arg) for arg in node.args))
        raise ToolError("Only numbers, + - * / // % **, parentheses and math functions.")

    if len(expression) > 300:
        raise ToolError("The expression is too long.")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError(f"That is not a valid expression: {exc.msg}.") from exc
    try:
        return float(walk(tree))
    except ZeroDivisionError as exc:
        raise ToolError("Division by zero.") from exc
    except (OverflowError, ValueError) as exc:
        raise ToolError(f"The result cannot be computed: {exc}.") from exc


_LENGTH = {
    "mm": 0.001,
    "cm": 0.01,
    "m": 1.0,
    "km": 1000.0,
    "in": 0.0254,
    "ft": 0.3048,
    "mi": 1609.344,
}
_MASS = {"g": 0.001, "kg": 1.0, "t": 1000.0, "oz": 0.028349523125, "lb": 0.45359237}
Unit = Literal["mm", "cm", "m", "km", "in", "ft", "mi", "g", "kg", "t", "oz", "lb", "c", "f", "k"]


def convert(value: float, source: str, target: str) -> float:
    for table in (_LENGTH, _MASS):
        if source in table and target in table:
            return value * table[source] / table[target]
    temperatures = {"c", "f", "k"}
    if source in temperatures and target in temperatures:
        celsius = {"c": value, "f": (value - 32) * 5 / 9, "k": value - 273.15}[source]
        return {"c": celsius, "f": celsius * 9 / 5 + 32, "k": celsius + 273.15}[target]
    raise ToolError(f"Cannot convert {source} to {target}: they measure different things.")


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ToolError(
            f"Unknown time zone {name!r}; use an IANA name like Europe/Berlin."
        ) from exc


def build_toolbox_server() -> MCPServer:
    server = MCPServer(
        "toolbox",
        title="Toolbox",
        description="Everyday utilities for agents: arithmetic, units, time zones.",
        version=VERSION,
        log_level="WARNING",
    )
    read_only = ToolAnnotations(read_only_hint=True, idempotent_hint=True)

    @server.tool(
        description="Evaluate an arithmetic expression, such as (12.5 * 4) / 3.",
        annotations=read_only,
    )
    def calculate(expression: str) -> float:
        return round(evaluate(expression), 10)

    @server.tool(
        description="Convert a length, mass or temperature between units.", annotations=read_only
    )
    def convert_units(value: float, from_unit: Unit, to_unit: Unit) -> float:
        return round(convert(value, from_unit, to_unit), 6)

    @server.tool(description="The current date and time in a time zone.", annotations=read_only)
    def current_time(timezone: str = "UTC") -> str:
        return datetime.now(UTC).astimezone(_zone(timezone)).isoformat(timespec="seconds")

    @server.tool(
        description="Convert an ISO 8601 date and time from one time zone to another.",
        annotations=read_only,
    )
    def convert_timezone(time: str, from_timezone: str, to_timezone: str) -> str:
        try:
            parsed = datetime.fromisoformat(time)
        except ValueError as exc:
            raise ToolError("Use an ISO 8601 time such as 2026-10-23T14:30.") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_zone(from_timezone))
        return parsed.astimezone(_zone(to_timezone)).isoformat(timespec="minutes")

    @server.tool(description="A new random UUID.")
    def random_uuid() -> str:
        return str(uuid.uuid4())

    @server.tool(
        description="Wait, then answer. Useful to see how the gateway handles slow tools.",
        annotations=read_only,
    )
    async def wait(seconds: Annotated[float, Field(ge=0, le=15)] = 1.0) -> str:
        await asyncio.sleep(seconds)
        return f"Waited {seconds:g} seconds."

    return server
