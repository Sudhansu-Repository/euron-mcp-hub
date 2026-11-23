"""Rule patterns over canonical tool names, and how specific each one is.

Patterns use shell-style wildcards on the whole canonical name (`tickets.create_ticket`):
`*` matches any run of characters and `?` any one character. Of all the rules matching a
tool, the most specific decides:

    exact name  >  more literal characters  >  fewer

so `tickets.delete_ticket` beats `tickets.delete_*`, which beats `tickets.*`, which beats
`*`. Character classes (`[abc]`) are not supported: a pattern is meant to be read at a
glance in a review.
"""

from __future__ import annotations

import re
from fnmatch import fnmatchcase
from functools import lru_cache
from typing import Final

ANY: Final = "*"
_WILDCARDS: Final = frozenset("*?")
# Server part: slug characters and wildcards. Tool part: tool-name characters and wildcards.
_PATTERN = re.compile(r"^(?:\*|[a-z0-9*?-]{1,48}\.[A-Za-z0-9._*?-]{1,200})$")


def validate_pattern(pattern: str) -> str:
    """The pattern, normalised; raises ValueError with a readable reason."""
    value = pattern.strip()
    if not value:
        raise ValueError("A pattern cannot be empty.")
    if not _PATTERN.fullmatch(value):
        raise ValueError(
            "Use <server>.<tool> with * or ? wildcards, for example tickets.create_ticket, "
            "tickets.get_* or *."
        )
    return value


def has_wildcard(pattern: str) -> bool:
    return any(char in _WILDCARDS for char in pattern)


@lru_cache(maxsize=4096)
def specificity(pattern: str) -> tuple[int, int]:
    """Sort key: exact names first, then by the number of literal characters."""
    literal = sum(1 for char in pattern if char not in _WILDCARDS)
    return (0 if has_wildcard(pattern) else 1, literal)


def matches(pattern: str, qualified_name: str) -> bool:
    if pattern == ANY:
        return True
    if not has_wildcard(pattern):
        return pattern == qualified_name
    return fnmatchcase(qualified_name, pattern)
