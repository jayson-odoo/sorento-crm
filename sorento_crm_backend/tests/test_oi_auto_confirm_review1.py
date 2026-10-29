"""OI-AUTO-CONFIRM review round 1, backend (lead rulings, fixed contract).

Reviewer verdict NOT READY on PR #1986. Rulings pinned here, each traced to the UAC
(`documentation/plans/scm/oi-auto-confirm-29oct-acceptance-criteria.md`):

1. A reserve is NOT a document link (AC-AC-10b, blocker 2): `links_for_rows` returns no entry
   for it; the worklist row carries `reserve_label` ("Reserved @ <warehouse code>") beside
   `reserved_qty`; `linked_qty` is the documents only (40), `reserve_requestable_qty` is 49.
2. Item swap (AC-AC-10, blocker 3): a link counts as cover only while its PO line / SPO
   allocation product is the row's CURRENT item. Reserve links: no product check.
3. Cancelled SO line (lead ruling c, AC-AC-9/AC-AC-15): a live row on a cancelled core SO line
   with no live link is done; with a live link it is NOT done until a manual Confirm.
4. `open_qty` (should-fix 7) on worklist rows and OI detail lines.
5. Companion (AC-AC-10a, nit 9).
6. Confirm writes ONE audit row per batch (security N1).
7. Hook coverage (should-fix 4): SPO retire / revive, AutoCount cancel doc, PO push, sheet import.

Postgres only; every test seeds its own chain.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.audit import AuditLog
from app.models.base import company_scope
from app.models.procurement import PurchaseOrderLine, SPOAllocation
from app.models.product import Product
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    INQUIRY_RAISED,
    OrderInquiry,
    OrderInquiryLink,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from ._pg_fixture import blank_session
from .test_ac_removed_lines_spo_ingest import _push_spo, _repush, _row_on_spo, _snapshot
from .test_ingest_documents import (  # noqa: F401  (env is a fixture)
    INGEST_PO,
    _po_line,
    _po_record,
    env,
)
from .test_oi_auto_confirm import (
    _assert_done_by_system,
    _new_user,
    _p,
    _reload,
    bundle_world,  # noqa: F401  (fixture)
)
from .test_oi_cancelled_line_used_confirm import _inquiry, _line_chain, _oi_row
from .test_order_inquiry_handshake import (  # noqa: F401  (fixtures + helpers)
    LIST as HS_LIST,
    _open_po_line,
    _raise_one_row,
    api,
    world,
)
from .test_order_inquiry_kinds import _link, _product, _sorento, _spo_allocation, _uid
from .test_order_inquiry_reserve import (  # noqa: F401  (fixtures + helpers)
    LIST,
    WL_MARKER,
    _line_on_authored_order,
    _purchase_order,
    _row,
    _user,
    worklist_api,
)
from .test_planning_changes import _warehouse

BASE = "/api/v1/project-sales"


def _open(item) -> Decimal:
    assert "open_qty" in item, "the row carries open_qty"
    return Decimal(str(item["open_qty"]))


ACK_URL = f"{BASE}/order-inquiries/acknowledge"


# =============================================================================================
# 1 + 4. A reserve is not a document link; worklist row fields
# =============================================================================================


def _reserve_scene(worklist_api):
    """Row qty 139: PO link 40 + CS reserve 50 (the reviewer's measured case), plus a row
    with nothing reserved, a row whose only link died (PO line cancelled) and a row with
    3 bundled. All on one April month so one worklist call reads them."""
    client, db, company_id, seeded = worklist_api
    inquiry = db.get(OrderInquiry, seeded["authored_row"].order_inquiry_id)

    def _line_row(qty, day, tag, **fields):
        line = _line_on_authored_order(db, company_id, seeded, qty=qty, day=day)
        return _row(
            db, company_id, inquiry, so_line_id=line.id, item_code=f"{WL_MARKER}-{tag}",
            qty=qty, delivery_date=date(2026, 4, day), **fields,
        )

    po_line = _purchase_order(db, company_id)["line"]
    reserved_row = _line_row("139", 6, "R1BASE", po_line_id=po_line.id)
    # the PO link is 40 of 139
    link = db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == reserved_row.id).one()
    link.qty = Decimal("40")
    plain_row = _line_row("20", 7, "R1PLAIN")
    dead_line = _purchase_order(db, company_id)["line"]
    dead_row = _line_row("10", 8, "R1DEAD", po_line_id=dead_line.id)
    dead_line.line_status = "cancelled"
    # a REAL companion rule so `derive_bundles` (run by the reserve commit below) keeps
    # bundled_qty: 3 hosts at ratio 1 bundle 3 of the companion's 10
    from app.models.product_companion import ProductCompanionRule, ProductCompanionRuleHost
    from .test_order_inquiry_worklist import _product as _wl_product

    companion_product = _wl_product(db, f"{WL_MARKER}-R1BUND", "r1 companion")
    host_product = _wl_product(db, f"{WL_MARKER}-R1HOST", "r1 host")
    companion_product.company_id = company_id
    host_product.company_id = company_id
    db.flush()
    rule = ProductCompanionRule(
        id=_uid(), company_id=company_id, companion_product_id=companion_product.id,
        supplier_id=None, ratio=Decimal("1"), is_active=True,
    )
    db.add(rule)
    db.flush()
    db.add(ProductCompanionRuleHost(rule_id=rule.id, host_product_id=host_product.id))
    db.flush()
    _line_row("3", 11, "R1HOST")
    bundled_row = _line_row("10", 9, "R1BUND")
    db.commit()

    warehouse = _warehouse(db, f"ZZT-{_uid()[:6]}".upper())
    from app.services.order_inquiry_reserve_service import OrderInquiryReserveService

    service = OrderInquiryReserveService(db)
    service.create_request(
        inquiry_id=inquiry.id,
        rows=[{"row_id": reserved_row.id, "qty_requested": Decimal("99"),
               "warehouse_id": warehouse.id}],
        note=None,
        actor_user_id=_user(db, f"{WL_MARKER} requester r1"),
    )
    db.commit()
    service.commit_request(
        inquiry_id=inquiry.id,
        reserves=[{"row_id": reserved_row.id, "warehouse_id": warehouse.id,
                   "qty_reserved": Decimal("50"), "reason": "BRW only has 50 in stock"}],
        amendments=[],
        actor_user_id=_user(db, f"{WL_MARKER} reserver r1"),
    )
    db.commit()
    body = client.get(LIST, params={"delivery_month": "2026-04"}).json()
    by_id = {entry["id"]: entry for entry in body["data"]}
    return db, warehouse, by_id, reserved_row, plain_row, dead_row, bundled_row


def test_ac_ac_10b_the_worklist_row_names_the_reserve_beside_reserved_qty_not_as_a_link(
    worklist_api,
):
    _db, warehouse, by_id, reserved_row, plain_row, _dead, _bundled = _reserve_scene(
        worklist_api
    )
    item = by_id[reserved_row.id]

    assert item["reserved_qty"] == "50"
    assert item.get("reserve_label") == f"Reserved @ {warehouse.warehouse_code}", item.get(
        "reserve_label"
    )
    assert by_id[plain_row.id].get("reserve_label") is None
    assert "reserve_label" in by_id[plain_row.id], "null when nothing is reserved, but on the wire"
    assert not [l for l in item["links"] if l.get("kind") == "reserve"], item["links"]


def test_ac_ac_10b_linked_qty_is_documents_only_and_requestable_is_139_less_40_less_50(
    worklist_api,
):
    _db, _wh, by_id, reserved_row, _plain, _dead, _bundled = _reserve_scene(worklist_api)
    item = by_id[reserved_row.id]

    assert item["linked_qty"] == "40", "a reserve is not a document link"
    assert item["reserve_requestable_qty"] == 49, item["reserve_requestable_qty"]
    assert item["taken_from_po"] == "90"
    assert item["remaining_open"] == "49"


def test_open_qty_is_qty_less_live_links_less_bundled_never_below_zero(worklist_api):
    """Should-fix 7. Live = PO line not cancelled, SPO not retired; the reserve counts, a
    dead link does not, bundled_qty is taken off."""
    _db, _wh, by_id, reserved_row, plain_row, dead_row, bundled_row = _reserve_scene(
        worklist_api
    )

    assert _open(by_id[reserved_row.id]) == Decimal("49")
    assert _open(by_id[plain_row.id]) == Decimal("20")
    assert _open(by_id[dead_row.id]) == Decimal("10"), "dead link"
    assert _open(by_id[bundled_row.id]) == Decimal("7"), "10 less 3"


def test_open_qty_is_floored_at_zero_on_an_over_covered_row(worklist_api):
    client, db, company_id, seeded = worklist_api
    inquiry = db.get(OrderInquiry, seeded["authored_row"].order_inquiry_id)
    line = _line_on_authored_order(db, company_id, seeded, qty="10", day=10)
    po_line = _purchase_order(db, company_id)["line"]
    row = _row(
        db, company_id, inquiry, so_line_id=line.id, item_code=f"{WL_MARKER}-R1OVER", qty="10",
        delivery_date=date(2026, 4, 10), po_line_id=po_line.id,
    )
    db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row.id).one().qty = Decimal("14")
    db.commit()

    body = client.get(LIST, params={"delivery_month": "2026-04"}).json()
    item = next(entry for entry in body["data"] if entry["id"] == row.id)

    assert _open(item) == Decimal("0")


def test_the_oi_detail_lines_carry_open_qty(api):
    client, w = api
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]
    _po, line = _open_po_line(w, qty=50)
    ProjectOrderInquiryService(w.db).place_on_po_allocations(
        str(row.id), [{"po_line_id": str(line.id), "qty": "6"}], actor_user_id=None
    )
    w.db.commit()

    body = client.get(f"{BASE}/sales-orders/{fixture['order'].id}/order-inquiry").json()
    item = next(entry for entry in body["rows"] if entry["id"] == str(row.id))

    assert _open(item) == Decimal("4"), item.get("open_qty")


# =============================================================================================
# 3. Cancelled SO line
# =============================================================================================


def _cancelled_line_row(db, *, ack_state=ACK_AWAITING, line_status="cancelled", linked=False):
    company_id = _sorento(db)
    product = _product(db, f"ZZT-CC-{_uid()[:6]}", "zzt cancelled line")
    _so, _core, pso, mirror = _line_chain(
        db, company_id, product, qty="10", line_status=line_status
    )
    inquiry = _inquiry(db, company_id, pso.id)
    row = _oi_row(
        db, company_id, inquiry.id, mirror.id, product.product_code, "10",
        delivery_date=date(2026, 1, 15), state=INQUIRY_RAISED, ack_state=ack_state,
    )
    if linked:
        allocation = _spo_allocation(db, company_id, product, qty=10)
        _link(db, company_id, row.id, "10", spo_allocation_id=allocation.id,
              document=allocation.spo_number)
    db.flush()
    return company_id, row


def test_a_live_row_on_a_cancelled_line_with_no_live_link_is_done():
    with blank_session() as db:
        company_id, row = _cancelled_line_row(db)
        with company_scope(db, frozenset({company_id})):
            ProjectOrderInquiryService(db).auto_confirm([row.id])
        _assert_done_by_system(_reload(db, row))


def test_a_cancelled_line_row_that_was_acknowledged_stays_done_without_a_link():
    with blank_session() as db:
        company_id, row = _cancelled_line_row(db, ack_state=ACK_ACKNOWLEDGED)
        with company_scope(db, frozenset({company_id})):
            ProjectOrderInquiryService(db).auto_confirm([row.id])
        assert _reload(db, row).ack_state == ACK_ACKNOWLEDGED


@pytest.mark.parametrize("before", [ACK_AWAITING, ACK_ACKNOWLEDGED, ACK_CHANGED])
def test_a_cancelled_line_row_with_a_live_link_is_not_done_whatever_the_auto_rule_runs(before):
    with blank_session() as db:
        company_id, row = _cancelled_line_row(db, ack_state=before, linked=True)
        svc = ProjectOrderInquiryService(db)
        with company_scope(db, frozenset({company_id})):
            svc.auto_confirm([row.id])
            svc.refresh_link_state([row])
            svc.auto_confirm([row.id])
        _reload(db, row)
        assert row.ack_state in (ACK_AWAITING, ACK_CHANGED), row.ack_state
        assert row.acknowledged_at is None


def test_a_manual_confirm_finishes_a_cancelled_line_row_that_holds_a_live_link():
    with blank_session() as db:
        company_id, row = _cancelled_line_row(db, linked=True)
        buyer = _new_user(db)
        svc = ProjectOrderInquiryService(db)
        with company_scope(db, frozenset({company_id})):
            svc.auto_confirm([row.id])
            assert _reload(db, row).ack_state != ACK_ACKNOWLEDGED
            svc.acknowledge_rows([row.id], actor_user_id=buyer)
            assert _reload(db, row).ack_state == ACK_ACKNOWLEDGED
            svc.auto_confirm([row.id])
        assert _reload(db, row).ack_state == ACK_ACKNOWLEDGED, "the manual Confirm sticks"
        assert row.ack_override == "confirmed"


def test_an_open_line_with_a_live_link_is_still_done_the_cancelled_rule_is_not_general():
    with blank_session() as db:
        company_id, row = _cancelled_line_row(db, line_status="open", linked=True)
        with company_scope(db, frozenset({company_id})):
            ProjectOrderInquiryService(db).auto_confirm([row.id])
        _assert_done_by_system(_reload(db, row))


def _flag_cancelled_line(db, company_id, row):
    """The AutoCount line-cancel ingest's own call: the row's core line just transitioned."""
    from app.models.project_so import ProjectSalesOrderLine
    from app.services.project_order_inquiry_service import flag_rows_for_cancelled_lines

    mirror = db.get(ProjectSalesOrderLine, row.so_line_id)
    with company_scope(db, frozenset({company_id})):
        flag_rows_for_cancelled_lines(db, [str(mirror.core_sales_order_line_id)])
    db.flush()


def test_ac_ac_10e_the_cancel_flag_leaves_a_linkless_acknowledged_row_done():
    with blank_session() as db:
        company_id, row = _cancelled_line_row(db, ack_state=ACK_ACKNOWLEDGED)
        _flag_cancelled_line(db, company_id, row)
        _reload(db, row)
        assert row.ack_state == ACK_ACKNOWLEDGED, "nothing to order on a cancelled line"
        assert row.acknowledged_by is None


def test_ac_ac_10e_the_cancel_flag_reopens_a_linked_row_and_a_later_auto_confirm_keeps_it():
    with blank_session() as db:
        company_id, row = _cancelled_line_row(db, ack_state=ACK_ACKNOWLEDGED, linked=True)
        _flag_cancelled_line(db, company_id, row)
        assert _reload(db, row).ack_state == ACK_CHANGED
        svc = ProjectOrderInquiryService(db)
        with company_scope(db, frozenset({company_id})):
            svc.refresh_link_state([row])
            svc.auto_confirm([row.id])
        assert _reload(db, row).ack_state == ACK_CHANGED, "a later link write must not finish it"


def test_ac_ac_10e_a_manual_confirm_finishes_the_flagged_linked_row():
    with blank_session() as db:
        company_id, row = _cancelled_line_row(db, ack_state=ACK_ACKNOWLEDGED, linked=True)
        _flag_cancelled_line(db, company_id, row)
        assert _reload(db, row).ack_state == ACK_CHANGED
        buyer = _new_user(db)
        svc = ProjectOrderInquiryService(db)
        with company_scope(db, frozenset({company_id})):
            svc.acknowledge_rows([row.id], actor_user_id=buyer)
        assert _reload(db, row).ack_state == ACK_ACKNOWLEDGED
        assert row.ack_override == "confirmed"


# =============================================================================================
# 5. Companion follows the host's real standing
# =============================================================================================


def test_a_manually_confirmed_host_with_no_link_makes_its_companion_done(bundle_world):
    w = bundle_world
    w.rule("CKSW015", ["CKS1050"], supplier=None, ratio="1")
    host = w.row("CKS1050", 1, ack_state=ACK_AWAITING)
    companion = w.row("CKSW015", 1, ack_state=ACK_AWAITING)
    w.svc.derive_bundles(w.inquiry)
    w.db.flush()
    buyer = _new_user(w.db)

    w.svc.acknowledge_rows([host.id], actor_user_id=buyer)
    w.db.flush()

    assert _reload(w.db, host).ack_state == ACK_ACKNOWLEDGED
    assert host.ack_override == "confirmed"
    _assert_done_by_system(_reload(w.db, companion))


def test_a_rejected_host_does_not_make_its_companion_done(bundle_world):
    w = bundle_world
    w.rule("CKSW015", ["CKS1050"], supplier=None, ratio="1")
    host = w.row("CKS1050", 1, ack_state=ACK_AWAITING)
    companion = w.row("CKSW015", 1, ack_state=ACK_AWAITING)
    w.svc.derive_bundles(w.inquiry)
    w.db.flush()
    assert _reload(w.db, companion).bundled_with_row_id == host.id
    w.svc.reject_row(host.id, reason="not buying this", actor_user_id=_new_user(w.db))
    w.db.flush()
    w.db.refresh(host)
    assert host.ack_state == "rejected"

    w.svc.auto_confirm([host.id, companion.id])
    w.db.flush()
    assert _reload(w.db, companion).ack_state == ACK_AWAITING, "a rejected host is not cover"

    w.svc.derive_bundles(w.inquiry)
    w.svc.refresh_link_state([host, companion])
    w.db.flush()
    assert _reload(w.db, companion).bundled_qty == Decimal("0"), "a rejected host bundles nothing"
    assert companion.ack_state == ACK_AWAITING, "falls back to its own cover: none"


# =============================================================================================
# 6. Confirm writes one audit row per batch
# =============================================================================================


def test_confirm_writes_one_audit_row_per_batch_naming_the_actor_and_the_rows(api):
    from .test_order_inquiry_handshake import _as_purchasing

    _client, w = api
    first = _raise_one_row(api, qty="10")["row"]
    second = _raise_one_row(api, qty="5")["row"]
    ids = [str(first.id), str(second.id)]

    with _as_purchasing(w) as buyer:
        response = buyer.post(ACK_URL, json={"row_ids": ids})
    assert response.status_code == 200, response.text
    w.db.commit()

    entries = [
        entry
        for entry in w.db.query(AuditLog)
        .filter(AuditLog.entity_type == "project_order_inquiry_rows")
        .filter(AuditLog.user_id == w.buyer)
        .all()
        if set(ids) & set((entry.new_values or {}).get("row_ids", []))
    ]
    assert len(entries) == 1, f"one audit row per batch, got {len(entries)}"
    assert set((entries[0].new_values or {})["row_ids"]) == set(ids)
    assert "onfirm" in (entries[0].description or "")


def test_confirm_of_an_already_done_row_writes_no_audit_row(api):
    from .test_order_inquiry_handshake import _as_purchasing

    _client, w = api
    row = _raise_one_row(api, qty="10")["row"]
    _po, line = _open_po_line(w, qty=50)
    ProjectOrderInquiryService(w.db).place_on_po_allocations(
        str(row.id), [{"po_line_id": str(line.id), "qty": "10"}], actor_user_id=None
    )
    w.db.commit()

    with _as_purchasing(w) as buyer:
        assert buyer.post(ACK_URL, json={"row_ids": [str(row.id)]}).status_code == 200
    w.db.commit()

    entries = w.db.query(AuditLog).filter(
        AuditLog.entity_type == "project_order_inquiry_rows"
    ).filter(AuditLog.user_id == w.buyer).all()
    named = [e for e in entries if str(row.id) in (e.new_values or {}).get("row_ids", [])]
    assert named == [], "nothing moved, so nothing is audited"


# =============================================================================================
# 7. Hook coverage (kill-test guards)
# =============================================================================================


def test_hook_an_spo_line_retired_by_the_ingest_reopens_its_fully_covered_row(env, monkeypatch):
    from .test_ac_removed_lines_ingest import Quiet

    w = _push_spo(env)
    row_id, inquiry_id, _ = _row_on_spo(env, w, links=[(w.alloc_a, 10)])
    Quiet(env, monkeypatch)

    _repush(env, w, lines=[w.payload_b])

    after = _snapshot(env, row_id, inquiry_id)
    assert after["ack_state"] == ACK_AWAITING, after


def test_hook_a_revived_spo_line_makes_its_row_done_again(env, monkeypatch):
    from .test_ac_removed_lines_ingest import Quiet

    w = _push_spo(env)
    row_id, inquiry_id, _ = _row_on_spo(env, w, links=[(w.alloc_a, 10)])
    # A retirement that keeps the placement (LINKAGE-UNIFY U3: the link stays listed).
    env.db.execute(
        text("UPDATE spo_allocations SET retired_at = now() WHERE id = :i"), {"i": w.alloc_a}
    )
    env.db.execute(
        text("UPDATE " + _p() + ".order_inquiry_rows SET ack_state = 'awaiting', "
             "acknowledged_at = NULL WHERE id = :i"),
        {"i": row_id},
    )
    env.db.commit()
    Quiet(env, monkeypatch)

    _repush(env, w, lines=[w.payload_a, w.payload_b])

    after = _snapshot(env, row_id, inquiry_id)
    assert after["ack_state"] == ACK_ACKNOWLEDGED, after


def test_hook_a_po_push_that_leaves_a_row_fully_linked_makes_it_done(env):
    line = _po_line(env, qty_ordered=10)
    record = _po_record(env, lines=[line], supplier_ref=env.supplier_ref)
    assert env.post(INGEST_PO, [record]).status_code == 200
    header = env.header("purchase_orders", record["source_ref"])
    pol = env.po_lines(header["id"])[0]
    product = env.db.get(Product, str(pol["product_id"]))
    _so, _core, pso, mirror = _line_chain(env.db, env.company_a, product, qty="10")
    inquiry = _inquiry(env.db, env.company_a, pso.id)
    row = _oi_row(env.db, env.company_a, inquiry.id, mirror.id, product.product_code, "10",
                  ack_state=ACK_AWAITING)
    _link(env.db, env.company_a, row.id, "10", po_line_id=str(pol["id"]),
          document=header["po_number"])
    env.db.commit()

    res = env.post(INGEST_PO, [dict(record, lines=[dict(line, qty_ordered=12)])])
    assert res.status_code == 200, res.text
    env.db.expire_all()

    _assert_done_by_system(_reload(env.db, row))


def test_hook_a_sheet_import_row_born_with_no_link_is_awaiting():
    from .test_project_order_inquiry_import_migration import D_OCT, sheet, world as mig_world

    with mig_world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        row = w.one_row()
        assert row.ack_state == ACK_AWAITING, "no link: To order"
        assert row.acknowledged_by is None
        assert row.acknowledged_at is None
