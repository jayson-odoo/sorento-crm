"""S0 gate - rule-engine aggregate facts.

Golden set for ``app/rule_engine/aggregates.py``. The status engine's auto edges
("project has >= 1 purchase order") are authored as rule conditions over these
facts, so a wrong aggregate silently fires or withholds a state transition.

Owner/child pair under test is ``PurchaseOrder`` -> ``PurchaseOrderLine``: both
carry ``company_id``, and the child has both a numeric (``qty_ordered``) and a
date (``expected_date``) column, which is what exercises every op.

Postgres only (PRINCIPLES.md): real FK targets are seeded because Postgres
enforces the constraints sqlite silently ignored.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.company import Company
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.rule_engine.aggregates import (
    AggColumn,
    AggregatableRelation,
    aggregate_fact,
    expand_relation_facts,
)

from ._pg_fixture import blank_session

MARKER = "zzt-agg"


def _uid() -> str:
    return str(uuid.uuid4())


def _seed_catalog(db):
    """A product needs a category and a UOM (both NOT NULL FKs)."""
    category = ProductCategory(
        id=_uid(), category_code=f"{MARKER}-CAT", category_name=f"{MARKER} category"
    )
    uom = UnitOfMeasure(id=_uid(), uom_code=f"{MARKER}-EA", uom_name=f"{MARKER} each")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        id=_uid(),
        product_code=f"{MARKER}-P1",
        product_name=f"{MARKER} product",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(product)
    db.flush()
    return product


def _sorento_id(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _po(db, company_id: str, number: str) -> PurchaseOrder:
    po = PurchaseOrder(id=_uid(), po_number=number, company_id=company_id)
    db.add(po)
    db.flush()
    return po


def _line(db, po, product, company_id, qty, expected=None) -> PurchaseOrderLine:
    line = PurchaseOrderLine(
        id=_uid(),
        purchase_order_id=po.id,
        product_id=product.id,
        company_id=company_id,
        qty_ordered=Decimal(str(qty)),
        expected_date=expected,
    )
    db.add(line)
    db.flush()
    return line


# ---------------------------------------------------------------- construction


def test_unknown_op_rejected_at_registration():
    with pytest.raises(ValueError, match="Unknown aggregate op"):
        aggregate_fact(
            "x", "X", child_model=PurchaseOrderLine, fk_attr="purchase_order_id", op="median"
        )


def test_column_op_without_column_rejected():
    with pytest.raises(ValueError, match="requires a column"):
        aggregate_fact(
            "x", "X", child_model=PurchaseOrderLine, fk_attr="purchase_order_id", op="sum"
        )


def test_relation_rejects_unknown_column():
    relation = AggregatableRelation(
        key="lines",
        label="Lines",
        child_entity_type="purchase_order_line",
        child_model=PurchaseOrderLine,
        fk_attr="purchase_order_id",
        columns=(AggColumn(name="not_a_column", label="Nope", ops=("sum",)),),
    )
    with pytest.raises(ValueError, match="has no column 'not_a_column'"):
        expand_relation_facts(relation)


def test_relation_rejects_unknown_column_op():
    relation = AggregatableRelation(
        key="lines",
        label="Lines",
        child_entity_type="purchase_order_line",
        child_model=PurchaseOrderLine,
        fk_attr="purchase_order_id",
        columns=(AggColumn(name="qty_ordered", label="Qty", ops=("count",)),),
    )
    # count is a relation-level flag, never a per-column op.
    with pytest.raises(ValueError, match="Unknown aggregate op 'count'"):
        expand_relation_facts(relation)


def test_relation_expands_to_count_plus_column_ops():
    relation = AggregatableRelation(
        key="lines",
        label="PO Lines",
        child_entity_type="purchase_order_line",
        child_model=PurchaseOrderLine,
        fk_attr="purchase_order_id",
        columns=(
            AggColumn(name="qty_ordered", label="Qty", ops=("sum", "max")),
            AggColumn(name="expected_date", label="Expected", type="date", ops=("max",)),
        ),
    )
    facts = {f.key: f for f in expand_relation_facts(relation)}
    assert set(facts) == {
        "record.lines.count",
        "record.lines.sum.qty_ordered",
        "record.lines.max.qty_ordered",
        "record.lines.max.expected_date",
    }
    # sum/avg are always numeric; min/max inherit the column's declared type.
    assert facts["record.lines.sum.qty_ordered"].type == "number"
    assert facts["record.lines.max.expected_date"].type == "date"
    assert facts["record.lines.count"].label == "PO Lines · Count"
    assert facts["record.lines.max.qty_ordered"].label == "PO Lines · Max of Qty"


# ------------------------------------------------------------------ resolution


def test_count_and_sum_over_children():
    with blank_session() as db:
        company_id = _sorento_id(db)
        product = _seed_catalog(db)
        po = _po(db, company_id, f"{MARKER}-PO-1")
        _line(db, po, product, company_id, 3)
        _line(db, po, product, company_id, 4.5)

        count = aggregate_fact(
            "c", "C", child_model=PurchaseOrderLine, fk_attr="purchase_order_id"
        )
        total = aggregate_fact(
            "s",
            "S",
            child_model=PurchaseOrderLine,
            fk_attr="purchase_order_id",
            op="sum",
            column="qty_ordered",
        )
        assert count.resolver(po, db) == 2
        assert Decimal(str(total.resolver(po, db))) == Decimal("7.5")


def test_min_max_avg_and_date_column():
    with blank_session() as db:
        company_id = _sorento_id(db)
        product = _seed_catalog(db)
        po = _po(db, company_id, f"{MARKER}-PO-2")
        _line(db, po, product, company_id, 2, date(2026, 3, 1))
        _line(db, po, product, company_id, 8, date(2026, 9, 30))

        def fact(op, column):
            return aggregate_fact(
                op,
                op,
                child_model=PurchaseOrderLine,
                fk_attr="purchase_order_id",
                op=op,
                column=column,
            )

        assert Decimal(str(fact("min", "qty_ordered").resolver(po, db))) == Decimal("2")
        assert Decimal(str(fact("max", "qty_ordered").resolver(po, db))) == Decimal("8")
        assert Decimal(str(fact("avg", "qty_ordered").resolver(po, db))) == Decimal("5")
        assert fact("max", "expected_date").resolver(po, db) == date(2026, 9, 30)


def test_zero_children_sum_is_zero_but_min_is_none():
    """The asymmetry is deliberate: a sum of nothing is 0 so "amount invoiced"
    reads 0 rather than blank, while min/max/avg of nothing is None so a
    condition over it fails CLOSED and no transition fires."""
    with blank_session() as db:
        company_id = _sorento_id(db)
        po = _po(db, company_id, f"{MARKER}-PO-3")

        def fact(op):
            return aggregate_fact(
                op,
                op,
                child_model=PurchaseOrderLine,
                fk_attr="purchase_order_id",
                op=op,
                column="qty_ordered",
            )

        assert fact("sum").resolver(po, db) == 0
        assert fact("min").resolver(po, db) is None
        assert fact("max").resolver(po, db) is None
        assert fact("avg").resolver(po, db) is None
        count = aggregate_fact(
            "c", "C", child_model=PurchaseOrderLine, fk_attr="purchase_order_id"
        )
        assert count.resolver(po, db) == 0


def test_children_of_another_owner_are_excluded():
    with blank_session() as db:
        company_id = _sorento_id(db)
        product = _seed_catalog(db)
        mine = _po(db, company_id, f"{MARKER}-PO-4")
        theirs = _po(db, company_id, f"{MARKER}-PO-5")
        _line(db, mine, product, company_id, 10)
        _line(db, theirs, product, company_id, 999)

        total = aggregate_fact(
            "s",
            "S",
            child_model=PurchaseOrderLine,
            fk_attr="purchase_order_id",
            op="sum",
            column="qty_ordered",
        )
        assert Decimal(str(total.resolver(mine, db))) == Decimal("10")


def test_child_of_another_company_is_excluded():
    """Defense in depth. The central scope filter already narrows company-scoped
    reads, but a fact feeding an AUTOMATIC state transition must not depend on a
    single layer, so the resolver re-filters on the owner's company."""
    with blank_session() as db:
        srt = _sorento_id(db)
        other = Company(id=_uid(), name=f"{MARKER} co", code=f"{MARKER}-CO")
        db.add(other)
        db.flush()

        product = _seed_catalog(db)
        po = _po(db, srt, f"{MARKER}-PO-6")
        _line(db, po, product, srt, 5)
        # A line hanging off the same PO but stamped to a different company. Only
        # reachable via drift or a bad write; the resolver must still skip it.
        _line(db, po, product, other.id, 500)

        total = aggregate_fact(
            "s",
            "S",
            child_model=PurchaseOrderLine,
            fk_attr="purchase_order_id",
            op="sum",
            column="qty_ordered",
        )
        count = aggregate_fact(
            "c", "C", child_model=PurchaseOrderLine, fk_attr="purchase_order_id"
        )
        assert Decimal(str(total.resolver(po, db))) == Decimal("5")
        assert count.resolver(po, db) == 1


def test_where_clause_narrows_further():
    with blank_session() as db:
        company_id = _sorento_id(db)
        product = _seed_catalog(db)
        po = _po(db, company_id, f"{MARKER}-PO-7")
        _line(db, po, product, company_id, 1)
        open_line = _line(db, po, product, company_id, 6)
        open_line.line_status = "closed"
        db.flush()

        count = aggregate_fact(
            "c",
            "C",
            child_model=PurchaseOrderLine,
            fk_attr="purchase_order_id",
            where=PurchaseOrderLine.line_status == "open",
        )
        assert count.resolver(po, db) == 1
