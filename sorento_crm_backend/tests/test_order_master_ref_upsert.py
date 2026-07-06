"""Order master-ref upsert helpers — the logic the import path now reuses.

`import_excel_tracking` populates `customer_id` / `transporter_id` by routing each
mapped row through `_sync_order_master_refs`, exactly like `create_order` /
`update_order`. These tests pin that helper's find-or-create + idempotency +
pair-match + FK re-point behavior against a real sqlite session.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.order import Customer, Transporter
from app.services.order_service import OrderService


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    # The upsert helpers key on `func.btrim(...)` (a Postgres builtin sqlite lacks).
    @event.listens_for(engine, "connect")
    def _register_btrim(dbapi_conn, _rec):
        dbapi_conn.create_function(
            "btrim", 1, lambda s: s.strip() if s is not None else None, deterministic=True
        )

    # Only the two master tables the helpers touch.
    Base.metadata.create_all(engine, tables=[Customer.__table__, Transporter.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _svc(db):
    return OrderService(db)


def test_customer_created_from_new_debtor(db):
    svc = _svc(db)
    cid = svc._upsert_customer_from_debtor("Deluxe Home Center (KTN)", "300-D093")
    db.flush()
    row = db.query(Customer).filter(Customer.id == cid).one()
    assert row.customer_name == "Deluxe Home Center (KTN)"
    assert row.customer_code == "300-D093"
    assert db.query(Customer).count() == 1


def test_customer_upsert_is_idempotent(db):
    svc = _svc(db)
    a = svc._upsert_customer_from_debtor("Acme Sdn Bhd", "300-A001")
    b = svc._upsert_customer_from_debtor("  acme sdn bhd ", "300-a001")  # case/space noise
    assert a == b
    assert db.query(Customer).count() == 1


def test_same_code_distinct_names_get_separate_rows(db):
    """One Sage code can carry multiple debtor names — each pair is its own row."""
    svc = _svc(db)
    a = svc._upsert_customer_from_debtor("Deluxe Home Center (KTN)", "300-D093")
    b = svc._upsert_customer_from_debtor("Deluxe Home Center AC (I)", "300-D093")
    assert a != b
    assert db.query(Customer).count() == 2


def test_blank_code_falls_back_to_deterministic_slug(db):
    svc = _svc(db)
    a = svc._upsert_customer_from_debtor("No Code Debtor", None)
    b = svc._upsert_customer_from_debtor("No Code Debtor", "")
    assert a == b
    row = db.query(Customer).filter(Customer.id == a).one()
    assert row.customer_code.startswith("DBR-")
    assert db.query(Customer).count() == 1


def test_transporter_created_and_idempotent(db):
    svc = _svc(db)
    a = svc._upsert_transporter_from_text("Sri Jaya Logistics")
    b = svc._upsert_transporter_from_text("  sri jaya logistics ")
    assert a == b
    row = db.query(Transporter).filter(Transporter.id == a).one()
    assert row.name == "Sri Jaya Logistics"
    assert row.normalized_name == "sri jaya logistics"
    assert db.query(Transporter).count() == 1


def test_sync_populates_both_fks_from_text(db):
    """The single call the import branches make: debtor + transporter -> FKs."""
    svc = _svc(db)
    mapped = {
        "order_number": "DO-1",
        "debtor_name": "Fresh Debtor",
        "debtor_code": "300-F001",
        "transporter": "Fresh Transporter",
    }
    out = svc._sync_order_master_refs(mapped)
    db.flush()
    assert out["customer_id"] == str(db.query(Customer).one().id)
    assert out["transporter_id"] == str(db.query(Transporter).one().id)


def test_sync_ignores_blank_text(db):
    svc = _svc(db)
    out = svc._sync_order_master_refs({"order_number": "DO-2", "debtor_name": "", "transporter": None})
    assert "customer_id" not in out
    assert "transporter_id" not in out
    assert db.query(Customer).count() == 0
    assert db.query(Transporter).count() == 0
