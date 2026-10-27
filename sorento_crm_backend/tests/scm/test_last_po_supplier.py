"""The one "last PO supplier" rule (owner ruling 27 Oct, STOCK-POSITION-REPORT Q4).

`app/services/scm/last_po_supplier.py`: the supplier on a product's newest purchase-order line,
read by the stock position report and the low stock report (`summary_order_service.
_last_po_supplier_map`). Ordering is STOCKDEBT-PERF's (#1901): `issue_date` desc (no date last),
line `created_at` desc, `po_number` desc, line id desc. Cancelled POs and removed lines are skipped.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from app.models.procurement import ProductSupplier, PurchaseOrder, PurchaseOrderLine, Supplier
from tests.scm.conftest import requires_pg
from tests.scm.test_loading_plan import World
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZLP"


def _supplier(db, name) -> Supplier:
    s = Supplier(id=str(uuid.uuid4()), supplier_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
                 supplier_name=f"{MARKER} {name}", is_active=True)
    db.add(s)
    db.flush()
    return s


def _line(db, product, supplier, issued, *, po_number=None, status="active", created=None,
          removed=False, line_id=None) -> PurchaseOrderLine:
    po = PurchaseOrder(id=str(uuid.uuid4()), po_number=po_number or f"{MARKER}-{uuid.uuid4().hex[:8]}",
                       supplier_id=supplier.id, issue_date=issued, status=status)
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(id=str(uuid.uuid4()), purchase_order_id=po.id, product_id=product.id,
                             qty_ordered=1, qty_received=0, line_status="open", removed_unreferenced=removed,
                             created_at=created or datetime(2026, 1, 1, 9, 0))
    db.add(line)
    db.flush()
    return line


def _setup(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    return db, World(db)


def test_the_newest_po_line_names_the_supplier_cancelled_and_removed_skipped(scm_app):
    from app.services.scm.last_po_supplier import last_po_supplier_ids

    db, w = _setup(scm_app)
    p = w.product("A")
    old, new, cancelled, removed = (_supplier(db, n) for n in ("old", "new", "cancelled", "removed"))
    _line(db, p, old, date(2025, 1, 1))
    _line(db, p, new, date(2026, 3, 1))
    _line(db, p, cancelled, date(2026, 6, 1), status="cancelled")
    _line(db, p, removed, date(2026, 7, 1), removed=True)

    assert last_po_supplier_ids(db, [p.id]) == {str(p.id): str(new.id)}


def test_ties_break_on_line_created_then_po_number_and_undated_po_last(scm_app):
    from app.services.scm.last_po_supplier import last_po_supplier_ids

    db, w = _setup(scm_app)
    a, b = w.product("A"), w.product("B")
    s1, s2 = _supplier(db, "one"), _supplier(db, "two")
    day = date(2026, 5, 1)
    # A: same issue date, the later-created line wins.
    _line(db, a, s1, day, created=datetime(2026, 5, 1, 10))
    _line(db, a, s2, day, created=datetime(2026, 5, 1, 9))
    # B: same date and created_at, the higher PO number wins.
    _line(db, b, s1, day, po_number=f"{MARKER}-PO-0002")
    _line(db, b, s2, day, po_number=f"{MARKER}-PO-0001")
    # (The line id breaks a tie inside ONE PO only: a PO number is unique per company and a PO
    # has one supplier, so that key keeps the pick stable but cannot change the supplier.)
    # An undated PO never beats a dated one.
    d = w.product("D")
    _line(db, d, s1, None, created=datetime(2026, 9, 1))
    _line(db, d, s2, date(2020, 1, 1))

    got = last_po_supplier_ids(db, [a.id, b.id, d.id])
    assert got == {str(a.id): str(s1.id), str(b.id): str(s1.id), str(d.id): str(s2.id)}


def test_no_po_means_no_supplier_whatever_the_product_links_say(scm_app):
    from app.services.scm.last_po_supplier import last_po_supplier_ids

    db, w = _setup(scm_app)
    p = w.product("A")
    linked = _supplier(db, "primary link")
    db.add(ProductSupplier(id=str(uuid.uuid4()), product_id=p.id, supplier_id=linked.id, is_primary_supplier=True))
    db.flush()
    assert last_po_supplier_ids(db, [p.id]) == {}


def test_every_product_when_none_is_named(scm_app):
    from app.services.scm.last_po_supplier import last_po_supplier_ids

    db, w = _setup(scm_app)
    a, b = w.product("A"), w.product("B")
    s = _supplier(db, "one")
    _line(db, a, s, date(2026, 1, 1))
    _line(db, b, s, date(2026, 1, 1))
    got = last_po_supplier_ids(db, None)
    assert got[str(a.id)] == str(s.id) and got[str(b.id)] == str(s.id)


def test_another_companys_po_never_names_the_supplier(scm_app):
    from app.models.company import Company
    from app.services.scm.last_po_supplier import last_po_supplier_ids

    db, w = _setup(scm_app)
    p = w.product("A")
    mine, theirs_s = _supplier(db, "mine"), _supplier(db, "theirs")
    _line(db, p, mine, date(2025, 1, 1))
    other = str(uuid.uuid4())
    db.add(Company(id=other, name=f"{MARKER} other {other[:6]}", code=f"{MARKER}{uuid.uuid4().hex[:6]}".upper(),
                   is_active=True))
    db.flush()
    po = PurchaseOrder(id=str(uuid.uuid4()), po_number=f"{MARKER}-THEIRS", supplier_id=theirs_s.id,
                       issue_date=date(2026, 9, 1), status="active", company_id=other)
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(id=str(uuid.uuid4()), purchase_order_id=po.id, product_id=p.id, qty_ordered=1,
                             qty_received=0, line_status="open", company_id=other))
    db.flush()
    assert last_po_supplier_ids(db, [p.id]) == {str(p.id): str(mine.id)}


def test_the_low_stock_report_reads_the_same_rule(scm_app, monkeypatch):
    """`summary_order_service._last_po_supplier_map` asks the shared helper, never its own query."""
    from app.services.scm import last_po_supplier, summary_order_service

    db, w = _setup(scm_app)
    p = w.product("A")
    s = _supplier(db, "spy")
    _line(db, p, s, date(2026, 1, 1))
    calls = []
    real = last_po_supplier.last_po_supplier_ids

    def spy(session, product_ids):
        calls.append(list(product_ids or []))
        return real(session, product_ids)

    monkeypatch.setattr(last_po_supplier, "last_po_supplier_ids", spy)
    out = summary_order_service._last_po_supplier_map(db, [p.id])
    assert calls == [[p.id]]
    assert out[p.id]["supplier_name"] == s.supplier_name
