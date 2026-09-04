"""The unicode-dash normaliser, direct (AC-103).

**Engine-defect + coverage-gap found while kill-testing the replay suite (tester,
S0+S1 review).** The dash normaliser (search ``-- unicode dash normalize --`` in
``output_exchange.py``) lives inside ``suggest_follow_up``, not inside
``output_exchange``/``post_process`` where its own comment ("Runs on EVERY turn")
reads as if it belonged. ``engine.run_turn`` calls both in sequence
(``post_process`` then ``suggest_follow_up``) so the normaliser DOES run every real
turn - that part is fine. But the two functions are replayed against SEPARATE fixture
sets in ``test_replay.py`` (``output_exchange`` fixtures never call
``suggest_follow_up``, and vice versa), and neither the 3 vendored + full-corpus
``suggest-follow-up`` fixtures nor the 86 vendored + full-corpus ``output_exchange``
fixtures carry a dash character outside ASCII ``-`` in ``entities[].raw`` or
``entities[].canonical_code``. Short-circuiting the block to a no-op left
``test_replay.py`` fully green on both node's fixture sets (173 combined cases). The
block exists because of a real production incident (exec 12053189: "SRT332-GM"
carrying a U+2212 MINUS SIGN missed the resolver's exact match), so zero corpus
coverage of it is a real gap against AC-008's "5 real captures per branch" floor and
AC-103's explicit claim ("including... the unicode-dash normalisation") - flagged as a
follow-up to backfill a real n8n capture, not something this hand-written unit test
should paper over (AC-005/AC-008 reserve the fixture corpus itself for real captures).

This file exercises the exact two-call sequence ``engine.run_turn`` uses
(``post_process`` then ``suggest_follow_up``) so the property has SOME automated
guard in the meantime.
"""
from __future__ import annotations

import json

from app.services.chatbot.head.output_exchange import output_exchange, suggest_follow_up

# The two dashes exec 12053189's own incident and `jsc._DASHES`'s comment both name:
# U+2212 MINUS SIGN and U+2013 EN DASH - both in the normaliser's character class.
MINUS_SIGN = "−"  # U+2212
EN_DASH = "–"  # U+2013


def _parser_output(**overrides) -> dict:
    base = {
        "message_type": "business_query",
        "intent_hint": "check_product",
        "domain_hint": "master_products",
        "scope_intent": "specific",
        "is_affirmative": None,
        "user_goal": "checking a product",
        "access_levels": [],
        "date_mode": None,
        "date_filter_start": None,
        "date_filter_end": None,
        "match_mode": "and",
        "demand_qty": None,
        "entities": [],
        "entity_op": "replace_combine",
        "scope_exclusive": False,
        "requested_attributes": [],
        "contains_flyer": False,
        "reference_positions": [],
        "reference_target": None,
        "person_mention": None,
        "is_active": None,
        "order_status": None,
        "correction": False,
        "routing": {"suggested_team": None, "suggested_agent": None},
        "escalation": {"is_escalation_confirmation": False},
    }
    base.update(overrides)
    return base


def _run(entities: list[dict], *, previous_conversation_state: dict | None = None) -> list[dict]:
    """The real pipeline `engine.run_turn` follows: `post_process` then `suggest_follow_up`."""
    json_item = {"output": json.dumps(_parser_output(entities=entities))}
    parent_input = {
        "latest_user_message": f"price for {entities[0]['raw']}" if entities else "hi",
        "contact_id": "ZZT-dash-1",
        "previous_conversation_state": previous_conversation_state or {},
    }
    parsed = output_exchange(json_item, parent_input)
    parsed = suggest_follow_up(parsed, parent_input)
    return parsed["output"]["entities"]


class TestUnicodeDashNormalisation:
    def test_a_minus_sign_in_raw_becomes_ascii_hyphen(self) -> None:
        entities = _run([{"raw": f"SRT332{MINUS_SIGN}GM", "hint": "product", "current_message": True}])
        assert entities[0]["raw"] == "SRT332-GM"

    def test_an_en_dash_in_canonical_code_becomes_ascii_hyphen(self) -> None:
        entities = _run(
            [
                {
                    "raw": f"SRT332{EN_DASH}GM",
                    "hint": "product",
                    "current_message": True,
                    "canonical_code": f"SRT332{EN_DASH}GM",
                }
            ]
        )
        assert entities[0]["raw"] == "SRT332-GM"
        assert entities[0]["canonical_code"] == "SRT332-GM"

    def test_an_ascii_hyphen_is_left_alone(self) -> None:
        entities = _run([{"raw": "SRT332-GM", "hint": "product", "current_message": True}])
        assert entities[0]["raw"] == "SRT332-GM"

    def test_runs_outside_the_suggest_offer_branch_too(self) -> None:
        """The comment is explicit: the normaliser runs on EVERY turn, not just a
        suggest_offer continuation - `selection_context` here is `disambiguation`, so
        the suggest_offer half of `suggest_follow_up` is inert (it only fires on
        `suggest_offer`) and only the dash block can be responsible for the change."""
        entities = _run(
            [{"raw": f"A{MINUS_SIGN}B", "hint": "product", "current_message": True}],
            previous_conversation_state={"selection_context": "disambiguation"},
        )
        assert entities[0]["raw"] == "A-B"

    def test_a_non_string_raw_is_left_alone_not_stringified(self) -> None:
        """`isinstance(..., str)` guards the substitution - a non-string raw is untouched."""
        entities = _run([{"raw": None, "hint": "product", "current_message": True}])
        assert entities[0]["raw"] is None
