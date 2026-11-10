"""RED tests B2: the SCM planner's `load_rates` reads the dated table (AC-ER-04).

`app.services.scm.money.load_rates(db)` must return the `exchange_rates` row in force TODAY per
currency, with `Rate.as_of == that row's effective_from`; a future-dated row does not apply
before its day; the legacy `scm.currency_rate` table is no longer read.

No clock freezing: rows are dated relative to `date.today()` with 10+ day margins, which stays
correct whichever zone "today" is computed in (UTC or Malaysia).

Contract 4.8 also moves `currency_rate_service` onto the dated table: `upsert_rate` writes the
`exchange_rates` row at effective_from = as_of or today (updating on the same date),
`list_rates` returns the in-force rows (same payload shape as before), `delete_rate(currency)`
deletes the in-force row.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from tests._pg_fixture import blank_session
from tests.support.costing_env import f

TODAY = date.today()


def _rate(db, currency, rate, eff):
    from app.models.costing import ExchangeRate
    import uuid

    row = ExchangeRate(id=str(uuid.uuid4()), currency=currency, rate_to_base=rate, effective_from=eff)
    db.add(row)
    db.flush()
    return row


def test_ac_er_04_load_rates_returns_the_row_in_force_today_with_its_effective_date():
    from app.services.scm.money import load_rates

    with blank_session() as db:
        _rate(db, "RMB", "0.60", TODAY - timedelta(days=60))
        _rate(db, "RMB", "0.625", TODAY - timedelta(days=10))
        _rate(db, "USD", "4.40", TODAY - timedelta(days=100))
        rates = load_rates(db)

        assert f(rates["RMB"].rate_to_base) == pytest.approx(0.625)
        assert rates["RMB"].as_of == TODAY - timedelta(days=10)
        assert f(rates["USD"].rate_to_base) == pytest.approx(4.40)
        assert rates["USD"].as_of == TODAY - timedelta(days=100)
        assert "MYR" not in rates


def test_ac_er_04_a_future_dated_row_does_not_apply_before_its_day():
    from app.services.scm.money import load_rates

    with blank_session() as db:
        _rate(db, "RMB", "0.625", TODAY - timedelta(days=10))
        _rate(db, "RMB", "0.70", TODAY + timedelta(days=10))  # scheduled
        _rate(db, "EUR", "5.00", TODAY + timedelta(days=10))  # scheduled, nothing in force
        rates = load_rates(db)

        assert f(rates["RMB"].rate_to_base) == pytest.approx(0.625)
        assert rates["RMB"].as_of == TODAY - timedelta(days=10)
        # a currency whose only row is in the future has no rate today (never a stand-in 1)
        assert "EUR" not in rates


def test_ac_er_04_a_row_effective_today_is_in_force():
    """Boundary: effective_from == today applies (<=). `today` is the Malaysian date, the helper
    the contract names (agent_class_service.today_malaysia)."""
    from app.services.sales.agent_class_service import today_malaysia
    from app.services.scm.money import load_rates

    my_today = today_malaysia()
    with blank_session() as db:
        _rate(db, "RMB", "0.60", my_today - timedelta(days=60))
        _rate(db, "RMB", "0.65", my_today)
        assert f(load_rates(db)["RMB"].rate_to_base) == pytest.approx(0.65)


def test_ac_er_04_the_legacy_scm_table_is_no_longer_read():
    from app.models.scm import CurrencyRate
    from app.services.scm.money import load_rates

    with blank_session() as db:
        db.add(CurrencyRate(currency="RMB", rate_to_base=9.99, as_of=TODAY))
        db.flush()
        assert "RMB" not in load_rates(db)  # only the dated table counts


def test_ac_er_04_a_planner_conversion_gives_the_same_number_as_before():
    from app.services.scm.money import load_rates, to_base

    with blank_session() as db:
        _rate(db, "USD", "4.4", TODAY - timedelta(days=30))
        out = to_base(45, "USD", load_rates(db))
        assert out.amount == pytest.approx(198.0)  # 45 x 4.4, rounded to 6 dp as before
        assert out.rate == pytest.approx(4.4)
        assert out.as_of == TODAY - timedelta(days=30)
        assert out.missing_currency is None

        missing = to_base(10, "EUR", load_rates(db))
        assert missing.amount is None and missing.missing_currency == "EUR"


# ------------------------------------------------------------- currency_rate_service on the dated table


def test_ac_er_04_upsert_rate_writes_a_dated_row_and_updates_on_the_same_date():
    from app.models.costing import ExchangeRate
    from app.services.scm import currency_rate_service as svc

    with blank_session() as db:
        first = svc.upsert_rate(db, "USD", 4.4, as_of=date(2026, 8, 1), note="bank")
        assert first["action"] == "created"
        rows = db.query(ExchangeRate).filter(ExchangeRate.currency == "USD").all()
        assert [r.effective_from for r in rows] == [date(2026, 8, 1)]

        again = svc.upsert_rate(db, "USD", 4.4, as_of=date(2026, 8, 1), note="bank")
        assert again["action"] == "unchanged"

        changed = svc.upsert_rate(db, "USD", 4.7, as_of=date(2026, 8, 1), note="bank")
        assert changed["action"] == "updated"
        assert db.query(ExchangeRate).filter(ExchangeRate.currency == "USD").count() == 1

        # a new date is a new dated row, not an overwrite
        svc.upsert_rate(db, "USD", 4.5, as_of=date(2026, 9, 1))
        assert db.query(ExchangeRate).filter(ExchangeRate.currency == "USD").count() == 2


def test_ac_er_04_upsert_rate_without_as_of_dates_the_row_today():
    from app.models.costing import ExchangeRate
    from app.services.scm import currency_rate_service as svc

    with blank_session() as db:
        svc.upsert_rate(db, "USD", 4.4)
        row = db.query(ExchangeRate).filter(ExchangeRate.currency == "USD").one()
        assert abs((row.effective_from - TODAY).days) <= 1


def test_ac_er_04_list_rates_returns_the_in_force_rows_in_the_old_shape():
    from app.services.scm import currency_rate_service as svc

    with blank_session() as db:
        _rate(db, "RMB", "0.60", TODAY - timedelta(days=60))
        _rate(db, "RMB", "0.625", TODAY - timedelta(days=10))
        _rate(db, "RMB", "0.70", TODAY + timedelta(days=10))
        out = svc.list_rates(db)
        rmb = [r for r in out["rates"] if r["currency"] == "RMB"]
        assert len(rmb) == 1
        assert rmb[0]["rate_to_base"] == pytest.approx(0.625)
        assert rmb[0]["as_of"] == (TODAY - timedelta(days=10)).isoformat()
        assert {"base_currency", "rates", "missing"} <= set(out)


def test_ac_er_04_delete_rate_removes_the_in_force_row_only():
    from app.models.costing import ExchangeRate
    from app.services.scm import currency_rate_service as svc

    with blank_session() as db:
        _rate(db, "RMB", "0.60", TODAY - timedelta(days=60))
        _rate(db, "RMB", "0.625", TODAY - timedelta(days=10))
        _rate(db, "RMB", "0.70", TODAY + timedelta(days=10))
        svc.delete_rate(db, "RMB")
        left = sorted(r.effective_from for r in db.query(ExchangeRate).filter(ExchangeRate.currency == "RMB"))
        assert left == [TODAY - timedelta(days=60), TODAY + timedelta(days=10)]
