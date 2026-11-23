"""Argument constraints: what a client may pass to a tool its policy allows.

Each constraint names an argument by path (`priority`, `filters.status`) and a rule. They
are checked before the call leaves the gateway, and every violation is reported back so a
model can correct its call instead of guessing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

_PATH = re.compile(r"^[A-Za-z0-9_-]{1,64}(?:\.[A-Za-z0-9_-]{1,64}){0,7}$")
_MISSING = object()


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    argument: str = Field(description="Argument path, for example `priority` or `filters.status`.")

    @field_validator("argument")
    @classmethod
    def _valid_path(cls, value: str) -> str:
        if not _PATH.fullmatch(value):
            raise ValueError("Use an argument name, or a dotted path into nested objects.")
        return value


class EqualsConstraint(_Base):
    rule: Literal["equals"]
    value: JsonValue


class OneOfConstraint(_Base):
    rule: Literal["one_of"]
    values: list[JsonValue] = Field(min_length=1, max_length=100)


class PatternConstraint(_Base):
    rule: Literal["pattern"]
    value: str = Field(min_length=1, max_length=200, description="A regular expression.")

    @field_validator("value")
    @classmethod
    def _compiles(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"Not a valid regular expression: {exc}") from exc
        return value


class MaxLengthConstraint(_Base):
    rule: Literal["max_length"]
    value: int = Field(ge=0, le=1_000_000)


class RangeConstraint(_Base):
    rule: Literal["range"]
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def _bounded(self) -> RangeConstraint:
        if self.min is None and self.max is None:
            raise ValueError("Set min, max or both.")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min must not be greater than max.")
        return self


class ForbiddenConstraint(_Base):
    rule: Literal["forbidden"]


Constraint = Annotated[
    EqualsConstraint
    | OneOfConstraint
    | PatternConstraint
    | MaxLengthConstraint
    | RangeConstraint
    | ForbiddenConstraint,
    Field(discriminator="rule"),
]


class ConstraintList(BaseModel):
    """Parses stored JSON back into typed constraints."""

    items: list[Constraint] = Field(default_factory=list, max_length=50)


def parse_constraints(raw: Sequence[Mapping[str, Any]]) -> list[Constraint]:
    return ConstraintList.model_validate({"items": list(raw)}).items


@dataclass(frozen=True, slots=True)
class Violation:
    argument: str
    rule: str
    message: str


def lookup(arguments: Mapping[str, Any], path: str) -> Any:
    """The value at a dotted path, or `_MISSING` when any step does not exist."""
    current: Any = arguments
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _shown(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def check(constraints: Sequence[Constraint], arguments: Mapping[str, Any]) -> list[Violation]:
    violations: list[Violation] = []
    for constraint in constraints:
        value = lookup(arguments, constraint.argument)
        message = _violation(constraint, value)
        if message is not None:
            violations.append(Violation(constraint.argument, constraint.rule, message))
    return violations


def _violation(constraint: Constraint, value: Any) -> str | None:
    name = f"`{constraint.argument}`"
    if isinstance(constraint, ForbiddenConstraint):
        return None if value is _MISSING else f"{name} may not be set by this client."
    if value is _MISSING:
        # A pinned value must be present; every other rule constrains values that are given.
        if isinstance(constraint, EqualsConstraint):
            return f"{name} is required and must be {_shown(constraint.value)}."
        return None
    if isinstance(constraint, EqualsConstraint):
        if value != constraint.value:
            return f"{name} must be {_shown(constraint.value)} (got {_shown(value)})."
        return None
    if isinstance(constraint, OneOfConstraint):
        if value not in constraint.values:
            allowed = ", ".join(_shown(v) for v in constraint.values[:10])
            return f"{name} must be one of {allowed} (got {_shown(value)})."
        return None
    if isinstance(constraint, PatternConstraint):
        if not isinstance(value, str) or re.fullmatch(constraint.value, value) is None:
            return f"{name} must match {constraint.value!r} (got {_shown(value)})."
        return None
    if isinstance(constraint, MaxLengthConstraint):
        if isinstance(value, str | list | dict) and len(value) > constraint.value:
            return f"{name} must be at most {constraint.value} long (got {len(value)})."
        return None
    if not _is_number(value):
        return f"{name} must be a number (got {_shown(value)})."
    if constraint.min is not None and value < constraint.min:
        return f"{name} must be at least {constraint.min:g} (got {value})."
    if constraint.max is not None and value > constraint.max:
        return f"{name} must be at most {constraint.max:g} (got {value})."
    return None
