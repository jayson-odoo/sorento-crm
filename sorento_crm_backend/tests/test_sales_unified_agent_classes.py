"""SALES-UNIFIED round 3 (plan 2.9; owner rulings Q6 to Q8 (a)) and the stock position report's
entry point: dated agent classes, the third class `other`, the sales order class re-derived
from them, and `invoiced_sales.quantity_by_product_month`.

Postgres only, every row seeded here; fictional codes.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.main import app  # noqa: F401  (import order)
from app.models.base import set_company_scope
from app.models.order import SalesOrder
from app.models.sales import SalesAgentClass
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.error_handler import AppException
from tests._mc_lookup_seed import product
from tests._pg_fixture import blank_session, unique_code
from tests._sales_unified_seed import agent, by_type, cust, doc, line, so

D = Decimal
JUN = date(2026, 6, 15)
JUL = date(2026, 7, 15)


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


def _order(db, agent_row, when, *, demand_class=None, order_type=None):
    header, lines = so(db, demand_class=demand_class)
    header.sales_agent_id = agent_row.id
    header.order_date = when
    header.order_type = order_type
    db.flush()
    return header, lines


def _class_of(db, header):
    db.expire_all()
    return db.get(SalesOrder, header.id).demand_class


# ------------------------------------------------------------------ dated classes


def test_q6_a_move_from_july_closes_the_open_row_and_rederives_only_july_on(db):
    from app.services.sales import agent_class_service as svc

    a = agent(db, unique_code("ZZTCLS"))
    june, _ = _order(db, a, JUN, demand_class="retail")
    july, _ = _order(db, a, JUL, demand_class="retail")
    svc.add(db, str(a.id), demand_class="retail", from_month=None, to_month=None)
    svc.add(db, str(a.id), demand_class="project", from_month=date(2026, 7, 1), to_month=None)

    rows = svc.rows_of(db, str(a.id))
    assert [(r.demand_class, r.from_month, r.to_month) for r in rows] == [
        ("retail", None, date(2026, 6, 1)),
        ("project", date(2026, 7, 1), None),
    ]
    assert _class_of(db, june) == "retail"
    assert _class_of(db, july) == "project"
    db.expire_all()
    assert db.get(type(a), a.id).demand_class == "project"  # the open row, mirrored


def test_q6_overlapping_rows_and_an_unknown_class_are_422(db):
    from app.services.sales import agent_class_service as svc

    a = agent(db, unique_code("ZZTCLS"))
    svc.add(db, str(a.id), demand_class="retail", from_month=date(2026, 1, 1), to_month=date(2026, 6, 1))
    with pytest.raises(AppException) as overlap:
        svc.add(db, str(a.id), demand_class="project", from_month=date(2026, 3, 1), to_month=date(2026, 4, 1))
    assert overlap.value.status_code == 422 and overlap.value.code == "class_overlap"
    with pytest.raises(AppException) as bad:
        svc.add(db, str(a.id), demand_class="dealer", from_month=date(2027, 1, 1), to_month=None)
    assert bad.value.code == "invalid_class"


def test_q8_the_stated_order_type_wins_over_the_agents_class(db):
    from app.services.sales import agent_class_service as svc

    a = agent(db, unique_code("ZZTCLS"))
    stated, _ = _order(db, a, JUN, demand_class="project", order_type="PROJECT")
    svc.add(db, str(a.id), demand_class="retail", from_month=None, to_month=None)
    assert _class_of(db, stated) == "project"


def test_q8_the_dry_run_reports_moves_and_writes_nothing(db):
    from app.services.sales import agent_class_service as svc

    a = agent(db, unique_code("ZZTCLS"))
    db.add(SalesAgentClass(sales_agent_id=a.id, demand_class="project"))
    db.flush()
    header, _ = _order(db, a, JUN, demand_class="retail")

    moves = svc.rederive(db, agent_ids=[str(a.id)], apply=False)
    assert [(m.agent, m.month, m.before, m.after, m.orders, m.amount) for m in moves] == [
        (a.sales_agent, "2026-06", "retail", "project", 1, D("100.00"))
    ]
    assert _class_of(db, header) == "retail"
    svc.rederive(db, agent_ids=[str(a.id)], apply=True)
    assert _class_of(db, header) == "project"


def test_q8_an_agent_with_no_class_leaves_the_order_unset_never_the_segment(db):
    from app.services.sales import agent_class_service as svc

    a = agent(db, unique_code("ZZTCLS"))
    header, _ = _order(db, a, JUN, demand_class="project")  # stamped by a segment guess
    moves = svc.rederive(db, agent_ids=[str(a.id)], apply=True)
    assert moves and moves[0].after is None
    assert _class_of(db, header) is None


def test_q8_the_class_is_now_x_moves_only_this_month_on(db):
    from app.services.sales import agent_class_service as svc

    a = agent(db, unique_code("ZZTCLS"))
    db.add(SalesAgentClass(sales_agent_id=a.id, demand_class="retail"))
    db.flush()
    past, _ = _order(db, a, date(2025, 1, 10), demand_class="retail")
    # Stored differently from what the dated rule says: an all-time re-derive WOULD move it.
    stale, _ = _order(db, a, date(2025, 2, 10), demand_class="project")
    blank, _ = _order(db, a, date(2025, 3, 10), demand_class=None)
    now, _ = _order(db, a, date(2026, 7, 5), demand_class="retail")
    svc.set_current(db, str(a.id), "project", today=date(2026, 7, 20))
    assert _class_of(db, past) == "retail"
    assert _class_of(db, stale) == "project" and _class_of(db, blank) is None
    assert _class_of(db, now) == "project"
    rows = svc.rows_of(db, str(a.id))
    assert [(r.demand_class, r.from_month, r.to_month) for r in rows] == [
        ("retail", None, date(2026, 6, 1)),
        ("project", date(2026, 7, 1), None),
    ]


def test_q8_the_ingest_reads_the_class_on_the_orders_date():
    from app.services.document_ingest_service import DocumentIngestService  # noqa: F401
    from app.services.sales.agent_class_service import ClassCache, class_on

    rows = [
        SalesAgentClass(demand_class="retail", from_month=None, to_month=date(2026, 6, 1)),
        SalesAgentClass(demand_class="project", from_month=date(2026, 7, 1), to_month=None),
    ]
    assert class_on(rows, JUN) == "retail"
    assert class_on(rows, JUL) == "project"
    assert class_on(rows, None) is None
    assert ClassCache  # the ingest's per-batch reader


# ------------------------------------------------------------------ the third class


def test_q7_other_plans_as_retail_and_reports_as_other(db):
    from app.services.scm.demand_class import DEMAND_CLASSES, planning_class
    from app.services.scm.priority import demand_value

    assert "other" in DEMAND_CLASSES
    assert planning_class("other") == "retail" and planning_class("project") == "project"
    assert demand_value({"PO1": "other"}, {"retail": 2.0, "project": 3.0}, "PO1") == 2.0

    header, lines = so(db, demand_class="other")
    doc(db, "invoice", "70.00", date(2026, 1, 15), lines=[line(so_line=lines[0])])
    doc(db, "invoice", "30.00", date(2026, 1, 16), lines=[line(so_line=so(db, demand_class="retail")[1][0])])
    assert by_type(db) == {"Other": D("70.00"), "Dealer": D("30.00")}


# ------------------------------------------------------------------ entry point (#1913)


def test_quantity_by_product_month_nets_credit_notes_by_month_and_product(db):
    from app.services.sales.invoiced_sales import quantity_by_product_month

    p, q = product(db, company_id=DEFAULT_COMPANY_ID), product(db, company_id=DEFAULT_COMPANY_ID)
    doc(db, "invoice", "50.00", date(2026, 1, 5), lines=[line(qty="5", prod=p)])
    doc(db, "credit_note", "20.00", date(2026, 1, 20), lines=[line(qty="2", prod=p)])
    doc(db, "cash_sale", "10.00", date(2026, 2, 3), lines=[line(qty="1", prod=p), line(qty="4", prod=q)])
    doc(db, "invoice", "99.00", date(2026, 2, 4), status="cancelled", lines=[line(qty="9", prod=p)])
    doc(db, "invoice", "10.00", date(2026, 2, 5), lines=[line(qty="7", item_code="ZZT-NOT-A-PRODUCT")])

    got = quantity_by_product_month(db, date(2026, 1, 1), date(2026, 3, 1))
    assert {(pid, m): D(str(n)) for pid, m, n in got} == {
        (str(p.id), "2026-01"): D("3"),
        (str(p.id), "2026-02"): D("1"),
        (str(q.id), "2026-02"): D("4"),
    }
    only_q = quantity_by_product_month(db, date(2026, 1, 1), date(2026, 3, 1), [str(q.id)])
    assert [(pid, m) for pid, m, _n in only_q] == [(str(q.id), "2026-02")]
    assert quantity_by_product_month(db, date(2026, 1, 1), date(2026, 3, 1), []) == []
    # since inclusive, until exclusive: 3 Feb is in [3 Feb, 4 Feb), 20 Jan is not in [6 Jan, 20 Jan).
    assert {(pid, D(str(n))) for pid, _m, n in quantity_by_product_month(db, date(2026, 2, 3), date(2026, 2, 4))} == {
        (str(p.id), D("1")), (str(q.id), D("4")),
    }
    assert quantity_by_product_month(db, date(2026, 1, 6), date(2026, 1, 20)) == []


def test_b2_a_bounded_past_row_does_not_close_the_current_class(db):
    from app.services.sales import agent_class_service as svc

    a = agent(db, unique_code("ZZTCLS"))
    may, _ = _order(db, a, date(2026, 5, 10), demand_class="retail")
    march, _ = _order(db, a, date(2026, 3, 10), demand_class="retail")
    svc.add(db, str(a.id), demand_class="retail", from_month=None, to_month=None)
    with pytest.raises(AppException) as clash:
        svc.add(db, str(a.id), demand_class="project", from_month=date(2026, 3, 1), to_month=date(2026, 4, 1))
    assert clash.value.code == "class_overlap"  # history goes in by editing, never by closing "now"
    assert _class_of(db, may) == "retail" and _class_of(db, march) == "retail"
    db.expire_all()
    assert db.get(type(a), a.id).demand_class == "retail"


def test_s1_the_screens_class_edit_fills_blank_orders_from_this_month_only(db):
    from app.services.scm import sales_agent_service

    a = agent(db, unique_code("ZZTCLS"))
    old_blank, _ = _order(db, a, date(2020, 7, 10), demand_class=None)
    sales_agent_service.annotate(db, a, demand_class="project", write_demand_class=True)
    db.flush()
    assert _class_of(db, old_blank) is None
