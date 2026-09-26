"""Timing harness for the low stock export on a 5,000-row run (PLAN-excel-preview-26sep,
owner ruling 26 Sep Q8: measure before and after). Not a test: the file name does not
match `test_*.py`, so the suite never collects it. Run it by path:

    pytest -q -s tests/scm/bench_low_stock_export.py

Seeds 5,000 frozen rows (60 suppliers x 25 categories, a third of them below their level)
inside a rolled-back session, then times the model build, the file write and the whole
export three times each and prints the best of three.
"""
from __future__ import annotations

import time
import uuid
from datetime import date, datetime

import pytest

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import OrderSummaryRow, ReorderRun
from tests.scm.conftest import requires_pg
from tests.scm.test_product_grain_summary import db  # noqa: F401

pytestmark = requires_pg

ROWS = 5000


def _u() -> str:
    return str(uuid.uuid4())


def _seed(db) -> str:
    tag = uuid.uuid4().hex[:6].upper()
    cats = [
        ProductCategory(id=_u(), category_code=f"ZZTB{tag}C{i:02d}", category_name="bench")
        for i in range(25)
    ]
    uom = UnitOfMeasure(id=_u(), uom_code=f"ZZTB{tag}U", uom_name="bench")
    db.add_all([*cats, uom])
    db.flush()
    run = ReorderRun(
        id=_u(), status="completed", buy_scope="warehouse", source_system="scm",
        source_ref=f"ZZTB{tag}RUN", decision_grain="product",
        front_planning_contract_version=1,
    )
    db.add(run)
    db.flush()
    products, rows = [], []
    for i in range(ROWS):
        p = Product(
            id=_u(), product_code=f"ZZTB{tag}-{i:05d}", product_name="bench",
            description=f"Bench product {i} with a description long enough to wrap",
            category_id=cats[i % 25].id, base_uom_id=uom.id, list_price=0,
            is_active=True, is_discontinued=False, reorder_quantity=(i % 7) * 10 or None,
        )
        products.append(p)
        rows.append(OrderSummaryRow(
            id=_u(), run_id=run.id, product_id=p.id, as_of=date(2026, 9, 26),
            computed_at=datetime(2026, 9, 26, 6, 0, 0),
            pool_on_hand=(i % 90), reorder_level=(i % 3) * 30 + 20,
            suggested_qty=(i % 11) * 5, supplier_name=f"Bench supplier {i % 60:02d}",
            last_receipt_qty=(i % 13) or None,
            last_receipt_date=date(2026, 8, 1 + i % 28) if i % 4 else None,
        ))
    db.add_all(products)
    db.flush()
    db.add_all(rows)
    db.flush()
    # A fresh test database has no planner statistics, so without this Postgres plans the
    # report's join for 1 row and nested-loops 12.5M pairs (3 s). Production tables are
    # analysed by autovacuum; this makes the bench read like production.
    from sqlalchemy import text

    for table in ("scm.order_summary_row", "products", "product_categories"):
        db.execute(text(f"ANALYZE {table}"))
    return str(run.id)


def _best(fn, n=3):
    best, out = None, None
    for _ in range(n):
        t0 = time.perf_counter()
        out = fn()
        dt = time.perf_counter() - t0
        best = dt if best is None or dt < best else best
    return best, out


@pytest.mark.parametrize("split", ["none", "supplier_category"])
def test_bench_export(db, split):  # noqa: F811
    from app.services.scm import low_stock_report_service as lsr

    run_id = _seed(db)
    frozen_t, _ = _best(lambda: lsr._split(db, run_id))
    total_t, out = _best(lambda: lsr.export_low_stock(db, run_id=run_id, split=split))
    blob, _ct, _fn, counts = out
    print(
        f"\nBENCH split={split} rows={counts['all']} low={counts['low']} "
        f"sheets={counts['sheets']} read_run={frozen_t:.2f}s export_total={total_t:.2f}s "
        f"write~={total_t - frozen_t:.2f}s bytes={len(blob)}"
    )
    view = getattr(lsr, "build_low_stock_view", None)
    if view is not None:
        import json

        view_t, payload = _best(lambda: view(db, run_id=run_id, split=split))
        print(f"BENCH view split={split} {view_t:.2f}s json={len(json.dumps(payload))} bytes")

