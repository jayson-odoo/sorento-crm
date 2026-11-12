"""SPARE-PART-ORDER-REQUEST on the MIGRATED database, red-first (Phase 2).

T2 (P6): `projects.order_inquiries` refuses a sales-order inquiry with no sales order - the
CHECK the lane's migration adds (`inquiry_type <> 'sales_order' OR project_sales_order_id IS
NOT NULL`).

T13 (P5, crew ruling 12 Nov): an approved spare part request is NOT customer demand. After
final approval `scm.committed_v` and the reorder plan's own committed SELECT
(`demand.horizon_committed_select_sql`, what `reorder_run_service` reads) are unchanged for
the product at its location. A positive control proves the harness can see the row: the
same row relabelled ORDER IS counted, so "unchanged" is not a blind read.

Runs on the REAL database inside one rolled-back transaction, like
`test_order_inquiry_handshake.py`: the CHECK and the view live in migrations and the blank
scratch schema has neither. Every row is seeded here behind the ZZT marker (CI's database is
empty). Run after `alembic upgrade head`.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import engine

from ._forms_chain_support import SORENTO
from ._spare_part_request_support import (
    ONE_STAGE,
    add_stages,
    raised,
    row_for,
    seed_people_and_catalogue,
)


@contextmanager
def _real_db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def real(monkeypatch):
    from app.main import app  # noqa: F401  first app import (circular import guard)
    from app.models.base import set_company_scope
    from app.services import queue_service, respond_messaging_service
    from app.services.notification_service import NotificationService

    sent: list = []
    monkeypatch.setattr(
        NotificationService, "create_with_channel_preferences",
        lambda self, *a, **kw: sent.append((kw.get("user_id"), kw.get("type"))),
    )
    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **kw: SimpleNamespace(id="zzt-job"))
    monkeypatch.setattr(respond_messaging_service, "send_text_or_template", lambda *a, **kw: {})
    with _real_db_session() as db:
        set_company_scope(db, frozenset({SORENTO}))
        seeded = seed_people_and_catalogue(db)
        db.commit()
        yield SimpleNamespace(db=db, sent=sent, company_id=SORENTO, **vars(seeded))


# =============================================================================
# T2 - the database refuses a sales-order inquiry without a sales order (P6)
# =============================================================================


def test_T2_a_sales_order_inquiry_without_a_sales_order_fails_to_flush(real):
    from app.models.project_so import OrderInquiry

    db = real.db
    nested = db.begin_nested()
    db.add(
        OrderInquiry(
            company_id=SORENTO, inquiry_type="sales_order", project_sales_order_id=None, state="raised",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    nested.rollback()


def test_T2_existing_rows_default_to_sales_order_and_the_type_is_checked(real):
    db = real.db
    column = db.execute(
        text(
            "SELECT column_default, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'projects' AND table_name = 'order_inquiries' "
            "AND column_name = 'inquiry_type'"
        )
    ).first()
    assert column is not None, "projects.order_inquiries.inquiry_type exists"
    assert "sales_order" in (column[0] or "") and column[1] == "NO"
    nullable = db.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns WHERE table_schema = 'projects' "
            "AND table_name = 'order_inquiries' AND column_name = 'project_sales_order_id'"
        )
    ).scalar()
    assert nullable == "YES"


# =============================================================================
# T13 - an approved request is not committed demand (P5)
# =============================================================================


def _committed(db, product_id: str, warehouse_code: str) -> tuple[Decimal, Decimal]:
    from app.services.scm import demand

    view = db.execute(
        text(
            "SELECT COALESCE(SUM(cv.committed), 0) FROM scm.committed_v cv "
            "JOIN warehouses w ON w.id = cv.warehouse_id "
            "WHERE cv.product_id = :pid AND w.warehouse_code = :code"
        ),
        {"pid": product_id, "code": warehouse_code},
    ).scalar()
    planned = db.execute(
        text(
            f"SELECT COALESCE(SUM(cv.project_committed), 0) FROM ({demand.horizon_committed_select_sql()}) cv "
            "JOIN warehouses w ON w.id = cv.warehouse_id "
            "WHERE cv.product_id = :pid AND w.warehouse_code = :code"
        ),
        {"pid": product_id, "code": warehouse_code, "horizon": None, "horizon_start": None},
    ).scalar()
    return Decimal(str(view or 0)), Decimal(str(planned or 0))


def test_T13_final_approval_leaves_committed_demand_and_the_reorder_input_unchanged(real):
    w = real
    add_stages(w, ONE_STAGE)
    pid, code = str(w.product_a.id), w.loc_a.warehouse_code
    before = _committed(w.db, pid, code)

    inquiry = raised(w)
    assert inquiry.state == "raised"
    row = row_for(w.db, inquiry, w.product_a)
    assert row.state == "raised" and row.verb == "REPLENISH" and row.qty > 0

    assert _committed(w.db, pid, code) == before, "committed_v / plan SELECT moved"

    # Positive control: the same row as an ORDER instruction IS demand, so the read above
    # was looking at the right product and location.
    w.db.execute(
        text("UPDATE projects.order_inquiry_rows SET verb = 'ORDER' WHERE id = :id"), {"id": str(row.id)}
    )
    after_view, after_planned = _committed(w.db, pid, code)
    assert after_view == before[0] + Decimal(str(row.qty))
