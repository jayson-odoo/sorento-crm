"""Port of `test_route_unit.py` (AC-1592) onto the new seams.

`head/route.py` (`decide`, `route_turn`) no longer exists. Each of the old file's six
classes checked, in turn, and re-targeted or dropped:

* **`TestStockDenialGate`** (contract line 61, R1/H1) - PORTED below, against
  `engine.py::_stock_check_denied`/`_demand_qty_missing` (unchanged in shape from the
  seam `test_rearch_port_s6c...` already used for the same contract line). One
  assertion FLIPPED, not dropped: the old `test_on_a_missing_field_still_throws_
  exactly_as_live_does` proved live's own un-guarded `custom_fields.find(...).value`
  expression threw on a contact with no `is_allowed_stock` field. Probed the new
  function directly (confirmed this session): it does NOT throw - `jsc.get(row,
  "value")` on a `None` row returns `None`, and `None` is treated as "not explicitly
  allowed" (denied by default). Safer than the reproduction it replaces; the new test
  below asserts the safer behaviour instead of the old throw.

* **`TestIdeateNeverShadowedByHelpRequest`** (owner console defect C) - PORTED,
  confirmed correct: `turn/apply.py::_HELP_EXEMPT_DOMAINS = {"portal_link",
  "ideate"}` reproduces the fix exactly.

* **`TestLadderLaziness`** - RETIRED, not ported. Its "never reaches the throwing
  predicate" concern is moot now the predicate does not throw (see above). Its
  specific assertions also targeted domain-specific branch kinds
  (`branch == "check_promotion"`) the new `route()` no longer emits - `route()`
  returns one of 13 generic kinds and `business_query` covers every domain uniformly
  (`plan.domains` carries which); there is no equivalent domain-specific outcome to
  assert on.

* **`TestItemShape`** - RETIRED, not ported. Asserted `route_turn`'s n8n-shaped list
  output (`[{"json": {"branch_kind": ...}}]`, a "fan-in must not move" contract for a
  node graph). `turn/route.py::route(plan)` returns a plain string; there is no list-
  of-json-envelopes shape left to prove.

* **`TestTierRePick`**, **`TestOutOfRangeMemberPickReprompsInsteadOfLowSignal`** -
  RETIRED, not ported. Both matched a bare digit against a `tier_menu`/roster stored
  in raw session variables via Python text handling - the same class of mechanism
  `test_ascii_digit_semantics.py` also tested (AC-1592, that file's own retirement
  note applies here too): `turn/apply.py` is grep-guarded against `re.`/`.text`, and
  `_turn_helpers.PENDING_KINDS` includes `tier_pick` as one of the parser-driven
  structured pending kinds - the replacement lives in `test_rearch_s2_number_
  answers.py` (34 tests, green), not a text-matched tier menu.

* **`TestBroadenAllNeverReadAsLowSignal`**, **`TestAFilterModificationIsNeverLow
  Signal`** - PORTED below as RED findings, not retired. `turn/apply.py::_lane()`
  (grepped this session: no `scope_intent`, `broaden_axis` or
  `member_offer_filter_modification` reference anywhere in the file) returns
  `"casual"` for `message_type in {"casual", "unknown", "confirmation"}`
  unconditionally, before any of these three fields are consulted - reproducing
  BOTH owner console defects (item E, and pass 4 item E) the old ladder had already
  fixed. Confirmed empirically this session via direct `apply()` calls. Not the
  tester's fix to make.
"""
from __future__ import annotations

import pytest

from tests.chatbot._turn_helpers import build_policy, verdict


def _decide(v: dict, *, stock_denial_enabled: bool, custom_fields: list) -> str:
    """The real seam engine.py::run_turn calls (measured this session): contract
    58/61/62 short-circuit ROUTE from the contact's own record, ahead of `route()`."""
    from app.services.chatbot.contracts import Envelope
    from app.services.chatbot.engine import _demand_qty_missing, _stock_check_denied
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.route import route
    from app.services.chatbot.turn.state import Focus, Profile, State

    envelope = Envelope(
        contact={"id": "ZZT-1", "custom_fields": custom_fields},
        message={
            "event_type": "message.received",
            "contact": {"id": "ZZT-1"},
            "message": {
                "messageId": "m1",
                "contactId": "ZZT-1",
                "channelId": "whatsapp",
                "traffic": "incoming",
                "message": {"type": "text", "text": "x"},
            },
        },
    )
    if stock_denial_enabled and _stock_check_denied(envelope, v):
        return "demand_qty" if _demand_qty_missing(v) else "stock_denied"
    state = State(focus=Focus(), pending=None, profile=Profile())
    _state2, plan = apply(state, v, build_policy())
    return route(plan)


def _stock_verdict(**over) -> dict:
    return verdict(
        message_type="business_query",
        intent_hint="check_stock",
        domain_hint="inventory",
        entities=[{"raw": "SRTWC8517", "hint": "product", "current_message": True, "confident": True}],
        **over,
    )


class TestStockDenialGate:
    def test_off_by_default_the_lane_is_unreachable(self) -> None:
        branch = _decide(
            _stock_verdict(),
            stock_denial_enabled=False,
            custom_fields=[{"name": "is_allowed_stock", "value": "false"}],
        )
        assert branch == "business_query"

    def test_off_the_predicate_is_never_even_evaluated(self) -> None:
        branch = _decide(_stock_verdict(), stock_denial_enabled=False, custom_fields=[])
        assert branch == "business_query"

    def test_on_a_contact_without_stock_access_is_denied(self) -> None:
        branch = _decide(
            _stock_verdict(demand_qty=5),
            stock_denial_enabled=True,
            custom_fields=[{"name": "is_allowed_stock", "value": "false"}],
        )
        assert branch == "stock_denied"

    def test_on_a_missing_quantity_asks_for_one(self) -> None:
        branch = _decide(
            _stock_verdict(),
            stock_denial_enabled=True,
            custom_fields=[{"name": "is_allowed_stock", "value": "false"}],
        )
        assert branch == "demand_qty"

    def test_on_a_contact_WITH_stock_access_is_answered_normally(self) -> None:
        branch = _decide(
            _stock_verdict(),
            stock_denial_enabled=True,
            custom_fields=[{"name": "is_allowed_stock", "value": "true"}],
        )
        assert branch == "business_query"

    def test_on_a_missing_field_is_denied_not_thrown(self) -> None:
        """Was `test_on_a_missing_field_still_throws_exactly_as_live_does` - the new
        seam is guarded (`jsc.get` on a None row), so absence now reads as denied
        rather than raising. Safer, so the assertion flips instead of dropping."""
        branch = _decide(_stock_verdict(demand_qty=5), stock_denial_enabled=True, custom_fields=[])
        assert branch == "stock_denied"


class TestIdeateNeverShadowedByHelpRequest:
    def test_a_request_for_help_with_ideate_domain_hint_routes_to_ideate(self) -> None:
        v = verdict(message_type="request_for_help", domain_hint="ideate", intent_hint="submit_idea")
        branch = _decide(v, stock_denial_enabled=False, custom_fields=[])
        assert branch == "ideate", (
            "a domain_hint of 'ideate' must route to the ideate lane even when the "
            f"parser also stamped message_type request_for_help; got {branch!r}"
        )


class TestBroadenAllNeverReadAsLowSignal:
    def test_a_casual_broaden_all_reply_routes_to_clarify_menu_not_low_signal(self) -> None:
        v = verdict(message_type="casual", domain_hint=None, scope_intent="broaden")
        branch = _decide(v, stock_denial_enabled=False, custom_fields=[])
        assert branch == "clarify_menu", (
            "message_type casual + scope_intent broaden must route to clarify_menu, "
            f"not be swallowed by the casual shortcut; got {branch!r}. turn/apply.py::"
            "_lane() has no scope_intent/broaden_axis check at all (grepped this "
            "session) - owner console defect E's fix has no equivalent in the rearch."
        )


class TestAFilterModificationIsNeverLowSignal:
    def test_a_casual_message_with_an_open_business_domain_reaches_business_query(self) -> None:
        v = verdict(
            message_type="casual",
            intent_hint="check_order",
            domain_hint="order",
            entities=[{"raw": "hanlim", "hint": "customer", "current_message": True, "confident": True}],
        )
        branch = _decide(v, stock_denial_enabled=False, custom_fields=[])
        assert branch == "business_query", (
            "a turn narrowing a live business question (member_offer_filter_"
            "modification in the old ladder) must be answered, not swallowed by the "
            f"casual shortcut; got {branch!r}. turn/apply.py::_lane() has no "
            "member_offer_filter_modification check at all (grepped this session) - "
            "owner console pass 4 item E's fix has no equivalent in the rearch."
        )
