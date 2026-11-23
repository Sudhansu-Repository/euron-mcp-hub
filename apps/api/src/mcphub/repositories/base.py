from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class Repository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


def like_pattern(text: str) -> str:
    """A LIKE pattern matching `text` anywhere, with LIKE wildcards in it escaped."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
