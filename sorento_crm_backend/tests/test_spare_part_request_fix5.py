"""SPARE-PART-ORDER-REQUEST fix round 5 (browser pass 2), red-first (Phase 2). Backend half.

D1 A create-only requester's grids load: the calls the OI list and the Lines tab make beside the
   data call answer 200 for a create-slug holder, scoped to their own spare part inquiries:
   column-config GET / PUT for the three OI listing keys, the worklist summary (counts only their
   own), the reserve status summary, and the inquiry's reserve-requests read.
   NOTE: the lead allowed "or the FE does not call reserve-requests for a spare_part_request
   header"; if the coder takes that route, `test_D1_reserve_requests_*` is the one to drop (the
   FE half pins that the Lines tab leaves its loading state either way).
D2 GET /inventory/stock-status (useStockStatus, the line stock expand) answers a create-slug
   holder with quantities only: no sales-order number, customer name or supplier (the C1 rule
   for stock-detail), no cost; a projects.projects.view holder keeps the full payload; a user
   with no grant still 403.
D3 Lines come back in the order entered (create AND a reordering edit), on the detail and on
   the Lines (worklist) read. Six lines, so an incidental order matches by chance 1 in 720.
D5 The OI header detail carries the request total for this type (requester after submit).
D6 History: the approver's price change reads in the shared money format with 2 decimals
   ("35.00 -> 32.00", "RM 35.00 -> RM 32.00" accepted), and the final approval writes ONE raise
   entry (never "Raised to purchasing" + "Raised" at the same moment).

Postgres only (`blank_session`); every row seeded here.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal

import pytest

from ._forms_chain_support import uid, user
from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    CREATE,
    HEADERS,
    SPR,
    WORKLIST,
    approve,
    body,
    create,
    dec,
    line,
    make_product,
    raised,
    reload,
    role_grant,
    row_for,
    rows_of,
    sent,
    staged,
    submitted,
    svc,
    world,
)

BASE = "/api/v1/project-sales"
LISTING_KEYS = (
    "projects.projects.view::order-inquiry-headers",
    "projects.projects.view::order-inquiry-lines",
    "projects.projects.view::order-inquiry-worklist",
)
STOCK_STATUS = "/api/v1/inventory/stock-status"


# =============================================================================
# D1 - the side calls of the list and the Lines tab
# =============================================================================


@pytest.mark.parametrize("key", LISTING_KEYS)
def test_D1_column_config_reads_and_saves_for_a_create_only_requester(staged, key):
    w = staged
    res = w.as_user(w.requester).get(f"/api/v1/list-query/column-config/{key}")
    assert res.status_code == 200, res.text
    res = w.as_user(w.requester).put(
        f"/api/v1/list-query/column-config/{key}", json={"columns": [{"id": "inquiry_no", "visible": True}]}
    )
    assert res.status_code == 200, res.text


def _other_requesters_request(w):
    other = user(w.db, "spr second requester")
    role_grant(w.db, other, CREATE)
    w.db.commit()
    inquiry = svc().create(w.db, body(w), other)
    w.db.commit()
    svc().submit(w.db, reload(w.db, inquiry), other)
    w.db.commit()
    return approve(w, reload(w.db, inquiry), w.stage1.tier1)


def test_D1_the_worklist_summary_answers_and_counts_only_their_own(staged):
    from .test_oi_header_list import _header

    w = staged
    mine = raised(w)  # 2 rows
    _other_requesters_request(w)  # 2 rows, not theirs
    _header(w.db, w.company_id)  # a sales-order inquiry, not theirs
    res = w.as_user(w.requester).get(f"{BASE}/order-inquiries/summary")
    assert res.status_code == 200, res.text
    assert res.json()["total_rows"] == 2
    listed = w.as_user(w.requester).get(WORKLIST, params={"limit": 100})
    assert listed.status_code == 200, listed.text
    assert {r["order_inquiry_id"] for r in listed.json()["data"]} == {str(mine.id)}


def test_D1_the_reserve_status_summary_answers(staged):
    w = staged
    raised(w)
    res = w.as_user(w.requester).get(f"{BASE}/order-inquiries/reserve-status/summary")
    assert res.status_code == 200, res.text


def test_D1_reserve_requests_of_their_own_request_answer(staged):
    w = staged
    for inquiry in (create(w), raised(w)):
        res = w.as_user(w.requester).get(f"{BASE}/order-inquiries/{inquiry.id}/reserve-requests")
        assert res.status_code == 200, res.text


# =============================================================================
# D2 - /inventory/stock-status for the line stock expand
# =============================================================================


@pytest.fixture
def stock_world(staged):
    from app.models.order import Customer, SalesOrder, SalesOrderLine

    w = staged
    customer = Customer(
        id=uid(), company_id=w.company_id, customer_code=f"ZZT-C{uid()[:8]}",
        customer_name="ZZT Hidden Status Customer",
    )
    w.db.add(customer)
    w.db.flush()
    so = SalesOrder(
        id=uid(), company_id=w.company_id, so_number=f"ZZTSS{uid()[:8]}".upper(),
        customer_id=customer.id, status="open", demand_class="project",
        debtor_code=customer.customer_code, debtor_name=customer.customer_name,
    )
    w.db.add(so)
    w.db.flush()
    w.db.add(
        SalesOrderLine(
            id=uid(), company_id=w.company_id, sales_order_id=so.id, product_id=w.product_a.id,
            warehouse_id=w.loc_a.id, qty_ordered=Decimal("7"), qty_delivered=Decimal("0"),
            line_status="open",
        )
    )
    w.db.commit()
    w.so_number, w.customer_name = so.so_number, customer.customer_name
    return w


def _status(w, user_id):
    return w.as_user(user_id).get(STOCK_STATUS, params={"product_id": str(w.product_a.id)})


def test_D2_control_a_projects_viewer_gets_the_full_stock_status(stock_world):
    w = stock_world
    res = _status(w, w.outsider)
    assert res.status_code == 200, res.text
    assert w.so_number in res.text and w.customer_name in res.text


def test_D2_a_create_slug_holder_gets_quantities_only(stock_world):
    w = stock_world
    res = _status(w, w.requester)
    assert res.status_code == 200, res.text
    text = res.text
    assert w.so_number not in text, "no sales order number"
    assert w.customer_name not in text, "no customer name"
    costs = [m for m in re.finditer(r'"([a-z_]*cost[a-z_]*)":\s*("[^"]+"|[1-9][0-9.]*)', text)]
    assert costs == [], [m.group(0) for m in costs]
    assert "7" in text, "the SO quantity at the location is still there"


def test_D2_a_user_with_no_grant_is_still_refused(stock_world):
    w = stock_world
    nobody = user(w.db, "spr stock no grant")
    w.db.commit()
    assert _status(w, nobody).status_code == 403


# =============================================================================
# D3 - line order is kept
# =============================================================================


def _six_lines(w):
    names = ["zulu seal", "yankee hinge", "xray gasket", "whisky bolt", "victor nut", "uniform pin"]
    products = [make_product(w.db, n) for n in names]
    w.db.commit()
    return products


def _detail_order(w, inquiry) -> list:
    res = w.as_user(w.requester).get(f"{SPR}/{inquiry.id}")
    assert res.status_code == 200, res.text
    return [item["product_id"] for item in res.json()["lines"]]


def _worklist_order(w, inquiry) -> list:
    res = w.as_user(w.requester).get(WORKLIST, params={"inquiry_id": str(inquiry.id), "limit": 100})
    assert res.status_code == 200, res.text
    return [r["product_id"] for r in res.json()["data"]]


def test_D3_lines_come_back_in_the_order_entered(staged):
    w = staged
    products = _six_lines(w)
    entered = [str(p.id) for p in products]
    inquiry = create(
        w,
        lines=[line(p, w.loc_a, qty=str(10 - i), unit_price=str(5 + i)) for i, p in enumerate(products)],
    )
    assert _detail_order(w, inquiry) == entered
    assert _worklist_order(w, inquiry) == entered


def test_D3_a_reordering_edit_is_kept(staged):
    w = staged
    products = _six_lines(w)
    inquiry = create(w, lines=[line(p, w.loc_a, qty="2", unit_price="1") for p in products])
    ids = {str(r.product_id): str(r.id) for r in rows_of(w.db, inquiry)}
    reordered = list(reversed(products))
    svc().update(
        w.db, inquiry,
        body(w, lines=[{**line(p, w.loc_a, qty="2", unit_price="1"), "id": ids[str(p.id)]} for p in reordered]),
        w.requester,
    )
    w.db.commit()
    assert _detail_order(w, inquiry) == [str(p.id) for p in reordered]


# =============================================================================
# D5 - the request total on the OI page
# =============================================================================


def test_D5_the_header_detail_carries_the_request_total(staged):
    w = staged
    inquiry = submitted(w)  # 10 x 25.00 + 4 x 12.50
    res = w.as_user(w.requester).get(f"{HEADERS}/{inquiry.id}")
    assert res.status_code == 200, res.text
    assert "total" in res.json(), "the header detail names the request total"
    assert dec(res.json()["total"]) == Decimal("300")


# =============================================================================
# D6 - History: 2-decimal prices, one raise entry
# =============================================================================


def _history(w, inquiry) -> list:
    res = w.as_user(w.admin).get(f"{HEADERS}/{inquiry.id}/history")
    assert res.status_code == 200, res.text
    data = res.json()
    return data.get("events", data) if isinstance(data, dict) else data


def test_D6_a_price_change_reads_with_two_decimals(staged):
    w = staged
    inquiry = submitted(w)
    row = row_for(w.db, inquiry, w.product_a)
    svc().edit_line(w.db, inquiry, row.id, w.stage1.tier1, unit_price="32")
    w.db.commit()
    text = json.dumps(_history(w, inquiry), ensure_ascii=False)
    assert re.search(r"(RM )?25\.00\s*(->|→|to)\s*(RM )?32\.00", text), "price old -> new with 2 decimals"
    assert not re.search(r"\b25\s*(->|→|to)\s*32\b", text)


def test_D6_the_final_approval_writes_one_raise_entry(staged):
    w = staged
    inquiry = raised(w)
    events = _history(w, inquiry)
    raises = [e for e in events if re.search(r"\braised\b", f"{e.get('kind')} {e.get('title')}", re.I)]
    approvals = [e for e in events if re.search(r"\bapproved\b", f"{e.get('kind')} {e.get('title')}", re.I)]
    assert len(raises) <= 1, [(e.get("kind"), e.get("title")) for e in raises]
    assert len(approvals) <= 1, [(e.get("kind"), e.get("title")) for e in approvals]
    assert raises or approvals, "the approval is on History"
