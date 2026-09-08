"""Item 7 (8 Sep 2026): a customer-only order ask cannot use the by-product tool.

Measured on turns 3a56a48c, 0c171511, 8d69aa55, 11932963, 1cd826a0 ("delivery to hanlim"):
all 15 HANLIM TRADING customers resolved and were passed as `customer_ids`, but the pick was
`crm_order_management_orders_by_product_list` (0.485 vs the orders list's 0.466-0.473) with
`has_product: false`. That route REQUIRES a product narrower (`orders.py`
`has_product_narrower`) and answers an empty page without one, so a customer with 120+
orders was told "no order matched these".

The rule lives in `services.py` beside the F4 collapse (the CRM-policy seam) and is applied
in the lane between `select_tool` and `tool_filter`, so `tool_filter` stays the ported node.
"""
from __future__ import annotations

from app.services.chatbot.lanes.business import fetch
from app.services.chatbot.lanes.business.services import drop_by_product_without_product

_BY_PRODUCT = "crm_order_management_orders_by_product_list"
_ORDERS = "crm_order_management_orders_list"
_PO = "crm_procurement_po_placed_list"


def _hanlim_candidates() -> list[dict]:
    """Turn 1cd826a0's candidate pool, similarities verbatim."""
    return [
        {"name": _BY_PRODUCT, "similarity": 0.48480902363068923},
        {"name": _ORDERS, "similarity": 0.46613801910051644},
        {"name": _PO, "similarity": 0.3660272740687529},
    ]


def _pick(candidates, *, domain, has_product):
    kept, dropped = drop_by_product_without_product(candidates, domain=domain, has_product=has_product)
    pick = fetch.tool_filter(kept, has_product=has_product)
    tool_pick = pick.items[0]["json"]["_tool_pick"]
    if dropped:
        tool_pick["dropped_no_product"] = dropped
    return pick.items[0]["json"]["name"], tool_pick


class TestACustomerOnlyOrderAskPicksTheOrdersList:
    def test_the_3a56a48c_shape_picks_orders_list(self) -> None:
        name, tool_pick = _pick(_hanlim_candidates(), domain="order", has_product=False)
        assert name == _ORDERS
        assert tool_pick["dropped_no_product"] == [_BY_PRODUCT]
        assert [r["name"] for r in tool_pick["rejected"]] == [_PO]

    def test_a_product_only_ask_still_picks_by_product(self) -> None:
        name, tool_pick = _pick(_hanlim_candidates(), domain="order", has_product=True)
        assert name == _BY_PRODUCT
        assert "dropped_no_product" not in tool_pick

    def test_a_customer_plus_product_ask_is_unchanged(self) -> None:
        cands = [
            {"name": _ORDERS, "similarity": 0.4305},
            {"name": _BY_PRODUCT, "similarity": 0.3937},
            {"name": _PO, "similarity": 0.3622},
        ]
        name, tool_pick = _pick(cands, domain="order", has_product=True)
        assert name == _ORDERS
        assert [r["name"] for r in tool_pick["rejected"]] == [_BY_PRODUCT, _PO]
        assert "dropped_no_product" not in tool_pick


class TestEveryOtherPoolIsByteIdentical:
    def test_a_non_order_pool_is_untouched_even_without_a_product(self) -> None:
        cands = [{"name": "crm_incoming_stock_by_product", "similarity": 0.5}, {"name": _BY_PRODUCT, "similarity": 0.4}]
        kept, dropped = drop_by_product_without_product(cands, domain="incoming", has_product=False)
        assert kept is cands and dropped == []

    def test_an_unknown_has_product_leaves_the_pool_alone(self) -> None:
        cands = _hanlim_candidates()
        kept, dropped = drop_by_product_without_product(cands, domain="order", has_product=None)
        assert kept is cands and dropped == []

    def test_no_domain_leaves_the_pool_alone(self) -> None:
        cands = _hanlim_candidates()
        kept, dropped = drop_by_product_without_product(cands, domain=None, has_product=False)
        assert kept is cands and dropped == []

    def test_an_order_pool_with_only_the_by_product_tool_ends_not_found(self) -> None:
        """Dropping the one candidate is an OUTCOME (H11), not a crash: the lane's
        `not_found` arm answers it, which beats an empty page dressed as an answer."""
        kept, dropped = drop_by_product_without_product(
            [{"name": _BY_PRODUCT, "similarity": 0.5}], domain="order", has_product=False
        )
        assert kept == [] and dropped == [_BY_PRODUCT]
        assert fetch.tool_filter(kept, has_product=False).outcome == "not_found"
