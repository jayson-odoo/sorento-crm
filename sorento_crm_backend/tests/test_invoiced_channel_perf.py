"""INVOICED-CHANNEL-PERF: the Channel (sales type) column is set-based and gives the same values.

Plan: `documentation/plans/sales/PLAN-invoiced-channel-perf-01nov.md`. The Invoiced tab asks for
every detail column, and Channel made a real-size day take minutes. Two causes, each pinned here:

- the label CASE carried the whole sales type subquery once per sales type (seven copies);
- the class lookup scanned every sales order and tested each against the traced ids, rather than
  looking up the few orders a document traces to.

The values are pinned against `tests/_invoiced_sales_type_reference.py`, a frozen copy of the
expression as main had it, on a seeded sample that walks every rule. Postgres only; every row is
invented and seeded here.
"""
from __future__ import annotations

import random
import uuid
from datetime import date
from typing import Any, Dict, List

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ClauseElement, Executable

from app.main import app  # noqa: F401  (import order)
from app.models.base import set_company_scope
from app.models.finance import BillingDocumentLine
from app.models.order import SalesOrder
from app.models.sales import SetApartCustomer
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.reports.datasets.billing_document_lines import _base as line_base
from app.services.reports.datasets.billing_documents import _base as document_base
from app.services.sales import invoiced_sales as inv
from tests import _invoiced_sales_type_reference as ref
from tests._mc_lookup_seed import MOCHA_ID, seed_mocha
from tests._pg_fixture import blank_session, unique_code
from tests._sales_unified_seed import cust, delivery, doc, line, so


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


def _sql(expr: Any) -> str:
    return str(expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


# ------------------------------------------------------------------------ the query's shape


def test_the_channel_label_holds_the_sales_type_subquery_once():
    """A label CASE of `WHEN st = 'dealer' ... WHEN st = 'project' ...` inlines the sales type
    seven times, and Postgres runs each copy; `CASE st WHEN ...` runs it once. The class rule's
    own CASE names `mixed` once and the label names it once: two, not eight."""
    sql = _sql(inv.sales_type_label())
    assert sql.count(f"'{inv.MIXED}'") == 2


class _Explain(Executable, ClauseElement):
    inherit_cache = False

    def __init__(self, stmt: Any):
        self.stmt = stmt


@compiles(_Explain, "postgresql")
def _compile_explain(element: _Explain, compiler: Any, **kw: Any) -> str:
    sql = "EXPLAIN (ANALYZE, FORMAT JSON) " + compiler.process(element.stmt, **kw)
    # The one result column is the plan, not the inner select's first column: without this the
    # result is typed by that column (a UUID column turns the plan into a string).
    compiler._result_columns.clear()
    return sql


def _nodes(plan: Dict[str, Any]):
    yield plan
    for child in plan.get("Plans", ()):
        yield from _nodes(child)


def _sales_order_rows_read(db, stmt) -> int:
    """Rows of `sales_orders` the executed plan read (returned plus filtered away), over all loops."""
    (plan,) = db.execute(_Explain(stmt)).scalar_one()
    total = 0
    for node in _nodes(plan["Plan"]):
        if node.get("Relation Name") == "sales_orders":
            loops = node.get("Actual Loops", 1)
            total += (node.get("Actual Rows", 0) + node.get("Rows Removed by Filter", 0)) * loops
    return total


def _filler_sales_orders(db, n: int) -> None:
    db.execute(
        sa.insert(SalesOrder),
        [
            {"id": str(uuid.uuid4()), "so_number": unique_code("FSO"), "status": "open",
             "demand_class": "retail", "company_id": DEFAULT_COMPANY_ID}
            for _ in range(n)
        ],
    )
    db.flush()
    for table in ("sales_orders", "sales_order_lines", "orders", "order_lines",
                  "billing_documents", "billing_document_lines", "set_apart_customers"):
        db.execute(sa.text(f"ANALYZE {table}"))


@pytest.mark.parametrize("dataset", ["lines", "documents"])
def test_the_channel_looks_up_the_traced_sales_orders_and_never_scans_them_all(db, dataset):
    """Twenty invoices, each traced to one SO, among 3,000 sales orders: the Channel query reads
    the handful of orders the documents trace to, not the table once per document."""
    _filler_sales_orders(db, 3000)
    when = date(2026, 1, 15)
    for _ in range(20):
        _header, (so_line,) = so(db, demand_class="project")
        doc(db, "invoice", "10.00", when, lines=[line(so_line=so_line)])
    db.flush()
    base = line_base(None) if dataset == "lines" else document_base(None)
    stmt = base.add_columns(inv.sales_type_label().label("channel"))
    read = _sales_order_rows_read(db, stmt)
    # Every document can touch its own few orders through each rule (by line, by number,
    # through a DO, as a note's invoice), never the 3,000.
    assert read < 20 * 10, read


# ------------------------------------------------------------------------ same values


def _seed_sample(db) -> None:
    """A random but fixed mix over every rule: SO line links, SO and DO numbers, a DO's lines,
    from-number and header, a deleted DO, another company's SO number, untyped and mixed SOs,
    notes with and without their own traced lines, set apart customers by month."""
    rng = random.Random(20261101)
    seed_mocha(db)
    customers = [cust(db) for _ in range(8)]
    for c, (start, end) in zip(customers[:3], [
        (date(2026, 1, 1), None), (date(2026, 2, 1), date(2026, 2, 1)), (date(2026, 3, 1), None),
    ]):
        db.add(SetApartCustomer(company_id=DEFAULT_COMPANY_ID, customer_id=c.id, from_month=start, to_month=end))
    db.flush()

    orders = []
    for demand_class in ["retail", "retail", "project", "project", "other", None, "retail", "project", None, "other"]:
        orders.append(so(db, demand_class=demand_class, lines=rng.choice([1, 2])))
    foreign, _ = so(db, demand_class="project", company_id=MOCHA_ID)

    deliveries = []
    for i in range(12):
        header, so_lines = rng.choice(orders)
        kind = i % 4
        if kind == 0:
            deliveries.append(delivery(db, so_line=so_lines[0]))
        elif kind == 1:
            deliveries.append(delivery(db, from_so_no=header.so_number, from_type=rng.choice([None, "SO"])))
        elif kind == 2:
            deliveries.append(delivery(db, header_so=header))
        else:
            deliveries.append(delivery(db, so_line=so_lines[0], deleted=True))

    def random_line() -> dict:
        pick = rng.randrange(7)
        header, so_lines = rng.choice(orders)
        if pick == 0:
            return line(net="10.00", so_line=rng.choice(so_lines))
        if pick == 1:
            return line(net="10.00", from_type="SO", from_no=header.so_number)
        if pick == 2:
            return line(net="10.00", from_type="DO", from_no=rng.choice(deliveries).order_number)
        if pick == 3:
            return line(net="10.00", from_type="SO", from_no=foreign.so_number)
        if pick == 4:
            return line(net="10.00", from_type="SO", from_no=unique_code("NOSO"))
        return line(net="10.00")

    invoices = []
    for i in range(70):
        when = date(2026, rng.choice([1, 2, 3]), rng.randint(1, 28))
        customer = rng.choice(customers + [None])
        kind = rng.choice(["invoice", "invoice", "invoice", "cash_sale", "credit_note", "debit_note"])
        lines = [random_line() for _ in range(rng.choice([0, 1, 1, 2, 3]))]
        against = None
        if kind in ("credit_note", "debit_note") and invoices:
            against = rng.choice(invoices)
            if rng.random() < 0.6:
                lines = [line(net="10.00") for _ in range(rng.choice([0, 1]))]
        made = doc(db, kind, "10.00", when, customer=customer, against=against, lines=lines)
        if kind == "invoice":
            invoices.append(made)
    # Fixed: a note's own traced line wins over its invoice's orders (never both, never mixed).
    _p, (project_line,) = so(db, demand_class="project")
    _r, (retail_line,) = so(db, demand_class="retail")
    project_invoice = doc(db, "invoice", "10.00", date(2026, 1, 5), lines=[line(so_line=project_line)])
    doc(db, "credit_note", "10.00", date(2026, 1, 6), against=project_invoice, lines=[line(so_line=retail_line)])
    db.flush()


def _pairs(db, base, key) -> List[tuple]:
    stmt = base.add_columns(key.label("k"), ref.sales_type_label().label("old"), inv.sales_type_label().label("new"))
    return [tuple(r) for r in db.execute(stmt).all()]


def test_every_line_keeps_its_channel(db):
    _seed_sample(db)
    rows = _pairs(db, line_base(None), BillingDocumentLine.id)
    assert len(rows) > 60
    assert [r for r in rows if r[1] != r[2]] == []
    # The sample walks every sales type, so the equality is not vacuous.
    assert {r[1] for r in rows} == set(inv.SALES_TYPE_LABELS.values())


def test_every_document_keeps_its_channel(db):
    from app.models.finance import BillingDocument

    _seed_sample(db)
    rows = _pairs(db, document_base(None), BillingDocument.id)
    assert [r for r in rows if r[1] != r[2]] == []
    assert {r[1] for r in rows} == set(inv.SALES_TYPE_LABELS.values())


def test_the_channel_filter_keeps_the_same_documents(db):
    from app.models.finance import BillingDocument

    _seed_sample(db)
    for value, _label in inv.SALES_TYPES:
        old = set(db.execute(document_base(None).add_columns(BillingDocument.id)
                             .where(ref.sales_type().in_([value]))).scalars())
        new = set(db.execute(document_base(None).add_columns(BillingDocument.id)
                             .where(inv.sales_type_filter([value]))).scalars())
        assert old == new, value


def test_a_report_run_switches_jit_off_with_set_local(db):
    """The invoiced statements cost far above `jit_above_cost`, and the JIT compile took longer
    than the query (5 s on 0.3 s for a seeded month). The engine runs them with JIT off, for the
    report's own transaction."""
    from app.services.reports import engine
    from tests._sales_unified_seed import view

    from app.services.reports.datasets.billing_document_lines import ASK_DEFINITION

    db.execute(sa.text("SET LOCAL jit = on"))
    v = view(rows="month", cols="all", measures=("amount",), columns=("channel",))
    params = {k: val for k, val in v.params.items() if k != "company"}
    engine.run(db, ASK_DEFINITION, params, v, company_grants=frozenset({DEFAULT_COMPANY_ID}))
    assert db.execute(sa.text("SHOW jit")).scalar_one() == "off"


# ------------------------------------------------------------------------ once per document (round 3)


def _line_channel():
    from app.services.reports.datasets.billing_document_lines import DATASET

    return DATASET.column("channel").expr(None)


def test_the_line_datasets_channel_column_keeps_every_lines_value(db):
    """The line dataset reads Channel from its per-document LATERAL; every line still gets the
    value main's per-line expression gave it."""
    _seed_sample(db)
    stmt = line_base(None).add_columns(
        BillingDocumentLine.id, ref.sales_type_label().label("old"), _line_channel().label("new")
    )
    rows = db.execute(stmt).all()
    assert len(rows) > 60
    assert [r for r in rows if r[1] != r[2]] == []
    assert {r[1] for r in rows} == set(inv.SALES_TYPE_LABELS.values())


def test_the_line_datasets_channel_filter_keeps_the_same_lines(db):
    from app.services.reports.datasets.billing_document_lines import channel_condition

    _seed_sample(db)
    for value, _label in inv.SALES_TYPES:
        old = set(db.execute(line_base(None).add_columns(BillingDocumentLine.id)
                             .where(ref.sales_type().in_([value]))).scalars())
        new = set(db.execute(line_base(None).add_columns(BillingDocumentLine.id)
                             .where(channel_condition(None, [value]))).scalars())
        assert old == new, value
    # The order bases' words still read as the type they mean.
    retail = set(db.execute(line_base(None).add_columns(BillingDocumentLine.id)
                            .where(channel_condition(None, ["retail"]))).scalars())
    dealer = set(db.execute(line_base(None).add_columns(BillingDocumentLine.id)
                            .where(channel_condition(None, ["dealer"]))).scalars())
    assert retail and retail == dealer


def _subplan_loops(db, stmt) -> List[int]:
    """The `Actual Loops` of every SubPlan and InitPlan the executed plan holds (the sales type is
    nothing but those), over one process so the counts are exact."""
    db.execute(sa.text("SET LOCAL max_parallel_workers_per_gather = 0"))
    (plan,) = db.execute(_Explain(stmt)).scalar_one()
    return [n.get("Actual Loops", 0) for n in _nodes(plan["Plan"]) if "Subplan Name" in n]


def _many_line_invoices(db, documents: int, lines_each: int) -> None:
    when = date(2026, 1, 15)
    for _ in range(documents):
        _header, so_lines = so(db, demand_class="retail", lines=1)
        doc(db, "invoice", "10.00", when,
            lines=[line(net="1.00", so_line=so_lines[0]) for _ in range(lines_each)])
    db.flush()
    for table in ("billing_documents", "billing_document_lines", "sales_orders", "sales_order_lines"):
        db.execute(sa.text(f"ANALYZE {table}"))


@pytest.mark.parametrize("read", ["column", "filter", "group"])
def test_a_many_line_invoice_computes_its_channel_once_not_once_per_line(db, read):
    """Three invoices of 120 lines: every piece of the sales type runs at most once per document
    (3), never once per line (360). Per line, each run read the document's own lines, so an
    n-line invoice cost n x n. The Channel column, the Channel filter (Top selling items always
    sends it, every type ticked) and a summary grouped by Channel each read it."""
    from app.services.reports.datasets.billing_document_lines import channel_condition

    _many_line_invoices(db, 3, 120)
    base = line_base(None)
    if read == "column":
        stmt = base.add_columns(BillingDocumentLine.id, _line_channel().label("channel"))
    elif read == "filter":
        stmt = base.add_columns(BillingDocumentLine.id).where(
            channel_condition(None, [value for value, _label in inv.SALES_TYPES])
        )
    else:
        stmt = base.add_columns(_line_channel().label("channel"), sa.func.count()).group_by(sa.text("1"))
    loops = _subplan_loops(db, stmt)
    assert loops, "the plan computes no sales type at all"
    assert max(loops) <= 3, loops


def test_a_line_query_that_does_not_read_channel_never_computes_it(db):
    """A query that does not read Channel (the pivot by month, the row count, the totals) never
    runs the sales type: the planner may keep the LATERAL join, but with its output unread it
    computes nothing."""
    _many_line_invoices(db, 3, 120)
    stmt = line_base(None).add_columns(BillingDocumentLine.id, sa.func.count().over())
    assert all(n == 0 for n in _subplan_loops(db, stmt))
