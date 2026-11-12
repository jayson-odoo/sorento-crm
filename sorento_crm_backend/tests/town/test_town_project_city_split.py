"""TOWN-PROJECT-CITY Phase 2 (red): `today.split` and the project share of `deliveries`.

Contract: PLAN-town-project-city-11nov.md "Phase 2 contract" (`today.split`, `deliveries.project_orders`,
`deliveries.project_states`). Postgres only (`blank_session`), every row seeded here.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.main import app  # noqa: F401
from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID, seed_mocha
from tests._pg_fixture import blank_session
from tests._sales_unified_seed import cust, doc, line
from tests.town._town_project_seed import delivery_order, due_order
from tests.town._town_seed import DAY, NOW, D, dealer_doc, project_doc


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        seed_mocha(s)
        yield s


def _build(db, company_id=DEFAULT_COMPANY_ID):
    from app.services.town.snapshot import build_snapshot

    return build_snapshot(db, company_id, DAY, now=NOW)


def _seed_mixed_day(db):
    a, b, c = cust(db), cust(db), cust(db)
    dealer_doc(db, a, "1000.00", DAY)
    dealer_doc(db, a, "100.00", DAY, kind="credit_note")  # dealer credit note: negative, not counted
    project_doc(db, b, "2500.50", DAY)
    project_doc(db, b, "300.00", DAY)
    doc(db, "invoice", "75.25", DAY, customer=c, lines=[line()])  # no sales order: other
    doc(db, "credit_note", "25.00", DAY, customer=c, lines=[line()])  # other credit note
    # all of these stay out of today
    dealer_doc(db, a, "999.99", DAY - timedelta(days=1))
    doc(db, "invoice", "888.00", DAY, customer=c, status="cancelled")
    doc(db, "invoice", "5000.00", DAY, customer=cust(db, company_id=MOCHA_ID), company_id=MOCHA_ID)


def test_split_amounts_per_type_with_credit_notes_signed(db):
    _seed_mixed_day(db)
    split = _build(db)["today"]["split"]
    assert split["dealer"]["amount"] == "900.00"
    assert split["project"]["amount"] == "2800.50"
    assert split["other"]["amount"] == "50.25"
    assert all(isinstance(split[k]["amount"], str) for k in ("dealer", "project", "other"))


def test_split_counts_exclude_credit_notes(db):
    _seed_mixed_day(db)
    split = _build(db)["today"]["split"]
    assert [split[k]["invoice_count"] for k in ("dealer", "project", "other")] == [1, 2, 1]


def test_split_adds_up_to_today_exactly(db):
    _seed_mixed_day(db)
    today = _build(db)["today"]
    total = sum(D(today["split"][k]["amount"]) for k in ("dealer", "project", "other"))
    assert total == D(today["amount"]) == D("3750.75")
    assert sum(today["split"][k]["invoice_count"] for k in ("dealer", "project", "other")) == today["invoice_count"] == 4


def test_split_on_an_empty_day_is_zero_not_missing(db):
    assert _build(db)["today"]["split"] == {
        "dealer": {"amount": "0.00", "invoice_count": 0},
        "project": {"amount": "0.00", "invoice_count": 0},
        "other": {"amount": "0.00", "invoice_count": 0},
    }


def test_split_has_exactly_the_three_keys(db):
    _seed_mixed_day(db)
    assert set(_build(db)["today"]["split"]) == {"dealer", "project", "other"}


def test_split_is_per_company(db):
    _seed_mixed_day(db)
    mocha = _build(db, MOCHA_ID)["today"]["split"]
    assert sum(D(mocha[k]["amount"]) for k in mocha) == D("5000.00")
    assert sum(mocha[k]["invoice_count"] for k in mocha) == 1


# ------------------------------------------------------------------------------ deliveries


def test_project_orders_counts_due_sales_orders_with_demand_class_project(db):
    c = cust(db)
    due_order(db, c, DAY - timedelta(days=2), "project")
    due_order(db, c, DAY, "project")
    due_order(db, c, DAY - timedelta(days=1), "retail")  # a dealer order: due, not project
    due_order(db, c, DAY + timedelta(days=3), "project")  # not due yet
    out = _build(db)["deliveries"]
    assert out["to_deliver"] == 3
    assert out["project_orders"] == 2


def test_project_orders_zero_and_empty_states_when_nothing_due(db):
    out = _build(db)["deliveries"]
    assert out["project_orders"] == 0
    assert out["project_states"] == []


def test_project_states_are_the_customers_state_earliest_due_first_cap_three(db):
    johor = cust(db)
    johor.region = "Johor"
    sabah = cust(db)
    sabah.region = "sabah"  # matched through my_state, case-insensitive
    nowhere = cust(db)  # no region, no delivery orders: state null
    selangor = cust(db)
    selangor.region = "Selangor"
    db.flush()
    due_order(db, sabah, DAY - timedelta(days=9), "project")
    due_order(db, nowhere, DAY - timedelta(days=7), "project")
    due_order(db, johor, DAY - timedelta(days=5), "project")
    due_order(db, selangor, DAY - timedelta(days=1), "project")  # the fourth: cut by the cap
    out = _build(db)["deliveries"]
    assert out["project_orders"] == 4
    assert out["project_states"] == [
        {"state": "Sabah", "orders": 1},
        {"state": None, "orders": 1},
        {"state": "Johor", "orders": 1},
    ]


def test_project_states_use_the_postcode_rule_when_region_is_empty(db):
    c = cust(db)
    delivery_order(db, c, "Lot 1, Jalan X, 81300 Skudai, Johor", DAY - timedelta(days=3))
    due_order(db, c, DAY - timedelta(days=1), "project")
    assert _build(db)["deliveries"]["project_states"] == [{"state": "Johor", "orders": 1}]
