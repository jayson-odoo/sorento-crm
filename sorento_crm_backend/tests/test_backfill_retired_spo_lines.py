"""RED test for AC-H7: `scripts/backfill_retired_spo_lines.py`.

UAC: documentation/plans/autocount/hide-retired-spo-lines-acceptance-criteria.md
     AC-H7.
PLAN: documentation/plans/autocount/PLAN-hide-retired-spo-lines.md, section 3
      ("Backfill").

Contract: `run(db, company_id, dry_run=True) -> dict` (a `documents` key at
minimum, same shape as `scripts/dedupe_spo_xlsx_superseded.run`), CLI
`--company <code> [--dry-run|--apply]`. Stamps
`retired_at = coalesce(updated_at, now())` where `source_system = 'autocount'`
AND `line_status = 'closed'` AND `coalesce(receipt_status,'pending') <>
'fully_received'` AND `coalesce(quantity_received, 0) = 0` AND `retired_at IS
NULL`.

The module does not exist yet, so the import happens INSIDE the test body -
collection of the rest of the suite must not fail just because this one
script is still unbuilt.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.procurement import SPOAllocation
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTBACKFILLRETIRE"


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


class TestAcH7BackfillScript:
    def test_dry_run_writes_nothing_apply_stamps_only_the_eligible_row_second_apply_is_a_no_op(
        self, db
    ):
        """AC-H7. Three autocount rows on one document: a closed row with zero
        receipt and no `retired_at` (eligible), a fully-received closed row
        (not eligible - it arrived), and a closed row with a partial receipt
        (not eligible - `quantity_received != 0`).

        `--dry-run` writes nothing and names one document; `--apply` stamps
        only the first row; a second `--apply` reports zero.

        RED today: `scripts.backfill_retired_spo_lines` does not exist.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        stamped_updated_at = datetime(2026, 8, 1, 3, 30, 0)

        eligible = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID,
            spo_number=spo_number,
            spo_line_number=1,
            product_id=product.id,
            allocated_quantity=10,
            quantity_received=0,
            receipt_status="pending",
            line_status="closed",
            source_system="autocount",
            retired_at=None,
            updated_at=stamped_updated_at,
        )
        fully_received = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID,
            spo_number=spo_number,
            spo_line_number=2,
            product_id=product.id,
            allocated_quantity=10,
            quantity_received=10,
            receipt_status="fully_received",
            line_status="closed",
            source_system="autocount",
            retired_at=None,
        )
        partial_receipt = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID,
            spo_number=spo_number,
            spo_line_number=3,
            product_id=product.id,
            allocated_quantity=10,
            quantity_received=4,
            receipt_status="pending",
            line_status="closed",
            source_system="autocount",
            retired_at=None,
        )
        db.add_all([eligible, fully_received, partial_receipt])
        db.flush()
        db.commit()

        from scripts.backfill_retired_spo_lines import run  # noqa: PLC0415 - module not built yet

        summary1 = run(db, DEFAULT_COMPANY_ID, dry_run=True)

        db.expire_all()
        rows_after_dry = (
            db.execute(
                text(
                    "SELECT id, retired_at FROM spo_allocations WHERE spo_number = :n"
                ),
                {"n": spo_number},
            )
            .mappings()
            .all()
        )
        assert len(rows_after_dry) == 3
        assert all(r["retired_at"] is None for r in rows_after_dry), (
            "a dry run must write nothing",
            rows_after_dry,
        )
        assert summary1.get("documents", 0) == 1, summary1

        summary2 = run(db, DEFAULT_COMPANY_ID, dry_run=False)
        assert summary2.get("documents", 0) == 1, summary2

        db.expire_all()
        rows_after_apply = {
            str(r["id"]): r["retired_at"]
            for r in db.execute(
                text(
                    "SELECT id, retired_at FROM spo_allocations WHERE spo_number = :n"
                ),
                {"n": spo_number},
            )
            .mappings()
            .all()
        }
        assert rows_after_apply[eligible.id] is not None, rows_after_apply
        assert rows_after_apply[fully_received.id] is None, rows_after_apply
        assert rows_after_apply[partial_receipt.id] is None, rows_after_apply

        # `retired_at = coalesce(updated_at, now())`: this row's `updated_at`
        # was seeded a month in the past, so `retired_at` must land there too,
        # not at "now" - checked loosely (within a day, tz-naive) rather than
        # to the second, so this does not pin exactly how the implementation
        # attaches a timezone to a naive `updated_at` value.
        stamped = rows_after_apply[eligible.id]
        stamped_naive = stamped.replace(tzinfo=None) if stamped.tzinfo is not None else stamped
        assert abs((stamped_naive - stamped_updated_at).total_seconds()) < 24 * 3600, (
            stamped,
            stamped_updated_at,
        )
        assert abs((stamped_naive - datetime.now()).total_seconds()) > 7 * 24 * 3600, stamped

        summary3 = run(db, DEFAULT_COMPANY_ID, dry_run=False)
        assert summary3.get("documents", 0) == 0, summary3
