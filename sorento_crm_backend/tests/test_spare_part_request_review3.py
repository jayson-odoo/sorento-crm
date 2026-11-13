"""SPARE-PART-ORDER-REQUEST browser pass on 300a42e1, red-first.

Price visibility (crew ruling (b), PR body): the requester and the request's APPROVERS always see
unit price and total. An approver who has already approved is still the request's approver: after
the last approval their History must show the price change (old -> new), not "hidden", and the
detail must still carry the prices. A plain viewer without `products.cost.view` stays masked.
"""
from __future__ import annotations

from decimal import Decimal

from ._spare_part_request_support import HEADERS, SPR, dec  # noqa: F401
from .test_spare_part_request_cost import _price_change, costed, _line  # noqa: F401  (fixture)
from ._spare_part_request_support import sent, staged, world  # noqa: F401  (fixtures)


def test_R12_the_approver_still_sees_the_price_change_in_history_after_approving(costed):
    w = costed
    done = _price_change(w)
    res = w.as_user(w.stage1.tier1).get(f"{HEADERS}/{done.id}/history")
    assert res.status_code == 200, res.text
    assert "hidden" not in res.text, "an approver of record sees their own price change"
    assert "27.5" in res.text


def test_R12_the_approver_still_sees_prices_on_the_request_after_approving(costed):
    w = costed
    done = _price_change(w)
    res = w.as_user(w.stage1.tier1).get(f"{SPR}/{done.id}")
    assert res.status_code == 200, res.text
    line = _line(res.json()["lines"], w.product_a)
    assert dec(line["unit_price"]) == Decimal("27.5")


def test_R12_guard_a_viewer_without_cost_view_still_gets_hidden(costed):
    w = costed
    done = _price_change(w)
    res = w.as_user(w.viewer).get(f"{HEADERS}/{done.id}/history")
    assert res.status_code == 200, res.text
    assert "27.5" not in res.text and "hidden" in res.text
