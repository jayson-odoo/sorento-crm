"""`--all-suppliers` on `scripts/backfill_product_supplier_from_last_po.py`
(PLAN-product-supplier-all-po.md, 10 Sep 2026).

Phase 2 tests, from `product-supplier-all-po-acceptance-criteria.md` (AC-ALL.1-13) and the
plan's own "Test list" (T1-T9), each docstring citing the AC id(s) it covers. Round 2 adds
two reviewer kill-test cases (AC-ALL.12, AC-ALL.13) and extends T1/T4/T5/T7/T9 per the
plan's "Rulings addendum" (deterministic tiebreaks, cost-never-without-currency, DEFAULT
never a secondary link) - the implementation for all of this already landed
(`3c08f335a`, `ae3947bc5`), so these run GREEN.

The script-level tests (T1-T7, T9) run on an EMPTY scratch schema
(`tests._pg_fixture.blank_session`), exactly like the existing S15 script tests in
`test_supplier_last_po_s15.py` - the sweep reads every product with PO history under
company scope, so counting it against the shared prod-copy DB would make an exact
assertion impossible. T8 (`summary_order_service._last_po_supplier_map`) runs against the
shared DB via the `chain`/`db`/`_po`/`_supplier` fixtures from `test_summary_order_service.py`,
same as that file's own AC-S15.1-S15.5 tests.

Run ONLY:
    pytest tests/scm/test_supplier_all_po.py tests/scm/test_supplier_last_po_s15.py -q
Never the full scm suite against the shared DB.
"""
from __future__ import annotations

import contextlib
import sys
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.inventory import Warehouse
from app.models.procurement import (
    ProductSupplier,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.product import Product
from app.services.scm import summary_order_service as svc
from tests._pg_fixture import blank_session, unique_code
from tests.scm.test_summary_order_service import _link, _po, _supplier, chain, db  # noqa: F401

MARKER = "ZZTSAP"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


# =========================================================================== #
# scratch-schema fixtures and seed helpers (T1-T7, T9)
# =========================================================================== #


@pytest.fixture()
def scratch_db():
    """An EMPTY scratch schema - see the module docstring for why."""
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


def _seed_po_line(db, product, wh, supplier, *, status="closed", issue_date,
                   order_currency=None, line_currency=None, unit_cost=None):
    """One PO with one line for `product` under `supplier` - each call is a distinct PO,
    matching how the plan's AC-ALL.3 describes a supplier's "lines" (each with its own
    `issue_date`, since recency is read off `purchase_orders.issue_date`)."""
    po = PurchaseOrder(
        id=_u(), po_number=unique_code(MARKER)[:50], supplier_id=supplier.id,
        status=status, issue_date=issue_date, currency=order_currency,
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, warehouse_id=wh.id,
        qty_ordered=10, qty_received=0, unit_cost=unit_cost, currency=line_currency,
    )
    db.add(line)
    db.flush()
    return po, line


# =========================================================================== #
# T1 / AC-ALL.9 - without the flag, today's behaviour holds
# =========================================================================== #


def test_default_path_unchanged_without_flag(scratch_db):
    """T1 / AC-ALL.9: without --all-suppliers, `run(apply=True)` still creates exactly
    ONE non-DEFAULT link per product - the last-PO supplier, primary - and a supplier Q
    known only through a cancelled PO gets no link at all (ruling 3 applies in the
    default path too: `all_suppliers=False` keeps today's behaviour "byte-for-byte
    except ruling 3"). Since the flag is off, the created link's terms stay NULL -
    nothing here invents a commercial term - and the report's created/promoted/
    default_removed counts are exactly 1/0/1."""
    from scripts.backfill_product_supplier_from_last_po import run as backfill_run

    db = scratch_db
    wh = _seed_warehouse(db)
    default = _seed_supplier(db, "DEFAULT", "Default Supplier")
    x = _seed_supplier(db, unique_code("X")[:30], "Supplier X")
    y = _seed_supplier(db, unique_code("Y")[:30], "Supplier Y")
    q = _seed_supplier(db, unique_code("Q")[:30], "Supplier Q")
    p = _seed_product(db, code_stem="P1")
    _link(db, p, default, primary=True)
    _seed_po_line(db, p, wh, x, status="closed", issue_date=date(2024, 3, 1),
                  unit_cost=10, order_currency="USD")
    _seed_po_line(db, p, wh, y, status="closed", issue_date=date(2026, 5, 1),
                  unit_cost=20, order_currency="USD")
    # Q's only PO for P is cancelled AND the newest by issue_date - it must not win.
    _seed_po_line(db, p, wh, q, status="cancelled", issue_date=date(2026, 6, 1),
                  unit_cost=5, order_currency="USD")

    report = backfill_run(db, apply=True)

    links = {
        str(l.supplier_id): l
        for l in db.query(ProductSupplier).filter(ProductSupplier.product_id == p.id).all()
    }
    assert set(links) == {str(y.id)}
    assert links[str(y.id)].is_primary_supplier is True
    assert links[str(y.id)].unit_cost is None
    assert links[str(y.id)].currency is None
    assert report["created"] == 1
    assert report["promoted"] == 0
    assert report["default_removed"] == 1


# =========================================================================== #
# T2 / AC-ALL.1 + AC-ALL.2 - two suppliers, newest primary, DEFAULT removed
# =========================================================================== #


def test_two_suppliers_creates_two_links_newest_primary_default_removed(scratch_db):
    """T2 / AC-ALL.1 + AC-ALL.2: product P bought from X (older PO, 2024-03-01) and Y
    (newer PO, 2026-05-01), neither cancelled. `run(apply=True, all_suppliers=True)`
    creates exactly two links, (P, Y) primary, (P, X) not, and P's DEFAULT link is
    deleted (DEFAULT is not the newest pair)."""
    from scripts.backfill_product_supplier_from_last_po import run as backfill_run

    db = scratch_db
    wh = _seed_warehouse(db)
    default = _seed_supplier(db, "DEFAULT", "Default Supplier")
    x = _seed_supplier(db, unique_code("X")[:30], "Supplier X")
    y = _seed_supplier(db, unique_code("Y")[:30], "Supplier Y")
    p = _seed_product(db, code_stem="P1")
    _link(db, p, default, primary=True)
    _seed_po_line(db, p, wh, x, issue_date=date(2024, 3, 1), unit_cost=10, order_currency="USD")
    _seed_po_line(db, p, wh, y, issue_date=date(2026, 5, 1), unit_cost=20, order_currency="USD")

    report = backfill_run(db, apply=True, all_suppliers=True)

    links = {
        str(l.supplier_id): l
        for l in db.query(ProductSupplier).filter(ProductSupplier.product_id == p.id).all()
    }
    assert set(links) == {str(x.id), str(y.id)}
    assert links[str(y.id)].is_primary_supplier is True
    assert links[str(x.id)].is_primary_supplier is False
    assert report["default_removed"] == 1


# =========================================================================== #
# T3 / AC-ALL.3 + AC-ALL.4 - terms from the newest PRICED line
# =========================================================================== #


def test_terms_come_from_newest_priced_line_line_currency_wins(scratch_db):
    """T3 / AC-ALL.3 + AC-ALL.4: X's lines for P are 2024-01-10 (unit_cost 10.00, line
    currency NULL, order currency CNY), 2024-03-01 (unit_cost 11.50, line currency USD,
    order currency CNY), 2024-06-01 (unpriced, newest by date). (P, X).unit_cost /
    .currency come from the newest PRICED line: 11.50 / USD - the line currency beats
    the order currency and the unpriced newer line is ignored. Supplier Z has only a
    NULL-cost line for P, so (P, Z) is created with unit_cost NULL and currency NULL -
    no invented price."""
    from scripts.backfill_product_supplier_from_last_po import run as backfill_run

    db = scratch_db
    wh = _seed_warehouse(db)
    x = _seed_supplier(db, unique_code("X")[:30], "Supplier X")
    z = _seed_supplier(db, unique_code("Z")[:30], "Supplier Z")
    p = _seed_product(db, code_stem="P1")
    _seed_po_line(db, p, wh, x, issue_date=date(2024, 1, 10), unit_cost=Decimal("10.00"),
                  order_currency="CNY", line_currency=None)
    _seed_po_line(db, p, wh, x, issue_date=date(2024, 3, 1), unit_cost=Decimal("11.50"),
                  order_currency="CNY", line_currency="USD")
    _seed_po_line(db, p, wh, x, issue_date=date(2024, 6, 1), unit_cost=None,
                  order_currency="CNY", line_currency=None)
    _seed_po_line(db, p, wh, z, issue_date=date(2023, 1, 1), unit_cost=None,
                  order_currency="CNY")

    backfill_run(db, apply=True, all_suppliers=True)

    links = {
        str(l.supplier_id): l
        for l in db.query(ProductSupplier).filter(ProductSupplier.product_id == p.id).all()
    }
    assert links[str(x.id)].unit_cost == Decimal("11.50")
    assert links[str(x.id)].currency == "USD"
    assert links[str(z.id)].unit_cost is None
    assert links[str(z.id)].currency is None


# =========================================================================== #
# T4 / AC-ALL.5 - a keyed price is never overwritten; a NULL one is filled
# =========================================================================== #


def test_existing_keyed_price_kept_null_price_filled(scratch_db):
    """T4 / AC-ALL.5: (P, X) already exists with unit_cost 12.00 / MYR, moq 25,
    order_multiple 5, lead 14 - the sweep must leave every one of those fields exactly
    as-is and `terms_filled` must not count it, even though X has a newer priced PO line
    (99.00 USD). (P, W) already exists with unit_cost NULL and W has a priced PO line
    (7.25 CNY) - the sweep fills unit_cost/currency and counts it once in
    `terms_filled`."""
    from scripts.backfill_product_supplier_from_last_po import run as backfill_run

    db = scratch_db
    wh = _seed_warehouse(db)
    x = _seed_supplier(db, unique_code("X")[:30], "Supplier X")
    w = _seed_supplier(db, unique_code("W")[:30], "Supplier W")
    p = _seed_product(db, code_stem="P1")
    _link(db, p, x, cost=Decimal("12.00"), currency="MYR", lead=14, moq=25, multiple=5)
    _link(db, p, w, cost=None, currency=None)
    _seed_po_line(db, p, wh, x, issue_date=date(2024, 1, 1), unit_cost=Decimal("99.00"),
                  order_currency="USD")
    _seed_po_line(db, p, wh, w, issue_date=date(2024, 1, 1), unit_cost=Decimal("7.25"),
                  order_currency="CNY")

    report = backfill_run(db, apply=True, all_suppliers=True)

    links = {
        str(l.supplier_id): l
        for l in db.query(ProductSupplier).filter(ProductSupplier.product_id == p.id).all()
    }
    assert links[str(x.id)].unit_cost == Decimal("12.00")
    assert links[str(x.id)].currency == "MYR"
    assert links[str(x.id)].standard_lead_time_days == 14
    assert links[str(x.id)].moq == 25
    assert links[str(x.id)].order_multiple == 5
    assert links[str(w.id)].unit_cost == Decimal("7.25")
    assert links[str(w.id)].currency == "CNY"
    assert report["terms_filled"] == 1


# =========================================================================== #
# T5 / AC-ALL.6 - cancelled POs do not exist for this sweep
# =========================================================================== #


def test_cancelled_pos_do_not_exist_for_the_sweep(scratch_db):
    """T5 / AC-ALL.6: supplier Q's only PO for P is 'cancelled' - no (P, Q) link is
    created. P's newest PO (supplier R) is also cancelled; P's newest non-cancelled PO
    names supplier Y - (P, Y) is primary and no (P, R) link exists. Y ALSO has a PRICED
    but cancelled line newer than its own non-cancelled one - the cancelled filter must
    apply inside the `priced` CTE too, separately from the `pairs` one, so (P, Y) still
    gets NULL unit_cost rather than the cancelled line's price."""
    from scripts.backfill_product_supplier_from_last_po import run as backfill_run

    db = scratch_db
    wh = _seed_warehouse(db)
    q = _seed_supplier(db, unique_code("Q")[:30], "Supplier Q")
    r = _seed_supplier(db, unique_code("R")[:30], "Supplier R")
    y = _seed_supplier(db, unique_code("Y")[:30], "Supplier Y")
    p = _seed_product(db, code_stem="P1")
    _seed_po_line(db, p, wh, q, status="cancelled", issue_date=date(2024, 1, 1),
                  unit_cost=5, order_currency="USD")
    _seed_po_line(db, p, wh, y, status="closed", issue_date=date(2024, 6, 1),
                  unit_cost=None, order_currency="USD")
    _seed_po_line(db, p, wh, y, status="cancelled", issue_date=date(2025, 1, 1),
                  unit_cost=Decimal("77.00"), order_currency="USD")
    _seed_po_line(db, p, wh, r, status="cancelled", issue_date=date(2026, 1, 1),
                  unit_cost=15, order_currency="USD")

    backfill_run(db, apply=True, all_suppliers=True)

    links = {
        str(l.supplier_id): l
        for l in db.query(ProductSupplier).filter(ProductSupplier.product_id == p.id).all()
    }
    assert str(q.id) not in links
    assert str(r.id) not in links
    assert links[str(y.id)].is_primary_supplier is True
    assert links[str(y.id)].unit_cost is None


# =========================================================================== #
# T6 / AC-ALL.7 - idempotent
# =========================================================================== #


def test_second_apply_is_a_pure_no_op(scratch_db):
    """T6 / AC-ALL.7: after the sweep has already been applied once, a second
    `run(apply=True, all_suppliers=True)` reports created 0, promoted 0, terms_filled 0,
    default_removed 0, and the `product_suppliers` row count for P is unchanged."""
    from scripts.backfill_product_supplier_from_last_po import run as backfill_run

    db = scratch_db
    wh = _seed_warehouse(db)
    default = _seed_supplier(db, "DEFAULT", "Default Supplier")
    x = _seed_supplier(db, unique_code("X")[:30], "Supplier X")
    y = _seed_supplier(db, unique_code("Y")[:30], "Supplier Y")
    p = _seed_product(db, code_stem="P1")
    _link(db, p, default, primary=True)
    _seed_po_line(db, p, wh, x, issue_date=date(2024, 3, 1), unit_cost=Decimal("10.00"),
                  order_currency="USD")
    _seed_po_line(db, p, wh, y, issue_date=date(2026, 5, 1), unit_cost=Decimal("20.00"),
                  order_currency="USD")

    backfill_run(db, apply=True, all_suppliers=True)
    before_count = (
        db.query(ProductSupplier).filter(ProductSupplier.product_id == p.id).count()
    )

    report2 = backfill_run(db, apply=True, all_suppliers=True)

    assert report2["created"] == 0
    assert report2["promoted"] == 0
    assert report2["terms_filled"] == 0
    assert report2["default_removed"] == 0
    after_count = (
        db.query(ProductSupplier).filter(ProductSupplier.product_id == p.id).count()
    )
    assert after_count == before_count


# =========================================================================== #
# T7 / AC-ALL.8 - dry-run writes nothing
# =========================================================================== #


def test_dry_run_writes_nothing_reports_pairs_seen_and_created(scratch_db):
    """T7 / AC-ALL.8: `run(apply=False, all_suppliers=True)` writes nothing; the report
    shows `pairs_seen` 2 and `created` 1 (X already has a link, only Y's is new).
    `product_suppliers` for P is exactly the rows that existed before the call: X's
    pre-existing non-primary link (keyed unit_cost 12.00 / MYR) and its DEFAULT link -
    both untouched in every field, and no Y row is written."""
    from scripts.backfill_product_supplier_from_last_po import run as backfill_run

    db = scratch_db
    wh = _seed_warehouse(db)
    default = _seed_supplier(db, "DEFAULT", "Default Supplier")
    x = _seed_supplier(db, unique_code("X")[:30], "Supplier X")
    y = _seed_supplier(db, unique_code("Y")[:30], "Supplier Y")
    p = _seed_product(db, code_stem="P1")
    _link(db, p, default, primary=True)
    _link(db, p, x, cost=Decimal("12.00"), currency="MYR", primary=False)
    _seed_po_line(db, p, wh, x, issue_date=date(2024, 3, 1), unit_cost=Decimal("10.00"),
                  order_currency="USD")
    _seed_po_line(db, p, wh, y, issue_date=date(2026, 5, 1), unit_cost=Decimal("20.00"),
                  order_currency="USD")

    before = db.query(ProductSupplier).filter(ProductSupplier.product_id == p.id).all()
    before_by_supplier = {str(l.supplier_id): (l.is_primary_supplier, l.unit_cost, l.currency)
                           for l in before}

    report = backfill_run(db, apply=False, all_suppliers=True)

    assert report["pairs_seen"] == 2
    assert report["created"] == 1
    after = db.query(ProductSupplier).filter(ProductSupplier.product_id == p.id).all()
    assert after == before
    assert len(after) == 2
    after_by_supplier = {str(l.supplier_id): (l.is_primary_supplier, l.unit_cost, l.currency)
                          for l in after}
    assert after_by_supplier == before_by_supplier
    assert str(default.id) in after_by_supplier
    assert str(x.id) in after_by_supplier
    assert str(y.id) not in after_by_supplier


# =========================================================================== #
# T8 / AC-ALL.10 - the order sheet's Supplier column agrees (shared DB, chain fixtures)
# =========================================================================== #


def test_last_po_supplier_map_skips_cancelled_po(db, chain):
    """T8 / AC-ALL.10: a product's newest PO is cancelled (supplier R); its newest
    NON-cancelled PO names supplier Y. `summary_order_service._last_po_supplier_map`
    must name Y, never R - so the order sheet's Supplier column keeps agreeing with the
    backfill script (ruling 3)."""
    f = chain
    product = f["product"]
    y = _supplier(db, "Supplier Y")
    r = _supplier(db, "Supplier R, cancelled newest")
    older = _po(db, product, f["bin"], 10, supplier=y, issued_days_ago=30)
    older.status = "closed"
    newer = _po(db, product, f["bin"], 10, supplier=r, issued_days_ago=2)
    newer.status = "cancelled"
    db.flush()

    out = svc._last_po_supplier_map(db, [product.id])
    assert out[product.id]["supplier_name"] == "Supplier Y"


# =========================================================================== #
# T9 / AC-ALL.11 - CLI parses --all-suppliers
# =========================================================================== #


def test_cli_parses_all_suppliers_flag(monkeypatch):
    """T9 / AC-ALL.11: `--all-suppliers` is accepted by the CLI and threads through to
    `run(..., all_suppliers=True)`. No real session, company-scope listener or DB
    connection is touched - `main`'s `SessionLocal`, `register_company_scope_listeners`
    and `company_scope` are all patched out; only argparse and the call into `run` are
    under test."""
    import scripts.backfill_product_supplier_from_last_po as script

    captured: dict = {}

    def fake_run(db, **kwargs):
        captured.update(kwargs)
        return {
            "mode": "DRY-RUN (no writes)", "products_seen": 0, "pairs_seen": 0,
            "created": 0, "promoted": 0, "terms_filled": 0, "default_removed": 0,
            "default_all_removed": 0, "default_supplier_found": True, "samples": [],
        }

    class _FakeDb:
        def close(self):
            pass

    @contextlib.contextmanager
    def fake_company_scope(db, ids):
        yield

    monkeypatch.setattr(script, "run", fake_run)
    monkeypatch.setattr(script, "SessionLocal", lambda: _FakeDb())
    monkeypatch.setattr(script, "register_company_scope_listeners", lambda: None)
    monkeypatch.setattr(script, "company_scope", fake_company_scope)
    monkeypatch.setattr(
        sys, "argv",
        ["backfill_product_supplier_from_last_po.py", "--dry-run", "--all-suppliers"],
    )

    rc = script.main()

    assert rc == 0
    assert captured.get("all_suppliers") is True


def test_print_report_shows_pairs_seen_and_terms_filled_only_when_all_suppliers(capsys):
    """T9 / AC-ALL.11: `_print_report` prints the `pairs seen` and `terms filled` labels
    when `all_suppliers=True`, and omits both when it is False (or left at its default)."""
    import scripts.backfill_product_supplier_from_last_po as script

    report = {
        "mode": "DRY-RUN (no writes)", "products_seen": 1, "pairs_seen": 2,
        "created": 1, "promoted": 0, "terms_filled": 1, "default_removed": 1,
        "default_all_removed": 0, "default_supplier_found": True, "samples": [],
    }

    script._print_report(report, drop_default_all=False, all_suppliers=True)
    on_output = capsys.readouterr().out
    assert "pairs seen" in on_output
    assert "terms filled" in on_output

    script._print_report(report, drop_default_all=False, all_suppliers=False)
    off_output = capsys.readouterr().out
    assert "pairs seen" not in off_output
    assert "terms filled" not in off_output


# =========================================================================== #
# AC-ALL.12 - DEFAULT is never a secondary link (review round 2)
# =========================================================================== #


def test_default_is_never_a_secondary_link(scratch_db):
    """AC-ALL.12: the DEFAULT supplier has an OLDER non-cancelled PO line for P; Y has a
    newer one. After `run(apply=True, all_suppliers=True)`: no (P, DEFAULT) link exists
    at all (DEFAULT is skipped as a non-primary pair, never created or kept as a
    secondary link), (P, Y) is primary, and `default_removed == 1` counts the
    pre-existing DEFAULT link that was removed."""
    from scripts.backfill_product_supplier_from_last_po import run as backfill_run

    db = scratch_db
    wh = _seed_warehouse(db)
    default = _seed_supplier(db, "DEFAULT", "Default Supplier")
    y = _seed_supplier(db, unique_code("Y")[:30], "Supplier Y")
    p = _seed_product(db, code_stem="P1")
    _link(db, p, default, primary=True)
    _seed_po_line(db, p, wh, default, issue_date=date(2024, 1, 1),
                  unit_cost=Decimal("1.00"), order_currency="USD")
    _seed_po_line(db, p, wh, y, issue_date=date(2026, 1, 1),
                  unit_cost=Decimal("2.00"), order_currency="USD")

    report = backfill_run(db, apply=True, all_suppliers=True)

    links = {
        str(l.supplier_id): l
        for l in db.query(ProductSupplier).filter(ProductSupplier.product_id == p.id).all()
    }
    assert str(default.id) not in links
    assert set(links) == {str(y.id)}
    assert links[str(y.id)].is_primary_supplier is True
    assert report["default_removed"] == 1


# =========================================================================== #
# AC-ALL.13 - cost is never written without its currency (review round 2)
# =========================================================================== #


def test_priced_line_with_no_currency_writes_no_price(scratch_db):
    """AC-ALL.13: a priced PO line for (P, Z) whose LINE currency AND ORDER currency are
    both NULL. The created link gets unit_cost NULL and currency NULL - a cost is never
    written without its currency - and `terms_filled` stays 0 (this is a CREATED link,
    not a fill on an existing one)."""
    from scripts.backfill_product_supplier_from_last_po import run as backfill_run

    db = scratch_db
    wh = _seed_warehouse(db)
    z = _seed_supplier(db, unique_code("Z")[:30], "Supplier Z")
    p = _seed_product(db, code_stem="P1")
    _seed_po_line(db, p, wh, z, issue_date=date(2024, 1, 1), unit_cost=Decimal("50.00"),
                  order_currency=None, line_currency=None)

    report = backfill_run(db, apply=True, all_suppliers=True)

    links = {
        str(l.supplier_id): l
        for l in db.query(ProductSupplier).filter(ProductSupplier.product_id == p.id).all()
    }
    assert links[str(z.id)].unit_cost is None
    assert links[str(z.id)].currency is None
    assert report["terms_filled"] == 0
