"""TOWN-PROJECT-CITY Phase 2 (red): `trading_houses` section of the snapshot.

Contract: PLAN-town-project-city-11nov.md "Phase 2 contract" (`trading_houses`). Postgres only.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.main import app  # noqa: F401
from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID, seed_mocha
from tests._pg_fixture import blank_session
from tests._sales_unified_seed import cust, doc, line, so
from tests.town._town_project_seed import funnel, link_trading_house, project
from tests.town._town_seed import DAY, NOW, dealer_doc, project_doc


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        seed_mocha(s)
        yield s


@pytest.fixture
def ids(db):
    return funnel(db)


def _houses(db, company_id=DEFAULT_COMPANY_ID):
    from app.services.town.snapshot import build_snapshot

    return build_snapshot(db, company_id, DAY, now=NOW)["trading_houses"]


def test_empty_section_when_no_trading_house(db, ids):
    assert _houses(db) == {"more": 0, "rows": []}


def test_trading_house_party_with_customer_on_open_project_is_a_row(db, ids):
    th = cust(db, name="ZZT TH Alpha")
    th.region = "Kuala Lumpur"
    db.flush()
    link_trading_house(db, project(db, ids), th)
    out = _houses(db)
    assert out["more"] == 0
    assert out["rows"] == [{
        "key": str(th.id), "name": "ZZT TH Alpha", "state": "Kuala Lumpur", "open_projects": 1, "today_docs": 0,
    }]


def test_party_without_customer_id_is_not_a_row(db, ids):
    link_trading_house(db, project(db, ids), cust(db), with_customer=False)
    assert _houses(db)["rows"] == []


def test_other_roles_are_not_trading_houses(db, ids):
    link_trading_house(db, project(db, ids), cust(db), role="architect")
    assert _houses(db)["rows"] == []


@pytest.mark.parametrize("outcome,stage", [("lost", "lost"), ("won", "po_received"), ("dormant", "dormant")])
def test_closed_projects_only_means_no_row(db, ids, outcome, stage):
    link_trading_house(db, project(db, ids, outcome=outcome, stage=stage), cust(db))
    assert _houses(db)["rows"] == []


def test_unapproved_portal_project_gives_no_row(db, ids):
    link_trading_house(db, project(db, ids, approval="pending"), cust(db))
    assert _houses(db)["rows"] == []


def test_open_projects_counts_only_open_ones_and_each_once(db, ids):
    th = cust(db)
    open_a, open_b = project(db, ids), project(db, ids)
    link_trading_house(db, open_a, th)
    link_trading_house(db, open_a, th)  # a second party of the same customer on the same project
    link_trading_house(db, open_b, th)
    link_trading_house(db, project(db, ids, outcome="lost", stage="lost"), th)
    (row,) = _houses(db)["rows"]
    assert row["open_projects"] == 2


def test_cap_twelve_with_more_ordered_by_open_projects_then_code(db, ids):
    houses = [cust(db, code=f"ZZT-TH{i:02d}", name=f"ZZT House {i:02d}") for i in range(14)]
    for house in houses:
        link_trading_house(db, project(db, ids), house)
    link_trading_house(db, project(db, ids), houses[13])  # two open projects: first
    out = _houses(db)
    assert len(out["rows"]) == 12
    assert out["more"] == 2
    assert [r["name"] for r in out["rows"]] == ["ZZT House 13"] + [f"ZZT House {i:02d}" for i in range(11)]
    assert out["rows"][0]["open_projects"] == 2


def test_today_docs_counts_only_project_type_invoices_posted_today(db, ids):
    th = cust(db)
    link_trading_house(db, project(db, ids), th)
    project_doc(db, th, "100.00", DAY)
    project_doc(db, th, "50.00", DAY)
    project_doc(db, th, "70.00", DAY - timedelta(days=1))  # yesterday
    dealer_doc(db, th, "10.00", DAY)  # a dealer-type document does not light the tower
    doc(db, "invoice", "5.00", DAY, customer=th, lines=[line()])  # no sales order
    project_doc(db, th, "20.00", DAY).status = "cancelled"
    db.flush()
    (row,) = _houses(db)["rows"]
    assert row["today_docs"] == 2


def test_credit_note_does_not_count_as_a_doc(db, ids):
    th = cust(db)
    link_trading_house(db, project(db, ids), th)
    project_doc(db, th, "100.00", DAY)
    header, _ = so(db, demand_class="project", customer=th)
    doc(db, "credit_note", "30.00", DAY, customer=th, lines=[line(net="30.00", from_type="SO", from_no=header.so_number)])
    (row,) = _houses(db)["rows"]
    assert row["today_docs"] == 1


def test_state_follows_the_postcode_rule(db, ids):
    from tests.town._town_project_seed import addr, delivery_order

    th = cust(db)
    delivery_order(db, th, addr("81300", "Skudai", "Johor"), DAY - timedelta(days=2))
    link_trading_house(db, project(db, ids), th)
    (row,) = _houses(db)["rows"]
    assert row["state"] == "Johor"


def test_state_null_when_unresolved(db, ids):
    link_trading_house(db, project(db, ids), cust(db))
    (row,) = _houses(db)["rows"]
    assert row["state"] is None


def test_other_company_trading_houses_are_absent(db, ids):
    mocha_th = cust(db, company_id=MOCHA_ID)
    link_trading_house(db, project(db, ids, company_id=MOCHA_ID), mocha_th)
    assert _houses(db)["rows"] == []
    assert [r["key"] for r in _houses(db, MOCHA_ID)["rows"]] == [str(mocha_th.id)]
