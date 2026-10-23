"""REPORT-SMART-L one ranking, round R3b (AC-OR3): the report ask carries the agent fill-rate note.

The old top selling report computed `sales_agent_fill_rate` only when a sales agent filter was used:
the share of the window's sales orders (every other filter applied, the agent filter NOT) that carry
any sales agent at all, and its reply printed "Note: only N% of sales orders in this period carry a
sales agent." below 95%. Item and category rankings now run on the report ask, which has neither.
The presenter half is in `sorento_crm_mcp/tests/test_one_ranking_r3b_presenter.py`. Postgres only;
every row seeded here (generic names).
"""
from __future__ import annotations

import pytest

from tests._chat_asker_seed import link_user
from tests._sales_report_do_seed import _contact, seed_agent, seed_customer, warehouse  # noqa: F401
from tests.test_report_ask_route import _ask, _ok, _prod, _sale, client, db  # noqa: F401
from tests.test_top_selling_report import _access
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code


def _staff(db):
    contact = _contact(db, granted=True)
    link_user(db, contact)
    _access(db, contact, "Sorento Office")
    db.commit()
    return contact


def _world(db, *, with_agent: int, without_agent: int):
    """`with_agent` SOs of agent A and `without_agent` SOs with no agent, one product each, one window."""
    cust = seed_customer(db, name=unique_code("Cust"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    agent = seed_agent(db, code=unique_code("Agent"))
    for i in range(with_agent):
        _sale(db, cust=cust, wh=wh, agent=agent, prod=_prod(db, unique_code("ZZTA", alpha=True)), qty=2, total="20.00")
    for i in range(without_agent):
        _sale(db, cust=cust, wh=wh, agent=None, prod=_prod(db, unique_code("ZZTN", alpha=True)), qty=1, total="10.00")
    db.commit()
    return agent


@pytest.mark.parametrize("group_by", ["product", "category"])
def test_r3b_1_an_item_ranking_with_an_agent_filter_carries_the_fill_rate(client, db, group_by) -> None:
    agent = _world(db, with_agent=2, without_agent=3)  # 2 of 5 sales orders carry an agent
    body = _ok(client, _staff(db), group_by=group_by, top_n=5, sales_agent_ids=[agent.id])
    assert body.get("sales_agent_fill_rate") == pytest.approx(0.4), body


def test_r3b_1_a_full_fill_is_carried_too_and_the_presenter_hides_it(client, db) -> None:
    agent = _world(db, with_agent=3, without_agent=0)
    body = _ok(client, _staff(db), group_by="product", top_n=5, sales_agent_ids=[agent.id])
    assert body.get("sales_agent_fill_rate") == pytest.approx(1.0), body


def test_r3b_2_guard_a_ranking_with_no_agent_filter_carries_no_fill_rate(client, db) -> None:
    _world(db, with_agent=2, without_agent=3)
    body = _ok(client, _staff(db), group_by="product", top_n=5)
    assert not body.get("sales_agent_fill_rate"), body


def test_r3b_3_guard_the_fill_rate_counts_only_the_contacts_company(client, db) -> None:
    from tests._mc_lookup_seed import seed_mocha

    agent = _world(db, with_agent=2, without_agent=3)  # the contact's company: 2 of 5 carry an agent
    mocha = seed_mocha(db)
    cust = seed_customer(db, name=unique_code("MochaCust"), company_id=mocha.id)
    wh = warehouse(db, company_id=mocha.id)
    for _ in range(10):  # another company: ten sales orders, none with an agent
        _sale(db, cust=cust, wh=wh, agent=None, prod=_prod_in(db, mocha.id), qty=1, total="10.00")
    db.commit()
    body = _ok(client, _staff(db), group_by="product", top_n=5, sales_agent_ids=[agent.id])
    assert body.get("sales_agent_fill_rate") == pytest.approx(0.4), body


def _prod_in(db, company_id):
    from tests._mc_lookup_seed import product

    return product(db, company_id=company_id, code=unique_code("ZZTM", alpha=True))
