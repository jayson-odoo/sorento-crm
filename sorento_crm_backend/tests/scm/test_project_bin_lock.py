"""G12's own count (S6, AC-6.11): open project-bin PO/SPO lines nobody has claimed at
all - what the PO/SPO upload result surfaces and what the PO view's own filter finds, so
Joey has a number to chase to zero backfilling `FromSODocList` in AutoCount.

`PLAN-scm-reorder-oi-feedback-1sep.md` S6, `scm-reorder-oi-feedback-1sep-acceptance-
criteria.md` AC-6.11. `count_unclaimed_project_bin_lines` / `has_unclaimed_project_bin_line`
(`app/services/scm/project_bin_lock.py`) and their `PurchaseOrderService.list(
unclaimed_project_bin=...)` wiring are exercised directly here - the two-line pass-through
in `outstanding_import_service.apply` / `po_history_service.apply` that surfaces the count
on the upload result calls this same function and is not separately re-exercised: doing so
would mean running the full import pipeline against the shared local database's real
80,000-line book, where a company-wide count is not an assertable number.

`blank_session`, not `pg_session`: `count_unclaimed_project_bin_lines` sums COMPANY-WIDE
with no marker to filter by, so a test against the real book could not assert an exact
figure.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.models.inventory import Warehouse
from app.models.procurement import (
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm.project_bin_lock import count_unclaimed_project_bin_lines
from app.services.scm.purchase_order_service import PurchaseOrderService

from .._pg_fixture import blank_session

MARKER = "ZZT-PBL"


def _uid() -> str:
    return str(uuid.uuid4())


class _World:
    def __init__(self, db):
        self.db = db
        self.company_id = db.execute(
            text("select id from companies where code = 'SRT'")
        ).scalar()
        cat = ProductCategory(
            id=_uid(), category_code=f"{MARKER}-CAT", category_name=f"{MARKER} cat",
        )
        uom = UnitOfMeasure(id=_uid(), uom_code=f"{MARKER}-U", uom_name=f"{MARKER} uom")
        db.add_all([cat, uom])
        db.flush()
        self.product = Product(
            id=_uid(), company_id=self.company_id, product_code=f"{MARKER}-7405",
            product_name=f"{MARKER} product", category_id=cat.id, base_uom_id=uom.id,
            list_price=0, is_active=True, is_discontinued=False,
        )
        self.supplier = Supplier(
            id=_uid(), company_id=self.company_id, supplier_code=f"{MARKER}-SUP",
            supplier_name=f"{MARKER} supplier", is_active=True,
        )
        # A project-BIN warehouse (G12's own lock) and an ordinary POOL one, so the
        # count and the filter can be shown to tell the two apart.
        self.bin_wh = Warehouse(
            id=_uid(), company_id=self.company_id, warehouse_code=f"{MARKER}-BIN",
            warehouse_name=f"{MARKER} bin", is_active=True, segment="project",
        )
        self.pool_wh = Warehouse(
            id=_uid(), company_id=self.company_id, warehouse_code=f"{MARKER}-POOL",
            warehouse_name=f"{MARKER} pool", is_active=True,
        )
        db.add_all([self.product, self.supplier, self.bin_wh, self.pool_wh])
        db.flush()

    def purchase_order(self, number: str, *, bin_qty=10, pool_qty=10) -> dict:
        """One order with a line at the project bin and one at the pool - the pool line
        is the control, never counted regardless of a claim."""
        po = PurchaseOrder(
            id=_uid(), company_id=self.company_id, po_number=number,
            supplier_id=self.supplier.id, status="active", issue_date=date(2026, 8, 1),
        )
        self.db.add(po)
        self.db.flush()
        bin_line = PurchaseOrderLine(
            id=_uid(), company_id=self.company_id, purchase_order_id=po.id,
            product_id=self.product.id, warehouse_id=self.bin_wh.id,
            qty_ordered=bin_qty, qty_received=0, line_status="open",
        )
        pool_line = PurchaseOrderLine(
            id=_uid(), company_id=self.company_id, purchase_order_id=po.id,
            product_id=self.product.id, warehouse_id=self.pool_wh.id,
            qty_ordered=pool_qty, qty_received=0, line_status="open",
        )
        self.db.add_all([bin_line, pool_line])
        self.db.flush()
        return {"po": po, "bin_line": bin_line, "pool_line": pool_line}

    def spo_allocation(self, number: str, *, qty=10) -> SPOAllocation:
        allocation = SPOAllocation(
            id=_uid(), company_id=self.company_id, spo_number=number, spo_line_number=1,
            product_id=self.product.id, warehouse_id=self.bin_wh.id,
            allocated_quantity=qty, quantity_received=0, quantity_rejected=0,
            receipt_status="pending", line_status="open", synced_to_excel=False,
        )
        self.db.add(allocation)
        self.db.flush()
        return allocation

    def sales_order_line(self, *, qty=10, delivered=0, line_status="open") -> str:
        """A CORE sales-order line for a claim to RESOLVE onto.

        The count is the exact complement of the lock (S4), and the lock reads only claims
        it can join through `so_line_id` - so a claim with no sales line behind it opens
        nothing, and the fixture has to be able to build the resolved case as well as the
        unresolved one.
        """
        so_id, line_id = _uid(), _uid()
        self.db.execute(
            text(
                "INSERT INTO sales_orders (id, company_id, so_number, order_date, status) "
                "VALUES (:i, :c, :n, :d, 'open')"
            ),
            {"i": so_id, "c": self.company_id, "n": f"{MARKER}-SO-{_uid()[:8]}",
             "d": date(2026, 7, 1)},
        )
        self.db.execute(
            text(
                "INSERT INTO sales_order_lines (id, company_id, sales_order_id, "
                "product_id, qty_ordered, qty_delivered, line_status) "
                "VALUES (:i, :c, :so, :p, :q, :qd, :ls)"
            ),
            {"i": line_id, "c": self.company_id, "so": so_id, "p": self.product.id,
             "q": qty, "qd": delivered, "ls": line_status},
        )
        self.db.flush()
        return line_id

    def claim(self, *, po_line_id=None, spo_allocation_id=None, resolved=True,
              so_line_id=None) -> None:
        """One claim on a line. `resolved=True` (the default) gives it a real, OPEN core
        sales-order line, which is what actually opens the line to the automatic pass;
        `resolved=False` leaves both `so_line_id` and `resolved_at` NULL, the state a book
        claim sits in until the sales order is uploaded."""
        if resolved and so_line_id is None:
            so_line_id = self.sales_order_line()
        self.db.execute(
            text(
                "INSERT INTO order_link_claim (id, company_id, so_number, po_number, "
                "item_code, source, po_line_id, spo_allocation_id, so_line_id, "
                "resolved_at) "
                "VALUES (:i, :c, :son, :pon, NULL, 'po_history', :pol, :spo, :sol, "
                ":resolved_at)"
            ),
            {
                "i": _uid(),
                "c": self.company_id,
                "son": f"{MARKER}-SO",
                "pon": f"{MARKER}-PO",
                "pol": po_line_id,
                "spo": spo_allocation_id,
                "sol": so_line_id if resolved else None,
                "resolved_at": date(2026, 8, 15) if resolved else None,
            },
        )
        self.db.flush()


@pytest.fixture()
def world():
    with blank_session() as db:
        built = _World(db)
        with company_scope(db, frozenset({built.company_id})):
            yield built


# ------------------------------------------------------------------- the count


def test_only_the_open_unclaimed_project_bin_line_is_counted(world):
    """AC-6.11: an open PO line at a project-bin warehouse, unclaimed, is counted; the
    same order's POOL line never is, whatever its claim state."""
    world.purchase_order(f"{MARKER}-PO-1")

    assert count_unclaimed_project_bin_lines(world.db, world.company_id) == 1


def test_a_claim_on_the_line_removes_it_from_the_count(world):
    made = world.purchase_order(f"{MARKER}-PO-2")
    world.claim(po_line_id=made["bin_line"].id)

    assert count_unclaimed_project_bin_lines(world.db, world.company_id) == 0


def test_an_unresolved_claim_leaves_the_line_counted(world):
    """The count is the exact COMPLEMENT of the lock (S4, review of PR #490).

    It used to treat any claim row as "claimed", including one whose sales order has not
    been uploaded - but the lock opens a line only for a claim it can join through
    `so_line_id`, so those lines stayed refused to the automatic pass. Joey chased the
    number to zero in AutoCount and nothing unlocked. A line whose only claim is
    unresolved is still work to do, so it is still counted.
    """
    made = world.purchase_order(f"{MARKER}-PO-3")
    world.claim(po_line_id=made["bin_line"].id, resolved=False)

    assert count_unclaimed_project_bin_lines(world.db, world.company_id) == 1


def test_a_settled_sales_order_leaves_the_line_counted(world):
    """Same rule from the other side: a claim whose sales-order line has been delivered
    reserves nothing and dedicates nothing (G7), so it opens nothing - and a line whose
    only claim is settled is unattributed again, not attributed for ever."""
    made = world.purchase_order(f"{MARKER}-PO-3B")
    settled = world.sales_order_line(qty=10, delivered=10)
    world.claim(po_line_id=made["bin_line"].id, so_line_id=settled)

    assert count_unclaimed_project_bin_lines(world.db, world.company_id) == 1


def test_an_unclaimed_spo_allocation_at_a_project_bin_is_counted_too(world):
    """G12's lock covers the SPO family exactly as it covers PO lines - the count sums
    both."""
    allocation = world.spo_allocation(f"{MARKER}-SPO-1")

    assert count_unclaimed_project_bin_lines(world.db, world.company_id) == 1

    world.claim(spo_allocation_id=allocation.id)
    assert count_unclaimed_project_bin_lines(world.db, world.company_id) == 0


def test_a_closed_line_is_never_counted(world):
    """A line no longer open carries no lock to clear - counting it would send Joey
    chasing a line that is not actionable any more."""
    made = world.purchase_order(f"{MARKER}-PO-4")
    made["bin_line"].line_status = "closed"
    world.db.flush()

    assert count_unclaimed_project_bin_lines(world.db, world.company_id) == 0


# --------------------------------------------------------------- the PO-view filter


def test_the_unclaimed_project_bin_filter_round_trips_on_the_purchase_order_list(world):
    """AC-6.11: `unclaimed_project_bin=True` finds the order while its bin line is
    unclaimed; `False` excludes it; once claimed, the order moves from one set to the
    other."""
    made = world.purchase_order(f"{MARKER}-PO-5")
    svc = PurchaseOrderService(world.db)

    unclaimed = svc.list(
        page=1, limit=50, sort="po_number", direction="asc", query=made["po"].po_number,
        status=None, supplier=None, unclaimed_project_bin=True,
    )
    assert {row["po_number"] for row in unclaimed["data"]} == {made["po"].po_number}

    claimed = svc.list(
        page=1, limit=50, sort="po_number", direction="asc", query=made["po"].po_number,
        status=None, supplier=None, unclaimed_project_bin=False,
    )
    assert claimed["data"] == []

    world.claim(po_line_id=made["bin_line"].id)

    unclaimed_after = svc.list(
        page=1, limit=50, sort="po_number", direction="asc", query=made["po"].po_number,
        status=None, supplier=None, unclaimed_project_bin=True,
    )
    assert unclaimed_after["data"] == []

    claimed_after = svc.list(
        page=1, limit=50, sort="po_number", direction="asc", query=made["po"].po_number,
        status=None, supplier=None, unclaimed_project_bin=False,
    )
    assert {row["po_number"] for row in claimed_after["data"]} == {made["po"].po_number}


def test_the_filter_is_silent_when_omitted(world):
    """Omitted narrows nothing - the ordinary case, and the one every OTHER PO-list
    caller relies on."""
    made = world.purchase_order(f"{MARKER}-PO-6")
    svc = PurchaseOrderService(world.db)

    out = svc.list(
        page=1, limit=50, sort="po_number", direction="asc", query=made["po"].po_number,
        status=None, supplier=None,
    )
    assert {row["po_number"] for row in out["data"]} == {made["po"].po_number}
