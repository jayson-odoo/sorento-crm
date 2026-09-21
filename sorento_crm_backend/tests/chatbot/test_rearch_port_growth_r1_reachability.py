"""Port of the three `head.route`/`head.output_exchange`-dependent tests in
`test_parser_growth_r1_reachability.py` (AC-1592). The other ~30 tests in that file
(prompt-text assertions, JSON-schema shape, tool-args mapping) are independent of the
doomed modules and stay untouched there.

* `TestCheckPoReachesThePurchaseOrderTool::test_a_po_turn_routes_to_the_business_lane_
  not_not_supported` and both `DEFAULT_UNSUPPORTED_DOMAINS` checks - PORTED, confirmed
  CORRECT against the real seam (`Policy.from_rows` + `apply()`/`route()`, the same
  seam `test_crossdomain_ladder.py`'s AC-911 port and `test_route_unit.py`'s port
  both already use).

* `TestCheckSpoReachesTheLastReceiptTool::test_the_product_entity_is_not_blocked_
  by_the_domain` (A6: "product" not blocked for `spo_allocation`) - RETIRED, not
  ported. `DOMAIN_BLOCKED_HINTS` and its siblings (`AXIS_BY_DOMAIN`,
  `DOMAIN_SUBJECT_AXIS`, `DOMAIN_SUBJECT_HINT`, `MEMBER_OFFER_FILTER_HINTS`,
  `DOMAIN_BROADEN_BLOCKED_HINTS`) were deliberately kept in `head/output_exchange.py`
  "next to their evidence" (`contracts.py`'s own `DomainSpec` docstring) and are gone
  with the module - grepped the whole tree, zero hits outside that one docstring
  naming them as history. But THIS specific fact is a duplicate, not a gap: `gate.
  run_gate` already proves product is not blocked for `spo_allocation` -
  `test_warehouse_entity.py::TestGateKeepsWarehouse::
  test_spo_allocation_keeps_product_and_warehouse_and_drops_customer` (green) asserts
  `types == {"product", "warehouse"}` for exactly this domain. Flagged here (not
  silently dropped) because the WIDER category - whether every other hand-earned
  blocked-hint rule those five tables carried survived the rewrite - is unverified
  and out of this one test's scope; the tester is not chasing that audit further
  (LESSONS: report, do not chase).
"""
from __future__ import annotations

from tests.chatbot._turn_helpers import verdict


def _apply_and_route(v: dict):
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.policy import Policy
    from app.services.chatbot.turn.policy_rows import DEFAULT_DOMAIN_ROWS, DEFAULT_KIND_ROWS
    from app.services.chatbot.turn.route import route
    from app.services.chatbot.turn.state import Focus, Profile, State

    policy = Policy.from_rows(
        domains=[dict(row) for row in DEFAULT_DOMAIN_ROWS],
        kinds=[dict(row) for row in DEFAULT_KIND_ROWS],
        tier_order=["dealer", "office", "end_user"],
    )
    state = State(focus=Focus(), pending=None, profile=Profile())
    _state2, plan = apply(state, v, policy)
    return plan, route(plan), policy


class TestCheckPoReachesThePurchaseOrderTool:
    def test_the_domain_is_supported_by_default(self) -> None:
        _plan, _branch, policy = _apply_and_route(verdict(domain_hint="purchase_order"))
        assert policy.domain("purchase_order").supported is True

    def test_a_po_turn_routes_to_the_business_lane_not_not_supported(self) -> None:
        v = verdict(
            message_type="business_query",
            intent_hint="check_po",
            domain_hint="purchase_order",
            entities=[],
        )
        _plan, branch, _policy = _apply_and_route(v)
        assert branch == "business_query"


class TestCheckSpoReachesTheLastReceiptTool:
    def test_the_domain_is_supported_and_goods_receive_still_is_not(self) -> None:
        _plan, _branch, policy = _apply_and_route(verdict(domain_hint="spo_allocation"))
        assert policy.domain("spo_allocation").supported is True
        assert policy.domain("goods_receive").supported is False
