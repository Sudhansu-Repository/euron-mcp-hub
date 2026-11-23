from __future__ import annotations

import uuid

from mcphub.models.enums import Effect
from mcphub.policy.engine import Rule, decide


def rule(pattern: str, effect: Effect) -> Rule:
    return Rule(pattern=pattern, effect=effect, id=uuid.uuid4())


def test_the_client_default_applies_when_no_rule_matches() -> None:
    assert decide([], Effect.DENY, "notes.create_note").allowed is False
    allow = decide([rule("tickets.*", Effect.DENY)], Effect.ALLOW, "notes.create_note")
    assert allow.allowed is True
    assert allow.rule is None
    assert "default" in allow.reason


def test_a_specific_deny_carves_an_exception_out_of_a_broad_allow() -> None:
    rules = [rule("tickets.*", Effect.ALLOW), rule("tickets.delete_ticket", Effect.DENY)]

    assert decide(rules, Effect.DENY, "tickets.create_ticket").allowed is True
    denied = decide(rules, Effect.DENY, "tickets.delete_ticket")
    assert denied.allowed is False
    assert denied.rule is not None
    assert denied.rule.pattern == "tickets.delete_ticket"
    assert "denies" in denied.reason


def test_a_specific_allow_opens_one_server_under_a_global_deny() -> None:
    rules = [rule("*", Effect.DENY), rule("notes.*", Effect.ALLOW)]

    assert decide(rules, Effect.ALLOW, "notes.search_notes").allowed is True
    assert decide(rules, Effect.ALLOW, "tickets.list_tickets").allowed is False


def test_the_longer_literal_wins_between_two_wildcards() -> None:
    rules = [rule("tickets.*", Effect.DENY), rule("tickets.get_*", Effect.ALLOW)]

    assert decide(rules, Effect.DENY, "tickets.get_ticket").allowed is True
    assert decide(rules, Effect.DENY, "tickets.update_status").allowed is False


def test_equally_specific_rules_resolve_to_deny_whatever_their_order() -> None:
    allow_first = [rule("tickets.get_*", Effect.ALLOW), rule("tickets.*_ticket", Effect.DENY)]
    deny_first = list(reversed(allow_first))

    for rules in (allow_first, deny_first):
        decision = decide(rules, Effect.ALLOW, "tickets.get_ticket")
        assert decision.allowed is False
        assert decision.rule is not None
        assert decision.rule.effect is Effect.DENY
