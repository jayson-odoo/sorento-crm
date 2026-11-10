"""RED tests B1: dated exchange rates (PRODUCT-COSTING, Phase 2). AC-ER-01..03, 06, 07.

ASSUMED SIGNATURES:
    app/services/costing/rates.py::rate_on(db, currency, day) -> obj | None
        obj has `.rate_to_base` (Decimal) and `.effective_from` (date); the row with the latest
        effective_from <= day. None when there is none. Never returns a stand-in 1.
    POST /api/v1/master-data/costing/exchange-rates answers 200 or 201 with the row JSON
        {id, currency, rate_to_base, units_per_base, effective_from, note, status}.
    PUT  /api/v1/master-data/costing/exchange-rates/{id} answers 200 with the same row JSON.
    Record action `exchange_rate.delete`: entity type "exchange_rate", destructive window,
        permission `scm.config.manage`; `execute(db, {"entity_id": id})` deletes the row.
    Audit rows: `entity_type == "exchange_rates"`, `entity_id == str(id)`, actions
        INSERT / UPDATE / DELETE (the model carries `__audit_track__ = True`).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from tests.support.costing_env import (
    COST_VIEW,
    RATE_READ,
    RATE_WRITE,
    costing_env,  # noqa: F401
    f,
)

D = date


def _ok(r):
    assert r.status_code in (200, 201), r.text
    return r.json()


# ------------------------------------------------------------------ AC-ER-02 / AC-ER-03 (service)


def test_ac_er_02_rate_in_force_on_a_date_is_latest_effective_from_not_after(costing_env):
    from app.services.costing.rates import rate_on

    e = costing_env
    e.rate("RMB", "0.617284", D(2026, 9, 1))
    e.rate("RMB", "0.625", D(2026, 11, 1))
    e.rate("RMB", "0.613497", D(2026, 12, 1))
    e.db.commit()

    r_oct = rate_on(e.db, "RMB", D(2026, 10, 31))
    assert f(r_oct.rate_to_base) == pytest.approx(0.617284, abs=1e-9)
    assert r_oct.effective_from == D(2026, 9, 1)

    # KILL TEST: `<` instead of `<=` would still give 0.617284 on the effective day itself.
    r_nov = rate_on(e.db, "RMB", D(2026, 11, 1))
    assert f(r_nov.rate_to_base) == pytest.approx(0.625, abs=1e-9)
    assert r_nov.effective_from == D(2026, 11, 1)

    r_dec = rate_on(e.db, "RMB", D(2026, 12, 1))
    assert f(r_dec.rate_to_base) == pytest.approx(0.613497, abs=1e-9)
    assert r_dec.effective_from == D(2026, 12, 1)

    # a day later than the last row keeps the last row
    assert f(rate_on(e.db, "RMB", D(2027, 3, 3)).rate_to_base) == pytest.approx(0.613497, abs=1e-9)


def test_ac_er_03_no_row_on_or_before_the_day_is_none_never_one(costing_env):
    from app.services.costing.rates import rate_on

    e = costing_env
    e.rate("RMB", "0.617284", D(2026, 9, 1))
    e.db.commit()

    assert rate_on(e.db, "RMB", D(2026, 8, 31)) is None  # before the first row
    assert rate_on(e.db, "EUR", D(2026, 11, 11)) is None  # a currency with no row at all


def test_ac_er_02_rates_are_per_currency(costing_env):
    from app.services.costing.rates import rate_on

    e = costing_env
    e.rate("RMB", "0.625", D(2026, 11, 1))
    e.rate("USD", "4.40", D(2026, 1, 1))
    e.db.commit()
    assert f(rate_on(e.db, "USD", D(2026, 11, 11)).rate_to_base) == pytest.approx(4.4)
    assert f(rate_on(e.db, "RMB", D(2026, 11, 11)).rate_to_base) == pytest.approx(0.625)


# ------------------------------------------------------------------ AC-ER-01 (routes)


def test_ac_er_01_add_a_rate_and_a_duplicate_pair_is_409(costing_env):
    e = costing_env
    e.as_user(e.user(RATE_WRITE, COST_VIEW))
    body = {"currency": "RMB", "effective_from": "2026-11-01", "rate_to_base": 0.625, "note": "bank"}
    row = _ok(e.post("/exchange-rates", body))
    assert row["currency"] == "RMB"
    assert row["effective_from"] == "2026-11-01"
    assert row["rate_to_base"] == pytest.approx(0.625)
    assert row["note"] == "bank"

    again = e.post("/exchange-rates", {**body, "rate_to_base": 0.7})
    assert again.status_code == 409, again.text

    # a different date for the same currency is fine
    other = e.post("/exchange-rates", {"currency": "RMB", "effective_from": "2026-12-01", "rate_to_base": 0.613497})
    assert other.status_code in (200, 201), other.text


@pytest.mark.parametrize("field,value", [
    ("rate_to_base", 0), ("rate_to_base", -0.5), ("units_per_base", 0), ("units_per_base", -1.6),
])
def test_ac_er_01_a_rate_not_greater_than_zero_is_422(costing_env, field, value):
    e = costing_env
    e.as_user(e.user(RATE_WRITE, COST_VIEW))
    r = e.post("/exchange-rates", {"currency": "RMB", "effective_from": "2026-11-01", field: value})
    assert r.status_code == 422, r.text


def test_ac_er_07_exactly_one_of_the_two_rate_fields(costing_env):
    e = costing_env
    e.as_user(e.user(RATE_WRITE, COST_VIEW))
    both = e.post("/exchange-rates", {"currency": "RMB", "effective_from": "2026-11-01",
                                      "rate_to_base": 0.625, "units_per_base": 1.6})
    assert both.status_code == 422, both.text
    neither = e.post("/exchange-rates", {"currency": "RMB", "effective_from": "2026-11-01"})
    assert neither.status_code == 422, neither.text


def test_ac_er_03_myr_row_is_refused(costing_env):
    e = costing_env
    e.as_user(e.user(RATE_WRITE, COST_VIEW))
    r = e.post("/exchange-rates", {"currency": "MYR", "effective_from": "2026-11-01", "rate_to_base": 1})
    assert r.status_code == 422, r.text
    r2 = e.post("/exchange-rates", {"currency": "myr", "effective_from": "2026-11-01", "rate_to_base": 1})
    assert r2.status_code == 422, r2.text


def test_ac_er_07_units_per_myr_entry_stores_the_inverse_and_both_directions_return(costing_env):
    from app.models.costing import ExchangeRate

    e = costing_env
    e.as_user(e.user(RATE_WRITE, COST_VIEW))
    row = _ok(e.post("/exchange-rates", {"currency": "RMB", "effective_from": "2026-11-01",
                                         "units_per_base": 1.6}))
    assert row["rate_to_base"] == pytest.approx(0.625, abs=1e-9)
    assert row["units_per_base"] == pytest.approx(1.6, abs=1e-4)

    stored = e.db.query(ExchangeRate).filter(ExchangeRate.id == row["id"]).one()
    assert f(stored.rate_to_base) == pytest.approx(0.625, abs=1e-9)  # stored 0.625000

    listed = e.get("/exchange-rates", currency="RMB")
    assert listed.status_code == 200, listed.text
    got = listed.json()["data"]
    assert len(got) == 1
    assert got[0]["rate_to_base"] == pytest.approx(0.625, abs=1e-9)
    assert got[0]["units_per_base"] == pytest.approx(1.6, abs=1e-4)


def test_ac_er_07_units_per_base_is_rounded_to_four_places(costing_env):
    e = costing_env
    e.as_user(e.user(RATE_WRITE, COST_VIEW))
    _ok(e.post("/exchange-rates", {"currency": "RMB", "effective_from": "2026-09-01",
                                   "rate_to_base": 0.617284}))
    got = e.get("/exchange-rates", currency="RMB").json()["data"][0]
    assert got["units_per_base"] == pytest.approx(1.62, abs=1e-4)
    assert got["units_per_base"] == round(got["units_per_base"], 4)


def test_ac_er_01_list_is_newest_first_per_currency_with_status(costing_env):
    """Margins of 10+ days either side of today keep this independent of the clock zone."""
    e = costing_env
    today = date.today()
    e.rate("RMB", "0.60", today - timedelta(days=60))
    e.rate("RMB", "0.625", today - timedelta(days=10))
    e.rate("RMB", "0.70", today + timedelta(days=10))
    e.rate("USD", "4.40", today - timedelta(days=30))
    e.db.commit()
    e.as_user(e.viewer())

    data = e.get("/exchange-rates", currency="RMB").json()["data"]
    assert [d["effective_from"] for d in data] == [
        (today + timedelta(days=10)).isoformat(),
        (today - timedelta(days=10)).isoformat(),
        (today - timedelta(days=60)).isoformat(),
    ]
    assert [d["status"] for d in data] == ["scheduled", "in_force", "past"]

    everything = e.get("/exchange-rates").json()["data"]
    assert {d["currency"] for d in everything} == {"RMB", "USD"}


def test_ac_er_01_put_edits_a_rate_and_accepts_units_per_base(costing_env):
    e = costing_env
    row = e.rate("RMB", "0.625", D(2026, 11, 1), note="old")
    e.db.commit()
    e.as_user(e.user(RATE_WRITE, COST_VIEW))

    r = e.put(f"/exchange-rates/{row.id}", {"rate_to_base": 0.63, "note": "new"})
    assert r.status_code == 200, r.text
    assert r.json()["rate_to_base"] == pytest.approx(0.63)
    assert r.json()["note"] == "new"

    r2 = e.put(f"/exchange-rates/{row.id}", {"units_per_base": 1.6})
    assert r2.status_code == 200, r2.text
    assert r2.json()["rate_to_base"] == pytest.approx(0.625, abs=1e-9)

    bad = e.put(f"/exchange-rates/{row.id}", {"rate_to_base": 0})
    assert bad.status_code == 422, bad.text


# ------------------------------------------------------------------ AC-ER-06 audit + deferred delete


def test_ac_er_06_add_and_edit_each_write_an_audit_row_with_old_and_new(costing_env):
    e = costing_env
    e.as_user(e.user(RATE_WRITE, COST_VIEW))
    row = _ok(e.post("/exchange-rates", {"currency": "RMB", "effective_from": "2026-11-01",
                                         "rate_to_base": 0.625}))
    audits = e.audit_rows("exchange_rates", row["id"])
    assert [a.action for a in audits] == ["INSERT"]

    assert e.put(f"/exchange-rates/{row['id']}", {"rate_to_base": 0.64}).status_code == 200
    audits = e.audit_rows("exchange_rates", row["id"])
    assert [a.action for a in audits] == ["INSERT", "UPDATE"]
    upd = audits[-1]
    assert float(upd.old_values["rate_to_base"]) == pytest.approx(0.625)
    assert float(upd.new_values["rate_to_base"]) == pytest.approx(0.64)
    assert upd.user_id == e.principal["id"]


def test_ac_er_06_delete_is_a_registered_deferred_destructive_action(costing_env):
    import app.services.record_actions  # noqa: F401  (registers the actions)
    from app.models.costing import ExchangeRate
    from app.services.form_action_grace import WINDOW_DESTRUCTIVE
    from app.services.form_action_registry import get_action

    action = get_action("exchange_rate.delete")
    assert action is not None
    assert action.entity_types == ("exchange_rate",)
    assert action.window == WINDOW_DESTRUCTIVE
    assert action.permission == "scm.config.manage"

    e = costing_env
    row = e.rate("RMB", "0.625", D(2026, 11, 1))
    e.db.commit()
    rid = str(row.id)

    action.execute(e.db, {"entity_id": rid})
    e.db.flush()
    assert e.db.query(ExchangeRate).filter(ExchangeRate.id == rid).count() == 0

    # already gone is not an error (the grace window can lapse after a manual delete)
    action.execute(e.db, {"entity_id": rid})


def test_ac_er_06_deferred_delete_writes_an_audit_row(costing_env):
    import app.services.record_actions  # noqa: F401
    from app.services.form_action_registry import get_action

    e = costing_env
    e.as_user(e.user(RATE_WRITE, COST_VIEW))
    row = _ok(e.post("/exchange-rates", {"currency": "USD", "effective_from": "2026-01-01",
                                         "rate_to_base": 4.4}))
    get_action("exchange_rate.delete").execute(e.db, {"entity_id": row["id"]})
    e.db.commit()
    assert [a.action for a in e.audit_rows("exchange_rates", row["id"])][-1] == "DELETE"


# ------------------------------------------------------------------ gates (AC-ER-07, AC-AX-01)


def test_ac_er_07_writing_needs_scm_config_manage_and_cost_view(costing_env):
    e = costing_env
    body = {"currency": "RMB", "effective_from": "2026-11-01", "rate_to_base": 0.625}

    e.as_user(e.user(COST_VIEW))
    assert e.post("/exchange-rates", body).status_code == 403
    e.as_user(e.user(RATE_WRITE))
    assert e.post("/exchange-rates", body).status_code == 403
    e.as_user(e.user())
    assert e.post("/exchange-rates", body).status_code == 403

    row = e.rate("RMB", "0.625", D(2026, 11, 1))
    e.db.commit()
    e.as_user(e.user(COST_VIEW))
    assert e.put(f"/exchange-rates/{row.id}", {"rate_to_base": 0.7}).status_code == 403
    e.as_user(e.user(RATE_WRITE))
    assert e.put(f"/exchange-rates/{row.id}", {"rate_to_base": 0.7}).status_code == 403

    e.as_user(e.user(RATE_WRITE, COST_VIEW))
    assert e.post("/exchange-rates", body).status_code in (200, 201)


def test_ac_ax_01_reading_rates_needs_cost_view(costing_env):
    e = costing_env
    e.rate("RMB", "0.625", D(2026, 11, 1))
    e.db.commit()
    e.as_user(e.user(RATE_READ))  # the SCM read slug is not the costing one
    assert e.get("/exchange-rates").status_code == 403
    e.as_user(e.viewer())
    assert e.get("/exchange-rates").status_code == 200


# ------------------------------------------------------------------ AC-ER-07 SCM routes keep their gates, now dated


SCM_RATES = "/api/v1/scm/config/currency-rates"


def test_ac_er_07_scm_read_keeps_dashboard_view_and_write_keeps_config_manage(costing_env):
    from app.models.costing import ExchangeRate

    e = costing_env
    e.as_user(e.user())
    assert e.client.get(SCM_RATES).status_code == 403
    assert e.client.put(f"{SCM_RATES}/USD", json={"rate_to_base": 4.4}).status_code == 403

    e.as_user(e.user(RATE_READ))
    assert e.client.get(SCM_RATES).status_code == 200
    assert e.client.put(f"{SCM_RATES}/USD", json={"rate_to_base": 4.4}).status_code == 403

    e.as_user(e.user(RATE_WRITE))
    r = e.client.put(f"{SCM_RATES}/USD", json={"rate_to_base": 4.4, "as_of": "2026-08-01"})
    assert r.status_code == 200, r.text
    # the SCM write lands in the dated table at effective_from = as_of (contract 4.8)
    row = e.db.query(ExchangeRate).filter(ExchangeRate.currency == "USD").one()
    assert row.effective_from == D(2026, 8, 1)
    assert f(row.rate_to_base) == pytest.approx(4.4)
