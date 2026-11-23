from __future__ import annotations

import pytest

from mcphub.policy.naming import canonical, qualify, split


@pytest.mark.parametrize("separator", [".", "__"])
def test_names_round_trip_with_either_separator(separator: str) -> None:
    for tool in ("create_ticket", "v2.search", "get__raw", "x"):
        name = qualify("tickets", tool, separator)
        assert split(name, separator) == ("tickets", tool)


def test_the_first_separator_is_the_boundary() -> None:
    assert split("notes.search.v2") == ("notes", "search.v2")
    assert split("notes__get__raw", "__") == ("notes", "get__raw")
    assert canonical("notes", "search") == "notes.search"


@pytest.mark.parametrize("name", ["", "notes", "notes.", ".search", "Notes.search", "no_tes.x"])
def test_names_without_a_valid_namespace_are_rejected(name: str) -> None:
    assert split(name) is None
