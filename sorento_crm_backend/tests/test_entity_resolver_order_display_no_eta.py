"""AC2 (chatbot-eta-not-in-turn): no `customer_order` ResolvedEntity carries
`estimated_delivery_date` in its `display`.

Owner ruling 10 Sep 2026: `orders.estimated_delivery_date` is not a real promise - the
import stamps it as `order_date + 2 business days` (`order_service.py` ~2824) on every
master row. It may still show in the CRM UI, but it must never reach the chatbot / turn
API, which reads its order facts off `entity_resolver`'s `display` dict. `actual_delivery_date`
IS a real fact (when the order was actually delivered) and must stay.

Covers all three `customer_order` probe tiers: exact (`_probe_customer_order`), prefix
(`_prefix_probe_customer_order`) and AND-mode (`_and_probe_customer_order`). DB tests run
inside a rolled-back Postgres session (see tests/_pg_fixture.py) and seed their own Order
row (ZZT prefix), so they hold on an empty CI database.
"""
import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.order import Order
from app.services import entity_resolver as er
from tests._pg_fixture import pg_session, unique_code


@pytest.fixture()
def db():
    ctx = pg_session()
    try:
        session = ctx.__enter__()
        session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - env dependent
        pytest.skip(f"Postgres unreachable: {exc}")
    try:
        yield session
    finally:
        ctx.__exit__(None, None, None)


def _order_with_dates(db: Session) -> Order:
    row = Order(
        id=str(uuid.uuid4()),
        order_number=unique_code("DO"),
        debtor_name="ZZT Eta Omission Sdn Bhd",
        debtor_code=unique_code("DBT")[:100],
        order_date=date(2026, 9, 8),
        estimated_delivery_date=date(2026, 9, 10),
        actual_delivery_date=date(2026, 9, 9),
    )
    db.add(row)
    db.flush()
    return row


def _assert_no_eta_has_actual(matches, *, uuid_str: str, where: str) -> None:
    hits = [m for m in matches if m.uuid == uuid_str]
    assert hits, f"{where}: seeded order was not resolved at all"
    for hit in hits:
        assert hit.entity_type == "customer_order"
        assert "estimated_delivery_date" not in hit.display, (
            f"{where}: display leaked estimated_delivery_date: {hit.display!r}"
        )
        assert "actual_delivery_date" in hit.display, (
            f"{where}: actual_delivery_date must stay: {hit.display!r}"
        )
        assert hit.display["actual_delivery_date"] == "2026-09-09"


def test_exact_probe_customer_order_display_omits_estimated_delivery_date(db):
    order = _order_with_dates(db)
    result = er._probe_customer_order(db, [order.order_number])
    matches = result[order.order_number]
    _assert_no_eta_has_actual(matches, uuid_str=str(order.id), where="exact probe")


def test_prefix_probe_customer_order_display_omits_estimated_delivery_date(db):
    order = _order_with_dates(db)
    prefix_token = order.order_number[:-2]
    matches = er._prefix_probe_customer_order(db, prefix_token)
    _assert_no_eta_has_actual(matches, uuid_str=str(order.id), where="prefix probe")


def test_and_probe_customer_order_display_omits_estimated_delivery_date(db):
    order = _order_with_dates(db)
    stripped = order.order_number.replace("-", "")
    matches = er._and_probe_customer_order(db, [stripped])
    _assert_no_eta_has_actual(matches, uuid_str=str(order.id), where="AND-mode probe")
