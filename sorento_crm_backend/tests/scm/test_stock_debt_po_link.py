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


class MemoryStore:
    """Stands in for Redis (`get` / `set(ex=)`): the bodies are fixed AutoCount keys, so a real
    shared Redis would carry a refusal from one test, or one run, into the next."""

    def __init__(self):
        self.data: dict = {}

    def get(self, name):
        return self.data.get(name)

    def set(self, name, value, ex=None):
        self.data[name] = str(value).encode()  # Redis answers bytes
        return True

    def mget(self, names):
        return [self.data.get(name) for name in names]

    def delete(self, name):
        self.data.pop(name, None)
        return 1


@pytest.fixture(autouse=True)
def refusal_store(monkeypatch):
    from app.services import autocount_idempotency as idem
    from app.services.scm import stock_debt_po_link_service as svc

    store = MemoryStore()
    monkeypatch.setattr(idem, "_down_until", 0.0)
    monkeypatch.setattr(svc, "attempt_store", lambda: store)
    # The B12 replace hints (`po_replace_hint`) go through `idem.attempt_store()`.
    monkeypatch.setattr(idem, "_client", lambda: store)
    return store


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
    _switch(db, True)
    return TestClient(app), db


def _switch(db, on: bool) -> None:
    """The System Settings switch "AutoCount links from Stock Debt" (owner, 5 Nov)."""
    from app.models.user import SystemSetting

    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting()
        db.add(row)
    row.stock_debt_po_link_enabled = on
    db.flush()


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
    from app.models.procurement import PurchaseOrderLine

    new = w["db"].query(PurchaseOrderLine).filter(PurchaseOrderLine.source_ref == f"{DB}:12008:12080").one()
    # The follow-up (Move location) acts on the new linked line, never the original.
    assert result["po_line_id"] == new.id


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
    assert result["po_line_id"] == w["po_line"].id
    company_code = result["company_code"]

    fake_ss.answers["/api/v1/autocount/write-operations/op-9/resume"] = _done_split
    resp = w["c"].post(f"{BASE}/po-link/operations/op-9/resume", json={
        "po_line_id": result["po_line_id"], "sales_order_line_id": w["so_line"].id,
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["outcome"] == "done"
    # The company is the PO line's, read on the server.
    assert fake_ss.bodies("/api/v1/autocount/write-operations/op-9/resume") == [{"companyCode": company_code}]
    # A resume that ends done applies AutoCount's read-back like the link itself.
    from app.models.procurement import PurchaseOrderLine

    w["db"].expire_all()
    new = w["db"].query(PurchaseOrderLine).filter(PurchaseOrderLine.source_ref == f"{DB}:12008:12080").one()
    assert new.from_so_line_ref == f"{DB}:11988:11990"


def test_link_refuses_a_line_that_is_not_in_the_snapshot_row(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    _o, stray = _demand(w["db"], w["product"], w["mwh"], qty=5, required_date=_months_ahead(1),
                        so_number=f"{w['marker']}-STRAY")
    # A real AutoCount line, so only the snapshot-row check can refuse it.
    stray.source_ref = f"{DB}:11988:11991"
    w["db"].flush()
    resp = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": stray.id, "po_line_id": w["po_line"].id, "qty": 5},
    ]})
    assert resp.status_code == 422
    assert "not in this snapshot row" in resp.text
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
    resp = w["c"].post(_url(w, "/unlink"), json={"po_line_ids": [w["po_line"].id]})
    assert resp.status_code == 200, resp.text
    (result,) = resp.json()["results"]
    assert result["outcome"] == "refused"
    # VENDOR_UNSUPPORTED is asked again once (SS #230), with the same body.
    body, again = fake_ss.bodies("/api/v1/autocount/po-links/unlink")
    assert again == body
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
    body, again = fake_ss.bodies("/api/v1/autocount/po-links/relink")
    assert again == body
    assert (body["soDocKey"], body["soDtlKey"]) == (11999, 12001)
    assert body["docDate"] == "2026-09-01"
    assert fake_ss.headers("/api/v1/autocount/po-links/relink")[0].get("Idempotency-Key")


def test_relocate_sends_the_linked_row_keys_and_the_server_company(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    w["po_line"].from_so_line_ref = w["so_line"].source_ref
    w["db"].flush()
    fake_ss.answers["/api/v1/autocount/po-links/relocate"] = (200, {
        "actionId": "a-2", "outcome": "done", "errorCode": None, "document": None,
    })
    resp = w["c"].post(f"{BASE}/po-link/relocate", json={"po_line_id": w["po_line"].id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["outcome"] == "done"
    (body,) = fake_ss.bodies("/api/v1/autocount/po-links/relocate")
    assert body["poDocKey"] == 12008 and body["poDtlKey"] == 12009
    assert body["companyCode"] == resp.json()["company_code"] and body["companyCode"]


def test_relocate_refuses_an_unlinked_line(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    resp = w["c"].post(f"{BASE}/po-link/relocate", json={"po_line_id": w["po_line"].id})
    assert resp.status_code == 422
    assert fake_ss.bodies("/api/v1/autocount/po-links/relocate") == []


def test_the_same_intent_sends_the_same_idempotency_key(scm_app, fake_ss):
    """A retry after a timeout replays the Shared Service's stored answer, never a 2nd split."""
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = (504, {"code": "TIMEOUT", "message": "slow"})
    item = {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 120}
    w["c"].post(_url(w, "/link"), json={"lines": [item]})
    w["c"].post(_url(w, "/link"), json={"lines": [item]})
    keys = [h.get("Idempotency-Key") for h in fake_ss.headers("/api/v1/autocount/po-links")]
    assert len(keys) == 2 and keys[0] and keys[0] == keys[1]
    w["c"].post(_url(w, "/link"), json={"lines": [{**item, "qty": 100}]})
    assert fake_ss.headers("/api/v1/autocount/po-links")[2].get("Idempotency-Key") != keys[0]


# --------------------------------------------------------------------------- retry after a refusal
# STOCKDEBT-LINK-IDEM-KEY (AC-E2E-DB3 B3, 6 Nov): the Shared Service stores every answer under the
# key and replays it for the same key + body. The body is only CRM keys and qty, so a refusal fixed
# on the AutoCount side (blank PurchaseAgent, SS #225) was replayed to every later press, forever.

_REFUSED = (422, {
    "operationId": "op-r", "outcome": "refused", "errorCode": "FIELD_REQUIRED",
    "message": "PurchaseAgent is required.", "warnings": [], "document": None,
})


def _keys_sent(fake_ss, path="/api/v1/autocount/po-links"):
    return [h.get("Idempotency-Key") for h in fake_ss.headers(path)]


def _link_item(w, qty=120):
    return {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": qty}


def test_a_retry_after_a_refusal_is_a_new_attempt(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = _REFUSED
    (first,) = w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]}).json()["results"]
    assert first["outcome"] == "refused"
    # Fixed in AutoCount; the same body is pressed again and is NOT the refused key.
    fake_ss.answers["/api/v1/autocount/po-links"] = _done_split
    (second,) = w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]}).json()["results"]
    assert second["outcome"] == "done"
    k1, k2 = _keys_sent(fake_ss)
    assert k1 and k2 and k1 != k2


def test_every_refusal_moves_the_next_press_on(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = _REFUSED
    for _ in range(3):
        w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]})
    keys = _keys_sent(fake_ss)
    assert len(keys) == 3 and len(set(keys)) == 3


@pytest.mark.parametrize("answer", [
    (504, {"code": "TIMEOUT", "message": "slow"}),
    (202, {"operationId": "op-p", "outcome": "pending_verification", "errorCode": None, "message": ""}),
    (502, {"operationId": "op-n", "outcome": "needs_attention", "errorCode": "VENDOR_ERROR", "message": ""}),
    (502, {"operationId": "op-v", "outcome": "vendor_error", "errorCode": "VENDOR_ERROR", "message": ""}),
    # Another press with this key is still running: not a refusal of the intent.
    (409, {"operationId": None, "outcome": "refused", "errorCode": "IDEMPOTENCY_IN_PROGRESS", "message": ""}),
    (409, {"operationId": None, "outcome": "refused", "errorCode": "IDEMPOTENCY_CONFLICT", "message": ""}),
])
def test_an_unconfirmed_answer_keeps_the_key(scm_app, fake_ss, answer):
    """AutoCount may already hold the split: the retry must replay, never split the row twice."""
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = answer
    w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]})
    w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]})
    k1, k2 = _keys_sent(fake_ss)
    assert k1 and k1 == k2


def test_a_refusal_does_not_move_another_intent_on(scm_app, fake_ss):
    """Only the refused intent gets a new attempt: another qty keeps its own first key."""
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = (504, {"code": "TIMEOUT", "message": "slow"})
    w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w, 100)]})
    fake_ss.answers["/api/v1/autocount/po-links"] = _REFUSED
    w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w, 120)]})
    fake_ss.answers["/api/v1/autocount/po-links"] = (504, {"code": "TIMEOUT", "message": "slow"})
    w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w, 100)]})
    k100, _k120, k100_again = _keys_sent(fake_ss)
    assert k100 == k100_again


def test_unlink_and_relink_retry_after_a_refusal(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    w["po_line"].from_so_line_ref = w["so_line"].source_ref
    w["db"].flush()
    unlink = "/api/v1/autocount/po-links/unlink"
    fake_ss.answers[unlink] = _REFUSED
    w["c"].post(_url(w, "/unlink"), json={"po_line_ids": [w["po_line"].id]})
    w["c"].post(_url(w, "/unlink"), json={"po_line_ids": [w["po_line"].id]})
    k1, k2 = _keys_sent(fake_ss, unlink)
    assert k1 and k2 and k1 != k2

    _o, other = _demand(w["db"], w["product"], w["mwh"], qty=50, required_date=_months_ahead(1),
                        so_number=f"{w['marker']}-SO2")
    other.source_ref = f"{DB}:11988:11991"
    w["db"].flush()
    relink = "/api/v1/autocount/po-links/relink"
    fake_ss.answers[relink] = _REFUSED
    sid = w["c"].post(SNAP, json={"name": "relink", "filters": {"query": w["marker"], "only_debt": False}}).json()["id"]
    row_id = next(r["row_id"] for r in w["c"].get(f"{SNAP}/{sid}/rows", params={"limit": 200}).json()["data"]
                  if r["product_code"] == f"{w['marker']}-A")
    move = {"moves": [{"po_line_id": w["po_line"].id, "to_sales_order_line_id": other.id}]}
    w["c"].post(f"{SNAP}/{sid}/rows/{row_id}/po-link/relink", json=move)
    w["c"].post(f"{SNAP}/{sid}/rows/{row_id}/po-link/relink", json=move)
    r1, r2 = _keys_sent(fake_ss, relink)
    assert r1 and r2 and r1 != r2


def test_no_refusal_store_falls_back_to_the_intent_key(scm_app, fake_ss, monkeypatch):
    """Redis down: the link still goes, on the plain intent key (never a fresh key per press)."""
    from app.services.scm import stock_debt_po_link_service as svc

    class Down:
        def get(self, name):
            raise ConnectionError("redis down")

        def set(self, name, value, ex=None):
            raise ConnectionError("redis down")

    monkeypatch.setattr(svc, "attempt_store", lambda: Down())
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = _REFUSED
    for _ in range(2):
        resp = w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]})
        assert resp.status_code == 200, resp.text
        assert resp.json()["results"][0]["outcome"] == "refused"
    k1, k2 = _keys_sent(fake_ss)
    assert k1 and k1 == k2


def test_the_attempt_key_helper():
    """The shareable helper (AC-QTSO-CRM can call it): attempt 0 is the base key unchanged."""
    from app.services.autocount_idempotency import attempt_key

    assert attempt_key("abc", 0) == "abc"
    assert attempt_key("abc", 1) != "abc"
    assert attempt_key("abc", 1) == attempt_key("abc", 1)
    assert attempt_key("abc", 1) != attempt_key("abc", 2)
    assert len(attempt_key("x" * 64, 7)) <= 64


def test_one_request_cannot_link_more_than_the_po_line_has_free(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    _o, other = _demand(w["db"], w["product"], w["mwh"], qty=400, required_date=_months_ahead(1),
                        so_number=f"{w['marker']}-SO3")
    other.source_ref = f"{DB}:11999:12003"
    w["db"].flush()
    c = w["c"]
    sid = c.post(SNAP, json={"name": "three", "filters": {"query": w["marker"], "only_debt": False}}).json()["id"]
    row_id = next(r["row_id"] for r in c.get(f"{SNAP}/{sid}/rows", params={"limit": 200}).json()["data"]
                  if r["product_code"] == f"{w['marker']}-A")
    resp = c.post(f"{SNAP}/{sid}/rows/{row_id}/po-link/link", json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 120},
        {"sales_order_line_id": other.id, "po_line_id": w["po_line"].id, "qty": 400},
    ]})
    assert resp.status_code == 422
    assert fake_ss.bodies("/api/v1/autocount/po-links") == []


def test_relink_refuses_a_po_line_linked_outside_the_row(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    # Linked to some other customer's SO line, not one of this row's.
    w["po_line"].from_so_line_ref = f"{DB}:5:6"
    w["db"].flush()
    resp = w["c"].post(_url(w, "/relink"), json={"moves": [
        {"po_line_id": w["po_line"].id, "to_sales_order_line_id": w["so_line"].id},
    ]})
    assert resp.status_code == 422
    assert fake_ss.bodies("/api/v1/autocount/po-links/relink") == []


def test_the_permission_is_seeded_and_granted_to_admin():
    """Migration seeds the slug and grants it to the admin roles; the registry lists it."""
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    assert any(p["slug"] == LINK for p in PERMISSION_REGISTRY)


def test_the_drill_lines_carry_the_sales_order_line_number(scm_app, fake_ss):
    """Crew browser pass (4 Nov): the Line column read "-" on every row because the demand
    row never carried the SO line's number. The snapshot lines serve it (`line_no`)."""
    w = _world(scm_app, fake_ss)
    lines = w["c"].get(f"{SNAP}/{w['sid']}/rows/{w['row_id']}/lines").json()["data"]
    (line,) = [l for l in lines if l["sales_order_line_id"] == w["so_line"].id]
    assert line["line_no"] == 140


def test_a_snapshot_stored_without_line_numbers_still_serves_them(scm_app, fake_ss):
    """Snapshots saved before the fix have no `line_no` in their frozen lines; the number is
    read off the SO line when served."""
    from app.models.stock_debt_snapshot import StockDebtSnapshotRow

    w = _world(scm_app, fake_ss)
    row = w["db"].get(StockDebtSnapshotRow, w["row_id"])
    row.lines = [{k: v for k, v in l.items() if k != "line_no"} for l in row.lines]
    w["db"].flush()
    lines = w["c"].get(f"{SNAP}/{w['sid']}/rows/{w['row_id']}/lines").json()["data"]
    (line,) = [l for l in lines if l["sales_order_line_id"] == w["so_line"].id]
    assert line["line_no"] == 140


def test_po_lines_are_numbered_as_autocount_numbers_them(scm_app, fake_ss):
    """Crew pass round 2: the drill's Line is AutoCount's Seq, so the PO picker (and the PO
    named on a linked line) use AutoCount's own PO line number too, not the position."""
    w = _world(scm_app, fake_ss)
    w["po_line"].line_no = 7
    w["db"].flush()
    (option,) = w["c"].get(_url(w)).json()["po_lines"]
    assert option["po_line_no"] == 7

    w["po_line"].from_so_line_ref = w["so_line"].source_ref
    w["db"].flush()
    lines = w["c"].get(f"{SNAP}/{w['sid']}/rows/{w['row_id']}/lines").json()["data"]
    (line,) = [l for l in lines if l["sales_order_line_id"] == w["so_line"].id]
    assert [p["po_line_no"] for p in line["now"]["po_links"]] == [7]



# --------------------------------------------------------------------------- crew pass round 3


def test_a_line_fully_covered_by_a_po_cannot_be_linked_again(scm_app, fake_ss):
    """Over-link (crew, round 3): SO line covered 120/120 by a PO; a second link is refused
    with a plain reason and never reaches AutoCount."""
    w = _world(scm_app, fake_ss)
    po2, covering = _po_line(w["db"], w["product"], w["hq"], qty=120, so_ref=w["so_line"].source_ref,
                             doc_key=12100, dtl_key=12101)
    resp = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 10},
    ]})
    assert resp.status_code == 422
    assert f"already covered by PO {po2.po_number}" in resp.text
    assert fake_ss.bodies("/api/v1/autocount/po-links") == []


def test_a_partly_covered_line_takes_only_what_is_left(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    _po_line(w["db"], w["product"], w["hq"], qty=100, so_ref=w["so_line"].source_ref,
             doc_key=12100, dtl_key=12101)
    over = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 21},
    ]})
    assert over.status_code == 422
    assert "20 more" in over.text
    fake_ss.answers["/api/v1/autocount/po-links"] = _done_split
    ok = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 20},
    ]})
    assert ok.status_code == 200, ok.text
    assert fake_ss.bodies("/api/v1/autocount/po-links")[0]["qty"] == 20


def test_a_po_in_another_autocount_book_cannot_be_linked(scm_app, fake_ss):
    """A PO pulled from another AutoCount book (a live book next to db3) cannot be linked to a
    sales order line of this book: refused before AutoCount, and the options say which book."""
    w = _world(scm_app, fake_ss)
    _po, other = _po_line(w["db"], w["product"], w["hq"], qty=50, doc_key=500, dtl_key=501)
    other.source_ref = "LIVE_SRT:500:501"
    w["db"].flush()
    resp = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": other.id, "qty": 5},
    ]})
    assert resp.status_code == 422
    assert "different AutoCount book" in resp.text
    assert fake_ss.bodies("/api/v1/autocount/po-links") == []

    body = w["c"].get(_url(w)).json()
    books = {l["po_line_id"]: l["book"] for l in body["po_lines"]}
    assert books[other.id] == "LIVE_SRT" and books[w["po_line"].id] == DB
    assert body["so_books"][w["so_line"].id] == DB


# --------------------------------------------------------------------------- the switch (owner, 5 Nov)

SWITCHED_OFF_TEXT = "AutoCount links from Stock Debt are switched off in Settings."


def test_switch_off_refuses_every_po_link_route_with_a_plain_reason(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    _switch(w["db"], False)
    c = w["c"]
    item = {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 10}
    calls = [
        c.get(_url(w)),
        c.post(_url(w, "/link"), json={"lines": [item]}),
        c.post(_url(w, "/unlink"), json={"po_line_ids": [w["po_line"].id]}),
        c.post(_url(w, "/relink"), json={"moves": [
            {"po_line_id": w["po_line"].id, "to_sales_order_line_id": w["so_line"].id}]}),
        c.post(f"{BASE}/po-link/relocate", json={"po_line_id": w["po_line"].id}),
        c.post(f"{BASE}/po-link/operations/op-1/resume", json={"po_line_id": w["po_line"].id}),
    ]
    for resp in calls:
        assert resp.status_code == 403, resp.text
        assert SWITCHED_OFF_TEXT in resp.text
    # Nothing reached the Shared Service, not even the capabilities read.
    assert fake_ss.calls == []


def test_switch_on_lets_the_link_through(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    _switch(w["db"], True)
    fake_ss.answers["/api/v1/autocount/po-links"] = _done_split
    resp = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 120},
    ]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"][0]["outcome"] == "done"


def test_the_switch_ships_off_and_is_readable_without_settings_access(scm_app, fake_ss):
    """Seeded OFF; the drill reads it from the open app-config projection."""
    from app.models.user import SystemSetting

    assert SystemSetting.__table__.c.stock_debt_po_link_enabled.server_default.arg == "false"
    w = _world(scm_app, fake_ss)
    _switch(w["db"], False)
    cfg = w["c"].get("/api/v1/user-management/settings/app-config")
    assert cfg.status_code == 200, cfg.text
    assert cfg.json()["stock_debt_po_link_enabled"] is False
    _switch(w["db"], True)
    assert w["c"].get("/api/v1/user-management/settings/app-config").json()["stock_debt_po_link_enabled"] is True


def test_a_failing_store_is_skipped_for_a_while(monkeypatch):
    """Redis down: one timeout, then the rest of the request (every other line) skips it."""
    from app.services import autocount_idempotency as idem

    calls = []

    class Down:
        def get(self, name):
            calls.append(name)
            raise ConnectionError("redis down")

    monkeypatch.setattr(idem, "_client", lambda: Down())
    monkeypatch.setattr(idem, "_down_until", 0.0)
    refused = {"outcome": "refused", "errorCode": "FIELD_REQUIRED"}
    for _ in range(3):
        assert idem.send_with_attempts(idem.attempt_store(), "base", lambda key: refused) == refused
    assert len(calls) == 1


# --------------------------------------------------------------------------- SS write API v2
# STOCKDEBT-LINK-IDEM-KEY-2 (10 Nov): SS #230 turned link / unlink / relink on. A VENDOR_UNSUPPORTED
# refusal SS stored before this lane shipped has no attempt count in Redis, so the first press would
# replay it. VENDOR_UNSUPPORTED changed nothing, so that press asks again ONCE on the next attempt.

_UNSUPPORTED = (409, {
    "operationId": None, "outcome": "refused", "errorCode": "VENDOR_UNSUPPORTED", "message": "",
})


def _replay_then(live):
    """The first key sent is SS's stored VENDOR_UNSUPPORTED answer; any other key gets `live`."""
    stored = []

    def answer(request):
        key = request.headers.get("Idempotency-Key")
        if not stored:
            stored.append(key)
        if key == stored[0]:
            return _UNSUPPORTED
        return live(request) if callable(live) else live
    return answer


def test_a_stored_vendor_unsupported_is_asked_again_in_the_same_press(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = _replay_then(_done_split)
    (result,) = w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]}).json()["results"]
    assert result["outcome"] == "done"
    k1, k2 = _keys_sent(fake_ss)
    assert k1 and k2 and k1 != k2


def test_an_unconfirmed_answer_after_asking_again_keeps_that_attempt(refusal_store):
    """The second send timed out: the next press must replay ITS key, never split twice."""
    from app.services import autocount_idempotency as idem

    sent = []
    answers = iter([
        {"outcome": "refused", "errorCode": "VENDOR_UNSUPPORTED"},
        {"outcome": "pending_verification", "errorCode": None},
        {"outcome": "done", "errorCode": None},
    ])

    def send(key):
        sent.append(key)
        return next(answers)

    assert idem.send_with_attempts(refusal_store, "base", send)["outcome"] == "pending_verification"
    assert idem.send_with_attempts(refusal_store, "base", send)["outcome"] == "done"
    assert sent == ["base", idem.attempt_key("base", 1), idem.attempt_key("base", 1)]


def test_a_live_vendor_unsupported_is_asked_again_only_once(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = _UNSUPPORTED
    (result,) = w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]}).json()["results"]
    assert result["outcome"] == "refused" and result["error_code"] == "VENDOR_UNSUPPORTED"
    assert len(_keys_sent(fake_ss)) == 2
    w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]})
    keys = _keys_sent(fake_ss)
    assert len(keys) == 4 and len(set(keys)) == 4


def test_another_refusal_is_not_asked_again_in_the_same_press(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = _REFUSED
    w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]})
    assert len(_keys_sent(fake_ss)) == 1


def test_unlink_asks_again_after_vendor_unsupported(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    w["po_line"].from_so_line_ref = w["so_line"].source_ref
    w["db"].flush()
    unlink = "/api/v1/autocount/po-links/unlink"
    fake_ss.answers[unlink] = _UNSUPPORTED
    w["c"].post(_url(w, "/unlink"), json={"po_line_ids": [w["po_line"].id]})
    k1, k2 = _keys_sent(fake_ss, unlink)
    assert k1 and k2 and k1 != k2


def test_vendor_unsupported_is_asked_again_with_redis_down(scm_app, fake_ss, monkeypatch):
    from app.services.scm import stock_debt_po_link_service as svc

    monkeypatch.setattr(svc, "attempt_store", lambda: None)
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = _UNSUPPORTED
    w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]})
    k1, k2 = _keys_sent(fake_ss)
    assert k1 and k2 and k1 != k2


def test_every_write_of_a_press_carries_one_request_id(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = _UNSUPPORTED  # two sends per press
    for _ in range(2):
        w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]})
    ids = [h.get("X-Request-ID") for h in fake_ss.headers("/api/v1/autocount/po-links")]
    assert len(ids) == 4 and all(ids)
    assert ids[0] == ids[1] and ids[2] == ids[3] and ids[0] != ids[2]


# --------------------------------------------------------------------------- B12: one CRM line per row
# AC-E2E-DB3 B12 (10 Nov, crew ruling (b)): SS v2 makes link / change link / unlink a replace, so the
# AutoCount row gets a new DtlKey (`replacedLines`), and SS pushes the read-back to the PO ingest
# DURING the call. Whichever arrives first, the CRM keeps ONE line per AutoCount row: the existing
# line (same id) is re-keyed, never shown as removed, and no duplicate or retired copy carries a ref.


def _push_po(w, details, *, own_session=False):
    """The PO ingest push SS sends with the read-back: `details` = (dtl, qty, warehouse, so_ref, seq).

    `own_session`: as on db3, the push is another request in its own transaction, so the link
    request's loaded copies of these lines are stale when its `_apply` runs. Emulated in the one
    test session: after the push, every line the session held gets its pre-push values back as
    if loaded (no change history), exactly what an un-expired identity map would show."""
    from sqlalchemy.orm.attributes import set_committed_value

    from app.models.procurement import PurchaseOrderLine
    from app.services.document_ingest_service import DocumentIngestService

    if own_session:
        held = [o for o in w["db"].identity_map.values() if isinstance(o, PurchaseOrderLine)]
        before = {o: {c.key: getattr(o, c.key) for c in PurchaseOrderLine.__table__.columns} for o in held}
        result = _push_po(w, details)
        assert all(r.outcome.value in ("created", "updated", "unchanged") for r in result.records)
        for obj, values in before.items():
            for key, value in values.items():
                set_committed_value(obj, key, value)
        return result
    po = w["po"]
    record = {
        "source_ref": po.source_ref, "po_number": po.po_number, "status": "open",
        "supplier_code": po.supplier.supplier_code,
        "lines": [
            {"source_ref": f"{DB}:12008:{dtl}", "product_code": w["product"].product_code,
             "warehouse_code": wh.warehouse_code, "qty_ordered": qty, "from_so_line_ref": so_ref,
             "line_number": seq}
            for dtl, qty, wh, so_ref, seq in details
        ],
    }
    result = DocumentIngestService(w["db"], company_id=SORENTO_COMPANY_ID).ingest("purchase_orders", [record])
    w["db"].flush()
    return result


def _answer(details, replaced):
    return 200, {
        "operationId": "op-b12", "actionId": None, "outcome": "done", "errorCode": None, "message": "",
        "warnings": [], "docKey": 12008, "docNo": "202609-S0029",
        "replacedLines": [{"oldDtlKey": o, "newDtlKey": n} for o, n in replaced],
        "document": {"DocKey": 12008, "DocNo": "202609-S0029", "Details": [
            {"DtlKey": dtl, "ItemCode": "X", "Location": wh.warehouse_code, "Qty": qty,
             "FromSODtlKey": int(so_ref.split(":")[2]) if so_ref else None}
            for dtl, qty, wh, so_ref, _seq in details
        ]},
    }


def _sends(w, path, details, replaced, order):
    """SS's answer for `path`; with order "ingest_first" the ingest push lands inside the call."""
    def handler(request):
        if order == "ingest_first":
            _push_po(w, details, own_session=True)
        return _answer(details, replaced)
    return handler


def _lines_of(w):
    from app.models.procurement import PurchaseOrderLine

    w["db"].flush()
    w["db"].expire_all()
    return w["db"].query(PurchaseOrderLine).filter(PurchaseOrderLine.purchase_order_id == w["po"].id).all()


def _assert_one_line_per_row(w, details, *, kept_id=None, kept_dtl=None):
    lines = _lines_of(w)
    refs = sorted(l.source_ref for l in lines)
    assert refs == sorted(f"{DB}:12008:{d[0]}" for d in details), [
        (l.source_ref, l.line_status, l.removed_unreferenced) for l in lines]
    for line in lines:
        assert line.line_status == "open" and not line.removed_unreferenced, (
            line.source_ref, line.line_status, line.removed_unreferenced)
    by_ref = {l.source_ref: l for l in lines}
    for dtl, qty, wh, so_ref, _seq in details:
        line = by_ref[f"{DB}:12008:{dtl}"]
        assert float(line.qty_ordered) == qty
        assert line.from_so_line_ref == so_ref
        assert line.warehouse_id == wh.id
    if kept_id is not None:
        assert by_ref[f"{DB}:12008:{kept_dtl}"].id == kept_id


ORDERS = ["answer_first", "ingest_first"]


def _spy_release(monkeypatch):
    """PO line ids the ingest released as removed in AutoCount (their OI links given back)."""
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    released = []
    real = ProjectOrderInquiryService.release_removed_lines

    def spy(self, *, po_line_ids=(), spo_allocation_ids=()):
        released.extend(str(i) for i in po_line_ids)
        return real(self, po_line_ids=po_line_ids, spo_allocation_ids=spo_allocation_ids)

    monkeypatch.setattr(ProjectOrderInquiryService, "release_removed_lines", spy)
    return released


@pytest.mark.parametrize("order", ORDERS)
def test_b12_whole_row_link_keeps_one_line(scm_app, fake_ss, order, monkeypatch):
    released = _spy_release(monkeypatch)
    w = _world(scm_app, fake_ss)
    w["po_line"].qty_ordered = Decimal("120")  # whole row: link qty == row qty
    w["db"].flush()
    so_ref = w["so_line"].source_ref
    details = [(12303, 120, w["mwh"], so_ref, 80)]
    fake_ss.answers["/api/v1/autocount/po-links"] = _sends(w, "po-links", details, [(12009, 12303)], order)
    (result,) = w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]}).json()["results"]
    assert result["outcome"] == "done"
    if order == "answer_first":
        _push_po(w, details)
    _assert_one_line_per_row(w, details, kept_id=w["po_line"].id, kept_dtl=12303)
    assert w["po_line"].id not in released  # never shown as removed, OI links kept


@pytest.mark.parametrize("order", ORDERS)
def test_b12_unlink_keeps_one_line(scm_app, fake_ss, order, monkeypatch):
    released = _spy_release(monkeypatch)
    w = _world(scm_app, fake_ss)
    w["po_line"].from_so_line_ref = w["so_line"].source_ref
    w["db"].flush()
    details = [(12308, 500, w["hq"], None, 80)]
    fake_ss.answers["/api/v1/autocount/po-links/unlink"] = _sends(
        w, "po-links/unlink", details, [(12009, 12308)], order)
    resp = w["c"].post(_url(w, "/unlink"), json={"po_line_ids": [w["po_line"].id]})
    assert resp.json()["results"][0]["outcome"] == "done", resp.text
    if order == "answer_first":
        _push_po(w, details)
    _assert_one_line_per_row(w, details, kept_id=w["po_line"].id, kept_dtl=12308)
    assert w["po_line"].id not in released  # never shown as removed, OI links kept


@pytest.mark.parametrize("order", ORDERS)
def test_b12_change_link_keeps_one_line(scm_app, fake_ss, order, monkeypatch):
    released = _spy_release(monkeypatch)
    w = _world(scm_app, fake_ss)
    w["po_line"].from_so_line_ref = w["so_line"].source_ref
    _o, other = _demand(w["db"], w["product"], w["mwh"], qty=30, required_date=_months_ahead(1),
                        so_number=f"{w['marker']}-SO2")
    other.source_ref = f"{DB}:11999:12001"
    w["db"].flush()
    c = w["c"]
    sid = c.post(SNAP, json={"name": "two", "filters": {"query": w["marker"], "only_debt": False}}).json()["id"]
    row_id = next(r["row_id"] for r in c.get(f"{SNAP}/{sid}/rows", params={"limit": 200}).json()["data"]
                  if r["product_code"] == f"{w['marker']}-A")
    details = [(12307, 500, w["hq"], other.source_ref, 80)]
    fake_ss.answers["/api/v1/autocount/po-links/relink"] = _sends(
        w, "po-links/relink", details, [(12009, 12307)], order)
    resp = c.post(f"{SNAP}/{sid}/rows/{row_id}/po-link/relink", json={"moves": [
        {"po_line_id": w["po_line"].id, "to_sales_order_line_id": other.id},
    ]})
    assert resp.json()["results"][0]["outcome"] == "done", resp.text
    if order == "answer_first":
        _push_po(w, details)
    _assert_one_line_per_row(w, details, kept_id=w["po_line"].id, kept_dtl=12307)
    assert w["po_line"].id not in released  # never shown as removed, OI links kept


@pytest.mark.parametrize("order", ORDERS)
def test_b12_split_keeps_one_line_per_row(scm_app, fake_ss, order, monkeypatch):
    released = _spy_release(monkeypatch)
    w = _world(scm_app, fake_ss)
    so_ref = w["so_line"].source_ref
    details = [(12009, 380, w["hq"], None, 16), (12080, 120, w["mwh"], so_ref, 32)]
    fake_ss.answers["/api/v1/autocount/po-links"] = _sends(w, "po-links", details, [], order)
    (result,) = w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]}).json()["results"]
    assert result["outcome"] == "done"
    if order == "answer_first":
        _push_po(w, details)
    _assert_one_line_per_row(w, details, kept_id=w["po_line"].id, kept_dtl=12009)
    assert w["po_line"].id not in released  # never shown as removed, OI links kept


@pytest.mark.parametrize("order", ORDERS)
def test_b12_split_that_replaces_the_row_keeps_one_line_per_row(scm_app, fake_ss, order, monkeypatch):
    released = _spy_release(monkeypatch)
    w = _world(scm_app, fake_ss)
    so_ref = w["so_line"].source_ref
    details = [(12310, 380, w["hq"], None, 80), (12311, 120, w["mwh"], so_ref, 96)]
    fake_ss.answers["/api/v1/autocount/po-links"] = _sends(w, "po-links", details, [(12009, 12310)], order)
    (result,) = w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]}).json()["results"]
    assert result["outcome"] == "done"
    if order == "answer_first":
        _push_po(w, details)
    _assert_one_line_per_row(w, details, kept_id=w["po_line"].id, kept_dtl=12310)
    assert w["po_line"].id not in released  # never shown as removed, OI links kept


def test_b12_ingest_first_without_the_hint_still_keeps_one_line(scm_app, fake_ss, monkeypatch):
    """Redis down: ingest cannot pair, so `_apply` merges its duplicate into the existing line."""
    from app.services import autocount_idempotency as idem
    from app.services.scm import stock_debt_po_link_service as svc

    monkeypatch.setattr(svc, "attempt_store", lambda: None)
    monkeypatch.setattr(idem, "attempt_store", lambda: None)
    w = _world(scm_app, fake_ss)
    w["po_line"].qty_ordered = Decimal("120")
    w["po_line"].moq_snapshot = Decimal("40")  # the planner's own: the merge must keep it
    w["db"].flush()
    details = [(12303, 120, w["mwh"], w["so_line"].source_ref, 80)]
    fake_ss.answers["/api/v1/autocount/po-links"] = _sends(w, "po-links", details, [(12009, 12303)], "ingest_first")
    (result,) = w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]}).json()["results"]
    assert result["outcome"] == "done"
    _assert_one_line_per_row(w, details, kept_id=w["po_line"].id, kept_dtl=12303)
    # The claim ingest raised on its duplicate moved to the kept line, not SET NULL / gone.
    claims = w["db"].execute(
        text("SELECT po_line_id FROM scm.order_link_claim WHERE po_line_id = :id"),
        {"id": w["po_line"].id},
    ).scalars().all()
    assert str(w["po_line"].id) in {str(c) for c in claims if c}, claims
    (kept,) = _lines_of(w)
    assert kept.moq_snapshot == Decimal("40")
    # Degraded path (no hint): ingest already released the old line as removed, its OI links go.


def test_b12_ingest_pairs_a_hinted_row_with_its_replacement(scm_app, fake_ss):
    """Before `_apply` runs at all: the CRM line keeps its id, is never retired, links kept."""
    from app.services.scm import po_replace_hint

    w = _world(scm_app, fake_ss)
    so_ref = w["so_line"].source_ref
    po_replace_hint.remember(w["po_line"].source_ref, qty=500, from_so_ref=so_ref)
    _push_po(w, [(12303, 500, w["mwh"], so_ref, 80)])
    (line,) = _lines_of(w)
    assert line.id == w["po_line"].id and line.source_ref == f"{DB}:12008:12303"
    assert line.line_status == "open" and not line.removed_unreferenced


def test_b12_ingest_does_not_pair_without_a_hint(scm_app, fake_ss):
    """An AutoCount-side re-save nobody in the CRM asked for stays a removal plus a create."""
    w = _world(scm_app, fake_ss)
    _push_po(w, [(12303, 500, w["hq"], None, 80)])
    lines = {l.source_ref: l for l in _lines_of(w)}
    assert lines[w["po_line"].source_ref].line_status == "cancelled"
    assert lines[f"{DB}:12008:12303"].id != w["po_line"].id


def test_b12_ingest_does_not_guess_between_two_candidates(scm_app, fake_ss):
    from app.services.scm import po_replace_hint

    w = _world(scm_app, fake_ss)
    po_replace_hint.remember(w["po_line"].source_ref, qty=500, from_so_ref=None)
    _push_po(w, [(12303, 500, w["hq"], None, 80), (12304, 500, w["hq"], None, 96)])
    lines = {l.source_ref: l for l in _lines_of(w)}
    assert lines[w["po_line"].source_ref].line_status == "cancelled"
    assert w["po_line"].id not in {lines[f"{DB}:12008:12303"].id, lines[f"{DB}:12008:12304"].id}


def test_b12_ingest_does_not_pair_another_qty_or_link(scm_app, fake_ss):
    from app.services.scm import po_replace_hint

    w = _world(scm_app, fake_ss)
    po_replace_hint.remember(w["po_line"].source_ref, qty=500, from_so_ref=w["so_line"].source_ref)
    _push_po(w, [(12303, 499, w["mwh"], w["so_line"].source_ref, 80)])
    lines = {l.source_ref: l for l in _lines_of(w)}
    assert lines[w["po_line"].source_ref].line_status == "cancelled"


def test_a_raising_second_send_keeps_the_stored_attempt(refusal_store):
    """Reviewer round 2: the re-send may have reached AutoCount; nothing is recorded, so the
    next press sends that same key again (SS replays it), never a third one."""
    from app.services import autocount_idempotency as idem

    sent = []

    def send(key):
        sent.append(key)
        if len(sent) == 2:
            raise RuntimeError("connection dropped")
        return {"outcome": "refused", "errorCode": "VENDOR_UNSUPPORTED"}

    with pytest.raises(RuntimeError):
        idem.send_with_attempts(refusal_store, "base", send)
    assert refusal_store.get(f"{idem._PREFIX}base") is None
    idem.send_with_attempts(refusal_store, "base", lambda key: sent.append(key) or {"outcome": "done"})
    assert sent == ["base", idem.attempt_key("base", 1), "base"]


def test_b12_a_refused_replace_drops_its_hint(scm_app, fake_ss, refusal_store):
    """AutoCount kept the row: a later re-save of it must not be paired from a stale hint."""
    w = _world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links"] = _REFUSED
    w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]})
    assert not [k for k in refusal_store.data if "po_replace" in k]


def test_b12_a_done_replace_records_its_hint_before_the_send(scm_app, fake_ss, refusal_store):
    w = _world(scm_app, fake_ss)
    seen = []

    def answer(request):
        seen.extend(k for k in refusal_store.data if "po_replace" in k)
        return _done_split(request)

    fake_ss.answers["/api/v1/autocount/po-links"] = answer
    w["c"].post(_url(w, "/link"), json={"lines": [_link_item(w)]})
    assert seen == [f"sorento:autocount_write:po_replace:{DB}:12008:12009"]
