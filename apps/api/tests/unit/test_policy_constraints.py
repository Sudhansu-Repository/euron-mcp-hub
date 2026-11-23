from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from mcphub.policy.constraints import check, lookup, parse_constraints


def violations(raw: list[dict[str, Any]], arguments: dict[str, Any]) -> list[str]:
    return [v.message for v in check(parse_constraints(raw), arguments)]


def test_equals_pins_a_value_and_requires_it() -> None:
    raw = [{"argument": "project", "rule": "equals", "value": "OPS"}]

    assert violations(raw, {"project": "OPS"}) == []
    assert violations(raw, {"project": "HR"}) == ["`project` must be 'OPS' (got 'HR')."]
    assert violations(raw, {}) == ["`project` is required and must be 'OPS'."]


def test_one_of_lists_the_allowed_values() -> None:
    raw = [{"argument": "priority", "rule": "one_of", "values": ["low", "normal", "high"]}]

    assert violations(raw, {"priority": "high"}) == []
    assert violations(raw, {}) == []
    (message,) = violations(raw, {"priority": "urgent"})
    assert "'low', 'normal', 'high'" in message
    assert "'urgent'" in message


def test_pattern_must_match_the_whole_string() -> None:
    raw = [{"argument": "path", "rule": "pattern", "value": r"/public/[a-z0-9/_-]+"}]

    assert violations(raw, {"path": "/public/docs/readme"}) == []
    assert violations(raw, {"path": "/private/keys"}) != []
    assert violations(raw, {"path": "/public/ok/../../etc"}) != []
    assert violations(raw, {"path": 42}) != []


def test_max_length_applies_to_strings_lists_and_objects() -> None:
    raw = [{"argument": "title", "rule": "max_length", "value": 5}]

    assert violations(raw, {"title": "short"}) == []
    assert violations(raw, {"title": "too long"}) == ["`title` must be at most 5 long (got 8)."]
    assert violations(raw, {"title": [1, 2, 3, 4, 5, 6]}) != []


def test_range_checks_numbers_and_refuses_booleans() -> None:
    raw = [{"argument": "amount", "rule": "range", "min": 0, "max": 100}]

    assert violations(raw, {"amount": 100}) == []
    assert violations(raw, {"amount": 100.5}) == ["`amount` must be at most 100 (got 100.5)."]
    assert violations(raw, {"amount": -1}) == ["`amount` must be at least 0 (got -1)."]
    assert violations(raw, {"amount": True}) == ["`amount` must be a number (got True)."]


def test_forbidden_arguments_must_be_absent() -> None:
    raw = [{"argument": "assignee", "rule": "forbidden"}]

    assert violations(raw, {"title": "x"}) == []
    assert violations(raw, {"assignee": None}) == ["`assignee` may not be set by this client."]


def test_paths_reach_into_nested_objects() -> None:
    raw = [{"argument": "filters.status", "rule": "one_of", "values": ["open"]}]
    arguments = {"filters": {"status": "closed"}}

    assert lookup(arguments, "filters.status") == "closed"
    assert violations(raw, arguments) == ["`filters.status` must be one of 'open' (got 'closed')."]
    assert violations(raw, {"filters": "not an object"}) == []


def test_every_violation_is_reported_not_just_the_first() -> None:
    raw: list[dict[str, Any]] = [
        {"argument": "priority", "rule": "one_of", "values": ["low"]},
        {"argument": "title", "rule": "max_length", "value": 3},
    ]

    assert len(violations(raw, {"priority": "high", "title": "longer"})) == 2


@pytest.mark.parametrize(
    "raw",
    [
        {"argument": "a", "rule": "pattern", "value": "(unclosed"},
        {"argument": "a", "rule": "range"},
        {"argument": "a", "rule": "range", "min": 5, "max": 1},
        {"argument": "a b", "rule": "forbidden"},
        {"argument": "a", "rule": "one_of", "values": []},
        {"argument": "a", "rule": "teleport"},
        {"argument": "a", "rule": "forbidden", "extra": True},
    ],
)
def test_malformed_constraints_are_refused_when_saved(raw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        parse_constraints([raw])
