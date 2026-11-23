"""Policy decisions: may this client use this tool, and under which rule?"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from mcphub.models.enums import Effect
from mcphub.policy.constraints import Constraint
from mcphub.policy.patterns import matches, specificity


@dataclass(frozen=True, slots=True)
class Rule:
    pattern: str
    effect: Effect
    id: uuid.UUID | None = None
    constraints: tuple[Constraint, ...] = ()
    rate_limit_per_minute: int | None = None
    redact: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    rule: Rule | None

    @property
    def reason(self) -> str:
        if self.rule is None:
            return "No rule matches, so the client's default applies."
        verb = "allows" if self.allowed else "denies"
        return f"Rule {self.rule.pattern!r} {verb} it."


def decide(rules: Sequence[Rule], default_effect: Effect, qualified_name: str) -> Decision:
    """The most specific matching rule decides; equally specific rules resolve to deny."""
    best: Rule | None = None
    best_key: tuple[int, int] | None = None
    for rule in rules:
        if not matches(rule.pattern, qualified_name):
            continue
        key = specificity(rule.pattern)
        if (
            best is None
            or best_key is None
            or key > best_key
            or (key == best_key and rule.effect is Effect.DENY)
        ):
            best, best_key = rule, key
    if best is None:
        return Decision(allowed=default_effect is Effect.ALLOW, rule=None)
    return Decision(allowed=best.effect is Effect.ALLOW, rule=best)
