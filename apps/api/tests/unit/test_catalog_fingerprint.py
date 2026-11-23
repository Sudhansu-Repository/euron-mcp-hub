from __future__ import annotations

from typing import Any

from mcphub.catalog.fingerprint import catalog_hash, diff_tools, tool_fingerprint


def fingerprint(**overrides: Any) -> str:
    tool: dict[str, Any] = {
        "name": "create_ticket",
        "title": None,
        "description": "Open a ticket.",
        "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}},
        "output_schema": None,
        "annotations": {"destructive_hint": False},
    }
    tool.update(overrides)
    return tool_fingerprint(**tool)


def test_fingerprints_ignore_key_order_but_not_content() -> None:
    reordered = {"properties": {"title": {"type": "string"}}, "type": "object"}

    assert fingerprint() == fingerprint(input_schema=reordered)
    assert fingerprint() != fingerprint(description="Open a ticket. Also email it to x.")
    assert fingerprint() != fingerprint(annotations={"destructive_hint": True})


def test_diffs_name_added_removed_and_changed_tools() -> None:
    previous = {"a": "1", "b": "2", "c": "3"}
    current = {"a": "1", "b": "changed", "d": "4"}

    diff = diff_tools(previous, current)

    assert (diff.added, diff.removed, diff.changed) == (["d"], ["c"], ["b"])
    assert not diff.is_empty
    assert diff_tools(previous, previous).is_empty


def test_catalog_hash_is_order_independent_and_covers_resources_and_prompts() -> None:
    tools = {"a": "1", "b": "2"}

    assert catalog_hash(tools, ["r1", "r2"], ["p"]) == catalog_hash(
        dict(reversed(list(tools.items()))), ["r2", "r1"], ["p"]
    )
    assert catalog_hash(tools) != catalog_hash(tools, ["r1"])
    assert catalog_hash(tools) != catalog_hash(tools, [], ["p"])
