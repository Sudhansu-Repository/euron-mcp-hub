from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Page[ItemT](ApiModel):
    items: list[ItemT]
    total: int
    limit: int
    offset: int


class CursorPage[ItemT](ApiModel):
    items: list[ItemT]
    next_cursor: str | None = None


class Ok(ApiModel):
    ok: bool = True
