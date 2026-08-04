"""The outstanding-SO upload fixtures for the tests that WRITE to the database.

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
           "QTY", "DELIVERY DATE", "STOCK LOCATION", "REMARK")

PROJECT_LABEL = "TUJU RESIDENCE"
DEALER_LABEL = "ARIA VERDE"


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
    )


def require_aliases(db) -> None:
    if not db.execute(text("SELECT 1 FROM import_field_alias "
                           "WHERE doc_type = 'outstanding_so' LIMIT 1")).scalar():
        pytest.skip("no outstanding_so aliases seeded in this database")


def seed_catalogue(db, codes: Codes) -> None:
    """Every product and warehouse the generated files name, and nothing else.

    No "insert only if absent" guard and no borrowed category or uom: the codes are unique to
    this test, so the insert is unconditional and the rows are unambiguously ours.
    """
    from app.models.inventory import Warehouse
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    require_aliases(db)

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


def workbook(rows, headers=HEADERS) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Outstanding SO"
    ws.append(list(headers))
    for row in rows:
        ws.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row(label, doc, so_date, debtor, item, qty, when, location, remark=None):
    return (label, doc, so_date, debtor, item, "PCS", qty, when, location, remark)


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
