"""SPARE-PART-ORDER-REQUEST, route level, red-first (Phase 2).

Captain test list T1 (wire shape), T5 (403 by direct API call), T14 (visibility), T15 (row
attachments). UAC: documentation/plans/purchasing/spare-part-order-request-12nov-acceptance-criteria.md.

Real routes, real RBAC (slugs through real roles), Postgres only (`blank_session`), every
row seeded here. Routes are the brief's contract under `/api/v1/project-sales`:
`/spare-part-requests*`, `/order-inquiry-rows/{row_id}/attachments*`, and the existing
`/order-inquiry-headers` + `/order-inquiries` (worklist) reads. A red before implementation
is a 404/405 on a missing route, a missing body key, or ImportError on the service module.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    HEADERS,
    ROW_ATT,
    SPR,
    TINY_PNG,
    WORKLIST,
    body,
    create,
    dec,
    raised,
    reload,
    row_for,
    sent,
    staged,
    stub_storage,
    submitted,
    svc,
    world,
)

DETAIL_KEYS = (
    "id", "inquiry_no", "inquiry_type", "state", "currency", "needed_by", "default_location",
    "reason", "requested_by", "submitted_at", "approved_at", "approved_by", "reject_reason",
    "can_decide", "can_edit", "total", "lines",
)
LINE_KEYS = (
    "id", "product_id", "item_code", "description", "stock_location", "qty", "unit_price",
    "total", "requested_qty", "requested_unit_price", "state",
)


def _post_draft(w) -> dict:
    res = w.as_user(w.requester).post(SPR, json=body(w))
    assert res.status_code == 201, res.text
    return res.json()


# =============================================================================
# T1 (wire) - POST creates a draft, GET returns every contract key (R1, R2)
# =============================================================================


def test_T1_post_creates_a_draft_and_the_detail_carries_every_contract_key(staged):
    w = staged
    res = w.as_user(w.requester).post(SPR, json=body(w))
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["state"] == "draft"
    assert created["inquiry_type"] == "spare_part_request"
    assert created["inquiry_no"].startswith("OR-")  # owner hand test 13 Nov: own series

    res = w.as_user(w.requester).get(f"{SPR}/{created['id']}")
    assert res.status_code == 200, res.text
    detail = res.json()
    for key in DETAIL_KEYS:  # response_model silently drops an undeclared field
        assert key in detail, f"{key} missing from the detail"
    assert detail["currency"] == "MYR"
    assert detail["needed_by"] == "2026-12-15"
    assert detail["can_edit"] is True
    assert detail["can_decide"] is False
    assert len(detail["lines"]) == 2
    for item in detail["lines"]:
        for key in LINE_KEYS:
            assert key in item, f"line.{key} missing"
    by_product = {item["product_id"]: item for item in detail["lines"]}
    a = by_product[str(w.product_a.id)]
    assert a["item_code"] == w.product_a.product_code
    assert dec(a["total"]) == Decimal("250")  # 10 x 25.00, server-side
    assert dec(by_product[str(w.product_b.id)]["total"]) == Decimal("50")  # 4 x 12.50
    assert dec(detail["total"]) == Decimal("300")


def test_T1_post_with_a_bad_body_is_422(staged):
    w = staged
    res = w.as_user(w.requester).post(SPR, json={"currency": "MYR", "lines": [{"qty": "abc"}]})
    assert res.status_code == 422, res.text


def test_T1_post_without_the_create_slug_is_403(staged):
    w = staged
    res = w.as_user(w.buyer).post(SPR, json=body(w))
    assert res.status_code == 403, res.text


def test_T1_put_replaces_the_lines_of_a_draft(staged):
    w = staged
    created = _post_draft(w)
    new_body = body(w, reason="Only the seal", lines=[body(w)["lines"][0]])
    res = w.as_user(w.requester).put(f"{SPR}/{created['id']}", json=new_body)
    assert res.status_code == 200, res.text
    detail = w.as_user(w.requester).get(f"{SPR}/{created['id']}").json()
    assert detail["reason"] == "Only the seal"
    assert len(detail["lines"]) == 1


# =============================================================================
# T5 (API) - approve / reject / edit refused by direct call (A2)
# =============================================================================


def test_T5_api_approve_by_the_requester_or_a_non_member_is_403(staged):
    w = staged
    created = _post_draft(w)
    res = w.as_user(w.requester).post(f"{SPR}/{created['id']}/submit")
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "pending_approval"

    for who in (w.requester, w.outsider):
        res = w.as_user(who).post(f"{SPR}/{created['id']}/approve", json={})
        assert res.status_code == 403, res.text
        res = w.as_user(who).post(f"{SPR}/{created['id']}/reject", json={"reason": "No"})
        assert res.status_code == 403, res.text
        row_id = created["lines"][0]["id"]
        res = w.as_user(who).patch(f"{SPR}/{created['id']}/lines/{row_id}", json={"qty": "1"})
        assert res.status_code == 403, res.text

    detail = w.as_user(w.stage1.tier1).get(f"{SPR}/{created['id']}").json()
    assert detail["can_decide"] is True
    assert detail["state"] == "pending_approval"


def test_T5_api_the_stage_member_edits_and_approves(staged):
    w = staged
    created = _post_draft(w)
    w.as_user(w.requester).post(f"{SPR}/{created['id']}/submit")
    row_id = next(item["id"] for item in created["lines"] if item["product_id"] == str(w.product_a.id))

    res = w.as_user(w.stage1.tier1).patch(
        f"{SPR}/{created['id']}/lines/{row_id}", json={"qty": "7", "unit_price": "30"}
    )
    assert res.status_code == 200, res.text
    detail = w.as_user(w.stage1.tier1).get(f"{SPR}/{created['id']}").json()
    edited = next(item for item in detail["lines"] if item["id"] == row_id)
    assert dec(edited["qty"]) == 7 and dec(edited["unit_price"]) == 30
    assert dec(edited["requested_qty"]) == 10 and dec(edited["requested_unit_price"]) == 25
    assert dec(edited["total"]) == 210

    res = w.as_user(w.stage1.tier1).post(f"{SPR}/{created['id']}/approve", json={"note": "ok"})
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "raised"


def test_T5_api_reject_without_a_reason_is_422(staged):
    w = staged
    created = _post_draft(w)
    w.as_user(w.requester).post(f"{SPR}/{created['id']}/submit")
    res = w.as_user(w.stage1.tier1).post(f"{SPR}/{created['id']}/reject", json={})
    assert res.status_code == 422, res.text


# =============================================================================
# T14 - purchasing sees it only from Raised; SO inquiries unchanged (P1, P3, P6)
# =============================================================================


def _so_driven_header(w):
    from .test_oi_header_list import _header

    return _header(w.db, w.company_id)


def _list(w, user_id, **params):
    res = w.as_user(user_id).get(HEADERS, params={"state": "all", "limit": 100, **params})
    assert res.status_code == 200, res.text
    return {item["id"]: item for item in res.json()["data"]}


def test_T14_purchasing_lists_only_the_raised_spare_part_inquiry(staged):
    w = staged
    draft = create(w)
    pending = submitted(w)
    rejected = submitted(w)
    svc().reject(w.db, rejected, w.stage1.tier1, "Too dear")
    w.db.commit()
    done = raised(w)
    so_driven = _so_driven_header(w)["inquiry"]

    listed = _list(w, w.buyer)
    assert str(draft.id) not in listed
    assert str(pending.id) not in listed
    assert str(rejected.id) not in listed
    item = listed[str(done.id)]
    assert item["inquiry_type"] == "spare_part_request"
    assert item["project_sales_order_id"] is None
    assert listed[str(so_driven.id)]["inquiry_type"] == "sales_order"


def test_T14_the_type_filter_is_multi_value(staged):
    w = staged
    done = raised(w)
    so_driven = _so_driven_header(w)["inquiry"]

    only_spare = _list(w, w.buyer, inquiry_type=["spare_part_request"])
    assert str(done.id) in only_spare and str(so_driven.id) not in only_spare
    only_so = _list(w, w.buyer, inquiry_type=["sales_order"])
    assert str(so_driven.id) in only_so and str(done.id) not in only_so
    both = _list(w, w.buyer, inquiry_type=["sales_order", "spare_part_request"])
    assert {str(done.id), str(so_driven.id)} <= set(both)


def test_T14_the_header_detail_opens_a_raised_spare_part_inquiry(staged):
    w = staged
    done = raised(w)
    res = w.as_user(w.buyer).get(f"{HEADERS}/{done.id}")
    assert res.status_code == 200, res.text
    assert res.json()["project_sales_order_id"] is None


def test_T14_a_draft_is_hidden_from_a_user_with_no_relation(staged):
    w = staged
    draft = create(w)
    for who in (w.outsider, w.buyer):
        res = w.as_user(who).get(f"{SPR}/{draft.id}")
        assert res.status_code in (403, 404), res.text
        res = w.as_user(who).get(f"{HEADERS}/{draft.id}")
        assert res.status_code in (403, 404), res.text
    assert w.as_user(w.requester).get(f"{SPR}/{draft.id}").status_code == 200


def test_T14_the_worklist_returns_the_raised_rows_with_their_product(staged):
    w = staged
    done = raised(w)
    res = w.as_user(w.buyer).get(WORKLIST, params={"inquiry_id": str(done.id), "limit": 100})
    assert res.status_code == 200, res.text
    rows = res.json()["data"]
    assert {r["product_id"] for r in rows} == {str(w.product_a.id), str(w.product_b.id)}
    for r in rows:
        assert r["verb"] == "REPLENISH"


def test_T14_the_worklist_never_lists_a_pending_inquirys_rows(staged):
    w = staged
    pending = submitted(w)
    res = w.as_user(w.buyer).get(WORKLIST, params={"limit": 200})
    assert res.status_code == 200, res.text
    row_ids = {str(r.id) for r in [row_for(w.db, pending, w.product_a), row_for(w.db, pending, w.product_b)]}
    assert not row_ids & {r["id"] for r in res.json()["data"]}


# =============================================================================
# T15 - row photos: requester while draft, approver while pending, never purchasing (R4, A3)
# =============================================================================


@pytest.fixture
def photos(staged, monkeypatch):
    from app.models.resources import AttachmentType

    from ._forms_chain_support import uid

    stub_storage(monkeypatch)
    staged.db.add(
        AttachmentType(
            id=uid(), type_name="Sales Order Line Attachment", code="so_line_attachment",
            allowed_extensions="jpg,jpeg,png,webp,gif,pdf,xlsx,xls", max_file_size_mb=10,
        )
    )
    staged.db.commit()
    return staged


def _upload(w, user_id, row_id, name="seal.png"):
    return w.as_user(user_id).post(
        f"{ROW_ATT}/{row_id}/attachments", files=[("files", (name, TINY_PNG, "image/png"))]
    )


def test_T15_requester_uploads_while_draft(photos):
    w = photos
    draft = create(w)
    row = row_for(w.db, draft, w.product_a)
    res = _upload(w, w.requester, row.id)
    assert res.status_code in (200, 201), res.text
    assert [f["filename"] for f in res.json()] == ["seal.png"]


def test_T15_purchasing_cannot_upload_while_pending(photos):
    w = photos
    pending = submitted(w)
    row = row_for(w.db, pending, w.product_a)
    res = _upload(w, w.buyer, row.id)
    assert res.status_code == 403, res.text


def test_T15_the_stage_approver_uploads_while_pending_and_the_lookup_returns_them(photos):
    w = photos
    pending = submitted(w)
    row = row_for(w.db, pending, w.product_a)
    res = _upload(w, w.stage1.tier1, row.id, name="worn.png")
    assert res.status_code in (200, 201), res.text

    res = w.as_user(w.stage1.tier1).post(f"{ROW_ATT}/attachments/lookup", json={"row_ids": [str(row.id)]})
    assert res.status_code == 200, res.text
    assert [f["filename"] for f in res.json()[str(row.id)]] == ["worn.png"]


def test_T15_the_requester_cannot_upload_once_pending(photos):
    w = photos
    pending = submitted(w)
    row = row_for(w.db, pending, w.product_a)
    res = _upload(w, w.requester, row.id)
    assert res.status_code == 403, res.text
    assert reload(w.db, pending).state == "pending_approval"
