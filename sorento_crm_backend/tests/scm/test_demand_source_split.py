"""Project demand comes from the Order Inquiry; retail demand from the outstanding book.

> "the order inquiry is the demand because the SO is processed by the customer service
>  team ... they will come up with order inquiry, which are the things that they think the
>  company should buy ... order inquiry is only for project side. So for dealer side is
>  exactly based on the sales order."

The engine sits in purchasing's chair. CS turns project sales orders into an Order Inquiry,
so a project SO CS has not decided on is CS saying "not yet" - it is NOT demand, and it is
SET ASIDE AND COUNTED (user decision 2026-08-10, widened by P3 on 26 Aug 2026) rather than
silently dropped. Retail carries no such filter: the outstanding book is the demand.

P3 made "the inquiry named it" mean the inquiry's own RAISED ROW rather than the
`demand_origin` stamp. The old sheet leg counted an order the legacy feed created even
while nobody had decided it on the fulfilment board, which is how M310-CR-PJ showed 16
units of Project demand with every one of its inquiry rows already placed. So a
sheet-origin order is now set aside exactly like any other undecided project order, and the
stamp survives only as provenance.

## Why origin is its own column

Adoption is the trap. When CS's outstanding extract later names an inquiry-created order it
takes ownership and OVERWRITES `source_system` to `scm_upload` - by design, so the sheet's
next upload cannot revert a quantity CS corrected. If OI-origin were read off
`source_system`, the act of CS adopting an order would silently delete its demand from the
next run. `demand_origin` is stamped at creation and never rewritten, so ownership can move
while origin stays.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

MARKER = "ZZTDSP"


def _committed(db, product_id: str) -> float:
    v = db.execute(
        text("SELECT COALESCE(SUM(committed), 0) FROM scm.committed_v WHERE product_id = :p"),
        {"p": product_id},
    ).scalar()
    return float(v or 0)


# --------------------------------------------------------------------------- #
# what counts as demand
# --------------------------------------------------------------------------- #

def test_a_sheet_origin_project_order_is_not_demand_either(world):
    """P3: the origin stamp is provenance, not a decision. Only a raised Order Inquiry row
    makes project demand, and this order has none."""
    db = world["db"]
    world["order"]("SO-OI", demand_class="project", demand_origin="scm_order_inquiry", qty=40)

    assert _committed(db, world["product"].id) == 0


def test_a_project_order_no_inquiry_named_is_not_demand(world):
    """CS filtered it out. The engine respects that instead of second-guessing it."""
    db = world["db"]
    world["order"]("SO-RAW", demand_class="project", demand_origin=None, qty=40)

    assert _committed(db, world["product"].id) == 0


def test_a_retail_order_is_demand_straight_from_the_book(world):
    db = world["db"]
    world["order"]("SO-RTL", demand_class="retail", demand_origin=None, qty=25)

    assert _committed(db, world["product"].id) == 25


def test_an_order_with_no_class_counts_as_retail_rather_than_vanishing(world):
    """demand_class NULL means "nobody said", and it reads as retail (P4) - the book-direct
    channel. Making it silently non-demand would punish the same gap twice, the second time
    invisibly; giving it a column of its own gave the plan a figure nobody could act on."""
    db = world["db"]
    world["order"]("SO-NULL", demand_class=None, demand_origin=None, qty=7)

    assert _committed(db, world["product"].id) == 7


def test_adoption_moves_ownership_without_deleting_the_demand(world):
    """The CS book adopts an inquiry order: `source_system` flips to scm_upload, and the
    demand MUST survive, because origin is its own column.

    Read on a RETAIL order since P3 - a project one contributes nothing either way now, so
    it could no longer tell the adoption bug apart from the split working."""
    db = world["db"]
    so = world["order"]("SO-ADOPT", demand_class="retail",
                        demand_origin="scm_order_inquiry", qty=40)
    before = _committed(db, world["product"].id)

    # what the outstanding importer's adoption block does
    db.execute(text(
        "UPDATE sales_orders SET source_system = 'scm_upload', source_ref = 'sales_order' "
        "WHERE id = :id"), {"id": so})
    db.flush()

    assert before == 40
    assert _committed(db, world["product"].id) == 40


# --------------------------------------------------------------------------- #
# the set-aside report
# --------------------------------------------------------------------------- #

def test_set_aside_project_demand_is_counted_and_named(world):
    from app.services.scm.demand_source_service import set_aside_project_demand

    db = world["db"]
    world["order"]("SO-RAW1", demand_class="project", demand_origin=None, qty=40)
    world["order"]("SO-RAW2", demand_class="project", demand_origin=None, qty=2)
    world["order"]("SO-OI1", demand_class="project", demand_origin="scm_order_inquiry", qty=9)

    report = set_aside_project_demand(db, product_ids=[str(world["product"].id)])

    # All three, since P3: the sheet-origin order is awaiting CS exactly like the two the
    # inquiry never named. Before, it was netted and this report said 2 / 42.
    assert report["orders"] == 3
    assert report["quantity"] == 51
    numbers = {s["so_number"] for s in report["sample"]}
    assert {f"{MARKER}-SO-RAW1", f"{MARKER}-SO-RAW2", f"{MARKER}-SO-OI1"} <= numbers


def test_a_clean_book_reports_zero_rather_than_failing(world):
    from app.services.scm.demand_source_service import set_aside_project_demand

    report = set_aside_project_demand(world["db"], product_ids=[str(world["product"].id)])

    assert report["orders"] == 0
    assert report["quantity"] == 0
    assert report["sample"] == []


# --------------------------------------------------------------------------- #
# the stamp at the source
# --------------------------------------------------------------------------- #

def test_the_order_inquiry_stamps_its_origin_on_orders_it_creates():
    """The apply path must write demand_origin, not just source_system, or adoption breaks
    the whole split later. Asserted against the service's own instantiation seam."""
    import inspect

    # Project Sales owns the importer now (ADR 0010). SCM still depends on the stamp it
    # writes, which is why this assertion stays on the SCM side of the fence.
    from app.services import project_order_inquiry_import_service

    src = inspect.getsource(project_order_inquiry_import_service)
    assert "demand_origin" in src, (
        "the order-inquiry importer never writes demand_origin; adoption will erase OI origin"
    )


@pytest.fixture()
def world():
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests._pg_fixture import pg_session, unique_code

    def _u() -> str:
        return str(uuid.uuid4())

    with pg_session() as db:
        cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                              category_name=f"{MARKER} cat")
        uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
        db.add_all([cat, uom])
        db.flush()
        product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                          category_id=cat.id, base_uom_id=uom.id, list_price=0,
                          is_active=True, is_discontinued=False)
        db.add(product)
        db.flush()

        wid = _u()
        db.execute(text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
            "counts_as_available) VALUES (:id, :c, :c, true, true)"),
            {"id": wid, "c": unique_code("W")[:20]})

        def order(stub: str, *, demand_class, demand_origin, qty: float) -> str:
            oid = _u()
            db.execute(text(
                "INSERT INTO sales_orders (id, so_number, status, demand_class, "
                "demand_origin, source_system) "
                "VALUES (:id, :n, 'open', :dc, :do, :src)"),
                {"id": oid, "n": f"{MARKER}-{stub}", "dc": demand_class,
                 "do": demand_origin,
                 "src": "scm_order_inquiry" if demand_origin else "scm_upload"})
            db.execute(text(
                "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
                "qty_ordered, qty_delivered, line_status, purchasing_status) "
                "VALUES (:id, :so, :p, :w, :q, 0, 'open', 'uncovered')"),
                {"id": _u(), "so": oid, "p": product.id, "w": wid, "q": qty})
            db.flush()
            return oid

        yield {"db": db, "product": product, "warehouse_id": wid, "order": order}
