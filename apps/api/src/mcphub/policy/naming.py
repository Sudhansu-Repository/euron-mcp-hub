"""Namespaced tool names: `<server slug><separator><upstream tool name>`.

Server slugs are lowercase letters, digits and hyphens, so neither separator (`.` or
`__`) can occur in one: the first separator in a name is always the boundary, and the
upstream tool name after it may contain anything, dots and underscores included.
Policy rules and the call log always use the canonical dot form.
"""

from __future__ import annotations

import re
from typing import Final

DOT: Final = "."
DOUBLE_UNDERSCORE: Final = "__"
SEPARATORS: Final = (DOT, DOUBLE_UNDERSCORE)
_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?$")


def qualify(server_slug: str, tool_name: str, separator: str = DOT) -> str:
    return f"{server_slug}{separator}{tool_name}"


def canonical(server_slug: str, tool_name: str) -> str:
    return qualify(server_slug, tool_name, DOT)


def split(name: str, separator: str = DOT) -> tuple[str, str] | None:
    """`(server slug, upstream tool name)`, or None when the name has no valid namespace."""
    server, found, tool = name.partition(separator)
    if not found or not tool or not _SLUG.fullmatch(server):
        return None
    return server, tool
