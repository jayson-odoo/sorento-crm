"""The company's own cash budget, which the planning screen used to invent instead of read.

`scm.purchasing_budget` has existed since M0 with nothing reading it, so the plan seeded its
budget at ~60% of its own cost: a RM 5.9m plan opened claiming RM 3.55m available and put 59
lines under `Over budget` for no business reason. These tests pin the read path, the period
resolution, and the fact that no configured budget means NO budget rather than a guess.

Rows are seeded by the test under its own period so nothing is borrowed off a table that is
empty in CI, and everything runs inside `pg_session()`, which rolls back.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.scm import PurchasingBudget
from app.services.scm import cash_budget_service as svc
from tests._pg_fixture import pg_session

MARKER = "ZZCASHB"


def _seed(db, *, amount, start, end, note=MARKER) -> PurchasingBudget:
    row = PurchasingBudget(
        id=str(uuid.uuid4()),
        scope_type="global",
        budget_amount=amount,
        currency="MYR",
        period_start=start,
        period_end=end,
        note=note,
        source_system="test",
    )
    db.add(row)
    db.flush()
    return row


def _clear(db) -> None:
    """This table is a singleton-ish global config, so a test that reads it has to own it."""
    db.query(PurchasingBudget).delete(synchronize_session=False)
    db.flush()


def test_no_configured_budget_reports_none_rather_than_a_number():
    # The whole point: an unset budget must not resolve to a plausible-looking figure.
    with pg_session() as db:
        _clear(db)

        out = svc.get_budget(db)

        assert out["configured"] is False
        assert out["budget_amount"] is None


def test_the_budget_in_force_today_wins():
    with pg_session() as db:
        _clear(db)
        _seed(db, amount=500000, start=date(2026, 7, 1), end=date(2026, 7, 31))
        _seed(db, amount=900000, start=date(2026, 8, 1), end=date(2026, 8, 31))

        out = svc.get_budget(db, on=date(2026, 8, 15))

        assert out["budget_amount"] == 900000
        assert out["period_start"] == "2026-08-01"


def test_a_budget_whose_month_ended_is_still_reported_rather_than_forgotten():
    # A screen that loses the budget on the first of the month is a screen people stop
    # trusting; the period travels with the figure so the staleness is visible.
    with pg_session() as db:
        _clear(db)
        _seed(db, amount=500000, start=date(2026, 7, 1), end=date(2026, 7, 31))

        out = svc.get_budget(db, on=date(2026, 9, 9))

        assert out["configured"] is True
        assert out["budget_amount"] == 500000
        assert out["period_end"] == "2026-07-31"


def test_an_open_ended_budget_applies():
    with pg_session() as db:
        _clear(db)
        _seed(db, amount=250000, start=None, end=None)

        assert svc.get_budget(db)["budget_amount"] == 250000


def test_setting_the_budget_updates_the_row_in_place():
    with pg_session() as db:
        _clear(db)
        _seed(db, amount=500000, start=date(2026, 8, 1), end=date(2026, 8, 31))

        out = svc.put_budget(db, budget_amount=5000000, currency="MYR", actor="tester")

        assert out["budget_amount"] == 5000000
        assert db.query(PurchasingBudget).count() == 1


def test_clearing_the_budget_puts_the_plan_back_to_whole():
    with pg_session() as db:
        _clear(db)
        _seed(db, amount=500000, start=date(2026, 8, 1), end=date(2026, 8, 31))

        out = svc.put_budget(db, budget_amount=None)

        assert out["configured"] is False
        assert svc.get_budget(db)["budget_amount"] is None


def test_setting_a_budget_when_none_exists_creates_one():
    with pg_session() as db:
        _clear(db)

        out = svc.put_budget(db, budget_amount=1234567, currency="MYR")

        assert out["budget_amount"] == 1234567
        assert out["currency"] == "MYR"
        assert db.query(PurchasingBudget).count() == 1


def test_a_supplier_scoped_window_is_not_mistaken_for_the_global_one():
    # Per-supplier windows are modelled but not resolved yet; reading one as the global
    # budget would show a limit that belongs to one supplier as the company's whole limit.
    with pg_session() as db:
        _clear(db)
        row = _seed(db, amount=80000, start=None, end=None)
        row.scope_type = "supplier"
        row.scope_ref = "SUP-ACME"
        db.flush()

        assert svc.get_budget(db)["configured"] is False


# --------------------------------------------------------------------------- #
# over the wire
# --------------------------------------------------------------------------- #


def test_the_budget_reads_back_over_http(scm_app):
    from fastapi.testclient import TestClient

    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _clear(db)
    _seed(db, amount=5000000, start=date(2026, 8, 1), end=date(2026, 8, 31))

    r = TestClient(app).get("/api/v1/scm/config/cash-budget")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is True
    assert body["budget_amount"] == 5000000


def test_setting_the_budget_needs_the_config_permission(scm_app):
    from fastapi.testclient import TestClient

    from tests.scm.conftest import as_user, seed_user

    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).put("/api/v1/scm/config/cash-budget", json={"budget_amount": 1})

    assert r.status_code == 403, r.text


def test_a_negative_budget_is_rejected_by_validation(scm_app):
    from fastapi.testclient import TestClient

    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role="admin")

    r = TestClient(app).put("/api/v1/scm/config/cash-budget", json={"budget_amount": -5})

    assert r.status_code == 422, r.text
