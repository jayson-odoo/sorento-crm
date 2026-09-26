"""S7 / AC-7.8 - an alias written from a PI line re-points that line, however it is spelled.

`PLAN-scm-ui-feedback-14sep.md` J5 puts ONE always-on dropdown in the PI Lines Product cell:
picking an option POSTs the supplier-code alias immediately, with no Edit and no Save, and
the line is expected to show the new code when the detail re-reads.

The plan's own S7 says the backend needs nothing and asks for this to be VERIFIED rather
than assumed: `supplier_code_alias_service.create` strips the code and `_rebind` compares
with `ilike`, so a case or trailing-space variant of what the line holds should already
re-point it. These tests are that verification. They are expected to be GREEN on the current
code and stay green - a REGRESSION PIN, not a red test - because the FE slice is about to
start sending exactly this shape from a new control, and a normalisation change in `_rebind`
would silently leave the picked line reading the old code.

Postgres (`pg_session`, rolled back), own seeds.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.product_set import ProductSet, ProductSetMember
from app.services.scm import proforma_invoice_service as svc
from app.services.scm import supplier_code_alias_service as alias_svc

from ._pg_fixture import pg_session
from .scm.test_proforma_invoice_import import World, _invoices, _lines, workbook

MARKER = "ZZPIRB"


def _product_set(db, world: World, code: str, member) -> ProductSet:
    """One of OUR sets, seeded here rather than borrowed: CI's database holds none."""
    product_set = ProductSet(
        id=str(uuid.uuid4()),
        set_code=f"{MARKER}-{code}-{world.tag}",
        name=code,
        is_active=True,
    )
    db.add(product_set)
    db.flush()
    db.add(
        ProductSetMember(
            id=str(uuid.uuid4()),
            product_set_id=product_set.id,
            product_id=member.id,
            quantity=1,
            sort_order=0,
        )
    )
    db.flush()
    return product_set


def _invoice_with_code(db, world: World, item_code: str):
    """An invoice whose only line carries `item_code` and binds to nothing."""
    svc.apply(
        db,
        workbook([["产品型号", "数量", "PRICE"], [item_code, 5, 12.5]]),
        supplier_id=str(world.supplier.id),
        currency="USD",
        source_ref=f"{MARKER}.xlsx",
    )
    db.flush()
    invoice = _invoices(db, world)[0]
    line = _lines(db, invoice.id)[0]
    assert line.product_id is None, "the fixture's code must start unbound"
    return invoice, line


def test_an_alias_for_a_lowercase_variant_repoints_the_line():
    with pg_session() as db:
        world = World(db)
        target = world.product("TARGET")
        stated = f"{MARKER}-SRTWC8366-RL"
        invoice, line = _invoice_with_code(db, world, stated)

        out = alias_svc.create(
            db,
            supplier_id=str(world.supplier.id),
            supplier_code=stated.lower(),
            product_id=str(target.id),
            actor="Ms Tee",
        )
        db.flush()

        assert out["rebound_invoice_lines"] == 1
        db.refresh(line)
        assert str(line.product_id) == str(target.id)


def test_an_alias_for_a_padded_variant_repoints_the_line():
    """A code copied out of a spreadsheet cell arrives with a trailing space."""
    with pg_session() as db:
        world = World(db)
        target = world.product("TARGET")
        stated = f"{MARKER}-SRTWC8366-RL"
        invoice, line = _invoice_with_code(db, world, stated)

        out = alias_svc.create(
            db,
            supplier_id=str(world.supplier.id),
            supplier_code=f"  {stated.lower()} ",
            product_id=str(target.id),
            actor="Ms Tee",
        )
        db.flush()

        assert out["rebound_invoice_lines"] == 1
        db.refresh(line)
        assert str(line.product_id) == str(target.id)


def test_picking_a_set_repoints_the_line_to_the_set_and_clears_the_product():
    """AC-7.4's server half: a set pick sends `product_set_id`, and a line that used to
    name a product has to stop naming it, or the convert splits the wrong thing."""
    with pg_session() as db:
        world = World(db)
        product = world.product("MEMBER")
        product_set = _product_set(db, world, "CWC605-RL", product)
        stated = f"{MARKER}-SRTWC8366-RL"
        invoice, line = _invoice_with_code(db, world, stated)

        alias_svc.create(
            db,
            supplier_id=str(world.supplier.id),
            supplier_code=stated,
            product_id=str(product.id),
            actor="Ms Tee",
        )
        db.flush()
        db.refresh(line)
        assert str(line.product_id) == str(product.id)

        out = alias_svc.create(
            db,
            supplier_id=str(world.supplier.id),
            supplier_code=stated.lower(),
            product_set_id=str(product_set.id),
            actor="Ms Tee",
        )
        db.flush()

        assert out["rebound_invoice_lines"] == 1
        db.refresh(line)
        assert line.product_id is None
        assert str(line.product_set_id) == str(product_set.id)


def test_an_alias_for_another_code_leaves_the_line_alone():
    """The negative half - `ilike` must not be widened into a prefix or a fuzzy match."""
    with pg_session() as db:
        world = World(db)
        target = world.product("TARGET")
        stated = f"{MARKER}-SRTWC8366-RL"
        invoice, line = _invoice_with_code(db, world, stated)

        out = alias_svc.create(
            db,
            supplier_id=str(world.supplier.id),
            supplier_code=f"{stated}-EXTRA",
            product_id=str(target.id),
            actor="Ms Tee",
        )
        db.flush()

        assert out["rebound_invoice_lines"] == 0
        db.refresh(line)
        assert line.product_id is None
