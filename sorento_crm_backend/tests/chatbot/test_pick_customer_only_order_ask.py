"""Item 7 (8 Sep 2026): a customer-only order ask cannot use the by-product tool.

Measured on turns 3a56a48c, 0c171511, 8d69aa55, 11932963, 1cd826a0 ("delivery to hanlim"):
all 15 HANLIM TRADING customers resolved and were passed as `customer_ids`, but the pick was
`crm_order_management_orders_by_product_list` (0.485 vs the orders list's 0.466-0.473) with
`has_product: false`. That route REQUIRES a product narrower (`orders.py`
`has_product_narrower`) and answers an empty page without one, so a customer with 120+
orders was told "no order matched these".

The fix was a policy seam that dropped the by-product tool from the candidate pool when no
product resolved. That seam is GONE, and so is the pool: since the tool RAG was dropped the
`order` domain calls `DOMAIN_SPEC["order"].tools[0]`, which is the orders list, on every
turn - product or no product. This file is the assertion that item 7's failure cannot come
back through a different door: a by-product pick is now impossible rather than filtered.
"""
from __future__ import annotations

from app.services.chatbot.contracts import DOMAIN_SPEC
from app.services.chatbot.lanes.business import fetch

_BY_PRODUCT = "crm_order_management_orders_by_product_list"
_ORDERS = "crm_order_management_orders_list"


class TestAnOrderAskAlwaysPicksTheOrdersList:
    def test_the_3a56a48c_shape_picks_orders_list(self) -> None:
        """The turn that reported "no order matched these" for 120+ orders."""
        assert fetch.select_tool("order") == [{"name": _ORDERS, "similarity": 1.0}]

    def test_the_pick_does_not_depend_on_a_resolved_product(self) -> None:
        """`has_product` reached the old seam as the reason to drop a candidate. It now
        only rides along on the trace: the same tool is picked either way."""
        for has_product in (True, False, None):
            pick = fetch.tool_filter(fetch.select_tool("order"), has_product=has_product)
            item = pick.items[0]["json"]
            assert item["name"] == _ORDERS
            assert item["_tool_pick"]["has_product"] is has_product
            assert item["_tool_pick"]["rejected"] == []

    def test_the_by_product_tool_is_not_a_candidate_for_any_domain(self) -> None:
        """It stays in `DOMAIN_SPEC["order"].tools` as an allow-list member (the probes
        may name it), but it is never `tools[0]`, so nothing can select it."""
        assert _BY_PRODUCT in DOMAIN_SPEC["order"].tools
        assert _BY_PRODUCT not in {
            spec.tools[0] for spec in DOMAIN_SPEC.values() if spec.tools
        }
