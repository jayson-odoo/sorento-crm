"""AC-6.12 (T): G12's OI lock never reaches the reorder engine's own supply read.

`PLAN-scm-reorder-oi-feedback-1sep.md` S6 G12: "Safe against double-buying because the
reorder engine nets open PO qty by location regardless of claims - the unclaimed line
still counts as supply in the plan; only the OI cover state waits for attribution."

Measured against `scm.on_order_v` (`alembic/versions/337_scm_on_order_from_spo.py`, the
current head definition, confirmed live 2 Sep 2026): it sums `spo_allocations` only, joins
neither `scm.order_link_claim` nor a warehouse's `segment` at all, and predates this slice
by nearly a month (6 Aug 2026, "Decision (user, 6 Aug 2026): supply is SPO only"). A PLAIN
purchase-order line was therefore already excluded from engine supply before G12 existed -
that half of the plan's own wording is about a fact that predates it, not a behaviour this
slice changes. The fact THIS slice's G12 claim actually rests on is the SPO half: an SPO
allocation destined for a project-bin warehouse, entirely UNCLAIMED, still nets as on-order
at that location exactly as it would anywhere else, because the view has no way to treat it
differently. `reorder_engine.load_net_position` is exercised directly (rather than
`scm.on_order_v` by raw SQL) because it is what a caller in this codebase actually calls.

`pg_session`, not `blank_session`: `scm.on_order_v` / `scm.net_position_v` are VIEWS created
by Alembic migrations, not tables `Base.metadata.create_all` reproduces, so the scratch
schema built by `blank_session` does not carry them at all. A fresh product id keeps the
real book's own rows out of this test's assertions even though the view has no per-test
isolation of its own.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.inventory import Warehouse
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, SPOAllocation, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm.reorder_engine import load_net_position
from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZTRPBN"
SORENTO = "00000000-0000-0000-0000-000000000001"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        set_company_scope(s, frozenset({SORENTO}))
        yield s


@pytest.fixture()
def world(db):
    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER), category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} uom")
    db.add_all([cat, uom])
    db.flush()
    product = Product(
        id=_u(), company_id=SORENTO, product_code=unique_code(MARKER),
        product_name=f"{MARKER} product", category_id=cat.id, base_uom_id=uom.id,
        list_price=0, is_active=True, is_discontinued=False,
    )
    # `segment = 'project'` (G12's own lock), and no `order_link_claim` will ever be
    # written naming this allocation - the point of the test.
    warehouse = Warehouse(
        id=_u(), company_id=SORENTO, warehouse_code=unique_code("W")[:20],
        warehouse_name=f"{MARKER} bin", is_active=True, segment="project",
    )
    supplier = Supplier(
        id=_u(), company_id=SORENTO, supplier_code=unique_code("S"),
        supplier_name=f"{MARKER} supplier",
    )
    db.add_all([product, warehouse, supplier])
    db.flush()
    return {"product": product, "warehouse": warehouse, "supplier": supplier}


def test_an_unclaimed_project_bin_spo_allocation_still_nets_as_on_order(db, world):
    allocation = SPOAllocation(
        id=_u(), company_id=SORENTO, spo_number=unique_code("SPO"), spo_line_number=1,
        product_id=world["product"].id, warehouse_id=world["warehouse"].id,
        allocated_quantity=25, quantity_received=0, quantity_rejected=0,
        receipt_status="pending", line_status="open", synced_to_excel=False,
    )
    db.add(allocation)
    db.flush()
    # No order_link_claim is written at all.

    net = load_net_position(db, world["product"].id, world["warehouse"].id)

    assert len(net) == 1
    assert Decimal(str(net[0]["on_order"])) == Decimal("25")


def test_a_plain_project_bin_po_line_is_absent_from_the_spo_only_on_order_view(db, world):
    """One half of the measurement: `scm.on_order_v` was SPO-only before this slice
    (migration 337, 6 Aug 2026), so a plain PO line contributes nothing to THAT view with
    or without a claim.

    On its own this says nothing about double-buying, which is why the test below exists:
    the engine does not size against `on_order` alone.
    """
    po = PurchaseOrder(
        id=_u(), company_id=SORENTO, po_number=unique_code(MARKER),
        supplier_id=world["supplier"].id, status="active", issue_date=date(2026, 8, 1),
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), company_id=SORENTO, purchase_order_id=po.id, product_id=world["product"].id,
        warehouse_id=world["warehouse"].id, qty_ordered=40, qty_received=0,
        line_status="open",
    ))
    db.flush()

    net = load_net_position(db, world["product"].id, world["warehouse"].id)

    assert net == [], "no stock, no SPO, no committed demand: the view has no row at all"


def test_the_engine_still_nets_an_unattributed_project_bin_po_line(db, world):
    """AC-6.12 proper, at ENGINE level (S6, review of PR #490).

    The claim G12 rests on is "safe against double-buying because the reorder engine nets
    open PO qty by location regardless of claims". The engine does NOT size against
    `scm.on_order_v` alone - `_compute_cell` takes `net = net_position + po_ordered`, and
    the `po_ordered` leg is `scm.po_ordered_v`, which sums every OPEN purchase-order line
    of an active order by `(product, warehouse)` and joins neither `scm.order_link_claim`
    nor a warehouse's `segment`.

    So a project-bin line nobody has attributed is still counted as supply the plan can
    see, and the lock costs the buyer nothing but the OI cover state. Asserted against the
    view the engine reads, with and without a claim, because "regardless of claims" is the
    half of the sentence that this slice could have broken.
    """
    po = PurchaseOrder(
        id=_u(), company_id=SORENTO, po_number=unique_code(MARKER),
        supplier_id=world["supplier"].id, status="active", issue_date=date(2026, 8, 1),
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_u(), company_id=SORENTO, purchase_order_id=po.id,
        product_id=world["product"].id, warehouse_id=world["warehouse"].id,
        qty_ordered=40, qty_received=0, line_status="open",
    )
    db.add(line)
    db.flush()

    def _po_ordered() -> float:
        return float(
            db.execute(
                text(
                    "SELECT COALESCE(SUM(ordered), 0) FROM scm.po_ordered_v "
                    " WHERE product_id = :p AND warehouse_id = :w"
                ),
                {"p": str(world["product"].id), "w": str(world["warehouse"].id)},
            ).scalar()
            or 0
        )

    assert _po_ordered() == 40.0, (
        "an unattributed project-bin line is invisible to the engine's supply read, which "
        "is the double-buy G12's own wording promises it is safe from"
    )

    # And with a claim naming somebody else entirely: the view has no way to tell, which
    # is exactly the property being pinned.
    db.execute(
        text(
            "INSERT INTO scm.order_link_claim (id, company_id, so_number, po_number, "
            "item_code, source, po_line_id, claimed_at) "
            "VALUES (:i, :c, :son, :pon, NULL, 'po_history', :pol, now())"
        ),
        {"i": _u(), "c": SORENTO, "son": unique_code("SO"), "pon": po.po_number,
         "pol": str(line.id)},
    )
    db.flush()

    assert _po_ordered() == 40.0, "a claim never changes what the engine counts as supply"
