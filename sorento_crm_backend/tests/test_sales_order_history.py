"""STANDARD-HISTORY wave 2 (lane STANDARD-HISTORY-W2): a sales order's History tab read.

Contract: `documentation/plans/audit/standard-history-10nov-acceptance-criteria.md`
AC-SH-W2-1 to W2-5.

    GET /api/v1/project-sales/sales-orders/{pso_id}/history   (projects.projects.view)
    GET /api/v1/scm/sales-orders/{so_id}/history              (scm.dashboard.view)

Both answer `{events: [...]}` in the wave 1 shape, newest first, from
`app/services/sales_order_history_service.py`. Real shapes (masked): SO423409 revisions,
SO414446 an AutoCount batch of 4 rows by the ESB integration applied by a CS user, SO401624
three refused Confirms, SO329258 four Unconfirm presses of 4 rows each.

Deviation from the card: `uq_projects_so_core_order` allows ONE project SO per core SO, so
"the SCM read merges two project SOs of one core SO" cannot be seeded; the SCM read is tested to
equal the project read for the one it has, and the two OIs of one SO the press test needs are the
base OI plus an amendment OI (`uq_project_order_inquiry_per_amendment`).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

from app.models.audit import AuditLog
from app.models.email_outbox import EmailOutbox
from app.models.notification import Notification
from app.models.planning_change import PlanningChangeBatch, PlanningChangeRow
from app.models.project_so import (
    DECISION_ACTIVE,
    DECISION_SUPERSEDED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryRow,
    SOAmendment,
    SOSupplyDecision,
)
from app.services.audit_service import log_audit
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from ._pg_fixture import blank_session
from .test_order_inquiry_worklist_raised_by import (
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

PSO_URL = "/api/v1/project-sales/sales-orders/{}/history"
SCM_URL = "/api/v1/scm/sales-orders/{}/history"
PSO_PERMS = ["projects.projects.view"]
SCM_PERMS = ["scm.dashboard.view"]

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

T_REV1 = datetime(2026, 9, 28, 9, 0, 0)
T_REV2 = datetime(2026, 9, 30, 10, 0, 0)
T_BATCH = datetime(2026, 10, 27, 9, 7, 0)
T_APPLIED = datetime(2026, 10, 27, 9, 30, 0)
T_REFUSED = datetime(2026, 10, 22, 15, 28, 0)
T_EMAIL = datetime(2026, 10, 1, 11, 0, 30)
T_PRESS = datetime(2026, 9, 23, 8, 0, 0)
T_SPLIT = datetime(2026, 10, 5, 8, 0, 0)
T_STATUS = datetime(2026, 9, 20, 8, 0, 0)
T_OTHER_COLUMN = datetime(2026, 9, 21, 8, 0, 0)
T_CANCEL = datetime(2026, 10, 6, 8, 0, 0)

ITEMS = ("B2155-NL-BLUE", "C-FH14", "CSA150", "CKS1050")


def _audit(db, **fields) -> AuditLog:
    row = AuditLog(id=_uid(), **fields)
    db.add(row)
    db.flush()
    return row


def _world(db):
    """One SO with every source of the History: two supply revisions, a refused Confirm, an
    AutoCount batch, a handover email, 4 Unconfirm presses' worth of rows, a line split, a
    status change, a status-less UPDATE and a manual row cancel."""
    company_id = _sorento(db)
    cs = _user(db, "ZZT CS Person", f"cs.{_uid()[:8]}@zzt.test")
    uploader = _user(db, "ZZT ESB Uploader", f"esb.{_uid()[:8]}@zzt.test")
    buyer = _user(db, "ZZT Purchasing Person", f"buy.{_uid()[:8]}@zzt.test")
    order = _adopted_order(db, company_id, f"ZZTSO{_uid()[:8]}")
    product = _product(db, f"ZZT-{_uid()[:6]}")
    line = _line(db, company_id, order, product)
    inquiry = _inquiry(db, company_id, order, raised_by=cs.id, raised_at=T_REV1)

    dec1 = SOSupplyDecision(
        id=_uid(), company_id=company_id, project_sales_order_id=order.id, revision_no=1,
        state=DECISION_SUPERSEDED, line_snapshots=[], confirmed_by=cs.id,
        confirmed_at=T_REV1, created_at=T_REV1, superseded_at=T_REV2,
    )
    db.add(dec1)
    db.flush()
    dec2 = SOSupplyDecision(
        id=_uid(), company_id=company_id, project_sales_order_id=order.id, revision_no=2,
        state=DECISION_ACTIVE, line_snapshots=[], confirmed_by=cs.id,
        confirmed_at=T_REV2, created_at=T_REV2, supersedes_id=dec1.id,
    )
    db.add(dec2)
    db.flush()
    rows = []
    for code in ITEMS:
        row = _row(db, company_id, inquiry, line, code, decision=dec2)
        row.created_at = T_REV2
        rows.append(row)
    db.flush()

    # A refused Confirm (SO401624): the message is the audit row's `reason`.
    _audit(
        db, entity_type="project_sales_orders", entity_id=order.id, action="EVENT",
        event="CONFIRM_REFUSED", user_id=cs.id, changed_at=T_REFUSED,
        root_entity_type="project_sales_orders", root_entity_id=order.id,
        reason="1 line cannot be confirmed. Nothing was written.",
        new_values={"preview": False, "lines": [{
            "so_line_no": 1, "item_code": "SRTSA-SS", "reason_code": "not_decided",
            "reason": "Not decided", "change": "Qty 10 -> 8"}]},
    )

    # An AutoCount batch (SO414446): uploaded by the ESB user, applied by a CS user.
    batch = PlanningChangeBatch(
        id=_uid(), company_id=company_id, created_at=T_BATCH, created_by=uploader.id,
        applied_at=T_APPLIED, applied_by=cs.id, order_count=1, line_count=4,
    )
    db.add(batch)
    db.flush()
    for n in range(4):
        db.add(PlanningChangeRow(
            id=_uid(), company_id=company_id, batch_id=batch.id,
            project_sales_order_id=order.id, project_line_id=line.id, line_no=1,
            item_code="MCM7833-CR", kind="qty_down", from_json={"qty": 10 + n},
            to_json={"qty": 8}, facts_json={}, applied_state="applied", created_at=T_BATCH,
        ))
    db.flush()

    # The handover email, tied to the OI through its notification.
    notification = Notification(
        id=_uid(), user_id=cs.id, type="order_inquiry_handover", title="OI: SOZZT",
        body="LOCATION | ITEM CODE | QTY | NEW QTY | DELIVERY | REMARK\n"
             "BRW-NTC | MCM7833-CR | 10 | 8 | 09/11/2026 | ORDER BACK\n",
        data={"source_kind": "order_inquiry_handover", "source_id": inquiry.id},
    )
    db.add(notification)
    db.flush()
    db.add(EmailOutbox(
        id=_uid(), event_key="notification_delivery", recipient_email="buyer1@example.test",
        recipients_json={"to": ["buyer1@example.test"], "cc": [], "bcc": []},
        subject="OI: SOZZT", body_text=notification.body, status="sent", sent_at=T_EMAIL,
        metadata_json={"notification_id": notification.id}, created_at=T_EMAIL,
    ))

    # A line split 10 -> 6 + 4 (project_line_split_service.py, the `log_audit` after replace).
    _audit(
        db, entity_type="project_so_line_splits", entity_id=line.id, action="UPDATE",
        user_id=cs.id, changed_at=T_SPLIT, company_id=company_id,
        root_entity_type="project_sales_orders", root_entity_id=order.id,
        old_values={"line_no": 1, "base_qty": "10", "base_date": "2026-11-09", "splits": []},
        new_values={"line_no": 1, "base_qty": "10", "base_date": "2026-11-09", "splits": [
            {"qty": "6", "delivery_date": "2026-11-09", "is_cancel": False,
             "sits_on_line_id": None, "remark": ""},
            {"qty": "4", "delivery_date": "2026-12-01", "is_cancel": False,
             "sits_on_line_id": None, "remark": ""},
        ]},
    )

    # The order's own UPDATE rows (audit listener shape: changed keys only).
    _audit(
        db, entity_type="project_sales_orders", entity_id=order.id, action="UPDATE",
        user_id=cs.id, changed_at=T_STATUS, company_id=company_id,
        old_values={"status": "draft"}, new_values={"status": "published"},
    )
    _audit(
        db, entity_type="project_sales_orders", entity_id=order.id, action="UPDATE",
        user_id=cs.id, changed_at=T_OTHER_COLUMN, company_id=company_id,
        old_values={"remarks": "a"}, new_values={"remarks": "b"},
    )
    # A manual cancel of a row (the OI service's own row, filed under the PSO as root).
    _audit(
        db, entity_type="project_order_inquiry_rows", entity_id=rows[3].id, action="EVENT",
        event="OI_ROW_CANCELLED", user_id=buyer.id, changed_at=T_CANCEL,
        root_entity_type="project_sales_orders", root_entity_id=order.id,
        new_values={"revision_no": None, "cause": "so_line_removed", "qty": 932,
                    "item_code": "CKS1050", "so_line_no": 1},
    )
    db.flush()
    return {
        "company_id": company_id, "cs": cs, "uploader": uploader, "buyer": buyer,
        "order": order, "line": line, "inquiry": inquiry, "rows": rows, "product": product,
        "dec1": dec1, "dec2": dec2,
    }


def _get(db, user_id, url, permissions):
    client, originals = _client(db, user_id, permissions)
    try:
        return client.get(url)
    finally:
        _restore(originals)


def _pso_events(db, world):
    response = _get(db, world["buyer"].id, PSO_URL.format(world["order"].id), PSO_PERMS)
    assert response.status_code == 200, response.text
    return response.json()["events"]


def _by_kind(events, kind):
    return [e for e in events if e["kind"] == kind]


# ----------------------------------------------------------------- 1. kinds, titles, order


def test_every_kind_appears_with_its_exact_title_newest_first():
    """AC-SH-W2-1, W2-3."""
    with blank_session() as db:
        world = _world(db)
        ProjectOrderInquiryService(db).acknowledge_rows(
            [r.id for r in world["rows"][:2]], actor_user_id=world["buyer"].id
        )
        db.commit()
        # Unconfirm the 4 rows of SO329258's shape, in one press, at a pinned time.
        events = _pso_events(db, world)

        for event in events:
            assert set(event) == {"id", "kind", "at", "actor", "title", "lines"}
            for entry in event["lines"]:
                assert set(entry) == {"row_id", "so_line_no", "item_code", "qty", "change"}

        titles = {e["kind"]: e["title"] for e in events}
        assert "Plan confirmed, revision 2" in [
            e["title"] for e in _by_kind(events, "revision_confirmed")
        ]
        assert titles["confirm_refused"] == (
            "Confirm refused: 1 line cannot be confirmed. Nothing was written."
        )
        assert titles["autocount_update"] == "AutoCount update: 4 lines changed"
        assert titles["email_sent"] == "Handover email sent"
        assert titles["line_split"] == "Split line 1: 10 → 6 + 4"
        assert titles["status_changed"] == "Status: Draft → Published"
        assert titles["confirmed"] == "Confirmed 2 lines"
        assert titles["cancelled"] == "Cancelled CKS1050"

        refused = _by_kind(events, "confirm_refused")[0]
        assert [l["item_code"] for l in refused["lines"]] == ["SRTSA-SS"]
        update = _by_kind(events, "autocount_update")[0]
        assert len(update["lines"]) == 4
        assert {l["item_code"] for l in update["lines"]} == {"MCM7833-CR"}
        assert {l["change"] for l in update["lines"]} <= {
            "Qty 10 -> 8", "Qty 11 -> 8", "Qty 12 -> 8", "Qty 13 -> 8"
        }
        rev2 = [e for e in _by_kind(events, "revision_confirmed") if e["title"].endswith("2")][0]
        assert set(ITEMS) & {l["item_code"] for l in rev2["lines"]}

        ats = [e["at"] for e in events]
        assert ats == sorted(ats, reverse=True)


def test_an_unconfirm_press_of_four_rows_is_one_event_with_the_oi_title():
    """AC-SH-W2-3: `unconfirmed` exactly as the OI history titles it (SO329258)."""
    with blank_session() as db:
        world = _world(db)
        service = ProjectOrderInquiryService(db)
        ids = [r.id for r in world["rows"]]
        service.acknowledge_rows(ids, actor_user_id=world["buyer"].id)
        db.flush()
        service.unacknowledge_rows(ids, actor_user_id=world["buyer"].id)
        db.commit()

        events = _pso_events(db, world)

        presses = _by_kind(events, "unconfirmed")
        assert len(presses) == 1
        assert presses[0]["title"] == "Unconfirmed 4 lines, back to To confirm"
        assert presses[0]["actor"] == "ZZT Purchasing Person"
        assert {l["item_code"] for l in presses[0]["lines"]} == set(ITEMS)


def test_an_autocount_update_names_who_applied_it_else_its_uploader():
    """AC-SH-W2-3."""
    with blank_session() as db:
        world = _world(db)
        db.commit()
        update = _by_kind(_pso_events(db, world), "autocount_update")[0]
        assert update["actor"] == "ZZT CS Person"

        batch = db.query(PlanningChangeBatch).filter(
            PlanningChangeBatch.company_id == world["company_id"]
        ).one()
        batch.applied_by = None
        batch.applied_at = None
        db.commit()
        update = _by_kind(_pso_events(db, world), "autocount_update")[0]
        assert update["actor"] == "ZZT ESB Uploader"


# ----------------------------------------------------------------- 2. a press shows once


def test_a_press_spanning_two_ois_of_the_same_so_appears_once():
    """AC-SH-W2-3: the base OI plus an amendment OI of one SO; one press over rows of both."""
    with blank_session() as db:
        world = _world(db)
        amendment = SOAmendment(
            id=_uid(), company_id=world["company_id"], project_sales_order_id=world["order"].id,
        )
        db.add(amendment)
        db.flush()
        second = OrderInquiry(
            id=_uid(), company_id=world["company_id"], inquiry_no=f"ZZTAM{_uid()[:8]}",
            project_sales_order_id=world["order"].id, amendment_id=amendment.id,
            state=INQUIRY_RAISED, raised_by=world["cs"].id, raised_at=T_REV2,
        )
        db.add(second)
        db.flush()
        other_row = OrderInquiryRow(
            id=_uid(), company_id=world["company_id"], order_inquiry_id=second.id,
            so_line_id=world["line"].id, item_code="CSA150", qty=Decimal("4"),
            verb=IV_ORDER, state=INQUIRY_RAISED,
        )
        db.add(other_row)
        db.flush()
        first_row = world["rows"][0]
        # The one audit row a two-OI press writes, filed under its first row only.
        log_audit(
            db, "project_order_inquiry_rows", first_row.id, "UPDATE",
            old_values={"rows": [{"id": first_row.id, "ack_state": "awaiting"},
                                 {"id": other_row.id, "ack_state": "awaiting"}]},
            new_values={"ack_state": "acknowledged", "row_ids": [first_row.id, other_row.id]},
            user_id=world["buyer"].id, company_id=world["company_id"],
            description="Confirm: 2 row(s) marked Done by hand",
        )
        db.commit()

        events = _pso_events(db, world)

        presses = _by_kind(events, "confirmed")
        assert len(presses) == 1
        assert presses[0]["title"] == "Confirmed 2 lines"
        assert {l["row_id"] for l in presses[0]["lines"]} == {first_row.id, other_row.id}


# ----------------------------------------------------------------- 3. status rows


def test_a_status_update_shows_and_a_row_changing_other_columns_does_not():
    """AC-SH-W2-3."""
    with blank_session() as db:
        world = _world(db)
        db.commit()
        events = _pso_events(db, world)

        status = _by_kind(events, "status_changed")
        assert [e["title"] for e in status] == ["Status: Draft → Published"]
        assert status[0]["actor"] == "ZZT CS Person"
        assert status[0]["at"].startswith("2026-09-20T08:00:00")
        # The remarks-only UPDATE (21 Sep) is no event of any kind.
        assert not [e for e in events if e["at"].startswith("2026-09-21")]


# ----------------------------------------------------------------- 4. SCM read


def test_the_scm_read_answers_the_same_events_as_the_project_read():
    """AC-SH-W2-1: the SCM read covers the project SO whose `so_id` is that SO."""
    with blank_session() as db:
        world = _world(db)
        db.commit()
        project = _pso_events(db, world)
        response = _get(
            db, world["buyer"].id, SCM_URL.format(world["order"].so_id), SCM_PERMS
        )
        assert response.status_code == 200, response.text
        scm = response.json()["events"]
        assert project
        assert [(e["kind"], e["title"], e["at"]) for e in scm] == [
            (e["kind"], e["title"], e["at"]) for e in project
        ]


def test_an_so_with_no_project_so_has_an_empty_history():
    """AC-SH-W2-1."""
    from app.models.order import Customer, SalesOrder

    with blank_session() as db:
        world = _world(db)
        customer = Customer(
            id=_uid(), company_id=world["company_id"], customer_code=f"ZZT-{_uid()[:8]}",
            customer_name="ZZT Lonely Customer",
        )
        db.add(customer)
        db.flush()
        core = SalesOrder(
            id=_uid(), company_id=world["company_id"], so_number=f"ZZTSO{_uid()[:8]}",
            customer_id=customer.id, order_date=date(2026, 1, 8),
        )
        db.add(core)
        db.commit()

        response = _get(db, world["buyer"].id, SCM_URL.format(core.id), SCM_PERMS)

        assert response.status_code == 200, response.text
        assert response.json() == {"events": []}


# ----------------------------------------------------------------- 5. 404 and company scope


def test_unknown_malformed_and_other_company_ids_are_404_on_both_routes():
    """AC-SH-W2-2."""
    from app.models.base import set_company_scope

    with blank_session() as db:
        world = _world(db)
        db.commit()
        # Guard against a vacuous pass while the routes do not exist: the real ids read 200.
        assert _get(db, world["buyer"].id, PSO_URL.format(world["order"].id), PSO_PERMS).status_code == 200
        assert _get(db, world["buyer"].id, SCM_URL.format(world["order"].so_id), SCM_PERMS).status_code == 200
        for url, perms in ((PSO_URL, PSO_PERMS), (SCM_URL, SCM_PERMS)):
            assert _get(db, world["buyer"].id, url.format(_uid()), perms).status_code == 404
            assert _get(db, world["buyer"].id, url.format("not-a-uuid"), perms).status_code == 404

        set_company_scope(db, frozenset({_uid()}))
        pso = _get(db, world["buyer"].id, PSO_URL.format(world["order"].id), PSO_PERMS)
        scm = _get(db, world["buyer"].id, SCM_URL.format(world["order"].so_id), SCM_PERMS)
        assert pso.status_code == 404, pso.text
        assert scm.status_code == 404, scm.text


def test_without_the_view_permission_both_reads_are_refused():
    """AC-SH-W2-1."""
    with blank_session() as db:
        world = _world(db)
        db.commit()
        assert _get(db, world["buyer"].id, PSO_URL.format(world["order"].id), []).status_code == 403
        assert _get(db, world["buyer"].id, SCM_URL.format(world["order"].so_id), []).status_code == 403


# ----------------------------------------------------------------- 6. API key refused


def test_an_api_key_principal_is_refused_on_both_routes():
    """AC-SH-W2-2: `require_permission`, not `_with_api_key`."""
    with blank_session() as db:
        world = _world(db)
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
            client = TestClient(app)
            headers = {"X-API-Key": "zzt-not-a-real-key"}
            pso = client.get(PSO_URL.format(world["order"].id), headers=headers)
            scm = client.get(SCM_URL.format(world["order"].so_id), headers=headers)
        finally:
            app.dependency_overrides.clear()
        assert pso.status_code in (401, 403), pso.text
        assert scm.status_code in (401, 403), scm.text


# ----------------------------------------------------------------- 7. no UUIDs


def test_no_uuid_reaches_a_title_or_a_line_change():
    """AC-SH-W2-4."""
    with blank_session() as db:
        world = _world(db)
        ProjectOrderInquiryService(db).acknowledge_rows(
            [r.id for r in world["rows"]], actor_user_id=world["buyer"].id
        )
        db.commit()
        events = _pso_events(db, world)
        assert len(events) >= 7
        for event in events:
            assert not UUID_RE.search(event["title"]), event["title"]
            for entry in event["lines"]:
                assert not UUID_RE.search(entry["change"]), entry["change"]
        text = str(events)
        for leaked in ("ip_address", "user_agent", "old_values", "new_values", "row_ids"):
            assert leaked not in text


# ----------------------------------------------------------------- 8. read-only


def test_the_read_writes_nothing():
    """AC-SH-W2-2."""
    with blank_session() as db:
        world = _world(db)
        db.commit()
        before = db.query(AuditLog).count()

        assert _pso_events(db, world)
        scm = _get(db, world["buyer"].id, SCM_URL.format(world["order"].so_id), SCM_PERMS)
        assert scm.status_code == 200, scm.text
        db.commit()

        assert db.query(AuditLog).count() == before


# ----------------------------------------------------------------- shared helpers (W2-5)


def test_the_three_services_share_one_helpers_module():
    """AC-SH-W2-5."""
    from app.services import (
        history_common,
        order_inquiry_history_service,
        planning_history_service,
        sales_order_history_service,
    )

    assert history_common.ROW_AUDIT_TYPES == ("project_order_inquiry_rows", "order_inquiry_rows")
    assert history_common.RAISE_WINDOW.total_seconds() == 5
    assert history_common.iso(datetime(2026, 11, 2, 9, 31)) == "2026-11-02T09:31:00"
    assert history_common.iso(None) is None
    assert order_inquiry_history_service._ROW_AUDIT_TYPES is history_common.ROW_AUDIT_TYPES
    assert order_inquiry_history_service._RAISE_WINDOW is history_common.RAISE_WINDOW
    assert planning_history_service._ROW_AUDIT_TYPES is history_common.ROW_AUDIT_TYPES
    assert planning_history_service._iso is history_common.iso
    assert order_inquiry_history_service._iso is history_common.iso
    assert callable(sales_order_history_service.history_for_project_so)
    assert callable(sales_order_history_service.history_for_so)
