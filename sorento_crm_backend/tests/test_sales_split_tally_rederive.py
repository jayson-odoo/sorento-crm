"""SALES-SPLIT-TALLY: the bulk re-derive never clears a stored sales order class.

The owner's prod dry run of `scripts/sales_order_class_rederive.py --company SRT` (30 Oct) would
have set about 15,800 orders to NULL ("Sales order type not set"): every order of an agent with no
class row and no mirror (historic agents, `sales_unified_0002` seeded rows only from a non-NULL
mirror) and every order with no agent. The bulk run therefore keeps a stored class whenever the
rule's answer is "nothing" (`rederive(keep_unset=True)`); it still moves an order whose agent HAS
a class, or whose type is stated. The screen's own edits keep Q8 (a) unchanged
(`test_sales_unified_agent_classes.py::test_q8_an_agent_with_no_class_leaves_the_order_unset_never_the_segment`).

Postgres only, every row seeded here; fictional codes.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.main import app  # noqa: F401  (import order)
from app.models.base import set_company_scope
from app.models.order import SalesOrder
from app.models.sales import SalesAgentClass
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import blank_session, unique_code
from tests._sales_unified_seed import agent, so

JUN = date(2026, 1, 15)


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


def _order(db, agent_row, *, demand_class, order_type=None, when=JUN):
    header, _ = so(db, demand_class=demand_class)
    header.sales_agent_id = agent_row.id if agent_row is not None else None
    header.order_date = when
    header.order_type = order_type
    db.flush()
    return header


def _class_of(db, header):
    db.expire_all()
    return db.get(SalesOrder, header.id).demand_class


def _seed(db):
    historic = agent(db, unique_code("ZZTHIS"))  # no class row, no mirror
    classed = agent(db, unique_code("ZZTCLS"))
    db.add(SalesAgentClass(sales_agent_id=classed.id, demand_class="other"))
    db.flush()
    return {
        "historic": _order(db, historic, demand_class="project"),
        "no_agent": _order(db, None, demand_class="retail"),
        "classed": _order(db, classed, demand_class="retail"),
        "stated": _order(db, historic, demand_class="retail", order_type="PROJECT"),
    }, [historic, classed]


def test_the_bulk_rederive_keeps_a_stored_class_when_the_rule_gives_none(db):
    from app.services.sales import agent_class_service as svc

    orders, agents = _seed(db)

    moves = svc.rederive(db, company_id=DEFAULT_COMPANY_ID, keep_unset=True, apply=False)
    mine = [m for m in moves if m.agent in {a.sales_agent for a in agents}]
    assert sorted((m.before, m.after) for m in mine) == [("retail", "other"), ("retail", "project")]
    assert all(m.after is not None for m in moves)

    svc.rederive(db, company_id=DEFAULT_COMPANY_ID, keep_unset=True, apply=True)
    assert _class_of(db, orders["historic"]) == "project"
    assert _class_of(db, orders["no_agent"]) == "retail"
    assert _class_of(db, orders["classed"]) == "other"
    assert _class_of(db, orders["stated"]) == "project"


def test_without_keep_unset_the_rule_still_clears_them(db):
    """The screen-edit path (Q8 (a) as ruled) is unchanged."""
    from app.services.sales import agent_class_service as svc

    orders, agents = _seed(db)
    svc.rederive(db, agent_ids=[str(a.id) for a in agents], apply=True)
    assert _class_of(db, orders["historic"]) is None
    assert _class_of(db, orders["classed"]) == "other"


def test_the_script_runs_the_bulk_rederive_with_keep_unset(db, monkeypatch):
    import app.database
    from app.services.sales import agent_class_service as svc
    from scripts import sales_order_class_rederive as script

    seen = {}

    def fake(_db, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(svc, "rederive", fake)
    monkeypatch.setattr(app.database, "SessionLocal", lambda: db)
    assert script.main([]) == 0
    assert seen.get("keep_unset") is True and seen.get("apply") is False
