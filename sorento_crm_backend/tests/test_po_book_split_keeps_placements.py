"""AC-G3 - the buyer re-keys the split in AutoCount and re-uploads the book.

`PLAN-scm-cs-planning-uat.md` section 3.G. The captain, 25 August 2026: the occupancy panel
must live BESIDE the purchase-order line, "not in it: the user re-keys the split in AutoCount
and re-uploads, and an upload overwriting our split would lose it".

The scenario is PO-2026/07-0029's own. It carries one line, DC1 500, and three placements
want the goods elsewhere: 6 and 7 at BRW, 487 at BRW-BB. The buyer acts on that finding,
splits the line in AutoCount into BRW-BB 487 + BRW 13, and uploads the book again. AC-G3:
"keeps every placement attached to the line whose warehouse matches; none is orphaned or
unplaced."

TWO HALVES, both here.

* **the matcher** - `po_history_service` keyed lines by the document's line NUMBER alone,
  and the structured extract has no line number of its own, so identity there is POSITIONAL.
  Inserting one line at the top of a document therefore shifts every ordinal below it and the
  re-upload rewrites the wrong rows. Matching on `(product_id, warehouse_id)` FIRST and the
  ordinal only afterwards is what makes a split re-import land on the right lines.
* **the placements** - a matcher can rewrite a line, but it cannot MOVE a placement from one
  line to another, and that is what the AC asks for. `relink_to_matching_lines` is that step,
  run after either book channel writes.

`blank_session`: these assertions name exactly which lines a document has, and the shared
local database holds the captain's real 80,000-line book.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.scm import po_history_service
from app.services.scm.po_listing_reader import (
    LAYOUT_STRUCTURED,
    PoListingLine,
    PoListingOrder,
    PoListingResult,
)
from app.services.scm.purchase_order_service import PurchaseOrderService

from ._pg_fixture import blank_session

MARKER = "ZZT-SPLIT"
P = "projects"


def _uid() -> str:
    return str(uuid.uuid4())


def _projects(db) -> str:
    current = db.execute(text("select current_schema()")).scalar()
    return "projects" if current in (None, "public") else f'"{current}_projects"'


class _World:
    """One purchase order at DC1, occupied by three placements that want it elsewhere."""

    NUMBER = "PO-2026/07-0029"

    def __init__(self, db):
        self.db = db
        self.company_id = db.execute(
            text("select id from companies where code = 'SRT'")
        ).scalar()
        self.warehouses: dict[str, str] = {}
        self._inquiries = 0
        self.po_svc = PurchaseOrderService(db)
        self.oi_svc = ProjectOrderInquiryService(db)
        self._build()

    def _build(self) -> None:
        db = self.db
        cat, uom = _uid(), _uid()
        db.execute(
            text(
                "INSERT INTO product_categories (id, category_code, category_name) "
                "VALUES (:i, :c, :c)"
            ),
            {"i": cat, "c": f"{MARKER}-CAT"},
        )
        db.execute(
            text("INSERT INTO units_of_measure (id, uom_code, uom_name) VALUES (:i, :c, :c)"),
            {"i": uom, "c": f"{MARKER}-UOM"},
        )
        self.product_code = f"{MARKER}-WESERP10B"
        self.product = _uid()
        db.execute(
            text(
                "INSERT INTO products (id, company_id, product_code, product_name, "
                "category_id, base_uom_id, list_price) "
                "VALUES (:i, :c, :code, :code, :cat, :uom, 0)"
            ),
            {
                "i": self.product,
                "c": self.company_id,
                "code": self.product_code,
                "cat": cat,
                "uom": uom,
            },
        )
        pool = _uid()
        db.execute(
            text(
                "INSERT INTO warehouses (id, company_id, warehouse_code, warehouse_name, "
                "is_active) VALUES (:i, :c, 'BRW', 'BRW', true)"
            ),
            {"i": pool, "c": self.company_id},
        )
        self.warehouses["BRW"] = pool
        for code in ("BRW-BB", "DC1"):
            wid = _uid()
            db.execute(
                text(
                    "INSERT INTO warehouses (id, company_id, warehouse_code, "
                    "warehouse_name, is_active, pool_warehouse_id) "
                    "VALUES (:i, :c, :code, :code, true, :p)"
                ),
                {"i": wid, "c": self.company_id, "code": code, "p": pool},
            )
            self.warehouses[code] = wid
        self.supplier_code = f"{MARKER}-SUP"
        self.supplier = _uid()
        db.execute(
            text(
                "INSERT INTO suppliers (id, company_id, supplier_code, supplier_name, "
                "is_active) VALUES (:i, :c, :code, :code, true)"
            ),
            {"i": self.supplier, "c": self.company_id, "code": self.supplier_code},
        )
        db.flush()

    # -- the book --------------------------------------------------------------

    def purchase_order(self, lines) -> tuple[str, list[str]]:
        """`lines` is (location, ordered, line_no). Written as the book writes them."""
        po = _uid()
        self.db.execute(
            text(
                "INSERT INTO purchase_orders (id, company_id, po_number, supplier_id, "
                "status, issue_date, source_system, source_ref) "
                "VALUES (:i, :c, :n, :s, 'active', :d, 'scm_po_history', 'structured')"
            ),
            {
                "i": po,
                "c": self.company_id,
                "n": self.NUMBER,
                "s": self.supplier,
                "d": date(2026, 7, 5),
            },
        )
        ids = []
        for location, ordered, line_no in lines:
            lid = _uid()
            self.db.execute(
                text(
                    "INSERT INTO purchase_order_lines (id, company_id, "
                    "purchase_order_id, product_id, warehouse_id, qty_ordered, "
                    "qty_received, line_status, expected_date, source_ref, source_system) "
                    "VALUES (:i, :c, :po, :p, :w, :q, 0, 'open', :e, :r, 'scm_po_history')"
                ),
                {
                    "i": lid,
                    "c": self.company_id,
                    "po": po,
                    "p": self.product,
                    "w": self.warehouses[location],
                    "q": ordered,
                    "e": date(2026, 8, 4),
                    "r": str(line_no),
                },
            )
            ids.append(lid)
        self.db.flush()
        return po, ids

    def placement(self, so_number: str, qty, *, on: str, wants: str) -> str:
        """One order inquiry row wanting `qty` at `wants`, linked to PO line `on`."""
        core = _uid()
        self.db.execute(
            text(
                "INSERT INTO sales_orders (id, company_id, so_number, status, order_date, "
                "demand_class) VALUES (:i, :c, :n, 'open', :d, 'project')"
            ),
            {"i": core, "c": self.company_id, "n": so_number, "d": date(2025, 12, 10)},
        )
        pso = _uid()
        self.db.execute(
            text(
                "INSERT INTO " + P + ".sales_orders (id, company_id, provisional_ref, "
                "autocount_doc_no, so_id, status, created_at, updated_at) "
                "VALUES (:i, :c, :ref, :ref, :so, 'adopted', now(), now())"
            ),
            {"i": pso, "c": self.company_id, "ref": so_number, "so": core},
        )
        self._inquiries += 1
        inquiry = _uid()
        self.db.execute(
            text(
                "INSERT INTO " + P + ".order_inquiries (id, company_id, inquiry_no, "
                "project_sales_order_id, state, raised_at) "
                "VALUES (:i, :c, :no, :p, 'raised', now())"
            ),
            {
                "i": inquiry,
                "c": self.company_id,
                "no": f"OI-{self._inquiries:06d}",
                "p": pso,
            },
        )
        row = _uid()
        self.db.execute(
            text(
                "INSERT INTO " + P + ".order_inquiry_rows (id, company_id, "
                "order_inquiry_id, item_code, qty, verb, stock_location, state, "
                "redirected_to_pool, created_at) "
                "VALUES (:i, :c, :inq, :code, :q, 'ORDER', :loc, 'placed', false, now())"
            ),
            {
                "i": row,
                "c": self.company_id,
                "inq": inquiry,
                "code": self.product_code,
                "q": Decimal(str(qty)),
                "loc": wants,
            },
        )
        self.db.execute(
            text(
                "INSERT INTO " + P + ".order_inquiry_links (id, company_id, row_id, "
                "po_line_id, document, qty, auto, linked_at, created_at) "
                "VALUES (:i, :c, :r, :l, :d, :q, true, now(), now())"
            ),
            {
                "i": _uid(),
                "c": self.company_id,
                "r": row,
                "l": on,
                "d": self.NUMBER,
                "q": Decimal(str(qty)),
            },
        )
        self.db.flush()
        return row

    # -- what the re-uploaded book says ----------------------------------------

    def book(self, lines) -> PoListingResult:
        """The parsed extract, as `po_history_service` would receive it.

        Built rather than generated from bytes: the structured reader resolves its 27 headers
        through `import_field_alias`, which is seeded by a MIGRATION and therefore absent
        from a `create_all` scratch schema. The write path is what AC-G3 is about, and this
        is its input type.
        """
        order = PoListingOrder(
            po_number=self.NUMBER,
            order_date=date(2026, 7, 5),
            supplier_code=self.supplier_code,
            supplier_name=self.supplier_code,
            currency="",
            total=None,
            local_total=None,
            source_row=2,
        )
        for index, (location, qty) in enumerate(lines, start=1):
            order.lines.append(
                PoListingLine(
                    line_no=index,
                    item_code=self.product_code,
                    description=self.product_code,
                    uom="",
                    qty_ordered=qty,
                    unit_price=None,
                    amount=None,
                    local_amount=None,
                    is_stock_item=True,
                    source_row=index + 2,
                    location=location,
                    expected_date=date(2026, 8, 4),
                )
            )
        result = PoListingResult(layout=LAYOUT_STRUCTURED)
        result.orders.append(order)
        result.total_rows = len(lines) + 1
        return result

    def lines_of(self, po_id: str):
        """(location, ordered, line id) for the order, in insertion order."""
        return [
            (row[0], float(row[1]), str(row[2]))
            for row in self.db.execute(
                text(
                    "SELECT w.warehouse_code, l.qty_ordered, l.id FROM purchase_order_lines l "
                    "LEFT JOIN warehouses w ON w.id = l.warehouse_id "
                    "WHERE l.purchase_order_id = :po ORDER BY l.created_at, l.id"
                ),
                {"po": po_id},
            )
        ]


@pytest.fixture()
def world():
    global P
    with blank_session() as db:
        P = _projects(db)
        built = _World(db)
        with company_scope(db, frozenset({built.company_id})):
            yield built


@pytest.fixture()
def split(world, monkeypatch):
    """The re-upload, applied. Answers the world plus the ids before and after."""
    po, (dc1,) = world.purchase_order([("DC1", 500, 1)])
    world.placement("SO416191", 6, on=dc1, wants="BRW")
    world.placement("SO416191-B", 7, on=dc1, wants="BRW")
    world.placement("SO324132", 487, on=dc1, wants="BRW-BB")

    book = world.book([("BRW-BB", 487), ("BRW", 13)])
    monkeypatch.setattr(po_history_service, "_parse", lambda db, data: book)
    # The upload itself relinks - the tests below assert what a BUYER gets from
    # re-uploading the book, not what a helper does when a test calls it by hand.
    po_history_service.apply(world.db, b"")
    world.db.flush()
    return {"po": po, "dc1": dc1}


# ------------------------------------------------------------------- the matcher


def test_a_split_re_upload_writes_one_line_per_location_and_does_not_double_the_order(
    world, split
):
    """The document now states two lines, so the order holds two, not three.

    Matching on `(product_id, warehouse_id)` first is what makes a second identical upload
    idempotent under a POSITIONAL identity: the structured extract carries no line number of
    its own, so an inserted line shifts every ordinal below it.
    """
    held = {(location, qty) for location, qty, _id in world.lines_of(split["po"])}
    assert held == {("BRW-BB", 487.0), ("BRW", 13.0)}


def test_re_uploading_the_same_split_book_again_changes_nothing(world, split, monkeypatch):
    """Idempotency, which is the property the ordinal alone cannot hold."""
    before = world.lines_of(split["po"])

    book = world.book([("BRW-BB", 487), ("BRW", 13)])
    monkeypatch.setattr(po_history_service, "_parse", lambda db, data: book)
    po_history_service.apply(world.db, b"")
    world.db.flush()

    assert world.lines_of(split["po"]) == before


def test_a_reordered_book_lands_on_the_same_lines_it_did_before(world, split, monkeypatch):
    """The ordinals swap and nothing moves: (product, location) is the identity.

    Under the ordinal alone this upload rewrites BRW-BB's line to hold BRW's quantity and
    vice versa, silently swapping 487 and 13 between two locations.
    """
    before = {location: line_id for location, _qty, line_id in world.lines_of(split["po"])}

    book = world.book([("BRW", 13), ("BRW-BB", 487)])
    monkeypatch.setattr(po_history_service, "_parse", lambda db, data: book)
    po_history_service.apply(world.db, b"")
    world.db.flush()

    after = {location: line_id for location, _qty, line_id in world.lines_of(split["po"])}
    assert after == before


# ---------------------------------------------------------------- the placements


def test_every_placement_lands_on_the_line_whose_warehouse_matches(world, split):
    """AC-G3, the whole of it: 487 onto the BRW-BB line, 6 and 7 onto the BRW line."""
    blocks = {
        block["warehouse_code"]: block
        for block in world.po_svc.get_one(split["po"])["allocations"]
    }
    assert sorted(p["qty"] for p in blocks["BRW-BB"]["placements"]) == [487]
    assert sorted(p["qty"] for p in blocks["BRW"]["placements"]) == [6, 7]


def test_no_placement_is_orphaned_or_left_marked_as_a_location_mismatch(world, split):
    """"None is orphaned or unplaced": the same three placements, all of them now on a line
    that states the location their demand asked for."""
    blocks = world.po_svc.get_one(split["po"])["allocations"]
    placements = [p for block in blocks for p in block["placements"]]
    assert sorted(p["qty"] for p in placements) == [6, 7, 487]
    assert not any(p["location_differs"] for p in placements)


def test_the_rows_stay_linked_rather_than_falling_back_to_the_board(world, split):
    """A move is not an unlink. A row that dropped back to `raised` would be re-cascaded by
    the next auto-link pass and could land on somebody else's supply."""
    states = [
        row[0]
        for row in world.db.execute(
            text("SELECT state FROM " + P + ".order_inquiry_rows ORDER BY created_at")
        )
    ]
    assert states == ["placed", "placed", "placed"]


def test_a_placement_already_on_a_matching_line_is_left_exactly_where_it_is(world):
    """The move only ever runs toward a better fit. A book upload that changed nothing this
    row cares about must not rewrite its link, or every upload would churn the audit."""
    po, (brw_bb,) = world.purchase_order([("BRW-BB", 100, 1)])
    row = world.placement("SO400000", 40, on=brw_bb, wants="BRW-BB")
    before = world.db.execute(
        text("SELECT po_line_id, linked_at FROM " + P + ".order_inquiry_links "
             "WHERE row_id = :r"),
        {"r": row},
    ).one()

    moved = world.oi_svc.relink_to_matching_lines(
        [po], actor_user_id=None, trigger="po_book_upload"
    )

    after = world.db.execute(
        text("SELECT po_line_id, linked_at FROM " + P + ".order_inquiry_links "
             "WHERE row_id = :r"),
        {"r": row},
    ).one()
    assert moved == 0
    assert after == before


def test_a_placement_with_nowhere_better_to_go_stays_put_rather_than_being_dropped(world):
    """The book no longer carries the demand's location at all. Leaving the placement where
    it is keeps the quantity recorded against the document, which is honest; dropping it
    would put the row back on the board claiming nothing has been bought for it."""
    po, (dc1,) = world.purchase_order([("DC1", 100, 1)])
    row = world.placement("SO400001", 40, on=dc1, wants="BRW-BB")

    moved = world.oi_svc.relink_to_matching_lines(
        [po], actor_user_id=None, trigger="po_book_upload"
    )

    held = world.db.execute(
        text("SELECT po_line_id::text FROM " + P + ".order_inquiry_links "
             "WHERE row_id = :r"),
        {"r": row},
    ).scalar()
    assert moved == 0
    assert held == dc1
