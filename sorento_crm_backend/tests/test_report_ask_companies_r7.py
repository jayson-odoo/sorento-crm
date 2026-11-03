"""Round 7 RED tests (O-R2, route): `GET /order-management/report-ask` with no `company` and a contact holding 2+ companies
adds `companies` = [{"name", "amount", "qty"}] (one per company with a figure for the filters, in the contact's company
order, the same filters, totals only); a named `company`, or a one-company contact, has no `companies` key.

Pinned shape (flagged to the captain): the entry carries the same figure keys the total does (`amount`, `qty`), flat.
Postgres only, every row seeded here.
"""
from __future__ import annotations

from decimal import Decimal

from app.models.company import Company
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import seed_mocha
from tests._sales_report_do_seed import client, db, money  # noqa: F401  (fixtures)
from tests.test_report_ask_account_type import _ask, _ledger, _ok, _sale, _staff

D = Decimal


def _world(db):
    mocha = seed_mocha(db)
    _sale(db, "invoiced", _ledger(db), "100.00")
    _sale(db, "invoiced", _ledger(db), "50.00")
    _sale(db, "invoiced", _ledger(db, company_id=mocha.id), "400.00", company_id=mocha.id)
    db.commit()
    names = {c.id: c.name for c in db.query(Company).all()}
    return mocha, names[DEFAULT_COMPANY_ID], names[mocha.id]


def test_two_companies_with_figures_and_no_company_gives_a_total_per_company(client, db) -> None:
    mocha, sorento, mocha_name = _world(db)
    body = _ok(client, _staff(db, extra_company=mocha.id))
    companies = body.get("companies")
    assert companies, f"O-R2: no `companies` in the body: {sorted(body)}"
    assert [c["name"] for c in companies] == [sorento, mocha_name], companies
    assert [money(c["amount"]) for c in companies] == [D("150.00"), D("400.00")], companies
    assert sum(money(c["amount"]) for c in companies) == money(body["total"]["amount"]) == D("550.00"), (companies, body["total"])


def test_a_named_company_has_no_companies_key(client, db) -> None:
    mocha, _sorento, mocha_name = _world(db)
    body = _ok(client, _staff(db, extra_company=mocha.id), company=mocha_name)
    assert money(body["total"]["amount"]) == D("400.00"), body["total"]
    assert "companies" not in body or not body["companies"], body.get("companies")


def test_a_one_company_contact_has_no_companies_key(client, db) -> None:
    _mocha, _sorento, _m = _world(db)
    body = _ok(client, _staff(db))
    assert money(body["total"]["amount"]) == D("150.00"), body["total"]
    assert "companies" not in body or not body["companies"], body.get("companies")


def test_a_company_with_no_figure_for_the_filters_is_left_out(client, db) -> None:
    """Guard (a vacuous pass today: the key is absent): Mocha holds no sale for the filters, so it is not listed."""
    mocha = seed_mocha(db)
    _sale(db, "invoiced", _ledger(db), "100.00")
    db.commit()
    names = {c.id: c.name for c in db.query(Company).all()}
    body = _ok(client, _staff(db, extra_company=mocha.id))
    assert names[mocha.id] not in [c["name"] for c in body.get("companies") or []], body.get("companies")


def test_a_breakdown_carries_company_totals_only(client, db) -> None:
    mocha, sorento, mocha_name = _world(db)
    body = _ok(client, _staff(db, extra_company=mocha.id), group_by="month", top_n=100)
    companies = body.get("companies")
    assert companies, f"O-R2: no `companies` on a breakdown: {sorted(body)}"
    assert [c["name"] for c in companies] == [sorento, mocha_name], companies
    assert all(set(c) <= {"name", "amount", "qty", "count"} for c in companies), f"totals only, no rows: {companies}"
    assert sum(money(c["amount"]) for c in companies) == money(body["total"]["amount"]), (companies, body["total"])


def test_no_companies_when_compare_to_is_set(client, db) -> None:
    """Q5 route: a comparison run carries no per-company split."""
    mocha, _sorento, _m = _world(db)
    body = _ok(client, _staff(db, extra_company=mocha.id), compare_to="previous_period")
    assert body.get("status") == "ok", body
    assert "companies" not in body or not body["companies"], body.get("companies")


def test_no_companies_when_the_run_is_not_ok(client, db) -> None:
    """Q5 route: a refused / not-ok run carries no per-company split."""
    mocha, _sorento, _m = _world(db)
    resp = _ask(client, _staff(db, extra_company=mocha.id), account_types="ZZNOPE")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("status") != "ok", f"setup: want a not-ok run, got {body.get('status')}"
    assert "companies" not in body or not body["companies"], body.get("companies")
