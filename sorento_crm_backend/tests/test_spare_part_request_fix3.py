"""SPARE-PART-ORDER-REQUEST fix round 3 (browser pass), red-first (Phase 2).

B1 A requester holding ONLY `procurement.spare_part_requests.create` (no projects.projects.view /
   view_own) reads their own spare part inquiries: the Order Inquiries list filtered to the type,
   the OI page's header detail and its Lines (worklist) all answer 200.
B2 A user with `projects.projects.view_own` + the create slug can create and work their request:
   the project-sales own-scope guard (`app/api/v1/projects/_own_scope.py`) must not refuse the
   `/spare-part-requests*` routes ("Not available with access to your own records only").
B3 The line stock panel (`OrderInquiryStockGrid` -> GET /fulfilment-planning/stock-detail) answers
   200 for a create-slug holder (stock quantities only; no cost value), and still refuses a user
   with no grant at all.

Postgres only (`blank_session`); every row seeded here.
"""
from __future__ import annotations

import pytest

from ._forms_chain_support import user
from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    CREATE,
    HEADERS,
    SPR,
    WORKLIST,
    body,
    create,
    raised,
    role_grant,
    sent,
    staged,
    world,
)

VIEW_OWN = "projects.projects.view_own"
STOCK_DETAIL = "/api/v1/project-sales/fulfilment-planning/stock-detail"


# =============================================================================
# B1 - a create-only requester reads their own spare part inquiries
# =============================================================================


def test_B1_the_create_only_requester_lists_their_own_spare_part_inquiries(staged):
    w = staged
    draft = create(w)
    done = raised(w)
    res = w.as_user(w.requester).get(
        HEADERS, params={"state": "all", "limit": 100, "inquiry_type": ["spare_part_request"]}
    )
    assert res.status_code == 200, res.text
    listed = {item["id"] for item in res.json()["data"]}
    assert {str(draft.id), str(done.id)} <= listed


def test_B1_the_create_only_requester_opens_their_oi_page_header_and_lines(staged):
    w = staged
    for inquiry in (create(w), raised(w)):
        res = w.as_user(w.requester).get(f"{HEADERS}/{inquiry.id}")
        assert res.status_code == 200, res.text
        assert res.json()["inquiry_type"] == "spare_part_request"
        res = w.as_user(w.requester).get(WORKLIST, params={"inquiry_id": str(inquiry.id), "limit": 100})
        assert res.status_code == 200, res.text
        assert len(res.json()["data"]) == 2


def test_B1_the_create_only_requester_still_cannot_read_a_sales_order_inquiry(staged):
    from .test_oi_header_list import _header

    w = staged
    so_inquiry = _header(w.db, w.company_id)["inquiry"]
    res = w.as_user(w.requester).get(f"{HEADERS}/{so_inquiry.id}")
    assert res.status_code in (403, 404), res.text
    res = w.as_user(w.requester).get(HEADERS, params={"state": "all", "limit": 100})
    if res.status_code == 200:
        assert str(so_inquiry.id) not in {item["id"] for item in res.json()["data"]}


# =============================================================================
# B2 - view_own + create may create and work a spare part request
# =============================================================================


@pytest.fixture
def own_user(staged):
    uid_ = user(staged.db, "spr own-scope requester")
    role_grant(staged.db, uid_, VIEW_OWN, CREATE)
    staged.db.commit()
    return uid_


def test_B2_a_view_own_holder_with_the_create_slug_creates_and_submits(staged, own_user):
    w = staged
    res = w.as_user(own_user).post(SPR, json=body(w))
    assert res.status_code == 201, res.text
    spr_id = res.json()["id"]
    assert w.as_user(own_user).get(f"{SPR}/{spr_id}").status_code == 200
    res = w.as_user(own_user).put(f"{SPR}/{spr_id}", json=body(w, reason="Only the seal"))
    assert res.status_code == 200, res.text
    res = w.as_user(own_user).post(f"{SPR}/{spr_id}/submit")
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "pending_approval"


def test_B2_the_own_scope_guard_opens_every_spare_part_request_route():
    from app.api.v1.projects import _own_scope
    from app.main import app

    routes = [
        (method, route.path_format)
        for route in app.routes
        if "/spare-part-requests" in getattr(route, "path_format", "")
        for method in getattr(route, "methods", ()) or ()
        if method not in ("HEAD", "OPTIONS")
    ]
    assert routes, "the spare part request routes are mounted"
    refused = [(m, p) for (m, p) in routes if _own_scope.classify(m, p) is None]
    assert refused == []


# =============================================================================
# B3 - the line stock panel answers for a create-slug holder
# =============================================================================


def _cost_values(value, path="") -> list:
    out = []
    if isinstance(value, dict):
        for key, item in value.items():
            if "cost" in key.lower() and item not in (None, "", 0, "0"):
                out.append(f"{path}.{key}")
            out += _cost_values(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            out += _cost_values(item, f"{path}[{index}]")
    return out


def test_B3_stock_detail_answers_a_create_slug_holder_without_cost(staged):
    w = staged
    res = w.as_user(w.requester).get(
        STOCK_DETAIL, params={"product_id": str(w.product_a.id), "warehouse_id": str(w.loc_a.id)}
    )
    assert res.status_code == 200, res.text
    assert _cost_values(res.json()) == []


def test_B3_stock_detail_still_refuses_a_user_with_no_grant(staged):
    w = staged
    nobody = user(w.db, "spr no grant")
    w.db.commit()
    res = w.as_user(nobody).get(
        STOCK_DETAIL, params={"product_id": str(w.product_a.id), "warehouse_id": str(w.loc_a.id)}
    )
    assert res.status_code == 403, res.text
