"""What the call log keeps of a tool call's arguments.

Paths named by the matching rule are replaced, and so is any value under a key that looks
like a credential, wherever it is nested: a model pasting a token into an argument does
not put that token in the audit log. Long strings are shortened and oversized records
keep only their top-level keys, so one call cannot bloat the log.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Any, Final

import orjson

from mcphub.policy.scrub import scrub_patterns

REDACTED: Final = "[redacted]"
TRUNCATED: Final = "[truncated]"
MAX_STRING: Final = 2000
MAX_ITEMS: Final = 100
MAX_DEPTH: Final = 8
# Matched against the words of a key (`refresh_token`, `clientSecret`, `X-Api-Key`), not
# its substrings, so counts such as `max_tokens` are not mistaken for credentials.
SENSITIVE_WORDS: Final = frozenset(
    {
        "password",
        "passwords",
        "passwd",
        "passphrase",
        "secret",
        "secrets",
        "token",
        "apikey",
        "authorization",
        "auth",
        "credential",
        "credentials",
        "cookie",
        "pin",
    }
)
SENSITIVE_PAIRS: Final = frozenset({("api", "key"), ("private", "key"), ("access", "key")})
_WORDS = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|[0-9]+")


def is_sensitive_key(key: str) -> bool:
    words = [word.lower() for word in _WORDS.findall(key)]
    if any(word in SENSITIVE_WORDS for word in words):
        return True
    return any(pair in SENSITIVE_PAIRS for pair in pairwise(words))


def _clean(value: Any, depth: int) -> Any:
    if depth > MAX_DEPTH:
        return TRUNCATED
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if is_sensitive_key(str(key)) else _clean(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        items = [_clean(item, depth + 1) for item in value[:MAX_ITEMS]]
        if len(value) > MAX_ITEMS:
            items.append(f"[{len(value) - MAX_ITEMS} more items]")
        return items
    if isinstance(value, str):
        # A credential pasted into free text is masked even under an innocent key.
        shortened = (
            value[:MAX_STRING] + f"... [{len(value)} characters]"
            if len(value) > MAX_STRING
            else value
        )
        return scrub_patterns(shortened)
    return value


def _replace_path(target: dict[str, Any], path: str) -> None:
    *parents, leaf = path.split(".")
    current: Any = target
    for part in parents:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]
    if isinstance(current, dict) and leaf in current:
        current[leaf] = REDACTED


def redact(
    arguments: Mapping[str, Any] | None, paths: Sequence[str] = (), *, max_bytes: int = 16_384
) -> dict[str, Any] | None:
    if arguments is None:
        return None
    cleaned: dict[str, Any] = _clean(arguments, 0)
    for path in paths:
        _replace_path(cleaned, path)
    if len(orjson.dumps(cleaned, default=str)) > max_bytes:
        return dict.fromkeys(list(cleaned)[:MAX_ITEMS], TRUNCATED)
    return cleaned
