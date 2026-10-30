"""OI-AUTO-CONFIRM owner ruling 30 Oct 2026 (UAC AC-AC-10e): EVERY live row on a cancelled SO
line is done (`acknowledged`, by NULL), with or without a PO/SPO link. Purchasing never acts
on it: the cancel stamps no `changed`, queues no purchasing email or notice, and the row never
counts in To order. Replaces rule (c). Postgres only, every test seeds its own chain.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models.base import company_scope
from app.models.project_so import ACK_ACKNOWLEDGED, ACK_AWAITING
from app.services.oi_auto_confirm_backfill import backfill_auto_confirm
from app.services.project_order_inquiry_service import (
    _CHANGED_WITH_LINKS_PENDING_KEY,
    _HANDOVER_PENDING_KEY,
    _PURCHASING_NOTIFY_PENDING_KEY,
    ProjectOrderInquiryService,
)

from ._pg_fixture import blank_session
from .test_oi_auto_confirm import _header_row, header_api  # noqa: F401  (fixture)
from .test_oi_auto_confirm_review1 import _cancelled_line_row, _flag_cancelled_line
from .test_oi_auto_confirm_review2 import _po_linked_row
from .test_oi_cancelled_line_used_confirm import (  # noqa: F401  (db, env are fixtures)
    _cancel_via_so_edit,
    _create_then_prep_push,
    _inquiry,
    _line_chain,
    _mirror_for_ingest_line,
    _oi_row,
    _so_edit_chain,
    db,
    env,
)
from .test_order_inquiry_kinds import _product, _sorento, _uid

OLD_STAMP = datetime(2026, 1, 2, 3, 4, 5)
PENDING_KEYS = (_HANDOVER_PENDING_KEY, _PURCHASING_NOTIFY_PENDING_KEY, _CHANGED_WITH_LINKS_PENDING_KEY)


def _seed(db, kind):
    if kind == "covered":
        return _po_linked_row(db)
    if kind == "actioned":
        return _po_linked_row(db, actioned=True)
    return _cancelled_line_row(db, ack_state=ACK_ACKNOWLEDGED, line_status="open")


@pytest.mark.parametrize("kind", ["covered", "actioned", "uncovered"])
def test_ac_ac_10e_the_cancel_leaves_every_acknowledged_row_done_and_stamps_nothing(kind):
    with blank_session() as db:
        company_id, row = _seed(db, kind)
        if kind == "uncovered":
            # the real precondition of the flag: the core line is now cancelled
            from app.models.order import SalesOrderLine
            from app.models.project_so import ProjectSalesOrderLine

            mirror = db.get(ProjectSalesOrderLine, row.so_line_id)
            db.get(SalesOrderLine, mirror.core_sales_order_line_id).line_status = "cancelled"
        row.changed_at = OLD_STAMP
        db.flush()
        for key in PENDING_KEYS:
            db.info.pop(key, None)

        _flag_cancelled_line(db, company_id, row)
        db.refresh(row)
        assert row.ack_state == ACK_ACKNOWLEDGED, row.ack_state
        assert row.acknowledged_by is None
        assert row.changed_at == OLD_STAMP, "the cancel stamps no changed_at"
        for key in PENDING_KEYS:
            assert not db.info.get(key), f"the cancel queued {key} for purchasing"

        svc = ProjectOrderInquiryService(db)
        with company_scope(db, frozenset({company_id})):
            svc.refresh_link_state([row])
            svc.auto_confirm([row.id])
        db.refresh(row)
        assert row.ack_state == ACK_ACKNOWLEDGED, "a later auto_confirm keeps it done"
        assert row.changed_at == OLD_STAMP
        for key in PENDING_KEYS:
            assert not db.info.get(key)


def test_ac_ac_10e_a_header_with_only_cancelled_line_rows_is_completed_and_not_to_order(
    header_api,
):
    client, db, company_id = header_api
    product = _product(db, f"ZZT-CD-{_uid()[:6]}", "zzt cancelled done")
    _so, _core, pso, mirror = _line_chain(
        db, company_id, product, qty="10", line_status="cancelled"
    )
    inquiry = _inquiry(db, company_id, pso.id)
    row = _oi_row(
        db, company_id, inquiry.id, mirror.id, product.product_code, "10",
        ack_state=ACK_AWAITING,
    )
    from .test_order_inquiry_kinds import _link, _spo_allocation

    allocation = _spo_allocation(db, company_id, product, qty=10)
    _link(db, company_id, row.id, "10", spo_allocation_id=allocation.id,
          document=allocation.spo_number)
    db.flush()
    with company_scope(db, frozenset({company_id})):
        ProjectOrderInquiryService(db).auto_confirm([row.id])
    db.commit()

    assert _header_row(client, str(inquiry.id), "completed") is not None
    assert _header_row(client, str(inquiry.id), "outstanding") is None
    listed = client.get(
        "/api/v1/project-sales/order-inquiries", params={"ack": "to_confirm", "limit": 200}
    )
    assert listed.status_code == 200, listed.text
    assert str(row.id) not in {r["id"] for r in listed.json()["data"]}


def test_ac_ac_10e_the_backfill_makes_a_linked_cancelled_line_row_done():
    with blank_session() as db:
        _company_id, row = _cancelled_line_row(db, ack_state=ACK_AWAITING, linked=True)
        db.flush()

        backfill_auto_confirm(db.connection())
        db.flush()

        db.refresh(row)
        assert row.ack_state == ACK_ACKNOWLEDGED
        assert row.acknowledged_by is None


# A newly cancelled line makes EVERY live row on it done, awaiting and changed included.
_TO_ORDER = [("awaiting", None), ("changed", datetime(2026, 1, 1))]


@pytest.mark.parametrize("row_ack,pre_changed_at", _TO_ORDER)
def test_ac_ac_10e_so_edit_cancel_makes_an_awaiting_or_changed_row_done(
    db, row_ack, pre_changed_at
):
    from app.models.order import SalesOrderLine
    from app.models.project_so import INQUIRY_RAISED, OrderInquiryRow

    so, _product, line, row = _so_edit_chain(
        db, row_state=INQUIRY_RAISED, row_ack=row_ack, changed_at=pre_changed_at
    )
    for key in PENDING_KEYS:
        db.info.pop(key, None)

    _cancel_via_so_edit(db, so)

    db.expire_all()
    assert db.get(SalesOrderLine, line.id).line_status == "cancelled"
    row = db.get(OrderInquiryRow, row.id)
    assert row.ack_state == ACK_ACKNOWLEDGED, row.ack_state
    assert row.acknowledged_by is None
    assert row.changed_at == pre_changed_at, "the cancel stamps no changed_at"
    for key in PENDING_KEYS:
        assert not db.info.get(key), f"the cancel queued {key} for purchasing"


@pytest.mark.parametrize("row_ack,pre_changed_at", _TO_ORDER)
def test_ac_ac_10e_autocount_cancel_makes_an_awaiting_or_changed_row_done(
    env, row_ack, pre_changed_at
):
    from app.models.project_so import OrderInquiryRow
    from .test_ingest_documents import INGEST_SO

    record, header, line, product_id = _create_then_prep_push(env)
    _mirror, row = _mirror_for_ingest_line(
        env, header["id"], line["id"], product_id, row_ack=row_ack, changed_at=pre_changed_at,
    )

    res = env.post(INGEST_SO, [dict(record, status="cancelled")])
    assert res.status_code == 200, res.text

    env.db.expire_all()
    assert env.so_lines(header["id"])[0]["line_status"] == "cancelled"
    row = env.db.get(OrderInquiryRow, row.id)
    assert row.ack_state == ACK_ACKNOWLEDGED, row.ack_state
    assert row.acknowledged_by is None
    assert row.changed_at == pre_changed_at, "the cancel stamps no changed_at"
