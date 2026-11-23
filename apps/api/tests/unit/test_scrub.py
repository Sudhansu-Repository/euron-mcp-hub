from __future__ import annotations

import pytest

from mcphub.policy.redaction import REDACTED, redact
from mcphub.policy.scrub import scrub_known, scrub_patterns


def test_known_secret_values_are_masked_wherever_they_appear() -> None:
    text = "upstream said: bad token tkt_ABCDEF123456, got Bearer tkt_ABCDEF123456"

    result = scrub_known(text, ["tkt_ABCDEF123456", "ab"])

    assert "tkt_ABCDEF123456" not in result
    assert result.count(REDACTED) == 2


def test_short_values_are_not_masked_by_value() -> None:
    assert scrub_known("the cat sat", ["cat"]) == "the cat sat"


@pytest.mark.parametrize(
    "secret",
    [
        "Bearer abcdefghijklmnop",
        "mch_k3j4h5g6f7d8s9a0",
        "sk-proj-abcdefghijklmnopqrstuvwx",
        "ghp" + "_abcdefghijklmnopqrstuvwxyz0123456789",
        "AKIA" + "IOSFODNN7EXAMPLE",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV",
    ],
)
def test_credential_shapes_are_masked(secret: str) -> None:
    result = scrub_patterns(f"failed calling upstream with {secret} twice")

    assert secret not in result
    assert REDACTED in result


def test_key_value_credentials_keep_their_names() -> None:
    result = scrub_patterns("connect failed: api_key=abcd1234efgh, password: hunter2hunter2")

    assert "abcd1234efgh" not in result
    assert "hunter2hunter2" not in result
    assert "api_key=[redacted]" in result


def test_ordinary_text_is_untouched() -> None:
    text = "Ticket TCK-1204 was moved to pending by the ops agent."

    assert scrub_patterns(text) == text


def test_audit_arguments_mask_credentials_pasted_into_free_text() -> None:
    result = redact({"note": "use Bearer abcdefghijklmnop to log in", "count": 3})

    assert result == {"note": f"use Bearer {REDACTED} to log in", "count": 3}
