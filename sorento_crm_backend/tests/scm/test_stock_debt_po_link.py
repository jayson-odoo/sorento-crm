"""Stock Debt snapshot: link a PO line to an SO line through AutoCount (AC-LINK-CRM-UI).

Plan: `documentation/plans/autocount/PLAN-ac-link-crm-ui-04nov.md`. Gateway contract: SS PR #191
`documentation/plans/sprint-5/57-autocount-write-qtso-contract.md` (+ plan 55 relocate).

WRITTEN BEFORE THE IMPLEMENTATION (Phase 2, red first). The fake Shared Service is an
`httpx.MockTransport` on `foundryx_autocount_client.TRANSPORT`; every request it sees is kept in
`calls`, so a test asserts the exact gateway body the CRM sent.

Postgres only, every chain seeded here, everything rolled back.
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text

import tests.support.fake_foundryx as fake_foundryx
from tests.scm.conftest import SORENTO_COMPANY_ID, as_user, ensure_reference_data, requires_pg, seed_user
from tests.scm.test_stock_debt_routes import BASE, VIEW, _demand, _months_ahead, _product, _supplier, _u, _warehouse

pytestmark = requires_pg

LINK = "projects.stock_debt.link_po"
SNAP = f"{BASE}/snapshots"
FAKE_BASE_URL = "http://fake-ss.test"
DB = "AED_SRT"

ALL_ON = [
    {"op": "split_link", "kind": "purchase-orders", "enabled": True, "reasonCode": None},
    {"op": "link_row", "kind": "purchase-orders", "enabled": False, "reasonCode": "VENDOR_UNSUPPORTED"},
    {"op": "unlink_row", "kind": "purchase-orders", "enabled": False, "reasonCode": "VENDOR_UNSUPPORTED"},
    {"op": "relink_row", "kind": "purchase-orders", "enabled": False, "reasonCode": "VENDOR_UNSUPPORTED"},
    {"op": "delete_line", "kind": "sales-orders", "enabled": False, "reasonCode": "VENDOR_UNSUPPORTED"},
]


# --------------------------------------------------------------------------- fake SS


class FakeSS:
    """Answers by path; `answers[path]` is `(status, body)` or a callable(request) -> that."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.answers: dict = {
            "/api/v1/autocount/write-capabilities": (200, {"capabilities": ALL_ON}),
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        answer = self.answers.get(request.url.path)
        if answer is None:
            return httpx.Response(404, json={"code": "NOT_FOUND", "message": "no route"})
        if callable(answer):
            answer = answer(request)
        status, body = answer
        return httpx.Response(status, json=body)

    def bodies(self, path: str) -> list[dict]:
        return [json.loads(r.content) for r in self.calls if r.url.path == path]

    def headers(self, path: str) -> list:
        return [r.headers for r in self.calls if r.url.path == path]


@pytest.fixture
def fake_ss(monkeypatch):
    from app.services import foundryx_autocount_client as client_mod

    fake = FakeSS()
    monkeypatch.setattr(client_mod, "TRANSPORT", httpx.MockTransport(fake.handler), raising=False)
    return fake


# --------------------------------------------------------------------------- seeding


def _client(scm_app, permissions=(VIEW, LINK)):
    from fastapi.testclient import TestClient
    from app.models.user import UserRoleAssignment

    app, db, gcu, gcuak = scm_app
    ensure_reference_data(db)
    uid = seed_user(db, None)
    role_id = _u()
    db.execute(
        text(
            "INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, is_default, "
            "created_at) VALUES (:id, :slug, :name, false, false, false, now())"
        ),
        {"id": role_id, "slug": f"zzt-po-link-{role_id[:8]}", "name": f"ZZT po link {role_id[:8]}"},
    )
    for slug in permissions:
        pid = db.execute(text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}).scalar()
        assert pid, f"{slug} must be seeded"
        db.execute(
            text(
                "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
                "VALUES (:id, :r, :p, now())"
            ),
            {"id": _u(), "r": role_id, "p": pid},
        )
    db.add(UserRoleAssignment(user_id=uid, role_id=role_id))
    db.flush()
    as_user(app, gcu, gcuak, uid)
    fake_foundryx.seed_foundryx_connection(db, base_url=FAKE_BASE_URL, api_key="fxa_link_test")
    return TestClient(app), db


def _po_line(db, product, warehouse, *, qty, received=0, so_ref=None, doc_key=12008, dtl_key=None,
             po=None, issue=date(2026, 9, 1)):
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    if po is None:
        po = PurchaseOrder(
            id=_u(), po_number=f"ZZTPO{_u()[:6]}".upper(), supplier_id=_supplier(db, f"ZZTS{_u()[:5]}").id,
            issue_date=issue, status="active", company_id=SORENTO_COMPANY_ID,
            source_system="autocount", source_ref=f"{DB}:{doc_key}",
        )
        db.add(po)
        db.flush()
    line = PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, warehouse_id=warehouse.id,
        qty_ordered=Decimal(str(qty)), qty_received=Decimal(str(received)), line_status="open",
        company_id=SORENTO_COMPANY_ID, source_system="autocount",
        source_ref=f"{DB}:{doc_key}:{dtl_key or int(uuid.uuid4().int % 10**6)}",
        from_so_line_ref=so_ref,
    )
    db.add(line)
    db.flush()
    return po, line


def _world(scm_app, fake_ss):
    """One product, an SO line short 120 at MWH-ZZ, an open PO line of 500 at HQ-ZZ, a snapshot."""
    c, db = _client(scm_app)
    marker = f"ZZTPL{_u()[:5]}".upper()
    hq = _warehouse(db, f"HQ{marker[-4:]}")
    mwh = _warehouse(db, f"MW{marker[-4:]}")
    product = _product(db, f"{marker}-A")
    order, so_line = _demand(db, product, mwh, qty=120, required_date=_months_ahead(1), so_number=f"{marker}-SO")
    order.order_date = date(2026, 10, 20)
    order.source_system = "autocount"
    order.source_ref = f"{DB}:11988"
    so_line.source_system = "autocount"
    so_line.source_ref = f"{DB}:11988:11990"
    so_line.line_no = 140
    po, po_line = _po_line(db, product, hq, qty=500, received=0, doc_key=12008, dtl_key=12009)
    db.flush()
    resp = c.post(SNAP, json={"name": f"{marker} snap", "filters": {"query": marker, "only_debt": False}})
    assert resp.status_code == 201, resp.text
    sid = resp.json()["id"]
    rows = c.get(f"{SNAP}/{sid}/rows", params={"limit": 200}).json()["data"]
    row_id = next(r["row_id"] for r in rows if r["product_code"] == f"{marker}-A")
    return {
        "c": c, "db": db, "sid": sid, "row_id": row_id, "product": product, "hq": hq, "mwh": mwh,
        "so": order, "so_line": so_line, "po": po, "po_line": po_line, "marker": marker,
    }


def _url(w, tail=""):
    return f"{SNAP}/{w['sid']}/rows/{w['row_id']}/po-link{tail}"


def _done_split(request):
    """Plan 55 split: line 12009 cut to 380, new line 12080 of 120 at MWH linked to SO 11990."""
    return 200, {
        "operationId": "op-1", "actionId": None, "outcome": "done", "errorCode": None, "message": "",
        "warnings": [], "docKey": 12008, "docNo": "202609-S0029", "replacedLines": [],
        "document": {
            "DocKey": 12008, "DocNo": "202609-S0029",
            "Details": [
                {"DtlKey": 12009, "ItemCode": "X", "Location": "HQ", "Qty": 380, "FromSODtlKey": None},
                {"DtlKey": 12080, "ItemCode": "X", "Location": "MWH", "Qty": 120, "FromSODtlKey": 11990},
            ],
        },
    }


# --------------------------------------------------------------------------- options + gate


def test_options_need_the_link_permission(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    c, _db = _client(scm_app, permissions=(VIEW,))
    assert c.get(_url(w)).status_code == 403


def test_options_list_open_unlinked_po_lines_with_po_qty_and_free(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    db = w["db"]
    # A linked line and a fully received line are used: never offered.
    _po_line(db, w["product"], w["hq"], qty=50, so_ref=f"{DB}:1:2", po=w["po"], dtl_key=12010)
    _po_line(db, w["product"], w["hq"], qty=40, received=40, po=w["po"], dtl_key=12011)
    _po_line(db, w["product"], w["hq"], qty=30, received=10, po=w["po"], dtl_key=12012)
    resp = w["c"].get(_url(w))
    assert resp.status_code == 200, resp.text
    lines = resp.json()["po_lines"]
    by_qty = {l["po_qty"]: l for l in lines}
    assert set(by_qty) == {500, 30}
    first = by_qty[500]
    assert first["po_number"] == w["po"].po_number
    # Numbered as `_po_rows` numbers it (created_at, id); every row here shares one now().
    assert first["po_line_no"] in {1, 2, 3, 4}
    assert first["free_qty"] == 500
    assert first["location_code"] == w["hq"].warehouse_code
    assert by_qty[30]["free_qty"] == 20


def test_capabilities_come_from_ss_with_plain_reasons(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    caps = w["c"].get(_url(w)).json()["capabilities"]
    assert caps["split_link"] == {"enabled": True, "reason": None}
    assert caps["link_row"] == {"enabled": False, "reason": "Waiting for AutoCount"}
    assert caps["unlink_row"]["reason"] == "Waiting for AutoCount"
    assert caps["relink_row"]["enabled"] is False
    sent = [r for r in fake_ss.calls if r.url.path.endswith("write-capabilities")]
    assert sent and sent[0].url.params["companyCode"]
    assert sent[0].headers["X-API-Key"] == "fxa_link_test"


def test_writes_switched_off_reads_as_switched_off_here(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/write-capabilities"] = (200, {"capabilities": [
        {**e, "enabled": False, "reasonCode": "WRITE_NOT_ALLOWED"} for e in ALL_ON
    ]})
    caps = w["c"].get(_url(w)).json()["capabilities"]
    assert caps["split_link"] == {"enabled": False, "reason": "Changes to AutoCount are switched off here"}


def test_ss_unreachable_disables_every_action(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/write-capabilities"] = (500, {"code": "INTERNAL", "message": "x"})
    caps = w["c"].get(_url(w)).json()["capabilities"]
    assert all(not v["enabled"] for v in caps.values())
    assert caps["split_link"]["reason"] == "Could not reach AutoCount"


# --------------------------------------------------------------------------- link


def test_split_link_sends_the_intent_and_applies_what_autocount_returned(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = _done_split
    resp = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 120},
    ]})
    assert resp.status_code == 200, resp.text
    (result,) = resp.json()["results"]
    assert result["outcome"] == "done"
    assert result["so_number"] == w["so"].so_number
    assert result["so_line_no"] == 140
    assert result["po_number"] == "202609-S0029"
    assert result["qty"] == 120

    (body,) = fake_ss.bodies("/api/v1/autocount/po-links")
    assert body["poDocKey"] == 12008 and body["poDtlKey"] == 12009
    assert body["soDocKey"] == 11988 and body["soDtlKey"] == 11990
    assert body["qty"] == 120
    assert body["soDocDate"] == "2026-10-20"
    assert body["companyCode"]
    assert fake_ss.headers("/api/v1/autocount/po-links")[0].get("Idempotency-Key")

    # AutoCount is the truth: the original line now reads 380, and the new linked line exists.
    from app.models.procurement import PurchaseOrderLine

    db = w["db"]
    db.expire_all()
    assert db.get(PurchaseOrderLine, w["po_line"].id).qty_ordered == Decimal("380")
    new = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.source_ref == f"{DB}:12008:12080").one()
    assert new.qty_ordered == Decimal("120")
    assert new.from_so_line_ref == f"{DB}:11988:11990"
    assert new.purchase_order_id == w["po"].id
    assert new.product_id == w["product"].id


def test_drill_now_shows_the_po_now_covering_the_line(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = _done_split
    w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 120},
    ]})
    lines = w["c"].get(f"{SNAP}/{w['sid']}/rows/{w['row_id']}/lines").json()["data"]
    (line,) = [l for l in lines if l["sales_order_line_id"] == w["so_line"].id]
    (link,) = line["now"]["po_links"]
    assert link["po_number"] == w["po"].po_number
    assert link["qty"] == 120.0
    assert link["po_line_no"] in {1, 2}
    assert link["po_line_id"] != w["po_line"].id


def test_whole_row_link_repoints_the_crm_line_to_the_new_row(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    w["po_line"].qty_ordered = Decimal("120")
    w["db"].flush()
    fake_ss.answers["/api/v1/autocount/po-links"] = (200, {
        "operationId": "op-2", "actionId": None, "outcome": "done", "errorCode": None, "message": "",
        "warnings": [], "docKey": 12008, "docNo": "202609-S0029",
        "replacedLines": [{"oldDtlKey": 12009, "newDtlKey": 12090}],
        "document": {"DocKey": 12008, "Details": [
            {"DtlKey": 12090, "Location": "MWH", "Qty": 120, "FromSODtlKey": 11990},
        ]},
    })
    resp = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 120},
    ]})
    assert resp.json()["results"][0]["outcome"] == "done"
    from app.models.procurement import PurchaseOrderLine

    w["db"].expire_all()
    line = w["db"].get(PurchaseOrderLine, w["po_line"].id)
    assert line.source_ref == f"{DB}:12008:12090"
    assert line.from_so_line_ref == f"{DB}:11988:11990"


def test_location_not_moved_is_a_warning_with_the_new_row_keys(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)

    def answer(request):
        status, body = _done_split(request)
        return status, {**body, "warnings": ["LOCATION_NOT_MOVED"]}

    fake_ss.answers["/api/v1/autocount/po-links"] = answer
    (result,) = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 120},
    ]}).json()["results"]
    assert result["outcome"] == "done"
    assert result["warnings"] == ["LOCATION_NOT_MOVED"]
    assert (result["po_doc_key"], result["po_dtl_key"]) == (12008, 12080)


def test_vendor_unsupported_is_a_refusal_and_changes_nothing(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = (409, {
        "operationId": None, "actionId": "a-1", "outcome": "refused", "errorCode": "VENDOR_UNSUPPORTED",
        "message": "", "document": None,
    })
    (result,) = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 120},
    ]}).json()["results"]
    assert result["outcome"] == "refused"
    assert result["error_code"] == "VENDOR_UNSUPPORTED"
    from app.models.procurement import PurchaseOrderLine

    w["db"].expire_all()
    assert w["db"].get(PurchaseOrderLine, w["po_line"].id).qty_ordered == Decimal("500")


def test_needs_attention_carries_the_operation_for_resume(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = (502, {
        "operationId": "op-9", "actionId": None, "outcome": "needs_attention", "errorCode": "VENDOR_ERROR",
        "message": "", "warnings": [], "document": None,
    })
    (result,) = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 120},
    ]}).json()["results"]
    assert result["outcome"] == "needs_attention"
    assert result["operation_id"] == "op-9"
    company_code = result["company_code"]

    fake_ss.answers["/api/v1/autocount/write-operations/op-9/resume"] = _done_split
    resp = w["c"].post(f"{BASE}/po-link/operations/op-9/resume", json={"company_code": company_code})
    assert resp.status_code == 200, resp.text
    assert resp.json()["outcome"] == "done"
    assert fake_ss.bodies("/api/v1/autocount/write-operations/op-9/resume") == [{"companyCode": company_code}]


def test_link_refuses_a_line_that_is_not_in_the_snapshot_row(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    _o, stray = _demand(w["db"], w["product"], w["mwh"], qty=5, required_date=_months_ahead(1),
                        so_number=f"{w['marker']}-STRAY")
    resp = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": stray.id, "po_line_id": w["po_line"].id, "qty": 5},
    ]})
    assert resp.status_code == 422
    assert fake_ss.bodies("/api/v1/autocount/po-links") == []


@pytest.mark.parametrize("qty", [0, 501])
def test_link_refuses_a_qty_outside_one_to_free(scm_app, fake_ss, qty):
    w = _world(scm_app, fake_ss)
    resp = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": qty},
    ]})
    assert resp.status_code == 422
    assert fake_ss.bodies("/api/v1/autocount/po-links") == []


def test_link_refuses_a_po_line_that_is_already_linked(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    w["po_line"].from_so_line_ref = f"{DB}:1:2"
    w["db"].flush()
    resp = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 10},
    ]})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- unlink / relink / relocate


def test_unlink_sends_each_linked_po_row_of_the_ticked_lines(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    w["po_line"].from_so_line_ref = w["so_line"].source_ref
    w["db"].flush()
    fake_ss.answers["/api/v1/autocount/po-links/unlink"] = (409, {
        "operationId": None, "outcome": "refused", "errorCode": "VENDOR_UNSUPPORTED", "message": "",
    })
    resp = w["c"].post(_url(w, "/unlink"), json={"sales_order_line_ids": [w["so_line"].id]})
    assert resp.status_code == 200, resp.text
    (result,) = resp.json()["results"]
    assert result["outcome"] == "refused"
    (body,) = fake_ss.bodies("/api/v1/autocount/po-links/unlink")
    assert (body["poDocKey"], body["poDtlKey"]) == (12008, 12009)


def test_relink_moves_a_po_row_to_another_line_of_the_row(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    w["po_line"].from_so_line_ref = w["so_line"].source_ref
    _o, other = _demand(w["db"], w["product"], w["mwh"], qty=30, required_date=_months_ahead(1),
                        so_number=f"{w['marker']}-SO2")
    other.source_ref = f"{DB}:11999:12001"
    w["db"].flush()
    # The target must be in the snapshot row: take a fresh snapshot that holds both lines.
    c = w["c"]
    sid = c.post(SNAP, json={"name": "two", "filters": {"query": w["marker"], "only_debt": False}}).json()["id"]
    row_id = next(r["row_id"] for r in c.get(f"{SNAP}/{sid}/rows", params={"limit": 200}).json()["data"]
                  if r["product_code"] == f"{w['marker']}-A")
    fake_ss.answers["/api/v1/autocount/po-links/relink"] = (409, {
        "operationId": None, "outcome": "refused", "errorCode": "VENDOR_UNSUPPORTED", "message": "",
    })
    resp = c.post(f"{SNAP}/{sid}/rows/{row_id}/po-link/relink", json={"moves": [
        {"po_line_id": w["po_line"].id, "to_sales_order_line_id": other.id},
    ]})
    assert resp.status_code == 200, resp.text
    (body,) = fake_ss.bodies("/api/v1/autocount/po-links/relink")
    assert (body["soDocKey"], body["soDtlKey"]) == (11999, 12001)
    assert body["docDate"] == "2026-09-01"
    assert fake_ss.headers("/api/v1/autocount/po-links/relink")[0].get("Idempotency-Key")


def test_relocate_sends_the_row_keys(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links/relocate"] = (200, {
        "actionId": "a-2", "outcome": "done", "errorCode": None, "document": None,
    })
    resp = w["c"].post(f"{BASE}/po-link/relocate", json={
        "company_code": "SRT", "po_doc_key": 12008, "po_dtl_key": 12080,
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["outcome"] == "done"
    (body,) = fake_ss.bodies("/api/v1/autocount/po-links/relocate")
    assert body == {"companyCode": "SRT", "poDocKey": 12008, "poDtlKey": 12080}


def test_the_permission_is_seeded_and_granted_to_admin():
    """Migration seeds the slug and grants it to the admin roles; the registry lists it."""
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    assert any(p["slug"] == LINK for p in PERMISSION_REGISTRY)
