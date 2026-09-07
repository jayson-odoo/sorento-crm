"""RED test for AC-X10 (D29): `scripts/dedupe_spo_xlsx_superseded.py`.

UAC: documentation/plans/autocount/spo-xlsx-supersede-acceptance-criteria.md AC-X10.
PLAN: documentation/plans/autocount/PLAN-spo-xlsx-supersede.md D29.

Contract: `run(db, company_id, since=None, dry_run=True) -> summary dict` -
shares the same `_supersede_xlsx_rows` algorithm the ingest service uses for
D25/D26/D27, applied to a company's already-appended ref rows (the existing
`spo_line_number` order standing in for "incoming" line order) against its
remaining ref-less xlsx-era rows.

The module does not exist yet, so the import is done INSIDE the test body,
not at module scope - collection of the rest of the suite must not fail just
because this one script is still unbuilt.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.inventory import Warehouse
from app.models.procurement import SPOAllocation
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTDEDUPE"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _seed_product(db) -> Product:
    category = ProductCategory(category_code=unique_code(MARKER), category_name="Cat")
    uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name="Each")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        product_code=unique_code(MARKER),
        product_name="Item",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("0"),
    )
    db.add(product)
    db.flush()
    return product


def _seed_warehouse(db) -> Warehouse:
    warehouse = Warehouse(
        warehouse_code=f"{MARKER}WH{uuid.uuid4().hex[:6]}", warehouse_name="Main"
    )
    db.add(warehouse)
    db.flush()
    return warehouse


class TestAcX10DedupeScript:
    def test_dry_run_writes_nothing_then_apply_supersedes_and_a_second_apply_is_a_no_op(
        self, db
    ):
        """AC-X10. A company holds SPO N with the AC-X1 xlsx row AND two ref
        rows already appended (line 17 qty 29, line 18 qty 18, both received
        0, open, `created_at` later than the xlsx row). `--dry-run` (here:
        `run(..., dry_run=True)`) prints/reports the plan and writes
        nothing; a non-dry run leaves two rows received 29 / 18 closed with
        the xlsx row's links moved to line 17 and the xlsx row deleted; a
        second non-dry run reports zero documents touched.

        RED today at the import line: `scripts/dedupe_spo_xlsx_superseded`
        does not exist.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        warehouse = _seed_warehouse(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"

        xlsx_row = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID,
            spo_number=spo_number,
            spo_line_number=1,
            product_id=product.id,
            location_code=warehouse.warehouse_code,
            allocated_quantity=47,
            quantity_received=47,
            line_status="closed",
            receipt_status="fully_received",
            source_system="scm_upload",
        )
        db.add(xlsx_row)
        db.flush()

        doc_ref = f"{MARKER}:SPO:{uuid.uuid4().hex[:8]}"
        ref_17 = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID,
            spo_number=spo_number,
            spo_line_number=17,
            product_id=product.id,
            warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code,
            allocated_quantity=29,
            quantity_received=0,
            line_status="open",
            receipt_status="pending",
            source_system="autocount",
            source_ref=f"{MARKER}:SPOL17:{uuid.uuid4().hex[:8]}",
            source_doc_ref=doc_ref,
        )
        ref_18 = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID,
            spo_number=spo_number,
            spo_line_number=18,
            product_id=product.id,
            warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code,
            allocated_quantity=18,
            quantity_received=0,
            line_status="open",
            receipt_status="pending",
            source_system="autocount",
            source_ref=f"{MARKER}:SPOL18:{uuid.uuid4().hex[:8]}",
            source_doc_ref=doc_ref,
        )
        db.add_all([ref_17, ref_18])
        db.flush()
        db.commit()

        from scripts.dedupe_spo_xlsx_superseded import run  # noqa: PLC0415 - module not built yet

        summary = run(db, DEFAULT_COMPANY_ID, dry_run=True)

        db.expire_all()
        rows_after_dry = (
            db.execute(
                text(
                    "SELECT id FROM spo_allocations WHERE spo_number = :n ORDER BY spo_line_number"
                ),
                {"n": spo_number},
            )
            .mappings()
            .all()
        )
        assert len(rows_after_dry) == 3, "a dry run must write nothing"
        assert str(xlsx_row.id) in {str(r["id"]) for r in rows_after_dry}
        assert summary.get("documents", 0) >= 1, summary

        summary2 = run(db, DEFAULT_COMPANY_ID, dry_run=False)

        db.expire_all()
        rows_after_apply = (
            db.execute(
                text(
                    "SELECT id, allocated_quantity, quantity_received, line_status "
                    "FROM spo_allocations WHERE spo_number = :n ORDER BY allocated_quantity"
                ),
                {"n": spo_number},
            )
            .mappings()
            .all()
        )
        assert len(rows_after_apply) == 2, rows_after_apply
        assert str(xlsx_row.id) not in {str(r["id"]) for r in rows_after_apply}
        by_qty = {r["allocated_quantity"]: r for r in rows_after_apply}
        assert by_qty[29]["quantity_received"] == 29
        assert by_qty[29]["line_status"] == "closed"
        assert by_qty[18]["quantity_received"] == 18
        assert by_qty[18]["line_status"] == "closed"

        summary3 = run(db, DEFAULT_COMPANY_ID, dry_run=False)
        assert summary3.get("documents") == 0, summary3
