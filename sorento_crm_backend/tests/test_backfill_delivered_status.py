"""AC2: `scripts/backfill_delivered_status.py` - orders stuck at NEW with a
delivery date already recorded get moved to DELIVERED. Dry-run by default,
`--apply` writes, and only NEW+dated+not-deleted rows are ever touched.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest

from app.models.base import set_company_scope
from app.models.order import Order, OrderStatus
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import customer, order
from tests._pg_fixture import blank_session

from scripts.backfill_delivered_status import backfill


@pytest.fixture
def db():
    with blank_session() as session:
        # The script runs with no request and no principal, so it sets the
        # all-companies scope. Mirror it here or the test proves something the
        # script never does.
        set_company_scope(session, None)
        for code, name in (("NEW", "New Order"), ("DELIVERED", "Delivered"), ("CANCELLED", "Cancelled")):
            session.add(OrderStatus(id=str(uuid.uuid4()), status_code=code, status_name=name, sequence=0))
        session.flush()
        yield session


def _status_id(db, code: str) -> str:
    return db.query(OrderStatus.id).filter(OrderStatus.status_code == code).scalar()


@pytest.fixture
def scenario(db):
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ACME SDN BHD")

    new_with_date = order(db, company_id=DEFAULT_COMPANY_ID, customer_id=cust.id)
    new_with_date.order_status_id = _status_id(db, "NEW")
    new_with_date.actual_delivery_date = date(2026, 7, 1)

    new_without_date = order(db, company_id=DEFAULT_COMPANY_ID, customer_id=cust.id)
    new_without_date.order_status_id = _status_id(db, "NEW")
    new_without_date.actual_delivery_date = None

    cancelled_with_date = order(db, company_id=DEFAULT_COMPANY_ID, customer_id=cust.id)
    cancelled_with_date.order_status_id = _status_id(db, "CANCELLED")
    cancelled_with_date.actual_delivery_date = date(2026, 7, 2)

    deleted_new_with_date = order(db, company_id=DEFAULT_COMPANY_ID, customer_id=cust.id)
    deleted_new_with_date.order_status_id = _status_id(db, "NEW")
    deleted_new_with_date.actual_delivery_date = date(2026, 7, 3)
    deleted_new_with_date.deleted_at = datetime(2026, 7, 4)

    db.commit()
    return {
        "new_with_date": new_with_date.id,
        "new_without_date": new_without_date.id,
        "cancelled_with_date": cancelled_with_date.id,
        "deleted_new_with_date": deleted_new_with_date.id,
    }


def test_dry_run_reports_candidate_and_writes_nothing(db, scenario):
    result = backfill(db, apply=False)
    assert result == {"candidates": 1, "updated": 0}

    new_id = _status_id(db, "NEW")
    row = db.query(Order).filter(Order.id == scenario["new_with_date"]).one()
    assert row.order_status_id == new_id


def test_apply_sets_delivered_only_on_the_one_row(db, scenario):
    result = backfill(db, apply=True)
    assert result == {"candidates": 1, "updated": 1}

    delivered_id = _status_id(db, "DELIVERED")
    new_id = _status_id(db, "NEW")
    cancelled_id = _status_id(db, "CANCELLED")

    row = db.query(Order).filter(Order.id == scenario["new_with_date"]).one()
    assert row.order_status_id == delivered_id

    untouched_new = db.query(Order).filter(Order.id == scenario["new_without_date"]).one()
    assert untouched_new.order_status_id == new_id

    untouched_cancelled = db.query(Order).filter(Order.id == scenario["cancelled_with_date"]).one()
    assert untouched_cancelled.order_status_id == cancelled_id

    untouched_deleted = db.query(Order).filter(Order.id == scenario["deleted_new_with_date"]).one()
    assert untouched_deleted.order_status_id == new_id

    # Idempotent: a second apply finds nothing left to do.
    second = backfill(db, apply=True)
    assert second == {"candidates": 0, "updated": 0}
