"""Keeping credentials out of logs, audit entries and tool results.

Two different jobs, kept apart on purpose:

- `scrub_known` removes the exact secret values the gateway itself injected into an
  upstream connection. It is safe to run on tool results sent back to clients: a hostile or
  careless server that echoes the bearer token it was given never hands it to a client.
- `scrub_patterns` also masks anything shaped like a credential (bearer tokens, MCPHub
  keys, cloud keys, JWTs). It is for text that is only stored or logged, never relayed,
  because it may mask a harmless string that merely looks like a token.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final

REDACTED: Final = "[redacted]"
# Values shorter than this are too likely to be ordinary words to mask by value.
MIN_SECRET_LENGTH: Final = 8

_PATTERNS: Final = (
    re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bmch_[A-Za-z0-9_-]{8,}"),
    re.compile(r"\b(?:sk|pk|rk)[-_](?:live|test|proj)?[-_]?[A-Za-z0-9]{16,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(
        r"(?i)\b(api[_-]?key|token|secret|password|passwd)\b(\s*[=:]\s*)[\"']?[^\s\"',;&]{6,}"
    ),
)


def scrub_known(text: str, secrets: Iterable[str]) -> str:
    """The text with every occurrence of the given secret values masked."""
    for secret in sorted(
        {s for s in secrets if len(s) >= MIN_SECRET_LENGTH}, key=len, reverse=True
    ):
        if secret in text:
            text = text.replace(secret, REDACTED)
    return text


def scrub_patterns(text: str) -> str:
    """The text with anything shaped like a credential masked."""
    for pattern in _PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
        elif pattern.groups == 1:
            text = pattern.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
        else:
            text = pattern.sub(REDACTED, text)
    return text
