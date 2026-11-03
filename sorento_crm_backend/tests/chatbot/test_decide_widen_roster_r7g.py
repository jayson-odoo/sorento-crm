"""Round 7g RED tests: `turn/decide.broadens_the_roster` / `picked_positions`.

Outside a report ask, "my ..." (`self_reference`) means the contact's own book, not the listed customers, so a
self_reference-only reply picks NO option of an open customer roster (as at ca34bc1e8a). With an asked report on the roster
payload, "my ..." and "overall" still widen to every customer (round 7f). "overall" (ranking_drill global) picks every option
in both. Pure unit tests over the pending and the verdict.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.turn import pending as P
from app.services.chatbot.turn.decide import picked_positions

OPTS = [
    {"position": 1, "label": "ZZT A SDN BHD", "entity_type": "customer", "payload": {}},
    {"position": 2, "label": "ZZT B SDN BHD", "entity_type": "customer", "payload": {}},
]
MY = {"self_reference": True, "order_status": "outstanding", "domain_hint": "order"}
OVERALL = {"ranking_drill": "global"}
ALL_CUSTOMERS = {"broaden_axis": "customer", "broaden_to": "all"}

NO_REPORT = [("outstanding", {"status": "outstanding"}), ("do_outstanding", {"status": "do_outstanding"}), ("no-status", {})]
REPORT = [
    ("sales_report", {"status": "sales_report"}),
    ("sales_analysis", {"status": "sales_analysis"}),
    ("sales_ranking", {"status": "sales_ranking", "ranking_ask": {"group_by": "product"}}),
]


def _pending(extra: dict):
    return P.ask("customer_pick", OPTS, payload={"domain": "order", **extra})


@pytest.mark.parametrize("name,extra", NO_REPORT, ids=[n for n, _ in NO_REPORT])
def test_g_a_my_alone_picks_nothing_on_a_roster_with_no_report_ask(name, extra) -> None:
    """(a) 'my orders' over an open customer roster outside a report ask: the contact's own book, no pick of every listed customer."""
    got = picked_positions(_pending(extra), dict(MY))
    assert got is None, f"7g (a, {name}): a self_reference-only reply picked {got}"


@pytest.mark.parametrize("name,extra", REPORT, ids=[n for n, _ in REPORT])
def test_g_b_my_still_widens_to_every_customer_with_an_asked_report(name, extra) -> None:
    """(b) the same roster WITH an asked report: 'my ...' still picks every customer (d6e stays green)."""
    got = picked_positions(_pending(extra), dict(MY))
    assert got is not None and got[0] == [1, 2], f"7g (b, {name}): want every option, got {got}"


@pytest.mark.parametrize("name,extra", NO_REPORT + REPORT, ids=[n for n, _ in NO_REPORT + REPORT])
@pytest.mark.parametrize("shape", [OVERALL, ALL_CUSTOMERS], ids=["overall", "all-customers"])
def test_g_c_overall_and_all_customers_pick_every_option_in_both(name, extra, shape) -> None:
    """(c) 'overall' (ranking_drill global) and 'all customers' pick every option, with or without a report ask (unchanged)."""
    got = picked_positions(_pending(extra), dict(shape))
    assert got is not None and got[0] == [1, 2], f"7g (c, {name}): want every option, got {got}"
