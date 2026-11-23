"""Small text helpers shared by services."""

from __future__ import annotations

import re
import unicodedata

SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?$")


def slugify(value: str, *, fallback: str = "item", max_length: int = 48) -> str:
    """Lowercase ASCII letters, digits and single hyphens.

    Server slugs become tool namespaces (`tickets.create_ticket`), so they never contain
    the separators `.` or `_`: the first separator in a tool name is always the boundary.
    """
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug[:max_length].strip("-") or fallback


def is_valid_slug(value: str) -> bool:
    return bool(SLUG_PATTERN.fullmatch(value))


def truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: max(0, limit - 3)] + "..."
