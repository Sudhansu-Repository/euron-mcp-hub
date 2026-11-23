from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mcphub.policy.patterns import matches, specificity, validate_pattern


@pytest.mark.parametrize(
    "pattern",
    ["*", "tickets.*", "tickets.create_ticket", "tick*.get_?", "notes.Search.v2", "a.b-c_d"],
)
def test_valid_patterns_are_accepted(pattern: str) -> None:
    assert validate_pattern(f"  {pattern} ") == pattern


@pytest.mark.parametrize(
    "pattern", ["", "   ", "tickets", "Tickets.list", "tickets.[ab]", "a b.c", "tickets.", ".x"]
)
def test_invalid_patterns_are_refused_with_a_reason(pattern: str) -> None:
    with pytest.raises(ValueError, match=r"pattern|<server>"):
        validate_pattern(pattern)


@pytest.mark.parametrize(
    ("pattern", "name", "expected"),
    [
        ("*", "tickets.create_ticket", True),
        ("tickets.*", "tickets.create_ticket", True),
        ("tickets.*", "notes.create_note", False),
        ("tickets.create_ticket", "tickets.create_ticket", True),
        ("tickets.create_ticket", "tickets.create_tickets", False),
        ("tickets.get_?", "tickets.get_1", True),
        ("tickets.get_?", "tickets.get_12", False),
        ("*.delete_*", "notes.delete_note", True),
        ("*.delete_*", "notes.update_note", False),
    ],
)
def test_matching_uses_shell_wildcards_on_the_whole_name(
    pattern: str, name: str, expected: bool
) -> None:
    assert matches(pattern, name) is expected


def test_exact_names_outrank_wildcards_and_longer_literals_outrank_shorter() -> None:
    ordered = ["tickets.delete_ticket", "tickets.delete_*", "tickets.*", "*.delete_*", "*"]
    assert sorted(ordered, key=specificity, reverse=True) == ordered


names = st.from_regex(r"[a-z][a-z0-9-]{0,10}\.[a-z_]{1,15}", fullmatch=True)


@given(name=names, cut=st.integers(min_value=0, max_value=30))
def test_an_exact_name_always_beats_any_wildcard_matching_it(name: str, cut: int) -> None:
    wildcard = name[: min(cut, len(name))] + "*"
    assert matches(wildcard, name)
    assert specificity(name) > specificity(wildcard)
