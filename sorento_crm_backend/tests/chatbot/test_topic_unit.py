"""The ONE definition of "the customer changed the subject" (owner ruling K, 2026-09-06).

Rules 1, 2 and 3 of the 6 Sep console pass all ask the same question - the tail before it
carries an offer roster forward, the head before it drops carried entities, the head
again before it reads a filter reply as a pick. Three copies of that answer is how the
roster, the entities and the pending offer end up disagreeing about what the conversation
is about, so there is one function and this is its truth table.

Pure; no database, no fixtures.
"""
from __future__ import annotations

import pytest

from app.services.chatbot import topic


@pytest.mark.parametrize(
    ("previous_domain", "new_domain", "new_offer", "expected", "why"),
    [
        ("order", "inventory", False, True, "a different named domain IS the change"),
        ("order", "order", False, False, "the same domain is one subject"),
        ("order", None, False, False, "a pick, a date window and a bare code all name no domain"),
        (None, "inventory", False, False, "a subject acquiring a name is not a new subject"),
        (None, None, False, False, "nothing named on either side"),
        ("order", "inventory", True, True, "a fresh offer wins whatever the domains say"),
        ("order", "order", True, True, "including within one domain: 'another promotion'"),
        (None, None, True, True, "and with no domain signal at all"),
    ],
)
def test_the_truth_table(
    previous_domain: str | None,
    new_domain: str | None,
    new_offer: bool,
    expected: bool,
    why: str,
) -> None:
    assert topic.changed(previous_domain, new_domain, new_offer=new_offer) is expected, why


def test_an_empty_string_is_not_a_domain() -> None:
    """`jsc.truthy`, not `is not None`: the wire carries "" for an absent domain as often
    as it carries null, and reading "" as a real domain makes every such turn a change."""
    assert topic.changed("order", "") is False
    assert topic.changed("", "order") is False
