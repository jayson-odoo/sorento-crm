"""REPORT-UNIFY phase 3 fix round, R1: the report ask takes a `company` (a name, code or id) that narrows the contact's
companies to that one. A company the contact does not hold is 403 `COMPANY_FORBIDDEN` (the sales analysis route's own
pattern), an unknown one 422 `unknown_company`; the header names the company."""
from __future__ import annotations

import pytest
from decimal import Decimal

from app.models.company import Company, RespondContactCompany
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha
from tests._pg_fixture import unique_code
from tests._report_ask_so_seed import seed_so_line
from tests._sales_report_do_seed import (  # noqa: F401  (client / db are fixtures)
    _as_contact,
    _contact,
    client,
    db,
    money,
    seed_customer,
)
from tests.test_top_selling_report import _access

ROUTE = "/api/v1/order-management/report-ask"
KEY = {"X-API-Key": "k"}
PERIOD = {"date_from": "2026-09-01", "date_to": "2026-09-30"}


def _world(db):
    """Sorento: qty 10 / 4 delivered / RM 1000 (undelivered 6 / 600). Mocha: 10 / 4 / RM 200 (undelivered 6 / 120).
    The contact holds BOTH companies and both reveals."""
    from app.services.contact_field_reveal_service import set_granted_keys

    seed_mocha(db)
    sorento_cust = seed_customer(db, name=unique_code("CS"))
    mocha_cust = seed_customer(db, name=unique_code("CM"), company_id=MOCHA_ID)
    sp, mp = product(db, company_id=DEFAULT_COMPANY_ID), product(db, company_id=MOCHA_ID)
    seed_so_line(db, cust=sorento_cust, prod=sp, qty=10, delivered=4, total="1000.00")
    seed_so_line(db, cust=mocha_cust, prod=mp, qty=10, delivered=4, total="200.00", company_id=MOCHA_ID)
    contact = _contact(db)
    db.add(RespondContactCompany(respond_contact_id=contact.id, company_id=MOCHA_ID))
    set_granted_keys(db, contact.id, ["sales_orders.sales_report", "sales_orders.outstanding"], actor_id=None)
    _access(db, contact, "Sorento Office")
    db.commit()
    names = {c.id: (c.name, c.code) for c in db.query(Company).all()}
    return contact, names


def _ask(client, contact, **params):
    return client.get(ROUTE, params={**PERIOD, "basis": "outstanding", **_as_contact(contact), **params}, headers=KEY)


def _tot(resp):
    assert resp.status_code == 200, resp.text
    total = resp.json()["total"]
    return int(total["qty"]), money(total["amount"])


def test_r1_without_a_company_a_two_company_contact_reads_both_as_today(client, db) -> None:
    contact, _names = _world(db)
    assert _tot(_ask(client, contact)) == (12, Decimal("720.00"))


@pytest.mark.parametrize("how", ["name", "code", "id"])
def test_r1_a_named_company_narrows_the_figure_to_that_company(client, db, how) -> None:
    contact, names = _world(db)
    name, code = names[DEFAULT_COMPANY_ID]
    mname, mcode = names[MOCHA_ID]
    one = {"name": name, "code": code, "id": DEFAULT_COMPANY_ID}[how]
    two = {"name": mname, "code": mcode, "id": MOCHA_ID}[how]
    assert _tot(_ask(client, contact, company=one)) == (6, Decimal("600.00"))
    assert _tot(_ask(client, contact, company=two)) == (6, Decimal("120.00"))


def test_r1_the_header_names_the_company(client, db) -> None:
    contact, names = _world(db)
    resp = _ask(client, contact, company=names[MOCHA_ID][0])
    filters = {f["key"]: f for f in resp.json()["filters"]}
    assert filters["company"]["values"] == [names[MOCHA_ID][0]], resp.json()["filters"]
    assert filters["company"]["label"] == "Company"


def test_r1_a_company_the_contact_does_not_hold_is_403_and_an_unknown_one_422(client, db) -> None:
    contact, names = _world(db)
    db.query(RespondContactCompany).filter(
        RespondContactCompany.respond_contact_id == contact.id, RespondContactCompany.company_id == MOCHA_ID
    ).delete()
    db.commit()
    refused = _ask(client, contact, company=names[MOCHA_ID][0])
    assert refused.status_code == 403 and refused.json()["code"] == "COMPANY_FORBIDDEN", refused.text
    unknown = _ask(client, contact, company="ZZT NO SUCH COMPANY")
    assert unknown.status_code == 422 and unknown.json()["code"] == "unknown_company", unknown.text
