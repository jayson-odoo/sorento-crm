"""STANDARD-HISTORY wave 1: one OI's History tab read
(`documentation/plans/audit/PLAN-standard-history-10nov.md`, UAC AC-SH-B1 to B7).

`GET /api/v1/project-sales/order-inquiry-headers/{inquiry_id}/history` merges the OI's own
trails into one newest-first list. The trigger case is OI-2611-0019: one Confirm on one row,
then one Unconfirm 8 s later that moved 9 rows, which no screen showed. Confirm / Unconfirm
are driven through the real service calls so the audit rows are the ones production writes.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from app.models.audit import AuditLog
from app.models.project_so import (
    INQUIRY_CANCELLED,
    OI_RAISE_RAISED,
    OrderInquiryRaise,
    OrderInquiryReleasedLink,
    OrderInquiryReserveEvent,
    OrderInquiryReserveRequest,
    OrderInquiryReserveRequestRow,
    RESERVE_EVENT_RESERVED,
)
from app.services.audit_service import log_audit
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from ._pg_fixture import blank_session
from .test_order_inquiry_worklist_raised_by import (
    READ_ONLY,
    _adopted_order,
    _client,
    _inquiry,
    _line,
    _product,
    _restore,
    _row,
    _sorento,
    _uid,
    _user,
)

BASE = "/api/v1/project-sales"
RAISED_AT = datetime(2026, 11, 2, 9, 31)


def _url(inquiry_id: str) -> str:
    return f"{BASE}/order-inquiry-headers/{inquiry_id}/history"


def _world(db, *, item_codes=("ZZT-SRTSP131", "ZZT-CKS1050", "ZZT-SRT320-CR")):
    company_id = _sorento(db)
    cs = _user(db, "ZZT CS Person", f"cs.{_uid()[:8]}@zzt.test")
    buyer = _user(db, "ZZT Purchasing Person", f"buy.{_uid()[:8]}@zzt.test")
    order = _adopted_order(db, company_id, f"ZZTSO{_uid()[:8]}")
    product = _product(db, f"ZZT-{_uid()[:6]}")
    line = _line(db, company_id, order, product)
    inquiry = _inquiry(db, company_id, order, raised_by=cs.id, raised_at=RAISED_AT)
    db.add(
        OrderInquiryRaise(
            id=_uid(), company_id=company_id, order_inquiry_id=inquiry.id,
            kind=OI_RAISE_RAISED, raised_by=cs.id, raised_at=RAISED_AT,
        )
    )
    rows = []
    for code in item_codes:
        row = _row(db, company_id, inquiry, line, code)
        row.created_at = RAISED_AT
        rows.append(row)
    db.flush()
    return {
        "company_id": company_id, "cs": cs, "buyer": buyer, "order": order,
        "line": line, "inquiry": inquiry, "rows": rows, "product": product,
    }


def _other_inquiry(db, world, item_code):
    """A second OI (its own order: one OI per sales order) with one row."""
    order = _adopted_order(db, world["company_id"], f"ZZTSO{_uid()[:8]}")
    line = _line(db, world["company_id"], order, world["product"])
    inquiry = _inquiry(db, world["company_id"], order, raised_by=world["cs"].id, raised_at=RAISED_AT)
    return _row(db, world["company_id"], inquiry, line, item_code)


def _get(db, user_id, inquiry_id, permissions=READ_ONLY):
    client, originals = _client(db, user_id, permissions)
    try:
        return client.get(_url(inquiry_id))
    finally:
        _restore(originals)


def _events(db, world):
    response = _get(db, world["buyer"].id, world["inquiry"].id)
    assert response.status_code == 200, response.text
    return response.json()["events"]


def test_confirm_then_unconfirm_are_one_event_each_listing_every_row_newest_first():
    """AC-SH-B1, B2: the OI-2611-0019 shape - a 1-row Confirm, then an Unconfirm that moved
    every confirmed row in one press."""
    with blank_session() as db:
        world = _world(db)
        rows = world["rows"]
        service = ProjectOrderInquiryService(db)
        # Two rows already confirmed earlier, then the 1-row Confirm, then the Unconfirm.
        service.acknowledge_rows([rows[1].id, rows[2].id], actor_user_id=world["cs"].id)
        db.flush()
        service.acknowledge_rows([rows[0].id], actor_user_id=world["buyer"].id)
        db.flush()
        service.unacknowledge_rows([r.id for r in rows], actor_user_id=world["buyer"].id)
        db.commit()
        # Pin the press times so "newest first" is not decided by insert order alone.
        audits = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "project_order_inquiry_rows")
            .filter(AuditLog.entity_id.in_([r.id for r in rows]))
            .order_by(AuditLog.changed_at)
            .all()
        )
        assert len(audits) == 3

        events = _events(db, world)

        for event in events:
            assert set(event) == {"id", "kind", "at", "actor", "title", "lines"}
            for entry in event["lines"]:
                assert set(entry) == {"row_id", "so_line_no", "item_code", "qty", "change"}

        presses = [e for e in events if e["kind"] in ("confirmed", "unconfirmed")]
        assert [e["kind"] for e in presses] == ["unconfirmed", "confirmed", "confirmed"]

        unconfirm = presses[0]
        assert unconfirm["title"] == "Unconfirmed 3 lines, back to To confirm"
        assert unconfirm["actor"] == "ZZT Purchasing Person"
        assert {e["row_id"] for e in unconfirm["lines"]} == {r.id for r in rows}
        assert {e["change"] for e in unconfirm["lines"]} == {"Confirmed → To confirm"}

        one_confirm = presses[1]
        # STANDARD-HISTORY v2: a one-line press names its item, in one plain sentence.
        assert one_confirm["title"] == "Confirmed ZZT-SRTSP131"
        assert [e["item_code"] for e in one_confirm["lines"]] == ["ZZT-SRTSP131"]
        assert one_confirm["lines"][0]["change"] == "To confirm → Confirmed"
        assert one_confirm["lines"][0]["so_line_no"] == 1

        ats = [e["at"] for e in events]
        assert ats == sorted(ats, reverse=True)


def test_a_press_filed_under_another_ois_row_is_found_and_never_leaks_that_oi():
    """AC-SH-B2, B3: a worklist Confirm across two OIs writes ONE audit row filed under the
    first row id - here the OTHER OI's row. This OI still sees the press, with only its
    own row in it."""
    with blank_session() as db:
        world = _world(db, item_codes=("ZZT-MINE",))
        foreign = _other_inquiry(db, world, "ZZT-OTHER-OI")
        mine = world["rows"][0]
        db.flush()
        # Exactly the row `acknowledge_rows` writes for a two-OI press
        # (project_order_inquiry_service.py, the Confirm `log_audit`), filed under the
        # OTHER OI's row - which row comes first is the query's order, so it is pinned here.
        log_audit(
            db, "project_order_inquiry_rows", foreign.id, "UPDATE",
            old_values={"rows": [{"id": foreign.id, "ack_state": "awaiting"},
                                 {"id": mine.id, "ack_state": "awaiting"}]},
            new_values={"ack_state": "acknowledged", "row_ids": [foreign.id, mine.id]},
            user_id=world["buyer"].id, company_id=world["company_id"],
            description="Confirm: 2 row(s) marked Done by hand",
        )
        db.commit()

        response = _get(db, world["buyer"].id, world["inquiry"].id)
        assert response.status_code == 200, response.text
        assert "ZZT-OTHER-OI" not in response.text
        assert foreign.id not in response.text
        confirms = [e for e in response.json()["events"] if e["kind"] == "confirmed"]
        assert len(confirms) == 1
        assert confirms[0]["title"] == "Confirmed ZZT-MINE"
        assert [e["item_code"] for e in confirms[0]["lines"]] == ["ZZT-MINE"]


def test_a_press_on_one_oi_stamps_that_oi_as_root_and_a_press_across_two_does_not():
    """AC-SH-B7 (owner Q3)."""
    with blank_session() as db:
        world = _world(db, item_codes=("ZZT-A", "ZZT-B"))
        service = ProjectOrderInquiryService(db)
        service.acknowledge_rows([r.id for r in world["rows"]], actor_user_id=world["buyer"].id)
        db.flush()
        service.unacknowledge_rows([world["rows"][0].id], actor_user_id=world["buyer"].id)
        db.flush()
        for audit in (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "project_order_inquiry_rows")
            .filter(AuditLog.entity_id.in_([r.id for r in world["rows"]]))
            .all()
        ):
            assert audit.root_entity_type == "project_order_inquiries"
            assert audit.root_entity_id == world["inquiry"].id

        foreign = _other_inquiry(db, world, "ZZT-C")
        db.flush()
        # rows[1] is still confirmed, so take a fresh pair: one row of each OI.
        service.unacknowledge_rows([world["rows"][1].id], actor_user_id=world["buyer"].id)
        db.flush()
        service.acknowledge_rows([foreign.id, world["rows"][1].id], actor_user_id=world["buyer"].id)
        db.flush()
        across = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "project_order_inquiry_rows")
            .filter(AuditLog.new_values["row_ids"].has_key(foreign.id))
            .one()
        )
        # The default root: the audit row's own entity (whichever row came first).
        assert across.root_entity_type == "project_order_inquiry_rows"
        assert across.root_entity_id == across.entity_id


def test_raise_link_release_reject_cancel_and_reserve_are_events_too():
    """AC-SH-B4."""
    with blank_session() as db:
        world = _world(db, item_codes=("ZZT-LINKED", "ZZT-REJECTED", "ZZT-CANCELLED", "ZZT-RES"))
        linked, rejected, cancelled, reserved = world["rows"]
        company_id = world["company_id"]
        buyer = world["buyer"]

        from app.models.procurement import PurchaseOrder, PurchaseOrderLine
        from app.models.project_so import OrderInquiryLink

        po = PurchaseOrder(
            id=_uid(), company_id=company_id, po_number=f"ZZT-PO-{_uid()[:6]}",
            issue_date=datetime(2026, 11, 1).date(), status="active",
        )
        db.add(po)
        db.flush()
        po_line = PurchaseOrderLine(
            id=_uid(), company_id=company_id, purchase_order_id=po.id,
            product_id=world["product"].id, qty_ordered=Decimal("20"),
            qty_received=Decimal("0"), expected_date=datetime(2026, 11, 20).date(),
            line_status="open",
        )
        db.add(po_line)
        db.flush()
        auto_at = datetime(2026, 11, 10, 2, 52)
        db.add(
            OrderInquiryLink(
                id=_uid(), company_id=company_id, row_id=linked.id, po_line_id=po_line.id,
                document=po.po_number, qty=Decimal("4"), linked_by=None, auto=True,
                linked_at=auto_at,
            )
        )
        db.add(
            OrderInquiryReleasedLink(
                id=_uid(), company_id=company_id, row_id=linked.id, po_line_id=po_line.id,
                document="ZZT-PO-OLD", qty=Decimal("2"), released_by=buyer.id,
                released_at=auto_at - timedelta(days=1),
            )
        )
        rejected.ack_state = "rejected"
        rejected.rejected_by = buyer.id
        rejected.rejected_at = datetime(2026, 11, 5, 1, 0)
        rejected.rejected_reason = "No such item"
        cancelled.state = INQUIRY_CANCELLED
        log_audit(
            db, "project_order_inquiry_rows", cancelled.id, "EVENT",
            event="OI_ROW_CANCELLED",
            new_values={"cause": "so_line_removed", "qty": 932, "item_code": cancelled.item_code,
                        "so_line_no": 1},
            user_id=buyer.id, company_id=company_id,
            root_entity_type="project_sales_orders", root_entity_id=world["order"].id,
        )
        request = OrderInquiryReserveRequest(
            id=_uid(), company_id=company_id, order_inquiry_id=world["inquiry"].id, ordinal=1,
            requested_by=buyer.id,
        )
        db.add(request)
        db.flush()
        request_row = OrderInquiryReserveRequestRow(
            id=_uid(), company_id=company_id, request_id=request.id, row_id=reserved.id,
            qty_requested=Decimal("3"),
        )
        db.add(request_row)
        db.flush()
        db.add(
            OrderInquiryReserveEvent(
                id=_uid(), company_id=company_id, reserve_request_row_id=request_row.id,
                kind=RESERVE_EVENT_RESERVED, qty=Decimal("3"), actor_id=buyer.id,
                created_at=datetime(2026, 11, 6, 3, 0),
            )
        )
        db.commit()

        events = _events(db, world)
        by_kind = {}
        for event in events:
            by_kind.setdefault(event["kind"], []).append(event)

        raised = by_kind["raised"][0]
        assert raised["actor"] == "ZZT CS Person"
        assert raised["title"] == "Raised 4 lines"
        assert len(raised["lines"]) == 4

        link = by_kind["linked"][0]
        assert link["actor"] == "Automatic"
        assert link["title"] == f"{po.po_number} linked to ZZT-LINKED"
        assert link["lines"][0]["item_code"] == "ZZT-LINKED"
        assert link["lines"][0]["qty"] == 4

        released = by_kind["unlinked"][0]
        assert released["title"] == "ZZT-PO-OLD released from ZZT-LINKED"
        assert released["actor"] == "ZZT Purchasing Person"
        assert "ZZT-PO-OLD" in released["lines"][0]["change"]

        rejection = by_kind["rejected"][0]
        assert rejection["title"] == "Rejected ZZT-REJECTED"
        assert rejection["lines"][0]["item_code"] == "ZZT-REJECTED"
        assert "No such item" in rejection["lines"][0]["change"]

        cancel = by_kind["cancelled"][0]
        assert cancel["title"] == "Cancelled ZZT-CANCELLED"
        assert cancel["lines"][0]["item_code"] == "ZZT-CANCELLED"

        reserve = by_kind["reserved"][0]
        assert reserve["title"] == "Reserved ZZT-RES"
        assert reserve["lines"][0]["item_code"] == "ZZT-RES"
        assert reserve["lines"][0]["qty"] == 3


def test_no_ip_user_agent_or_raw_json_in_the_response():
    """AC-SH-B6."""
    with blank_session() as db:
        world = _world(db, item_codes=("ZZT-A",))
        ProjectOrderInquiryService(db).acknowledge_rows(
            [world["rows"][0].id], actor_user_id=world["buyer"].id
        )
        db.commit()
        # The press's audit row carries an IP and raw values; none of it may reach the tab.
        audit = db.query(AuditLog).filter(AuditLog.entity_id == world["rows"][0].id).one()
        assert audit.new_values and "row_ids" in audit.new_values
        text = _get(db, world["buyer"].id, world["inquiry"].id).text
        assert '"kind":"confirmed"' in text
        for leaked in ("ip_address", "user_agent", "old_values", "new_values", "row_ids"):
            assert leaked not in text


def test_without_the_view_permission_the_read_is_refused():
    """AC-SH-B5."""
    with blank_session() as db:
        world = _world(db, item_codes=("ZZT-A",))
        db.commit()
        response = _get(db, world["buyer"].id, world["inquiry"].id, permissions=[])
        assert response.status_code == 403, response.text


def test_an_unknown_or_other_company_oi_is_404():
    """AC-SH-B5: the session's own company-scope listener hides another company's OI, so
    the read 404s exactly like the header route."""
    with blank_session() as db:
        world = _world(db, item_codes=("ZZT-A",))
        db.commit()
        assert _get(db, world["buyer"].id, _uid()).status_code == 404

        from app.models.base import set_company_scope

        set_company_scope(db, frozenset({_uid()}))
        response = _get(db, world["buyer"].id, world["inquiry"].id)
        assert response.status_code == 404, response.text


def test_an_empty_company_scope_is_404_not_every_company():
    """AC-SH-B5, fail closed: a session with no company at all reads nothing."""
    with blank_session() as db:
        world = _world(db, item_codes=("ZZT-A",))
        db.commit()
        from app.models.base import set_company_scope

        set_company_scope(db, frozenset())
        assert _get(db, world["buyer"].id, world["inquiry"].id).status_code == 404


def test_an_api_key_principal_is_refused():
    """AC-SH-B5: the route takes a staff session only (`require_permission`, not
    `_with_api_key`), the PO-history ruling for audit reads."""
    with blank_session() as db:
        world = _world(db, item_codes=("ZZT-A",))
        db.commit()
        from fastapi.testclient import TestClient

        from app.database import get_db
        from app.dependencies import get_current_user_or_api_key
        from app.main import app

        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {
            "id": world["buyer"].id, "integration_id": _uid(), "role": "user",
        }
        try:
            response = TestClient(app).get(
                _url(world["inquiry"].id), headers={"X-API-Key": "zzt-not-a-real-key"}
            )
        finally:
            app.dependency_overrides.clear()
        assert response.status_code in (401, 403), response.text
