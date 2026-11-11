"""The SCM currency-rate screen on the dated table (PRODUCT-COSTING fix round 2, L2).

It keeps one live rate per currency: it may change today's, or schedule a later one. A date before
the rate in force is refused (Costing > Settings owns history).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from app.models.costing import ExchangeRate
from app.services.error_handler import AppException
from app.services.scm import currency_rate_service as svc
from tests._pg_fixture import blank_session

TODAY = date.today()


def _row(db, currency, rate, eff):
    db.add(ExchangeRate(id=str(uuid.uuid4()), currency=currency, rate_to_base=rate, effective_from=eff))
    db.flush()


def test_a_date_before_the_rate_in_force_is_refused():
    with blank_session() as db:
        _row(db, "CNY", "0.625", TODAY - timedelta(days=10))
        with pytest.raises(AppException) as e:
            svc.upsert_rate(db, "CNY", 0.6, as_of=TODAY - timedelta(days=40))
        assert e.value.status_code == 422
        assert "A past rate is added in Costing > Settings" in e.value.message
        assert db.query(ExchangeRate).filter(ExchangeRate.currency == "CNY").count() == 1


def test_the_in_force_date_updates_in_place():
    with blank_session() as db:
        _row(db, "CNY", "0.625", TODAY - timedelta(days=10))
        out = svc.upsert_rate(db, "CNY", 0.63, as_of=TODAY - timedelta(days=10))
        assert out["action"] == "updated"
        rows = db.query(ExchangeRate).filter(ExchangeRate.currency == "CNY").all()
        assert len(rows) == 1 and float(rows[0].rate_to_base) == pytest.approx(0.63)


def test_a_later_date_makes_a_scheduled_row_and_the_list_says_so():
    with blank_session() as db:
        _row(db, "CNY", "0.625", TODAY - timedelta(days=10))
        later = TODAY + timedelta(days=20)
        svc.upsert_rate(db, "CNY", 0.7, as_of=later)
        assert db.query(ExchangeRate).filter(ExchangeRate.currency == "CNY").count() == 2
        rmb = [r for r in svc.list_rates(db)["rates"] if r["currency"] == "CNY"]
        assert len(rmb) == 1 and rmb[0]["rate_to_base"] == pytest.approx(0.625)  # still the one in force
        assert rmb[0]["scheduled_from"] == later.isoformat()
        assert rmb[0]["scheduled_rate_to_base"] == pytest.approx(0.7)


def test_a_currency_with_no_scheduled_row_says_none():
    with blank_session() as db:
        _row(db, "CNY", "0.625", TODAY - timedelta(days=10))
        rmb = svc.list_rates(db)["rates"][0]
        assert rmb["scheduled_from"] is None
