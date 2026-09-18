"""Slice 3 (`PLAN-oi-worklist-split-customer-project.md`, owner 18 Sep 2026): the worklist Actions
menu's own "Unconfirm (N)" - the reverse of Confirm, for a row taken on by mistake or a
reconfirm CS has not actually made yet.

Seeded DIRECTLY via ORM, exactly like `tests/scm/test_oi_worklist_raise_history.py` does
and for the same reason: `unacknowledge_rows` never calls `ProjectSupplyService.confirm`
at all, so there is nothing that route would prove here that stamping `ack_state` and its
companions directly does not already - the live confirm flow is a different seam
entirely, this file is about the handshake's own reversal.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models.audit import AuditLog
from app.models.company import Company
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    ACK_REJECTED,
    INQUIRY_CANCELLED,
    ProjectSalesOrder,
)
from tests._pg_fixture import blank_session

from ..test_order_inquiry_worklist import (
    LIST,
    MARKER,
    _client,
    _inquiry_for,
    _restore,
    _row,
    _sorento,
    _uid,
    _user,
    project_seed_service,
)

UNACK_URL = f"{LIST}/unacknowledge"
VIEW = "projects.projects.view"
ACKNOWLEDGE = "projects.order_inquiries.acknowledge"
PURCHASING = [VIEW, ACKNOWLEDGE]
CS_ONLY = [VIEW]


def _bare_order(db, company_id: str) -> ProjectSalesOrder:
    """An adopted order with no project and no core sales order - the minimum
    `_inquiry_for`/`_row` need to hang a row off, no more: this file is about the
    handshake's own `ack_state`, not the worklist's other columns."""
    order = ProjectSalesOrder(
        id=_uid(),
        company_id=company_id,
        project_id=None,
        provisional_ref=f"ZZT-UC-{_uid()[:8]}",
        autocount_doc_no=f"ZZT-UC-SO-{_uid()[:6]}",
        status="adopted",
    )
    db.add(order)
    db.flush()
    return order


@pytest.fixture()
def unconfirm_api():
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        buyer_id = _user(db, f"{MARKER} Buyer")
        order = _bare_order(db, company_id)
        inquiry = _inquiry_for(db, company_id, order)

        acknowledged_row = _row(
            db,
            company_id,
            inquiry,
            item_code="ZZT-UC-ACK",
            qty="5",
            ack_state=ACK_ACKNOWLEDGED,
            acknowledged_by=buyer_id,
            acknowledged_at=datetime(2026, 8, 1, 9, 0),
        )
        changed_row = _row(
            db,
            company_id,
            inquiry,
            item_code="ZZT-UC-CHANGED",
            qty="3",
            ack_state=ACK_CHANGED,
            acknowledged_by=buyer_id,
            acknowledged_at=datetime(2026, 8, 1, 9, 0),
            changed_at=datetime(2026, 8, 5, 9, 0),
        )
        awaiting_row = _row(
            db, company_id, inquiry, item_code="ZZT-UC-AWAIT", qty="2",
            ack_state=ACK_AWAITING,
        )
        rejected_row = _row(
            db,
            company_id,
            inquiry,
            item_code="ZZT-UC-REJ",
            qty="1",
            ack_state=ACK_REJECTED,
            rejected_by=buyer_id,
            rejected_at=datetime(2026, 8, 2, 9, 0),
            rejected_reason="No stock",
        )
        # Blocker S1 (review round 1): a row can be CANCELLED (e.g. by a re-confirm
        # superseding it) while its `ack_state` still reads `acknowledged` from before -
        # nothing else resets that column. Its handshake is history, not something
        # Unconfirm should reopen.
        cancelled_acknowledged_row = _row(
            db,
            company_id,
            inquiry,
            item_code="ZZT-UC-CANCELLED",
            qty="4",
            state=INQUIRY_CANCELLED,
            ack_state=ACK_ACKNOWLEDGED,
            acknowledged_by=buyer_id,
            acknowledged_at=datetime(2026, 8, 1, 9, 0),
        )

        other_company_id = _uid()
        with company_scope(db, None):
            db.add(
                Company(
                    id=other_company_id,
                    name=f"{MARKER} Other",
                    code=f"ZZ{_uid()[:6]}",
                )
            )
            db.flush()
            other_order = _bare_order(db, other_company_id)
            other_inquiry = _inquiry_for(db, other_company_id, other_order)
            other_row = _row(
                db,
                other_company_id,
                other_inquiry,
                item_code="ZZT-UC-OTHER",
                qty="9",
                ack_state=ACK_ACKNOWLEDGED,
                acknowledged_by=buyer_id,
                acknowledged_at=datetime(2026, 8, 1, 9, 0),
            )

        db.commit()
        client, originals = _client(db, buyer_id, PURCHASING)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id, {
                    "acknowledged_row": acknowledged_row,
                    "changed_row": changed_row,
                    "awaiting_row": awaiting_row,
                    "rejected_row": rejected_row,
                    "cancelled_acknowledged_row": cancelled_acknowledged_row,
                    "other_row": other_row,
                    "buyer_id": buyer_id,
                }
        finally:
            _restore(originals)


def test_an_acknowledged_row_goes_back_to_awaiting_with_cleared_stamps(unconfirm_api):
    client, db, _company_id, seeded = unconfirm_api
    row = seeded["acknowledged_row"]

    response = client.post(UNACK_URL, json={"row_ids": [str(row.id)]})

    assert response.status_code == 200, response.text
    assert response.json() == {"updated": 1, "skipped": 0}
    db.commit()
    db.expire_all()
    db.refresh(row)
    assert row.ack_state == ACK_AWAITING
    assert row.acknowledged_by is None
    assert row.acknowledged_at is None
    assert row.changed_at is None


def test_a_changed_row_goes_back_to_awaiting_but_keeps_changed_at(unconfirm_api):
    """Owner ruling, review round 1: `changed_at` is the Was/Now audit trail
    `_settle_row_in_place` reads and `_handshake_for_raise` carries across a carry, not a
    stamp of Unconfirm's own - clearing it here would erase a fact this press has
    nothing to do with."""
    client, db, _company_id, seeded = unconfirm_api
    row = seeded["changed_row"]
    original_changed_at = row.changed_at

    response = client.post(UNACK_URL, json={"row_ids": [str(row.id)]})

    assert response.status_code == 200, response.text
    assert response.json() == {"updated": 1, "skipped": 0}
    db.commit()
    db.expire_all()
    db.refresh(row)
    assert row.ack_state == ACK_AWAITING
    assert row.acknowledged_by is None
    assert row.acknowledged_at is None
    assert row.changed_at == original_changed_at


def test_an_awaiting_or_rejected_row_is_skipped_not_an_error(unconfirm_api):
    client, db, _company_id, seeded = unconfirm_api
    awaiting_id = str(seeded["awaiting_row"].id)
    rejected_id = str(seeded["rejected_row"].id)

    response = client.post(UNACK_URL, json={"row_ids": [awaiting_id, rejected_id]})

    assert response.status_code == 200, response.text
    assert response.json() == {"updated": 0, "skipped": 2}
    db.commit()
    db.expire_all()
    db.refresh(seeded["awaiting_row"])
    db.refresh(seeded["rejected_row"])
    assert seeded["awaiting_row"].ack_state == ACK_AWAITING
    assert seeded["rejected_row"].ack_state == ACK_REJECTED


def test_a_mixed_batch_updates_the_eligible_and_skips_the_rest(unconfirm_api):
    client, db, _company_id, seeded = unconfirm_api
    row_ids = [
        str(seeded["acknowledged_row"].id),
        str(seeded["changed_row"].id),
        str(seeded["awaiting_row"].id),
        str(seeded["rejected_row"].id),
    ]

    response = client.post(UNACK_URL, json={"row_ids": row_ids})

    assert response.status_code == 200, response.text
    assert response.json() == {"updated": 2, "skipped": 2}


def test_a_user_without_the_acknowledge_grant_is_refused_403(unconfirm_api):
    _client_unused, db, _company_id, seeded = unconfirm_api

    cs_client, originals = _client(db, seeded["buyer_id"], CS_ONLY)
    try:
        response = cs_client.post(
            UNACK_URL, json={"row_ids": [str(seeded["acknowledged_row"].id)]}
        )
        assert response.status_code == 403
    finally:
        _restore(originals)
        # Put the purchasing client back exactly as the fixture left it, so its own
        # `finally` block still restores the ORIGINAL (pre-fixture) permission mock.
        _client(db, seeded["buyer_id"], PURCHASING)


def test_another_companys_row_is_skipped_not_touched(unconfirm_api):
    client, db, _company_id, seeded = unconfirm_api
    other_row = seeded["other_row"]

    response = client.post(UNACK_URL, json={"row_ids": [str(other_row.id)]})

    assert response.status_code == 200, response.text
    assert response.json() == {"updated": 0, "skipped": 1}

    from app.models.base import company_scope

    with company_scope(db, None):
        db.commit()
        db.expire_all()
        db.refresh(other_row)
        assert other_row.ack_state == ACK_ACKNOWLEDGED
        assert other_row.acknowledged_by == seeded["buyer_id"]


def test_a_cancelled_row_is_skipped_not_reopened(unconfirm_api):
    """Blocker S1 (review round 1): `state == cancelled` is refused regardless of what
    `ack_state` still reads - a superseded row's handshake is history."""
    client, db, _company_id, seeded = unconfirm_api
    row = seeded["cancelled_acknowledged_row"]

    response = client.post(UNACK_URL, json={"row_ids": [str(row.id)]})

    assert response.status_code == 200, response.text
    assert response.json() == {"updated": 0, "skipped": 1}
    db.commit()
    db.expire_all()
    db.refresh(row)
    assert row.ack_state == ACK_ACKNOWLEDGED
    assert row.acknowledged_by == seeded["buyer_id"]


def test_unacknowledge_writes_an_audit_log_entry(unconfirm_api):
    """Security review round 1, item d: `OrderInquiryRow` carries no `__audit_track__`,
    so the generic session-dirty listener never sees this write - `unacknowledge_rows`
    has to write its own `log_audit` entry, naming the actor and the row it moved, or
    Unconfirm is a silent write nobody can trace."""
    client, db, _company_id, seeded = unconfirm_api
    row = seeded["acknowledged_row"]

    response = client.post(UNACK_URL, json={"row_ids": [str(row.id)]})

    assert response.status_code == 200, response.text
    db.commit()

    entries = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "project_order_inquiry_rows")
        .filter(AuditLog.user_id == seeded["buyer_id"])
        .all()
    )
    matching = [
        entry
        for entry in entries
        if str(row.id) in (entry.new_values or {}).get("row_ids", [])
        or entry.entity_id == str(row.id)
    ]
    assert matching, "no audit_logs entry names the actor and the row"
