"""S15 (PLAN-reorder-feedback-9sep.md, rulings 1-2, 10 Sep 2026) - the Order Summary
sheet's Supplier column reads the product's LAST PURCHASE ORDER supplier, never the
`product_suppliers` link.

Measured 10 Sep 2026 on the prod copy: `resolve_default_supplier_id`
(`app/services/rules/product_rules.py`) auto-links nearly every product to one
placeholder supplier (DEFAULT) on create/import, and 11,804 of 11,807
`product_suppliers` rows point at it, none marked primary. Reading that link table for
the Supplier column therefore prints "DEFAULT" on effectively every row; the newest
purchase order line names who the product was actually bought from.

Two things are pinned here:

* `summary_order_service._last_po_supplier_map` / `write_rows`'s `supplier_name`/`moq`
  fields (AC-S15.1-S15.5), against the shared prod-copy DB (`chain`/`db`/`_po`/`_supplier`
  /`_link` reused wholesale from `tests/scm/test_summary_order_service.py`, same as
  `test_order_summary_sheet.py` beside this file).
* `scripts/backfill_product_supplier_from_last_po.py` (AC-S15.6), against an EMPTY
  scratch schema (`tests._pg_fixture.blank_session`) rather than the shared DB - the
  script sweeps EVERY product with PO history under company scope, so counting it
  against real production data would make an exact assertion impossible.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.inventory import Warehouse
from app.models.procurement import ProductSupplier, Supplier
from app.models.product import Product
from app.models.scm import ReorderRecommendation
from app.services.scm import summary_order_service as svc
from tests._pg_fixture import blank_session, unique_code
from tests.scm.test_summary_order_service import _link, _po, _supplier, chain, db  # noqa: F401

MARKER = "ZZTS15"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _add_product(db, f, *, buy_qty=10, code_stem="SKU"):
    """A second product on the SAME run as `chain`'s own product, with its own buy
    recommendation - so `write_rows` freezes a row for it too."""
    product = Product(
        id=_u(), product_code=_code(code_stem), product_name="extra product",
        category_id=f["cat"].id, base_uom_id=f["uom"].id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(product)
    db.flush()
    db.add(ReorderRecommendation(
        id=_u(), run_id=f["run"].id, rec_type="buy", product_id=product.id,
        warehouse_id=f["bin"].id, rounded_qty=buy_qty, status="proposed",
    ))
    db.flush()
    return product


def _row_for(db, run_id, product_code):
    rows = svc.report(db, run_id=run_id)["rows"]
    return next(r for r in rows if r["product_code"] == product_code)


# =========================================================================== #
# AC-S15.1-S15.5: `_last_po_supplier_map` / `write_rows`
# =========================================================================== #


def test_supplier_column_is_the_last_po_supplier_not_the_link(db, chain):
    """AC-S15.1: P1 has a DEFAULT link (the auto-link every product gets) and two POs -
    older from X, newer from Y. The sheet prints Y, never DEFAULT, never X."""
    f = chain
    p1 = _add_product(db, f)
    default = _supplier(db, "DEFAULT")
    x = _supplier(db, "Supplier X")
    y = _supplier(db, "Supplier Y")
    _link(db, p1, default, primary=True)
    _po(db, p1, f["bin"], 10, supplier=x, issued_days_ago=60)
    _po(db, p1, f["bin"], 10, supplier=y, issued_days_ago=5)

    written = svc.write_rows(db, f["run"].id)
    assert written == 2  # chain's own product + p1

    row = _row_for(db, f["run"].id, p1.product_code)
    assert row["supplier_name"] == "Supplier Y"


def test_supplier_column_blank_when_no_po_history(db, chain):
    """AC-S15.2: P2 has only a DEFAULT link and no purchase order at all. The sheet
    prints BLANK, never DEFAULT."""
    f = chain
    p2 = _add_product(db, f)
    default = _supplier(db, "DEFAULT")
    _link(db, p2, default, primary=True)

    svc.write_rows(db, f["run"].id)
    row = _row_for(db, f["run"].id, p2.product_code)
    assert row["supplier_name"] is None


def test_chosen_supplier_still_wins_over_last_po_supplier(db, chain):
    """AC-S15.3: a buyer's explicit chosen supplier (record_decision) wins over the
    engine's last-PO reading, unchanged from before S15."""
    f = chain
    p3 = _add_product(db, f)
    y = _supplier(db, "Supplier Y")
    chosen = _supplier(db, "Chosen Co")
    _po(db, p3, f["bin"], 10, supplier=y)

    svc.write_rows(db, f["run"].id)
    svc.record_decision(
        db, p3.product_code, run_id=f["run"].id, chosen_qty=5,
        supplier_code=chosen.supplier_code, actor="tester",
    )

    row = _row_for(db, f["run"].id, p3.product_code)
    assert row["supplier_name"] == "Chosen Co"


def test_po_with_null_issue_date_sorts_last_not_first(db, chain):
    """AC-S15.4: a PO with no issue date is not read as "newest" merely because it was
    the last one inserted - `issue_date DESC NULLS LAST` keeps it behind a dated PO."""
    f = chain
    p4 = _add_product(db, f)
    x = _supplier(db, "Supplier X")
    y = _supplier(db, "Supplier Y, undated")
    _po(db, p4, f["bin"], 10, supplier=x, issued_days_ago=5)
    undated = _po(db, p4, f["bin"], 10, supplier=y, issued_days_ago=5)
    undated.issue_date = None
    db.flush()

    svc.write_rows(db, f["run"].id)
    row = _row_for(db, f["run"].id, p4.product_code)
    assert row["supplier_name"] == "Supplier X"


def test_remarks_moq_comes_from_the_last_po_suppliers_own_link(db, chain):
    """AC-S15.5: Remarks' MOQ is read from the LAST-PO supplier's own link, never
    another supplier's - X's moq=999 must not leak onto a row naming Y."""
    f = chain
    p5 = _add_product(db, f)
    x = _supplier(db, "Supplier X")
    y = _supplier(db, "Supplier Y")
    _link(db, p5, x, moq=999, primary=True)
    _link(db, p5, y, moq=500)
    _po(db, p5, f["bin"], 10, supplier=x, issued_days_ago=60)
    _po(db, p5, f["bin"], 10, supplier=y, issued_days_ago=5)

    svc.write_rows(db, f["run"].id)
    row = _row_for(db, f["run"].id, p5.product_code)
    assert row["supplier_name"] == "Supplier Y"
    assert row["moq"] == 500
    assert svc._remarks_text(row) == "MOQ 500"


def test_remarks_moq_is_null_when_the_last_po_supplier_has_no_link(db, chain):
    """AC-S15.5: no `product_suppliers` link for the last-PO supplier -> MOQ null,
    Remarks blank - never a stale figure from some other supplier's link."""
    f = chain
    p6 = _add_product(db, f)
    y = _supplier(db, "Supplier Y, unlinked")
    _po(db, p6, f["bin"], 10, supplier=y)

    svc.write_rows(db, f["run"].id)
    row = _row_for(db, f["run"].id, p6.product_code)
    assert row["supplier_name"] == "Supplier Y, unlinked"
    assert row["moq"] is None
    assert svc._remarks_text(row) == ""


# =========================================================================== #
# AC-S15.6: scripts/backfill_product_supplier_from_last_po.py
# =========================================================================== #


@pytest.fixture()
def scratch_db():
    """An EMPTY scratch schema, not the shared prod-copy DB - the script sweeps every
    product with PO history under company scope, and counting that against real
    production data would make an exact assertion impossible."""
    with blank_session() as session:
        yield session


def _seed_product(db, *, code_stem="SKU"):
    from app.models.product import ProductCategory, UnitOfMeasure

    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER)[:40], category_name="cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code(MARKER)[:20], uom_name="Each")
    db.add_all([cat, uom])
    db.flush()
    product = Product(
        id=_u(), product_code=unique_code(f"{MARKER}-{code_stem}"), product_name="item",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(product)
    db.flush()
    return product


def _seed_warehouse(db):
    wh = Warehouse(
        id=_u(), warehouse_code=unique_code(MARKER)[:30], warehouse_name="wh",
        is_active=True, counts_as_available=True,
    )
    db.add(wh)
    db.flush()
    return wh


def _seed_supplier(db, code, name):
    s = Supplier(id=_u(), supplier_code=code, supplier_name=name)
    db.add(s)
    db.flush()
    return s


def test_backfill_dry_run_reports_and_writes_nothing(scratch_db):
    """AC-S15.6: dry-run (the default) previews the plan and touches nothing."""
    from scripts.backfill_product_supplier_from_last_po import run as backfill_run

    db = scratch_db
    wh = _seed_warehouse(db)
    default = _seed_supplier(db, "DEFAULT", "Default Supplier")
    y = _seed_supplier(db, unique_code("Y")[:30], "Supplier Y")
    p1 = _seed_product(db, code_stem="P1")
    _link(db, p1, default, primary=True)
    _po(db, p1, wh, 10, supplier=y)

    report = backfill_run(db, apply=False)

    assert report["mode"].startswith("DRY-RUN")
    assert report["products_seen"] == 1
    assert report["created"] == 1
    assert report["promoted"] == 0
    assert report["default_removed"] == 1
    assert any(p1.product_code in s and y.supplier_code in s for s in report["samples"])

    # Nothing written: P1 still holds only its original DEFAULT link.
    links = db.query(ProductSupplier).filter(ProductSupplier.product_id == p1.id).all()
    assert len(links) == 1
    assert links[0].supplier_id == default.id


def test_backfill_apply_creates_promotes_and_removes_default_leaves_no_po_product(scratch_db):
    """AC-S15.6: --apply creates P1->Y primary and removes P1's DEFAULT link; a
    no-PO product's DEFAULT link (P2) is left alone without --drop-default-all; a
    product whose last-PO supplier already has a (non-primary) link is PROMOTED, not
    duplicated (P3 -> Z). Idempotent: a second --apply creates/promotes/removes 0."""
    from scripts.backfill_product_supplier_from_last_po import run as backfill_run

    db = scratch_db
    wh = _seed_warehouse(db)
    default = _seed_supplier(db, "DEFAULT", "Default Supplier")
    y = _seed_supplier(db, unique_code("Y")[:30], "Supplier Y")
    z = _seed_supplier(db, unique_code("Z")[:30], "Supplier Z")

    p1 = _seed_product(db, code_stem="P1")
    _link(db, p1, default, primary=True)
    _po(db, p1, wh, 10, supplier=y)

    p2 = _seed_product(db, code_stem="P2")
    _link(db, p2, default, primary=True)  # no PO at all

    p3 = _seed_product(db, code_stem="P3")
    _link(db, p3, z, primary=False)  # already linked, not yet primary
    _po(db, p3, wh, 10, supplier=z)
    db.flush()

    report = backfill_run(db, apply=True)

    assert report["mode"] == "APPLIED"
    assert report["products_seen"] == 2  # P1 and P3 have PO history; P2 does not
    assert report["created"] == 1        # P1 -> Y
    assert report["promoted"] == 1       # P3 -> Z
    assert report["default_removed"] == 1  # P1's DEFAULT link only

    p1_links = {
        str(l.supplier_id): l
        for l in db.query(ProductSupplier).filter(ProductSupplier.product_id == p1.id).all()
    }
    assert set(p1_links) == {str(y.id)}
    assert p1_links[str(y.id)].is_primary_supplier is True

    p2_links = db.query(ProductSupplier).filter(ProductSupplier.product_id == p2.id).all()
    assert len(p2_links) == 1
    assert p2_links[0].supplier_id == default.id  # untouched, no --drop-default-all

    p3_links = {
        str(l.supplier_id): l
        for l in db.query(ProductSupplier).filter(ProductSupplier.product_id == p3.id).all()
    }
    assert p3_links[str(z.id)].is_primary_supplier is True

    # Idempotent.
    report2 = backfill_run(db, apply=True)
    assert report2["created"] == 0
    assert report2["promoted"] == 0
    assert report2["default_removed"] == 0


def test_backfill_drop_default_all_removes_no_po_products_default_link(scratch_db):
    """AC-S15.6: `drop_default_all=True` additionally removes a no-PO product's DEFAULT
    link (P2), leaving a product WITH PO history and no DEFAULT link (P3, already
    resolved) untouched. Idempotent on a second run."""
    from scripts.backfill_product_supplier_from_last_po import run as backfill_run

    db = scratch_db
    wh = _seed_warehouse(db)
    default = _seed_supplier(db, "DEFAULT", "Default Supplier")
    y = _seed_supplier(db, unique_code("Y")[:30], "Supplier Y")

    p1 = _seed_product(db, code_stem="P1")
    _link(db, p1, default, primary=True)
    _po(db, p1, wh, 10, supplier=y)

    p2 = _seed_product(db, code_stem="P2")
    _link(db, p2, default, primary=True)  # no PO at all
    db.flush()

    report = backfill_run(db, apply=True, drop_default_all=True)
    assert report["default_removed"] == 1          # P1's own DEFAULT link
    assert report["default_all_removed"] == 1      # P2's, via --drop-default-all

    assert db.query(ProductSupplier).filter(ProductSupplier.product_id == p2.id).count() == 0

    report2 = backfill_run(db, apply=True, drop_default_all=True)
    assert report2["default_all_removed"] == 0
