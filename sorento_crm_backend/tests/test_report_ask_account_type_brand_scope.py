"""SALES-ACCOUNT-TYPE PR 1, AT-14: a brand-scoped contact's figure stays inside its brands with the
account filter on (own file: the brand-scope harness brings its own `db` and `api` fixtures, and the real
`apply_company_scope` that stamps the brand scope). Every row is seeded here; fictional names only.

World: one ledger typed CABANA and tagged [A/C IV] (plus a second so the number has a type), with a MOCHA
brand line 2 x 100.00 and a SORENTO brand line 3 x 1000.00, both fully delivered in September 2026.
A MOCHA-only contact sees 100.00 under account 4, an unscoped one 1,100.00.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests._brand_scope_seed import api, db, leaks, world  # noqa: F401  (fixtures by name)
from tests._report_ask_so_seed import seed_so_line
from tests._sales_report_do_seed import money
from tests._sales_unified_seed import cust

D = Decimal
ROUTE = "/api/v1/order-management/report-ask"
PERIOD = {"date_from": "2026-09-01", "date_to": "2026-09-30"}


@pytest.fixture
def typed(db, world):
    world.cust.customer_name = "ZZT BRAND CUSTOMER [A/C IV]"
    world.cust.autocount_debtor_type = "CABANA"
    cust(db, debtor_type="CABANA", name="ZZT SECOND LEDGER [A/C IV]")
    seed_so_line(db, cust=world.cust, prod=world.p_mocha, qty=2, total="100.00")
    seed_so_line(db, cust=world.cust, prod=world.p_sorento, qty=3, total="1000.00")
    db.commit()
    return world


def _ask(api, who, **params):
    resp = api.get(ROUTE, who, **PERIOD, basis="delivered", measure="amount", **params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_at_14_a_brand_scoped_contacts_account_figure_stays_inside_its_brands(api, typed) -> None:
    assert money(_ask(api, typed.scoped, account_types="4")["total"]["amount"]) == D("100.00")
    assert money(_ask(api, typed.unscoped, account_types="4")["total"]["amount"]) == D("1100.00")


def test_at_14_a_brand_scoped_contacts_split_by_account_type_stays_inside_its_brands(api, typed) -> None:
    body = _ask(api, typed.scoped, group_by="account_type", top_n=10)
    assert [(r["name"], money(r["amount"])) for r in body["rows"]] == [("CABANA", D("100.00"))], body["rows"]
