"""The outstanding-order upload fixtures for the tests that WRITE to the database.

Same two-week scenario as the committed `tests/scm/fixtures/outstanding_so_sample*.xlsx`,
but generated per test from codes the test owns, so the file and the seeded rows can never
disagree.

Why generated here and committed there. `test_outstanding_reader.py` asserts PARSING - dates
arriving as datetimes, quantities with separators, an unmapped column, headers in an order
nobody agreed - so a real-shaped committed file is the only honest input, and it touches no
database at all, so it cannot collide with anything. The service and route tests assert diff
and write semantics, which are indifferent to where the bytes came from and entirely
dependent on owning their rows: they seeded the literal `BRW-BB`, `SRTWC8613-RL`, `SO397450`
from the real extract, which already exist on any prod-copy database, so
`uq_warehouses_company_warehouse_code` rejected the seed and 14 tests errored on that
database while passing on an empty one. A test must not care which database it meets.

Renaming the seeded rows alone was not an option: the committed workbook names those codes,
so file and rows would silently drift apart. Generating both from one `Codes` value keeps
them in lockstep by construction.

The scenario is preserved exactly, because the assertions are about it:

  week 1                                              week 2
  project SO, item_rl  135 due 1 Jul                  135 due 15 Jul   (date moved 14 days)
  project SO, item_rl   72 due 3 Aug                   90 due 3 Aug    (qty changed)
  project SO, item_wt   60 due 30 Sep                  absent          (closed)
  project SO, item_new  absent                         12 due 1 Sep    (added)
  dealer  SO, item_wt    7 due 30 Oct                   7 due 30 Oct   (unchanged)
  dealer  SO, item_blue 7646 due 15 Nov               7646 due 15 Nov  (unchanged)

Only the values that BECOME database rows are marker-prefixed: SO numbers (`sales_orders`),
item codes (`products`) and stock locations (`warehouses`). The customer labels and debtor
codes stay as they are - they are file content that these paths never write, and keeping them
real keeps the label assertions readable.

The purchase-order book (`po_week1` / `po_week2`) mirrors that scenario line for line, over
the SAME products and warehouses, so a PO assertion reads next to its SO counterpart and any
divergence between the two paths is visible rather than buried in two different scenarios:

  week 1                                              week 2
  main PO, item_rl  135 due 1 Jul  (150 - 15 recd)    135 due 15 Jul   (date moved 14 days)
  main PO, item_rl   72 due 3 Aug                      90 due 3 Aug    (qty changed)
  main PO, item_wt   60 due 30 Sep                     absent          (closed)
  main PO, item_new  absent                            12 due 1 Sep    (added)
  alt  PO, item_wt    7 due 30 Oct                      7 due 30 Oct   (unchanged)
  alt  PO, item_blue 7646 due 15 Nov                 7646 due 15 Nov   (unchanged)

The first line carries a partial receipt on purpose (150 ordered, 15 received), because the
outstanding figure the plan needs is the DIFFERENCE and a file that never nets would let a
straight-through read of `QTY ORDERED` pass. Creditor codes ARE marker-prefixed, unlike the
SO side's debtor codes: they resolve to a `suppliers` row that the test seeds.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from io import BytesIO

import pytest
from sqlalchemy import text

MARKER = "ZZTOS"

# The real export's header row and column order, so the generated file exercises the same
# alias resolution (including PROJECT/CUSTOMER -> label and the unmapped REMARK column).
HEADERS = ("PROJECT/CUSTOMER", "S/O NO", "SO DATE", "DEBTOR CODE", "ITEM CODE", "UOM",
           "QTY", "DELIVERY DATE", "STOCK LOCATION", "ORDER TYPE", "REMARK")

# The purchase-order export's header row. Same shape of exercise: every alias the
# `outstanding_po` doc type declares, in an order nobody agreed, plus one unmapped column.
PO_HEADERS = ("SUPPLIER", "PO NO", "PO DATE", "CREDITOR CODE", "ITEM CODE", "UOM",
              "QTY ORDERED", "QTY RECEIVED", "ETA", "STOCK LOCATION", "UNIT COST",
              "CURRENCY", "REMARK")

PROJECT_LABEL = "TUJU RESIDENCE"
DEALER_LABEL = "ARIA VERDE"

SUPPLIER_MAIN_LABEL = "SIN HENG TRADING"
SUPPLIER_ALT_LABEL = "FOSHAN CERAMICS"


@dataclass(frozen=True)
class Codes:
    """One test's private code set. Names mirror the real extract's roles, not its strings."""

    project_so: str      # the multi-line project order
    dealer_so: str       # the two-line dealer order
    item_rl: str         # twice on the project order, at two different dates
    item_wt: str         # on both orders; the project line closes in week 2
    item_blue: str       # unchanged, large quantity
    item_new: str        # absent in week 1, added in week 2
    loc_project: str
    loc_dealer: str
    loc_bulk: str
    main_po: str         # the multi-line purchase order
    alt_po: str          # the two-line purchase order
    creditor_main: str   # resolves to the supplier on `main_po`
    creditor_alt: str    # resolves to the supplier on `alt_po`

    @property
    def items(self) -> tuple[str, ...]:
        return (self.item_rl, self.item_wt, self.item_blue, self.item_new)

    @property
    def locations(self) -> tuple[str, ...]:
        return (self.loc_project, self.loc_dealer, self.loc_bulk)

    @property
    def documents(self) -> tuple[str, ...]:
        """The scope the importer derives from either file, in the order it reports it."""
        return tuple(sorted((self.project_so, self.dealer_so)))

    @property
    def po_documents(self) -> tuple[str, ...]:
        """Same, for the purchase-order book."""
        return tuple(sorted((self.main_po, self.alt_po)))

    @property
    def creditors(self) -> tuple[tuple[str, str], ...]:
        """(creditor code, supplier name) for every supplier the PO files name."""
        return ((self.creditor_main, SUPPLIER_MAIN_LABEL),
                (self.creditor_alt, SUPPLIER_ALT_LABEL))


def make_codes() -> Codes:
    """A fresh, collision-free set. UPPERCASE because the importer normalises with `upper()`
    on both sides, so a lowercase hex suffix would never match."""
    tag = uuid.uuid4().hex[:8].upper()
    # SO1 / SO2 share the suffix so `sorted()` is deterministic: the project order first.
    return Codes(
        project_so=f"{MARKER}-SO1-{tag}",
        dealer_so=f"{MARKER}-SO2-{tag}",
        item_rl=f"{MARKER}-RL-{tag}",
        item_wt=f"{MARKER}-WT-{tag}",
        item_blue=f"{MARKER}-BLUE-{tag}",
        item_new=f"{MARKER}-NEW-{tag}",
        loc_project=f"{MARKER}-LP-{tag}",
        loc_dealer=f"{MARKER}-LD-{tag}",
        loc_bulk=f"{MARKER}-LB-{tag}",
        # PO1 / PO2 share the suffix so `sorted()` is deterministic: the main order first.
        main_po=f"{MARKER}-PO1-{tag}",
        alt_po=f"{MARKER}-PO2-{tag}",
        creditor_main=f"{MARKER}-CR1-{tag}",
        creditor_alt=f"{MARKER}-CR2-{tag}",
    )


def require_aliases(db, doc_type: str = "outstanding_so") -> None:
    """Fail, not skip, when the alias rows are missing.

    They are reference data the module cannot function without, and `scripts/bootstrap_env`
    seeds them from migration 311's own constant, so an empty table is a broken environment
    rather than an environment this suite does not apply to. As a skip it silently deleted
    the whole PO suite from the run - and a suite that vanishes reads exactly like a suite
    that passed.
    """
    if not db.execute(text("SELECT 1 FROM import_field_alias "
                           "WHERE doc_type = :d LIMIT 1"), {"d": doc_type}).scalar():
        pytest.fail(f"no {doc_type} rows in import_field_alias: this database was built "
                    f"without the SCM alias seed (migration 311 / bootstrap_env)")


def seed_catalogue(db, codes: Codes, doc_type: str = "outstanding_so") -> None:
    """Every product and warehouse the generated files name, and nothing else.

    No "insert only if absent" guard and no borrowed category or uom: the codes are unique to
    this test, so the insert is unconditional and the rows are unambiguously ours.
    """
    from app.models.inventory import Warehouse
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    require_aliases(db, doc_type)

    cat = ProductCategory(id=str(uuid.uuid4()),
                          category_code=f"{MARKER}-CAT-{uuid.uuid4().hex[:8]}".upper(),
                          category_name=f"{MARKER} category")
    uom = UnitOfMeasure(id=str(uuid.uuid4()),
                        uom_code=f"{MARKER}-U-{uuid.uuid4().hex[:6]}".upper(),
                        uom_name="pcs")
    db.add_all([cat, uom])
    db.flush()

    for code in codes.items:
        db.add(Product(id=str(uuid.uuid4()), product_code=code, product_name=code,
                       category_id=cat.id, base_uom_id=uom.id, list_price=0,
                       is_active=True, is_discontinued=False))
    for code in codes.locations:
        db.add(Warehouse(id=str(uuid.uuid4()), warehouse_code=code, warehouse_name=code,
                         is_active=True))
    db.flush()


def seed_suppliers(db, codes: Codes) -> None:
    """The suppliers the PO files' creditor codes resolve to, and nothing else.

    Separate from `seed_catalogue` because the SO path has no supplier and must not acquire
    rows it does not use: a test that seeds what it does not name cannot tell "resolved
    correctly" from "resolved to the only row present".
    """
    from app.models.procurement import Supplier

    for code, name in codes.creditors:
        db.add(Supplier(id=str(uuid.uuid4()), supplier_code=code, supplier_name=name,
                        is_active=True))
    db.flush()


def workbook(rows, headers=HEADERS, title="Outstanding SO") -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    ws.append(list(headers))
    for row in rows:
        ws.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


#: Every generated order STATES its class, because since QP1 (captain, 26 Aug 2026) the SO
#: import refuses a file whose orders it cannot classify - and these two debtor codes carry
#: no market segment and no agent, so nothing else here could answer for them.
#:
#: DEALER on every row, including the ones labelled with a project's name. `PROJECT/CUSTOMER`
#: is the buyer's NAME and has never decided a class; before the column existed these orders
#: imported with no class at all, and `scm.committed_v` counted them exactly as it counts
#: retail. Stating `DEALER` keeps that arithmetic and stating `PROJECT` would not - a
#: project-class order is not book demand since P3, so every committed-demand assertion in
#: these files would go to zero for a reason that has nothing to do with what they test.
#: The project/retail split has its own file, `test_outstanding_import_demand_class.py`.
_DEFAULT_ORDER_TYPE = "DEALER"


#: The column name and the value a fixture states to satisfy QP1, exported so the files
#: that build their OWN header sets say it the same way this one does rather than each
#: spelling the alias by hand.
ORDER_TYPE_HEADER = "ORDER TYPE"
DEALER_ORDER_TYPE = _DEFAULT_ORDER_TYPE


def so_headers(*columns) -> tuple:
    """A local SO header set, plus the ORDER TYPE column QP1 makes mandatory."""
    return tuple(columns) + (ORDER_TYPE_HEADER,)


def so_row(*values) -> tuple:
    """A local SO row, plus the class its file has to state. See `_DEFAULT_ORDER_TYPE`."""
    return tuple(values) + (DEALER_ORDER_TYPE,)


def _row(label, doc, so_date, debtor, item, qty, when, location, remark=None,
         order_type=_DEFAULT_ORDER_TYPE):
    return (label, doc, so_date, debtor, item, "PCS", qty, when, location, order_type,
            remark)


def week1(codes: Codes) -> bytes:
    """The first upload: five outstanding lines across two orders."""
    c = codes
    p, d = date(2026, 5, 4), date(2026, 5, 18)
    return workbook([
        _row(PROJECT_LABEL, c.project_so, p, "300-T012", c.item_rl, 135,
             date(2026, 7, 1), c.loc_project),
        _row(PROJECT_LABEL, c.project_so, p, "300-T012", c.item_rl, 72,
             date(2026, 8, 3), c.loc_project, "2nd phase"),
        _row(PROJECT_LABEL, c.project_so, p, "300-T012", c.item_wt, 60,
             date(2026, 9, 30), c.loc_project),
        _row(DEALER_LABEL, c.dealer_so, d, "300-A031", c.item_wt, 7,
             date(2026, 10, 30), c.loc_dealer, "dealer"),
        _row(DEALER_LABEL, c.dealer_so, d, "300-A031", c.item_blue, 7646,
             date(2026, 11, 15), c.loc_bulk),
    ])


def week2(codes: Codes) -> bytes:
    """A week later: one date slipped, one quantity grew, one line delivered, one new."""
    c = codes
    p, d = date(2026, 5, 4), date(2026, 5, 18)
    return workbook([
        _row(PROJECT_LABEL, c.project_so, p, "300-T012", c.item_rl, 135,
             date(2026, 7, 15), c.loc_project, "slipped"),
        _row(PROJECT_LABEL, c.project_so, p, "300-T012", c.item_rl, 90,
             date(2026, 8, 3), c.loc_project, "increased"),
        _row(PROJECT_LABEL, c.project_so, p, "300-T012", c.item_new, 12,
             date(2026, 9, 1), c.loc_project, "new"),
        _row(DEALER_LABEL, c.dealer_so, d, "300-A031", c.item_wt, 7,
             date(2026, 10, 30), c.loc_dealer, "dealer"),
        _row(DEALER_LABEL, c.dealer_so, d, "300-A031", c.item_blue, 7646,
             date(2026, 11, 15), c.loc_bulk),
    ])


# --------------------------------------------------------------------------- #
# the purchase-order book
# --------------------------------------------------------------------------- #

def po_workbook(rows, headers=PO_HEADERS) -> bytes:
    return workbook(rows, headers=headers, title="Outstanding PO")


def _po_row(supplier, doc, po_date, creditor, item, ordered, received, eta, location,
            unit_cost=None, currency=None, remark=None):
    return (supplier, doc, po_date, creditor, item, "PCS", ordered, received, eta,
            location, unit_cost, currency, remark)


# Public name for the same builder. `PO_MINIMAL` below cannot express a PO DATE, a received
# quantity or the money columns, and a defect test about exactly those columns must not
# hand-roll a second row shape that could drift from `PO_HEADERS`.
po_row = _po_row

# The shortest header set the `outstanding_po` aliases fully resolve: enough to place a line
# on the plan (document, item, quantity, arrival date, location) plus the counterparty.
# One-off files that assert diff or write semantics use this so the row reads at a glance.
PO_MINIMAL = ("PO NO", "CREDITOR CODE", "ITEM CODE", "QTY ORDERED", "ETA", "STOCK LOCATION")


def po_minimal_row(doc, creditor, item, ordered, eta, location):
    return (doc, creditor, item, ordered, eta, location)


def po_week1(codes: Codes) -> bytes:
    """The first upload: five outstanding lines across two purchase orders."""
    c = codes
    m, a = date(2026, 4, 6), date(2026, 4, 20)
    return po_workbook([
        # 150 ordered against 15 already received: 135 still to arrive.
        _po_row(SUPPLIER_MAIN_LABEL, c.main_po, m, c.creditor_main, c.item_rl, 150, 15,
                date(2026, 7, 1), c.loc_project, 12.5, "MYR"),
        _po_row(SUPPLIER_MAIN_LABEL, c.main_po, m, c.creditor_main, c.item_rl, 72, 0,
                date(2026, 8, 3), c.loc_project, 12.5, "MYR", "2nd container"),
        # No unit cost and no currency: the columns exist, this row leaves them empty.
        _po_row(SUPPLIER_MAIN_LABEL, c.main_po, m, c.creditor_main, c.item_wt, 60, 0,
                date(2026, 9, 30), c.loc_project),
        _po_row(SUPPLIER_ALT_LABEL, c.alt_po, a, c.creditor_alt, c.item_wt, 7, 0,
                date(2026, 10, 30), c.loc_dealer, 3.0, "USD", "spares"),
        _po_row(SUPPLIER_ALT_LABEL, c.alt_po, a, c.creditor_alt, c.item_blue, 7646, 0,
                date(2026, 11, 15), c.loc_bulk, 0.85, "USD"),
    ])


def po_week2(codes: Codes) -> bytes:
    """A week later: one ETA slipped, one quantity grew, one line arrived, one new."""
    c = codes
    m, a = date(2026, 4, 6), date(2026, 4, 20)
    return po_workbook([
        _po_row(SUPPLIER_MAIN_LABEL, c.main_po, m, c.creditor_main, c.item_rl, 150, 15,
                date(2026, 7, 15), c.loc_project, 12.5, "MYR", "vessel delayed"),
        _po_row(SUPPLIER_MAIN_LABEL, c.main_po, m, c.creditor_main, c.item_rl, 90, 0,
                date(2026, 8, 3), c.loc_project, 12.5, "MYR", "increased"),
        _po_row(SUPPLIER_MAIN_LABEL, c.main_po, m, c.creditor_main, c.item_new, 12, 0,
                date(2026, 9, 1), c.loc_project, 4.25, "MYR", "new"),
        _po_row(SUPPLIER_ALT_LABEL, c.alt_po, a, c.creditor_alt, c.item_wt, 7, 0,
                date(2026, 10, 30), c.loc_dealer, 3.0, "USD", "spares"),
        _po_row(SUPPLIER_ALT_LABEL, c.alt_po, a, c.creditor_alt, c.item_blue, 7646, 0,
                date(2026, 11, 15), c.loc_bulk, 0.85, "USD"),
    ])
