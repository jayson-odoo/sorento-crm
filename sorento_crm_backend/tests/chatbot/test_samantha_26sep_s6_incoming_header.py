"""Phase 2 RED tests - issue #1262 (Samantha case), slice 6, finding F6a.

Turn T6: "got eta" over carried products (memory, not a fresh product search) - the
resolver's product search runs against the leftover word "eta" and counts 0 against
the WRONG set, and the reply's header claims "0 products have incoming stock." right
above the real incoming rows.

`turn_runtime.envelope_of` already withholds `header_override` when `counted_set` is
False (AC-1316/AC-1317's own guard). The bug is that `lanes/business/fetch.py`'s
report builder BAKES the same header into `response`/`lane_text` unconditionally
(whenever `ctx["predicate"]` is present), and `turn/compose.py` prints `lane_text`
verbatim - so the withheld header still reaches the reply through the other carrier.

AC-S6-1: "got eta" over carried products (not a counted set) never shows a "N products
have incoming stock" header; the incoming rows still show.
AC-S6-2: a counted-set header never appears when `counted_set` is False, whichever
carrier held it (`header_override` or baked `response`).

Plan: PLAN-chatbot-samantha-slices-26sep.md, slice 6. UAC:
chatbot-samantha-slices-26sep-acceptance-criteria.md.
"""
from __future__ import annotations

from app.services.chatbot.turn.compose import compose
from app.services.chatbot.turn.policy import Policy
from app.services.chatbot.turn.state import Focus, Profile, State
from app.services.chatbot.turn_runtime import envelope_of
from app.services.chatbot.turn.plan import FetchSpec

from tests.chatbot._turn_helpers import TIER_ORDER_FIXTURE, _domain_row

_INCOMING_ROW_TEXT = (
    "1. *Company:* Mocha\n*Product Code:* M210-GM\n*Container:* SEGU4140083\n"
    "*ETA:* 2026-09-30\n*Incoming Quantity:* 200"
)


def _policy() -> Policy:
    row = _domain_row("incoming", narrowing={"product": "narrow_to_code"})
    return Policy.from_rows(domains=[row], kinds=[], tier_order=TIER_ORDER_FIXTURE)


def test_header_count_never_contradicts_the_rows_below_it():
    """AC-S6-2, at the seam `envelope_of` itself owns: `counted_set=False` must
    withhold the counted-set header from BOTH carriers a downstream reader might
    print - `header_override` (already correct) and the fetch's own baked
    `response`/`lane_text` (not correct: `fetch.py`'s report builder bakes
    "0 products have incoming stock." into `response` whenever a predicate rode on
    the ctx, with no `counted_set` check of its own).

    Red: `envelope["lane_text"]` still carries the baked header even though
    `header_override` was correctly withheld.
    """
    fragment = {
        "fetch": {
            "has_result": True,
            "answers": [{"fields": [{"label": "Product Code", "value": "M210-GM"}]}],
            "response": f"0 products have incoming stock.\n{_INCOMING_ROW_TEXT}",
            "set_header": "0 products have incoming stock.",
        }
    }
    spec = FetchSpec(domain="incoming", entities=[], filters={}, date_window=None)

    envelope = envelope_of(fragment, spec, entities=[], counted_set=False)

    assert envelope["header_override"] is None, "counted_set=False must withhold header_override"
    assert "have incoming stock" not in (envelope.get("lane_text") or ""), (
        f"the counted-set header survived on the OTHER carrier (lane_text): {envelope!r}"
    )


def test_t6_code_tier_incoming_answer_never_prints_the_counted_set_header():
    """AC-S6-1, at the reply text the customer actually reads: "got eta" over the
    carried products must show the ETA rows with no "N products have incoming stock"
    header, because the count was never over the products Samantha meant - it was
    over the leftover word "eta" searched against the whole catalogue (explainer
    section 4).

    Re-routed (26 Sep, coordinator round 4) through `turn_runtime.envelope_of` - the
    ONLY producer of `lane_text` in production - instead of a hand-built envelope
    dict that merely ASSERTED a `lane_text` value into existence. Same fragment
    shape `test_header_count_never_contradicts_the_rows_below_it` above already
    uses, carried one step further into `compose()` so this test grades the actual
    customer-facing text, not just the envelope.
    """
    fragment = {
        "fetch": {
            "has_result": True,
            "answers": [{"fields": [{"label": "Product Code", "value": "M210-GM"}]}],
            "response": f"0 products have incoming stock.\n{_INCOMING_ROW_TEXT}",
            "set_header": "0 products have incoming stock.",
        }
    }
    spec = FetchSpec(domain="incoming", entities=[], filters={}, date_window=None)

    envelope = envelope_of(fragment, spec, entities=[], counted_set=False)
    state = State(focus=Focus(), pending=None, profile=Profile(), turn_no=6)

    answer = compose([envelope], state, _policy(), ctx=None)

    assert "have incoming stock" not in answer.text, answer.text
    assert "M210-GM" in answer.text, "the real incoming row must still print"
