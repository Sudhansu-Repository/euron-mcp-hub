"""Opaque keyset cursors for append-heavy lists (the call log).

Offset pagination rescans every skipped row and shifts when new rows arrive; a keyset
cursor resumes strictly after the last row seen, in the `(created_at, id)` index order.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import datetime

import orjson

from mcphub.core.errors import UnprocessableError


@dataclass(frozen=True, slots=True)
class Cursor:
    created_at: datetime
    id: uuid.UUID

    def encode(self) -> str:
        raw = orjson.dumps([self.created_at.isoformat(), str(self.id)])
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @classmethod
    def decode(cls, value: str) -> Cursor:
        try:
            padded = value + "=" * (-len(value) % 4)
            created_at, row_id = orjson.loads(base64.urlsafe_b64decode(padded))
            return cls(datetime.fromisoformat(created_at), uuid.UUID(row_id))
        except (ValueError, TypeError, binascii.Error, orjson.JSONDecodeError) as exc:
            raise UnprocessableError(
                "That page cursor is not valid.", code="invalid_cursor"
            ) from exc
