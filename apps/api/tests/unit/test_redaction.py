from __future__ import annotations

from typing import Any

from mcphub.policy.redaction import REDACTED, TRUNCATED, is_sensitive_key, redact


def test_credential_like_keys_are_redacted_at_any_depth() -> None:
    arguments: dict[str, Any] = {
        "query": "invoices",
        "connection": {"api_key": "sk-123", "Authorization": "Bearer abc"},
        "auth": {"user": "svc"},
        "items": [{"password": "hunter2", "name": "x"}],
        "github-token": "ghp_x",
    }

    result = redact(arguments)

    assert result == {
        "query": "invoices",
        "connection": {"api_key": REDACTED, "Authorization": REDACTED},
        "auth": REDACTED,
        "items": [{"password": REDACTED, "name": "x"}],
        "github-token": REDACTED,
    }
    assert arguments["connection"]["api_key"] == "sk-123", "the caller's arguments are not modified"


def test_paths_named_by_the_policy_are_redacted() -> None:
    result = redact(
        {"customer": {"email": "a@b.example", "plan": "pro"}, "note": "hi"},
        ["customer.email", "note", "missing.path"],
    )

    assert result == {"customer": {"email": REDACTED, "plan": "pro"}, "note": REDACTED}


def test_long_strings_and_lists_are_shortened() -> None:
    result = redact({"body": "x" * 5000, "ids": list(range(150))})

    assert result is not None
    assert result["body"].endswith("... [5000 characters]")
    assert len(result["ids"]) == 101
    assert result["ids"][-1] == "[50 more items]"


def test_an_oversized_record_keeps_only_its_keys() -> None:
    result = redact({"a": "y" * 1500, "b": "z" * 1500}, max_bytes=1024)

    assert result == {"a": TRUNCATED, "b": TRUNCATED}


def test_no_arguments_stay_none() -> None:
    assert redact(None) is None


def test_sensitive_keys_are_detected_by_word_not_by_substring() -> None:
    for key in (
        "password",
        "DB_PASSWORD",
        "clientSecret",
        "x-api-key",
        "refresh_token",
        "AWSAccessKey",
        "Authorization",
        "privateKey",
    ):
        assert is_sensitive_key(key), key
    for key in ("title", "priority", "author", "max_tokens", "tokenizer", "keyboard", "pinned"):
        assert not is_sensitive_key(key), key
