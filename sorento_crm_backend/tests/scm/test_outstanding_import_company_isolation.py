"""The outstanding-orders importer must only ever see the ACTIVE company's rows.

This file exists because of one commit (ccc5f7323). Every code lookup in the importer
used raw SQL, and the multi-company isolation filter runs on ORM execution ONLY - a
`SELECT ... FROM products WHERE product_code = ...` sees EVERY company. That was not
theoretical: each company carries its own copy of the catalogue, so 11,390 product codes
exist twice in the real database. The lookup builds a dict keyed by code, so resolution
went to whichever row the database happened to return last, and an imported order line
could be attached to ANOTHER company's product, non-deterministically. `_existing_lines`
had the same flaw and it was worse: it decides what the diff compares against, so another
company's order could be diffed against this upload and reported closed by it.

So the property under test is not "the ORM is used" - that would be a test of the source
text. It is "resolution never crosses a company boundary", asserted on the product_id and
warehouse_id actually written to the sales order line, on what `_existing_lines` returns,
and on what the diff proposes to close. Reverting any lookup to raw SQL fails these.

Two shapes of evidence are used, because they fail differently:

* **Owned only by the other company.** Company B holds the code, company A does not.
  Resolution under A must FAIL (reported, never guessed). A raw lookup finds B's row every
  time, so this half is deterministic regardless of row order.
* **Held by both companies.** The duplicate that actually exists in production. Under A the
  answer must be A's row. A raw lookup keyed by code takes whichever row came back last,
  which is B's here because B's row is inserted second.

Every company, category, uom, product, warehouse, customer, market segment, order and line
is seeded by the test under a `ZZTISO` marker. Nothing is borrowed with `LIMIT 1`: CI's
database has no data, and a borrowed row is how a suite passes locally and dies in CI.
Everything runs inside `pg_session()`, which rolls back.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from io import BytesIO

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.access import MarketSegment
from app.models.base import set_company_scope
from app.models.company import Company
from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import PO, SO
from tests._pg_fixture import pg_session

MARKER = "ZZTISO"

# The header row the seeded `import_field_alias` rows map (doc_type = outstanding_so).
_HEADERS = ["S/O NO", "ITEM CODE", "QTY", "DELIVERY DATE", "STOCK LOCATION"]

# The same, for doc_type = outstanding_po. The creditor code is the PO book's third
# company-scoped lookup, alongside the item code and the stock location.
_PO_HEADERS = ["PO NO", "CREDITOR CODE", "ITEM CODE", "QTY ORDERED", "ETA", "STOCK LOCATION"]

# The SO headers plus the debtor code, for the tests about the customer LINK. Kept off
# `_HEADERS` so the lookup tests above still exercise a file that names no counterparty.
_SO_DEBTOR_HEADERS = ["S/O NO", "DEBTOR CODE", "ITEM CODE", "QTY", "DELIVERY DATE",
                      "STOCK LOCATION"]


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    """A marker-prefixed, UPPERCASE code. Uppercase matters: the importer normalises with
    `upper()` on both sides, so a lowercase hex suffix would simply never match."""
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _workbook(rows, headers=None) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers or _HEADERS)
    for row in rows:
        ws.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _po_workbook(rows) -> bytes:
    return _workbook(rows, headers=_PO_HEADERS)


# --------------------------------------------------------------------------- #
# world: two companies, each able to own its own copy of anything
# --------------------------------------------------------------------------- #

@dataclass
class World:
    """Two companies and the seeding helpers. `company_id` is always passed explicitly so
    the auto-stamp never decides ownership for us - the whole point is to control it."""

    db: Session
    a: str
    b: str

    def category_and_uom(self, company: str) -> tuple[str, str]:
        cat = ProductCategory(id=_u(), category_code=_code("CAT"),
                              category_name=f"{MARKER} category", company_id=company)
        uom = UnitOfMeasure(id=_u(), uom_code=_code("U")[:20], uom_name=f"{MARKER} unit",
                            company_id=company)
        self.db.add_all([cat, uom])
        self.db.flush()
        return cat.id, uom.id

    def product(self, code: str, company: str) -> str:
        cat_id, uom_id = self.category_and_uom(company)
        pid = _u()
        self.db.add(Product(id=pid, product_code=code, product_name=code,
                            category_id=cat_id, base_uom_id=uom_id, list_price=0,
                            is_active=True, is_discontinued=False, company_id=company))
        self.db.flush()
        return pid

    def warehouse(self, code: str, company: str) -> str:
        wid = _u()
        self.db.add(Warehouse(id=wid, warehouse_code=code, warehouse_name=code,
                              is_active=True, company_id=company))
        self.db.flush()
        return wid

    def order(self, number: str, company: str) -> str:
        oid = _u()
        self.db.add(SalesOrder(id=oid, so_number=number, status="open",
                               company_id=company))
        self.db.flush()
        return oid

    def line(self, order_id: str, product_id: str, company: str, qty: float = 10,
             required_date: date | None = None, warehouse_id: str | None = None) -> str:
        lid = _u()
        self.db.add(SalesOrderLine(id=lid, sales_order_id=order_id, product_id=product_id,
                                   warehouse_id=warehouse_id, qty_ordered=qty,
                                   qty_delivered=0, line_status="open",
                                   required_date=required_date, company_id=company))
        self.db.flush()
        return lid

    def supplier(self, code: str, company: str, name: str | None = None) -> str:
        sid = _u()
        self.db.add(Supplier(id=sid, supplier_code=code,
                             supplier_name=name or f"{MARKER} supplier {code}",
                             is_active=True, company_id=company))
        self.db.flush()
        return sid

    def segment(self, stem: str) -> str:
        """A market segment whose CODE carries the word the demand class keys off.

        `_class_of` matches "project" / "contract" as a substring of the code, so a
        marker-prefixed code still classifies exactly as the production ones do.
        """
        code = f"{MARKER}-{stem}-{uuid.uuid4().hex[:6]}".lower()
        self.db.add(MarketSegment(id=_u(), code=code, name=code, is_active=True))
        self.db.flush()
        return code

    def customer(self, code: str, name: str, company: str, segment: str | None) -> str:
        cid = _u()
        self.db.add(Customer(id=cid, customer_code=code, customer_name=name,
                             market_segment_code=segment, is_active=True,
                             company_id=company))
        self.db.flush()
        return cid


def _act_as(db: Session, company_id: str) -> None:
    """Run the next call as a single-company principal, exactly as a request would."""
    set_company_scope(db, frozenset({company_id}))


def _schema_isolates_supplier_code(db: Session, probing_company: str, code: str) -> bool:
    """Whether this schema enforces `supplier_code` uniqueness PER COMPANY.

    True on the migrated (production) schema (migration 305, `uq_suppliers_company_
    supplier_code`). False on a `create_all` schema (CI's `bootstrap_env`, and the blank
    scratch schemas): `suppliers.supplier_code` still declares a bare `unique=True` on
    the MODEL there, so a second supplier under a DIFFERENT company (`probing_company`)
    but the SAME code, already held by another company, is rejected outright - which is
    exactly what the back-create path this test exercises would attempt. Probed with a
    savepoint that is always rolled back: this reads the constraint, it does not seed a
    row, so it cannot affect the row counts the caller asserts afterwards.
    """
    savepoint = db.begin_nested()
    try:
        db.add(Supplier(id=_u(), supplier_code=code, supplier_name=f"{MARKER} probe",
                        is_active=True, company_id=probing_company))
        db.flush()
    except IntegrityError:
        savepoint.rollback()
        return False
    savepoint.rollback()
    return True


def _seed_duplicate_or_skip(db: Session, obj, why: str) -> None:
    """Insert a row that duplicates a code already held by the other company.

    Whether that is legal depends on the schema the test is running against. The migrated
    (production) database made these unique PER COMPANY, but `warehouses.warehouse_code`
    and `sales_orders.so_number` still declare a bare `unique=True` on the MODEL, so a
    database built by `create_all` (CI's `bootstrap_env`, and the blank scratch schemas)
    rejects the duplicate outright. Skip rather than fail: the companion
    "owned only by the other company" test covers the same lookup on every schema.
    """
    savepoint = db.begin_nested()
    try:
        db.add(obj)
        db.flush()
        savepoint.commit()
    except IntegrityError:
        savepoint.rollback()
        try:
            db.expunge(obj)
        except Exception:  # noqa: BLE001 - already detached, nothing to undo
            pass
        pytest.skip(why)


@pytest.fixture()
def db():
    with pg_session() as session:
        # Seed as an all-companies principal: every row below states its company_id
        # explicitly, and reads during seeding must not be filtered.
        set_company_scope(session, None)
        yield session


@pytest.fixture()
def world(db):
    if not db.execute(text("SELECT 1 FROM import_field_alias "
                           "WHERE doc_type = 'outstanding_so' LIMIT 1")).scalar():
        pytest.skip("no outstanding_so aliases seeded in this database")

    a, b = _u(), _u()
    db.add_all([
        Company(id=a, name=f"{MARKER} company A", code=_code("A")[:50], is_active=True),
        Company(id=b, name=f"{MARKER} company B", code=_code("B")[:50], is_active=True),
    ])
    db.flush()
    return World(db=db, a=a, b=b)


def _written_lines(db: Session, so_number: str):
    """Read the written lines with raw SQL ON PURPOSE: the assertion must see what actually
    landed in the table, including a row belonging to the wrong company."""
    return db.execute(text(
        "SELECT sol.product_id, sol.warehouse_id, sol.company_id, sol.line_status "
        "FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "WHERE so.so_number = :so"
    ), {"so": so_number}).fetchall()


# --------------------------------------------------------------------------- #
# 1. products
# --------------------------------------------------------------------------- #

def test_a_product_code_held_by_both_companies_resolves_to_the_active_one(world):
    """The production duplicate: 11,390 codes exist twice. Company A's upload must attach
    to company A's product."""
    db = world.db
    code = _code("ITEM")
    product_a = world.product(code, world.a)      # inserted first
    product_b = world.product(code, world.b)      # inserted second: what a raw lookup keeps
    so_number = _code("SO")

    _act_as(db, world.a)
    out = svc.apply(db, _workbook([[so_number, code, 10, date(2026, 7, 1), ""]]), SO)

    assert out["ok"] and out["applied"]["added"] == 1
    written = _written_lines(db, so_number)
    assert len(written) == 1
    assert str(written[0][0]) == product_a, (
        "the line was attached to another company's product with the same code"
    )
    assert str(written[0][0]) != product_b


def test_a_product_code_owned_only_by_another_company_is_never_resolved(world):
    """Company A does not stock this code. Resolution must fail and say so, not silently
    reach into company B's catalogue."""
    db = world.db
    code = _code("ITEM")
    world.product(code, world.b)
    so_number = _code("SO")

    _act_as(db, world.a)
    file = _workbook([[so_number, code, 10, date(2026, 7, 1), ""]])
    preview = svc.preview(db, file, SO)

    assert preview.counts["added"] == 0
    assert [(i.field, i.value) for i in preview.resolution_issues] == [("item_code", code)]

    out = svc.apply(db, file, SO)
    assert out["applied"]["added"] == 0
    assert _written_lines(db, so_number) == []


# --------------------------------------------------------------------------- #
# 2. warehouses
# --------------------------------------------------------------------------- #

def test_a_warehouse_code_owned_only_by_another_company_is_never_resolved(world):
    """A stock location company A does not have must be reported, not borrowed from B.

    Borrowing it would place company A's demand in a warehouse it cannot ship from, and
    every coverage / netting number for that location would then be wrong.
    """
    db = world.db
    item = _code("ITEM")
    location = _code("WH")[:50]
    world.product(item, world.a)
    world.warehouse(location, world.b)
    so_number = _code("SO")

    _act_as(db, world.a)
    file = _workbook([[so_number, item, 10, date(2026, 7, 1), location]])
    preview = svc.preview(db, file, SO)

    assert preview.counts["added"] == 0
    assert [(i.field, i.value) for i in preview.resolution_issues] == [
        ("stock_location", location)
    ]

    out = svc.apply(db, file, SO)
    assert out["applied"]["added"] == 0
    assert _written_lines(db, so_number) == []


def test_a_warehouse_code_held_by_both_companies_resolves_to_the_active_one(world):
    """Same duplicate story as products, on the schema that permits it (see
    `_seed_duplicate_or_skip`)."""
    db = world.db
    item = _code("ITEM")
    location = _code("WH")[:50]
    product_a = world.product(item, world.a)
    warehouse_a = world.warehouse(location, world.a)          # inserted first
    _seed_duplicate_or_skip(
        db,
        Warehouse(id=_u(), warehouse_code=location, warehouse_name=location,
                  is_active=True, company_id=world.b),
        "this schema enforces a globally unique warehouse_code, so the two companies "
        "cannot both hold the code",
    )
    so_number = _code("SO")

    _act_as(db, world.a)
    out = svc.apply(db, _workbook([[so_number, item, 10, date(2026, 7, 1), location]]), SO)

    assert out["applied"]["added"] == 1
    written = _written_lines(db, so_number)
    assert len(written) == 1
    assert str(written[0][0]) == product_a
    assert str(written[0][1]) == warehouse_a, (
        "the line was placed in another company's warehouse with the same code"
    )


# --------------------------------------------------------------------------- #
# 3. existing lines / the diff
# --------------------------------------------------------------------------- #

def test_existing_lines_never_returns_another_companys_order(world):
    """`_existing_lines` decides what the upload is compared against. Another company's
    order carrying the number the file names must not appear in it at all."""
    db = world.db
    item_b = _code("ITEM")
    so_number = _code("SO")
    order_b = world.order(so_number, world.b)
    world.line(order_b, world.product(item_b, world.b), world.b,
               qty=25, required_date=date(2026, 7, 1))

    _act_as(db, world.a)

    assert svc._existing_lines(db, {so_number}, svc._binding(SO)) == []


def test_the_preview_does_not_propose_closing_another_companys_order(world):
    """The end-to-end read path of the same bug: company A uploads the number company B's
    order carries, and the confirm screen must offer to close nothing.

    Preview writes nothing, so this is safe to assert against a document company A does not
    own - which is exactly the state the bug produced.
    """
    db = world.db
    so_number = _code("SO")
    item_b = _code("ITEMB")
    order_b = world.order(so_number, world.b)
    world.line(order_b, world.product(item_b, world.b), world.b,
               qty=25, required_date=date(2026, 7, 1))

    item_a = _code("ITEMA")
    world.product(item_a, world.a)

    _act_as(db, world.a)
    preview = svc.preview(db, _workbook([[so_number, item_a, 10, date(2026, 7, 1), ""]]), SO)

    assert preview.counts["added"] == 1
    assert preview.counts["closed"] == 0, (
        "the diff proposed closing another company's line: "
        f"{preview.samples.get('closed')}"
    )


def test_applying_an_upload_never_closes_a_line_owned_by_another_company(world):
    """The write path, on a document company A DOES own.

    Company B's line hangs off company A's order. That is the only shape this schema allows
    for the collision (`sales_orders.so_number` is declared globally unique on the model, so
    two orders cannot share a number on a `create_all` database), and it isolates the thing
    under test: `_existing_lines` must return company A's line and only company A's line.

    Both halves are asserted, because they fail separately. The diff must not COUNT a close
    (that is `_existing_lines`), and company B's row must still be open afterwards (that is
    the write).
    """
    db = world.db
    so_number = _code("SO")
    order_a = world.order(so_number, world.a)

    item_a = _code("ITEMA")
    world.line(order_a, world.product(item_a, world.a), world.a,
               qty=10, required_date=date(2026, 7, 1))

    item_b = _code("ITEMB")
    line_b = world.line(order_a, world.product(item_b, world.b), world.b,
                        qty=25, required_date=date(2026, 7, 1))

    _act_as(db, world.a)
    # The file restates company A's line exactly, and says nothing about company B's.
    out = svc.apply(db, _workbook([[so_number, item_a, 10, date(2026, 7, 1), ""]]), SO)

    assert out["counts"]["unchanged"] == 1
    assert out["counts"]["closed"] == 0, "the diff proposed closing another company's line"
    assert out["applied"]["closed"] == 0

    status = db.execute(text("SELECT line_status FROM sales_order_lines WHERE id = :i"),
                        {"i": line_b}).scalar()
    assert status == "open", "another company's line was closed by this upload"


# --------------------------------------------------------------------------- #
# 4. demand class / customers
# --------------------------------------------------------------------------- #

def test_the_demand_class_reads_a_customer_of_the_active_company_only(world):
    """Fulfilment priority is decided here. Reading company B's customer would set company
    A's order priority from the wrong row."""
    db = world.db
    code = _code("CUST")[:50]
    world.customer(code, f"{MARKER} B debtor", world.b, world.segment("project"))
    world.customer(code, f"{MARKER} A debtor", world.a, world.segment("retail"))

    _act_as(db, world.a)

    assert svc._class_of(svc._segment_of(db, code)) == "retail"


def test_a_customer_owned_only_by_another_company_does_not_set_the_demand_class(world):
    """The deterministic half: company A has no such debtor, so the segment answers
    nothing. A raw lookup finds company B's project customer and promotes the order."""
    db = world.db
    code = _code("CUST")[:50]
    world.customer(code, f"{MARKER} B debtor", world.b, world.segment("project"))

    _act_as(db, world.a)

    assert svc._class_of(svc._segment_of(db, code)) is None


# The SO book now LINKS that customer (`sales_orders.customer_id`), not just reads their
# segment, so the boundary matters on the write as well as on the classification: an order
# attributed to another company's debtor names the wrong buyer on every screen that reads
# it. Same pair of shapes as the creditor code below.

def _so_customer_code(db: Session, so_number: str):
    """The customer code on the written sales order, read with raw SQL on purpose."""
    return db.execute(text(
        "SELECT c.customer_code FROM sales_orders so "
        "LEFT JOIN customers c ON c.id = so.customer_id "
        "WHERE so.so_number = :so"
    ), {"so": so_number}).scalar()


def test_a_debtor_code_owned_only_by_another_company_is_never_linked(world):
    """Company A has no such debtor. The order is left unlinked, and the CODE is kept."""
    db = world.db
    item = _code("ITEM")
    debtor = _code("CUST")[:50]
    world.product(item, world.a)
    world.customer(debtor, f"{MARKER} B debtor", world.b, None)
    so_number = _code("SO")

    _act_as(db, world.a)
    file = _workbook([[so_number, debtor, item, 10, date(2026, 7, 1), ""]],
                     headers=_SO_DEBTOR_HEADERS)
    svc.apply(db, file, SO)

    assert _so_customer_code(db, so_number) is None, \
        "the sales order was attached to another company's customer"
    assert db.execute(text("SELECT debtor_code FROM sales_orders WHERE so_number = :s"),
                      {"s": so_number}).scalar() == debtor


def test_a_debtor_code_held_by_both_companies_links_the_active_one(world):
    """The production duplicate: company A's upload must attach to company A's customer."""
    db = world.db
    item = _code("ITEM")
    debtor = _code("CUST")[:50]
    world.product(item, world.a)
    world.customer(debtor, f"{MARKER} A debtor", world.a, None)      # inserted first
    _seed_duplicate_or_skip(
        db,
        Customer(id=_u(), customer_code=debtor, customer_name=f"{MARKER} B debtor",
                 is_active=True, company_id=world.b),
        "this schema enforces a globally unique customer_code, so the two companies "
        "cannot both hold the code",
    )
    so_number = _code("SO")

    _act_as(db, world.a)
    svc.apply(db, _workbook([[so_number, debtor, item, 10, date(2026, 7, 1), ""]],
                            headers=_SO_DEBTOR_HEADERS), SO)

    name = db.execute(text(
        "SELECT c.customer_name FROM sales_orders so "
        "JOIN customers c ON c.id = so.customer_id WHERE so.so_number = :s"
    ), {"s": so_number}).scalar()
    assert name == f"{MARKER} A debtor", (
        "the sales order was attached to another company's customer with the same code"
    )


# --------------------------------------------------------------------------- #
# 5. suppliers / the creditor code on the purchase-order book
# --------------------------------------------------------------------------- #
# The PO book adds a third company-scoped lookup, and reads/writes are isolated the same
# way as the other two for the same reason: suppliers are company-scoped, every company
# carries its own creditor list, and a code resolved across the boundary attaches this
# company's incoming shipment to a supplier it does not buy from - which is then who gets
# chased, scored for lateness, and paid. One difference from the other two: an unresolved
# creditor code is now back-created (`_Binding.party_back_create`), so "never resolved"
# below means "never resolved to company B's own row" - company A gets its own.

def _po_supplier_code(db: Session, po_number: str):
    """The supplier code on the written purchase order, read with raw SQL on purpose."""
    return db.execute(text(
        "SELECT s.supplier_code FROM purchase_orders po "
        "LEFT JOIN suppliers s ON s.id = po.supplier_id "
        "WHERE po.po_number = :po"
    ), {"po": po_number}).scalar()


def _po_supplier(db: Session, po_number: str):
    """(supplier id, company_id) on the written purchase order, read with raw SQL on
    purpose - the back-create test below needs to tell "attached to company B's own row"
    apart from "a distinct row created for company A that happens to share the code"."""
    return db.execute(text(
        "SELECT s.id::text, s.company_id::text FROM purchase_orders po "
        "LEFT JOIN suppliers s ON s.id = po.supplier_id "
        "WHERE po.po_number = :po"
    ), {"po": po_number}).fetchone()


def _requires_po_aliases(db: Session) -> None:
    if not db.execute(text("SELECT 1 FROM import_field_alias "
                           "WHERE doc_type = 'outstanding_po' LIMIT 1")).scalar():
        pytest.skip("no outstanding_po aliases seeded in this database")


def test_a_creditor_code_owned_only_by_another_company_gets_its_own_row_back_created(world):
    """Company A does not buy from this creditor - not company B's row, and never borrowed.

    Since the back-create AC (`outstanding_import_service.py`, `_Binding.party_back_create`)
    this is no longer "reported and left unlinked forever": company A's `apply()` creates
    its OWN minimal supplier under the SAME code, exactly as it would for a code nobody
    anywhere held. The isolation property under test does not change - a raw `SELECT ...
    FROM suppliers WHERE supplier_code = ...` still finds company B's row every time,
    whatever the row order, and that row must never be the one this purchase order attaches
    to, nor may this creation touch it.

    Only reachable on the schema that lets two companies each hold `supplier_code`
    (`_schema_isolates_supplier_code`, same reason as `_seed_duplicate_or_skip` below): a
    `create_all` schema still enforces the model's bare `unique=True` on the column, so
    the back-create insert itself would collide with company B's row there, and `apply()`
    correctly leaves the creditor unresolved rather than crash the upload (see the
    `IntegrityError` handling in `outstanding_import_service.apply`) - a real, safe
    behaviour on that schema, just not the one this test is about.
    """
    db = world.db
    _requires_po_aliases(db)
    item = _code("ITEM")
    creditor = _code("CRED")[:50]
    world.product(item, world.a)
    b_supplier_id = world.supplier(creditor, world.b)
    if not _schema_isolates_supplier_code(db, world.a, creditor):
        pytest.skip("this schema enforces a globally unique supplier_code, so company A "
                    "cannot back-create its own row under a code company B already holds")
    po_number = _code("PO")

    _act_as(db, world.a)
    file = _po_workbook([[po_number, creditor, item, 10, date(2026, 7, 1), ""]])
    preview = svc.preview(db, file, PO)

    assert [(i.field, i.value) for i in preview.resolution_issues] == [
        ("creditor_code", creditor)
    ]
    assert db.execute(
        text("SELECT count(*) FROM suppliers WHERE supplier_code = :c"), {"c": creditor}
    ).scalar() == 1, "preview must not write"

    out = svc.apply(db, file, PO)

    supplier_id, company_id = _po_supplier(db, po_number)
    assert _po_supplier_code(db, po_number) == creditor
    assert company_id == world.a, "the created supplier was not stamped with company A"
    assert supplier_id != b_supplier_id, \
        "the purchase order was attached to another company's supplier"
    assert out["suppliers_created"] == 1
    assert db.execute(
        text("SELECT count(*) FROM suppliers WHERE supplier_code = :c"), {"c": creditor}
    ).scalar() == 2, "company A must get its own row, company B's must be untouched"


def test_a_creditor_code_held_by_both_companies_resolves_to_the_active_one(world):
    """The production duplicate, on the schema that permits it (see
    `_seed_duplicate_or_skip`). Company A's upload must attach to company A's supplier."""
    db = world.db
    _requires_po_aliases(db)
    item = _code("ITEM")
    creditor = _code("CRED")[:50]
    world.product(item, world.a)
    world.supplier(creditor, world.a, name=f"{MARKER} A supplier")     # inserted first
    _seed_duplicate_or_skip(
        db,
        Supplier(id=_u(), supplier_code=creditor, supplier_name=f"{MARKER} B supplier",
                 is_active=True, company_id=world.b),
        "this schema enforces a globally unique supplier_code, so the two companies cannot "
        "both hold the code",
    )
    po_number = _code("PO")

    _act_as(db, world.a)
    svc.apply(db, _po_workbook([[po_number, creditor, item, 10, date(2026, 7, 1), ""]]), PO)

    name = db.execute(text(
        "SELECT s.supplier_name FROM purchase_orders po "
        "JOIN suppliers s ON s.id = po.supplier_id WHERE po.po_number = :po"
    ), {"po": po_number}).scalar()
    assert name == f"{MARKER} A supplier", (
        "the purchase order was attached to another company's supplier with the same code"
    )
