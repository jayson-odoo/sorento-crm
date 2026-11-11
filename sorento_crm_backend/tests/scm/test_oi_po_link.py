"""Order Inquiry rows link to PO lines through the SHARED Stock Debt link function (OI-PO-LINK).

Plan: `documentation/plans/scm/PLAN-oi-po-link-11nov.md`; contract: the AC ids in
`oi-po-link-11nov-acceptance-criteria.md`.

WRITTEN BEFORE THE IMPLEMENTATION (Phase 2, red first). The fake Shared Service, the PO / SO
seeding and the permission plumbing are reused from `test_stock_debt_po_link.py`; this module
adds the Order Inquiry chain (project SO -> project SO line -> core SO line, OI header, OI rows).

Postgres only, every chain seeded here, everything rolled back.
"""
from __future__ import annotations

import importlib
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg
from tests.scm.test_stock_debt_po_link import (  # noqa: F401  (fake_ss is a fixture)
    ALL_ON,
    DB,
    LINK,
    SNAP,
    FakeSS,
    MemoryStore,
    _client,
    _done_split,
    _keys_sent,
    _po_line,
    _switch,
    fake_ss,
)
from tests.scm.test_stock_debt_routes import VIEW, _demand, _months_ahead, _product, _supplier, _u, _warehouse

pytestmark = requires_pg

OI = "/api/v1/project-sales/order-inquiries"
PO_LINKS = "/api/v1/autocount/po-links"
UNLINK = "/api/v1/autocount/po-links/unlink"
PROJECTS_VIEW = "projects.projects.view"

_REFUSED = (422, {
    "operationId": "op-r", "outcome": "refused", "errorCode": "FIELD_REQUIRED",
    "message": "PurchaseAgent is required.", "warnings": [], "document": None,
})
_TIMEOUT = (504, {"code": "TIMEOUT", "message": "slow"})


@pytest.fixture(autouse=True)
def attempt_memory(monkeypatch):
    """Refusal attempts live in Redis in production; here a dict, so no run leaks into the next.
    Patched on whichever module owns `attempt_store`, old or new."""
    from app.services import autocount_idempotency as idem

    store = MemoryStore()
    monkeypatch.setattr(idem, "_down_until", 0.0)
    monkeypatch.setattr(idem, "_client", lambda: store)
    for name in ("app.services.scm.stock_debt_po_link_service", "app.services.scm.po_link_service"):
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        monkeypatch.setattr(module, "attempt_store", lambda: store, raising=False)
    return store


# --------------------------------------------------------------------------- seeding


def _oi_world(scm_app, *, permissions=(VIEW, LINK, PROJECTS_VIEW), snapshot=False):
    """One product; two AutoCount SO lines (120 at MWH, 30 at MWH); an open PO line of 500 at HQ;
    an OI header whose rows sit on those lines (two rows on the first line, one on the second)
    plus one row with no AutoCount line."""
    from app.models.project_so import (
        ACK_ACKNOWLEDGED,
        INQUIRY_RAISED,
        IV_ORDER,
        OrderInquiry,
        OrderInquiryRow,
        ProjectSalesOrder,
        ProjectSalesOrderLine,
        SO_STATUS_DRAFT,
    )
    from app.services.project_service import register_project

    c, db = _client(scm_app, permissions=permissions)
    app, _db, gcu, _gcuak = scm_app
    uid = app.dependency_overrides[gcu]()["id"]
    marker = f"ZZTOI{_u()[:5]}".upper()
    hq = _warehouse(db, f"HQ{marker[-4:]}")
    mwh = _warehouse(db, f"MW{marker[-4:]}")
    product = _product(db, f"{marker}-A")
    order, so_line = _demand(db, product, mwh, qty=120, required_date=_months_ahead(1), so_number=f"{marker}-SO")
    order.order_date = date(2026, 10, 20)
    order.source_system, order.source_ref = "autocount", f"{DB}:11988"
    so_line.source_system, so_line.source_ref, so_line.line_no = "autocount", f"{DB}:11988:11990", 140
    order2, other = _demand(db, product, mwh, qty=30, required_date=_months_ahead(1), so_number=f"{marker}-SO2")
    order2.order_date = date(2026, 10, 21)
    order2.source_system, order2.source_ref = "autocount", f"{DB}:11999"
    other.source_system, other.source_ref, other.line_no = "autocount", f"{DB}:11999:12001", 10
    po, po_line = _po_line(db, product, hq, qty=500, received=0, doc_key=12008, dtl_key=12009)

    project = register_project(
        db, company_id=SORENTO_COMPANY_ID, actor_user_id=uid, developer_party_id=None,
        title=f"{marker} Residences",
    )
    pso = ProjectSalesOrder(
        id=_u(), company_id=SORENTO_COMPANY_ID, project_id=project.id, area_group="TOWER",
        provisional_ref=f"ZZT-PSO-{_u()[:8]}", autocount_doc_no=f"SO{_u()[:6].upper()}",
        status=SO_STATUS_DRAFT, grouping_origin="area",
    )
    db.add(pso)
    db.flush()
    inquiry = OrderInquiry(
        id=_u(), company_id=SORENTO_COMPANY_ID, project_sales_order_id=pso.id,
        inquiry_no=f"OI-ZZ-{_u()[:6]}", state=INQUIRY_RAISED,
    )
    db.add(inquiry)
    db.flush()

    def project_line(core, n):
        row = ProjectSalesOrderLine(
            id=_u(), company_id=SORENTO_COMPANY_ID, project_sales_order_id=pso.id,
            core_sales_order_line_id=core.id if core is not None else None,
            line_no=n, product_id=product.id, qty=Decimal("10"),
        )
        db.add(row)
        db.flush()
        return row

    def oi_row(pline, qty="10"):
        row = OrderInquiryRow(
            id=_u(), company_id=SORENTO_COMPANY_ID, order_inquiry_id=inquiry.id,
            so_line_id=pline.id, item_code=product.product_code, qty=Decimal(qty),
            verb=IV_ORDER, state=INQUIRY_RAISED, ack_state=ACK_ACKNOWLEDGED,
        )
        db.add(row)
        db.flush()
        return row

    p1, p2, p_none = project_line(so_line, 1), project_line(other, 2), project_line(None, 3)
    rows = {"a": oi_row(p1), "b": oi_row(p1, "5"), "c": oi_row(p2), "none": oi_row(p_none)}
    world = {
        "c": c, "db": db, "uid": uid, "marker": marker, "product": product, "hq": hq, "mwh": mwh,
        "so": order, "so_line": so_line, "other": other, "po": po, "po_line": po_line,
        "inquiry": inquiry, "rows": rows, "pso": pso,
    }
    if snapshot:
        resp = c.post(SNAP, json={"name": f"{marker} snap", "filters": {"query": marker, "only_debt": False}})
        assert resp.status_code == 201, resp.text
        sid = resp.json()["id"]
        data = c.get(f"{SNAP}/{sid}/rows", params={"limit": 200}).json()["data"]
        world["sid"] = sid
        world["snap_row_id"] = next(r["row_id"] for r in data if r["product_code"] == f"{marker}-A")
    db.flush()
    return world


def _ids(w, *keys):
    return [w["rows"][k].id for k in keys]


def _item(w, line="so_line", qty=120, po_line="po_line"):
    return {"sales_order_line_id": w[line].id, "po_line_id": w[po_line].id, "qty": qty}


def _oi_link(w, lines, rows=("a", "b", "c")):
    return w["c"].post(f"{OI}/po-link/link", json={"row_ids": _ids(w, *rows), "lines": lines})


def _snap_link(w, lines):
    return w["c"].post(
        f"{SNAP}/{w['sid']}/rows/{w['snap_row_id']}/po-link/link", json={"lines": lines}
    )


def _two_step_answer():
    """Plan 55 split, cumulative: each call cuts the original row and adds one linked row."""
    state = {"orig": 500, "details": []}

    def answer(request):
        import json as _json

        body = _json.loads(request.content)
        state["orig"] -= int(body["qty"])
        new_key = 12080 if body["soDtlKey"] == 11990 else 12081
        state["details"].append(
            {"DtlKey": new_key, "Location": "MWH", "Qty": body["qty"], "FromSODtlKey": body["soDtlKey"]}
        )
        return 200, {
            "operationId": f"op-{new_key}", "actionId": None, "outcome": "done", "errorCode": None,
            "message": "", "warnings": [], "docKey": 12008, "docNo": "202609-S0029", "replacedLines": [],
            "document": {"DocKey": 12008, "DocNo": "202609-S0029", "Details": [
                {"DtlKey": 12009, "Location": "HQ", "Qty": state["orig"], "FromSODtlKey": None},
                *state["details"],
            ]},
        }

    return answer


# --------------------------------------------------------------------------- AC-1 shared function


def test_the_shared_service_module_exists_with_both_scope_builders():
    mod = importlib.import_module("app.services.scm.po_link_service")
    for name in ("PoLinkService", "PoLinkScope", "scope_for_snapshot_row", "scope_for_oi_rows"):
        assert hasattr(mod, name), name
    from app.services.scm.stock_debt_po_link_service import StockDebtPoLinkService  # still importable

    assert issubclass(StockDebtPoLinkService, mod.PoLinkService) or StockDebtPoLinkService is mod.PoLinkService


def test_stock_debt_and_order_inquiry_send_the_identical_body_for_the_same_pair(scm_app, fake_ss):
    """AC-1: one function. An unknown answer keeps the idempotency key, so the whole request
    (body AND key) of the two screens can be compared."""
    w = _oi_world(scm_app, snapshot=True)
    fake_ss.answers[PO_LINKS] = _TIMEOUT
    item = _item(w)
    assert _snap_link(w, [item]).status_code == 200
    assert _oi_link(w, [item], rows=("a",)).status_code == 200
    snap_body, oi_body = fake_ss.bodies(PO_LINKS)
    assert oi_body == snap_body
    k1, k2 = _keys_sent(fake_ss)
    assert k1 and k1 == k2


# --------------------------------------------------------------------------- AC-4 / AC-5 options


def test_oi_options_have_one_line_per_distinct_so_line_and_name_the_skipped_rows(scm_app, fake_ss):
    w = _oi_world(scm_app)
    resp = w["c"].post(f"{OI}/po-link/options", json={"row_ids": _ids(w, "a", "b", "c", "none")})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Rows a and b share one SO line: one line, not two.
    assert sorted(l["sales_order_line_id"] for l in body["lines"]) == sorted([w["so_line"].id, w["other"].id])
    first = next(l for l in body["lines"] if l["sales_order_line_id"] == w["so_line"].id)
    assert first["so_number"] == w["so"].so_number and first["line_no"] == 140
    assert {"open_qty", "po_links"} <= set(first)
    # Same shape as Stock Debt's options.
    assert {"capabilities", "po_lines", "so_books"} <= set(body)
    assert any(p["po_line_id"] == w["po_line"].id for p in body["po_lines"])
    assert body["capabilities"]["split_link"]["enabled"] is True
    # The row with no AutoCount SO line is named, with the plain reason.
    skipped = json.dumps(body["skipped"])
    assert w["inquiry"].inquiry_no in skipped and w["product"].product_code in skipped
    assert "Not in AutoCount yet" in skipped


def test_oi_options_refuse_rows_of_more_than_one_product(scm_app, fake_ss):
    from app.models.project_so import (
        ACK_ACKNOWLEDGED, INQUIRY_RAISED, IV_ORDER, OrderInquiryRow, ProjectSalesOrderLine,
    )

    w = _oi_world(scm_app)
    db = w["db"]
    product2 = _product(db, f"{w['marker']}-B")
    _o, line2 = _demand(db, product2, w["mwh"], qty=5, required_date=_months_ahead(1), so_number=f"{w['marker']}-B")
    line2.source_ref = f"{DB}:11988:11995"
    pl = ProjectSalesOrderLine(
        id=_u(), company_id=SORENTO_COMPANY_ID, project_sales_order_id=w["pso"].id,
        core_sales_order_line_id=line2.id, line_no=9, product_id=product2.id, qty=Decimal("1"),
    )
    db.add(pl)
    db.flush()
    other_row = OrderInquiryRow(
        id=_u(), company_id=SORENTO_COMPANY_ID, order_inquiry_id=w["inquiry"].id, so_line_id=pl.id,
        item_code=product2.product_code, qty=Decimal("1"), verb=IV_ORDER, state=INQUIRY_RAISED,
        ack_state=ACK_ACKNOWLEDGED,
    )
    db.add(other_row)
    db.flush()
    resp = w["c"].post(f"{OI}/po-link/options", json={"row_ids": [w["rows"]["a"].id, other_row.id]})
    assert resp.status_code == 422
    assert "Tick rows of one product." in resp.text


def test_oi_options_with_only_rows_outside_autocount_are_refused(scm_app, fake_ss):
    w = _oi_world(scm_app)
    resp = w["c"].post(f"{OI}/po-link/options", json={"row_ids": _ids(w, "none")})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- AC-6 / AC-7 link


def test_oi_link_sends_one_write_per_so_line_and_the_worklist_names_the_po(scm_app, fake_ss):
    w = _oi_world(scm_app)
    fake_ss.answers[PO_LINKS] = _two_step_answer()
    resp = _oi_link(w, [_item(w, "so_line", 120), _item(w, "other", 30)])
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert [r["outcome"] for r in results] == ["done", "done"]

    bodies = fake_ss.bodies(PO_LINKS)
    assert [(b["soDtlKey"], b["qty"]) for b in bodies] == [(11990, 120), (12001, 30)]
    assert all(b["poDocKey"] == 12008 and b["poDtlKey"] == 12009 for b in bodies)

    from app.models.procurement import PurchaseOrderLine

    db = w["db"]
    db.expire_all()
    refs = {
        r.source_ref: r.from_so_line_ref
        for r in db.query(PurchaseOrderLine).filter(PurchaseOrderLine.source_ref.in_(
            [f"{DB}:12008:12080", f"{DB}:12008:12081"]))
    }
    assert refs == {f"{DB}:12008:12080": f"{DB}:11988:11990", f"{DB}:12008:12081": f"{DB}:11999:12001"}

    # AC-7: the OI book step re-ran in the same request, so the worklist row names the PO.
    listing = w["c"].get(OI, params={"query": w["marker"], "limit": 100})
    assert listing.status_code == 200, listing.text
    by_id = {r["id"]: r for r in listing.json()["data"]}
    assert by_id[w["rows"]["a"].id]["po_number"] == w["po"].po_number
    assert by_id[w["rows"]["c"].id]["po_number"] == w["po"].po_number


def test_oi_partial_link_sends_the_split_body_and_applies_both_rows(scm_app, fake_ss):
    w = _oi_world(scm_app)
    fake_ss.answers[PO_LINKS] = _done_split
    resp = _oi_link(w, [_item(w, "so_line", 120)], rows=("a",))
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"][0]["outcome"] == "done"
    (body,) = fake_ss.bodies(PO_LINKS)
    assert body["qty"] == 120 and body["poDtlKey"] == 12009 and body["soDtlKey"] == 11990
    assert body["soDocDate"] == "2026-10-20"

    from app.models.procurement import PurchaseOrderLine

    db = w["db"]
    db.expire_all()
    assert db.get(PurchaseOrderLine, w["po_line"].id).qty_ordered == Decimal("380")
    linked = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.source_ref == f"{DB}:12008:12080").one()
    assert linked.qty_ordered == Decimal("120") and linked.from_so_line_ref == f"{DB}:11988:11990"


# --------------------------------------------------------------------------- AC-6 refusals


def test_oi_link_refuses_an_so_line_that_is_not_among_the_ticked_rows(scm_app, fake_ss):
    w = _oi_world(scm_app)
    resp = _oi_link(w, [_item(w, "other", 10)], rows=("a", "b"))  # `other` belongs to row c
    assert resp.status_code == 422
    assert fake_ss.bodies(PO_LINKS) == []


def test_oi_link_refuses_a_po_line_that_is_already_linked(scm_app, fake_ss):
    w = _oi_world(scm_app)
    w["po_line"].from_so_line_ref = f"{DB}:1:2"
    w["db"].flush()
    resp = _oi_link(w, [_item(w, "so_line", 10)])
    assert resp.status_code == 422
    assert fake_ss.bodies(PO_LINKS) == []


def test_oi_link_refuses_more_than_the_po_line_has_free_summed_over_the_request(scm_app, fake_ss):
    w = _oi_world(scm_app)
    w["po_line"].qty_ordered = Decimal("100")
    w["db"].flush()
    resp = _oi_link(w, [_item(w, "so_line", 80), _item(w, "other", 30)])
    assert resp.status_code == 422
    assert fake_ss.bodies(PO_LINKS) == []


# --------------------------------------------------------------------------- AC-8 retry


def test_oi_retry_after_a_refusal_is_a_new_attempt(scm_app, fake_ss):
    w = _oi_world(scm_app)
    fake_ss.answers[PO_LINKS] = _REFUSED
    first = _oi_link(w, [_item(w)], rows=("a",))
    assert first.status_code == 200, first.text
    result = first.json()["results"][0]
    assert result["outcome"] == "refused" and result["error_code"] == "FIELD_REQUIRED"
    assert "PurchaseAgent is required." in result["message"]
    fake_ss.answers[PO_LINKS] = _done_split
    assert _oi_link(w, [_item(w)], rows=("a",)).json()["results"][0]["outcome"] == "done"
    k1, k2 = _keys_sent(fake_ss)
    assert k1 and k2 and k1 != k2


@pytest.mark.parametrize("answer", [
    _TIMEOUT,
    (502, {"operationId": "op-v", "outcome": "vendor_error", "errorCode": "VENDOR_ERROR", "message": ""}),
])
def test_oi_unknown_outcome_keeps_the_key(scm_app, fake_ss, answer):
    w = _oi_world(scm_app)
    fake_ss.answers[PO_LINKS] = answer
    _oi_link(w, [_item(w)], rows=("a",))
    _oi_link(w, [_item(w)], rows=("a",))
    k1, k2 = _keys_sent(fake_ss)
    assert k1 and k1 == k2


# --------------------------------------------------------------------------- AC-9 unlink / change


def _linked_world(scm_app):
    w = _oi_world(scm_app)
    # A second PO line already linked to the first SO line (20 of its 120).
    _po, linked = _po_line(w["db"], w["product"], w["hq"], qty=20, so_ref=w["so_line"].source_ref,
                           doc_key=12100, dtl_key=12101)
    w["linked"] = linked
    w["db"].flush()
    return w


_UNLINK_DONE = (200, {
    "operationId": "op-u", "actionId": None, "outcome": "done", "errorCode": None, "message": "",
    "warnings": [], "docKey": 12100, "docNo": "202609-S0030",
    "document": {"DocKey": 12100, "Details": [{"DtlKey": 12101, "Location": "HQ", "Qty": 20, "FromSODtlKey": None}]},
})


def test_oi_unlink_sends_the_linked_po_row(scm_app, fake_ss):
    w = _linked_world(scm_app)
    fake_ss.answers[UNLINK] = _UNLINK_DONE
    resp = w["c"].post(f"{OI}/po-link/unlink", json={
        "row_ids": _ids(w, "a", "b", "c"), "po_line_ids": [w["linked"].id]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"][0]["outcome"] == "done"
    (body,) = fake_ss.bodies(UNLINK)
    assert (body["poDocKey"], body["poDtlKey"]) == (12100, 12101)


def test_oi_change_unlinks_first_then_links(scm_app, fake_ss):
    w = _linked_world(scm_app)
    fake_ss.answers[UNLINK] = _UNLINK_DONE
    fake_ss.answers[PO_LINKS] = _done_split
    resp = w["c"].post(f"{OI}/po-link/change", json={
        "row_ids": _ids(w, "a", "b", "c"),
        "changes": [{"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id}],
    })
    assert resp.status_code == 200, resp.text
    writes = [r.url.path for r in fake_ss.calls if r.url.path in (UNLINK, PO_LINKS)]
    assert writes == [UNLINK, PO_LINKS]
    assert {r.get("action") for r in resp.json()["results"]} >= {"unlink", "link"}


# --------------------------------------------------------------------------- AC-10 switch + permission


def test_switch_off_refuses_every_oi_po_link_route_and_sends_nothing(scm_app, fake_ss):
    w = _oi_world(scm_app)
    _switch(w["db"], False)
    rows = _ids(w, "a")
    calls = [
        w["c"].post(f"{OI}/po-link/options", json={"row_ids": rows}),
        w["c"].post(f"{OI}/po-link/link", json={"row_ids": rows, "lines": [_item(w, qty=10)]}),
        w["c"].post(f"{OI}/po-link/unlink", json={"row_ids": rows, "po_line_ids": [w["po_line"].id]}),
        w["c"].post(f"{OI}/po-link/change", json={"row_ids": rows, "changes": [
            {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id}]}),
    ]
    for resp in calls:
        assert resp.status_code == 403, resp.text
        assert "switched off" in resp.text
    assert fake_ss.calls == []


def test_without_the_link_permission_every_oi_po_link_route_is_403(scm_app, fake_ss):
    w = _oi_world(scm_app, permissions=(VIEW, PROJECTS_VIEW))
    rows = _ids(w, "a")
    calls = [
        w["c"].post(f"{OI}/po-link/options", json={"row_ids": rows}),
        w["c"].post(f"{OI}/po-link/link", json={"row_ids": rows, "lines": [_item(w, qty=10)]}),
        w["c"].post(f"{OI}/po-link/unlink", json={"row_ids": rows, "po_line_ids": [w["po_line"].id]}),
        w["c"].post(f"{OI}/po-link/change", json={"row_ids": rows, "changes": [
            {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id}]}),
    ]
    assert [r.status_code for r in calls] == [403, 403, 403, 403]
    assert fake_ss.bodies(PO_LINKS) == []


# --------------------------------------------------------------------------- AC-3a / AC-3b actor trace


def _actor_name(w):
    return w["db"].execute(text("SELECT name FROM users WHERE id = :i"), {"i": w["uid"]}).scalar()


def _assert_actor_headers(w, fake_ss, path):
    from urllib.parse import quote

    sent = fake_ss.headers(path)
    assert sent, f"no call reached {path}"
    for h in sent:
        assert h.get("X-Request-ID")
        assert h.get("X-Acting-User-Id") == w["uid"]
        assert h.get("X-Acting-User-Name") == quote(_actor_name(w), safe="")
        assert h.get("X-Actor-User-Id") is None and h.get("X-Actor-Name") is None


def test_one_press_carries_one_request_id_on_every_call(scm_app, fake_ss):
    w = _oi_world(scm_app)
    fake_ss.answers[PO_LINKS] = _two_step_answer()
    assert _oi_link(w, [_item(w, "so_line", 120), _item(w, "other", 30)]).status_code == 200
    ids = [h.get("X-Request-ID") for h in fake_ss.headers(PO_LINKS)]
    assert len(ids) == 2 and ids[0] and ids[0] == ids[1]
    _assert_actor_headers(w, fake_ss, PO_LINKS)


def test_a_name_with_a_space_and_a_non_ascii_character_is_percent_encoded(scm_app, fake_ss):
    w = _oi_world(scm_app)
    w["db"].execute(text("UPDATE users SET name = :n WHERE id = :i"), {"n": "Nur Aisyah Zoë", "i": w["uid"]})
    w["db"].flush()
    fake_ss.answers[PO_LINKS] = _TIMEOUT
    assert _oi_link(w, [_item(w, qty=10)], rows=("a",)).status_code == 200
    (h,) = fake_ss.headers(PO_LINKS)
    assert h["X-Acting-User-Name"] == "Nur%20Aisyah%20Zo%C3%AB"
    assert h["X-Acting-User-Id"] == w["uid"]


def test_actor_headers_ride_every_write_from_both_screens(scm_app, fake_ss):
    w = _oi_world(scm_app, snapshot=True)
    fake_ss.answers[PO_LINKS] = _TIMEOUT
    assert _snap_link(w, [_item(w, qty=10)]).status_code == 200
    _assert_actor_headers(w, fake_ss, PO_LINKS)
    fake_ss.calls.clear()
    assert _oi_link(w, [_item(w, qty=10)], rows=("a",)).status_code == 200
    _assert_actor_headers(w, fake_ss, PO_LINKS)

    fake_ss.calls.clear()
    w2 = _linked_world(scm_app)
    fake_ss.answers[UNLINK] = _UNLINK_DONE
    w2["c"].post(f"{OI}/po-link/unlink", json={"row_ids": _ids(w2, "a"), "po_line_ids": [w2["linked"].id]})
    _assert_actor_headers(w2, fake_ss, UNLINK)


def test_every_write_logs_one_audit_event_on_the_po_line(scm_app, fake_ss):
    from app.models.audit import AuditLog

    w = _oi_world(scm_app)
    fake_ss.answers[PO_LINKS] = _done_split
    assert _oi_link(w, [_item(w, qty=120)], rows=("a",)).status_code == 200
    request_id = fake_ss.headers(PO_LINKS)[0].get("X-Request-ID")
    db = w["db"]
    db.flush()
    events = (
        db.query(AuditLog)
        .filter(AuditLog.event == "scm.po_line.crm_link_write", AuditLog.entity_id == w["po_line"].id)
        .all()
    )
    assert len(events) == 1
    (event,) = events
    assert event.entity_type == "purchase_order_lines"
    assert event.user_id == w["uid"]
    new = event.new_values
    assert new["request_id"] == request_id
    assert new["operation_id"] == "op-1"
    assert new["outcome"] == "done" and new["qty"] in (120, 120.0, "120")
    assert new["action"]
