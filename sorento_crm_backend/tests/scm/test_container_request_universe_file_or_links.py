"""The container-request universe is the file when there is one, the sourcing links when not.

`PLAN-scm-loading-plan-lines-feedback-12sep.md`, AC-U1..U4. The captain's rule
(12 Sep 2026): a plan with a statement on file asks about what the statement names and nothing
else; a plan with none asks about what `product_suppliers` says we buy from them. Supplier
code aliases bind a file's codes to our products and are no membership leg of their own.

TEST-FIRST: written against the union rule these replace (AC-E0 / AC-D3), so each fails by
finding a row the new rule says must not be there.
"""
from __future__ import annotations

import uuid

from app.models.product_set import ProductSet, ProductSetMember
from app.services.scm import container_request_service as build_svc
from app.services.scm import supplier_code_alias_service as alias_svc
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg
from tests.scm.test_plan_owned_statement import MARKER, World, _codes, _retail_need, _row

pytestmark = requires_pg


def _uid() -> str:
    return str(uuid.uuid4())


def test_a_file_plan_lists_only_what_the_file_names():
    """AC-U1. Linked, owed, and not on the file: not a row."""
    with pg_session() as db:
        w = World(db)
        plan = w.plan("stock_list")
        w.stock_row("ON-FILE", packed=5, plan_id=str(plan.id))
        w.link("ON-FILE")
        w.link("LINKED-ONLY")
        for key in ("ON-FILE", "LINKED-ONLY"):
            _retail_need(db, w, key, 10)

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=plan)

        assert _codes(out["rows"]) == [w.code("ON-FILE")]
        assert _row(out, w.code("ON-FILE"))["rank"] == 1


def test_a_proforma_plan_lists_only_what_the_invoices_name():
    """AC-U1, the proforma half."""
    with pg_session() as db:
        w = World(db)
        plan = w.plan("proforma")
        w.invoice([("ON-FILE", 60)], plan_id=str(plan.id))
        w.link("LINKED-ONLY")
        for key in ("ON-FILE", "LINKED-ONLY"):
            _retail_need(db, w, key, 10)

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=plan)

        assert _codes(out["rows"]) == [w.code("ON-FILE")]


def test_a_file_plan_ignores_aliases_the_file_does_not_name():
    """AC-U1. A remembered code is a binding, not a membership."""
    with pg_session() as db:
        w = World(db)
        plan = w.plan("stock_list")
        w.stock_row("ON-FILE", packed=5, plan_id=str(plan.id))
        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=f"{MARKER}-THEIRS-{w.tag}",
            product_id=str(w.product("ALIASED").id),
            actor="Ms Tee",
        )
        for key in ("ON-FILE", "ALIASED"):
            _retail_need(db, w, key, 10)

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=plan)

        assert _codes(out["rows"]) == [w.code("ON-FILE")]


def test_a_no_file_plan_lists_only_the_sourcing_links():
    """AC-U2. Links in, through the link OR through a link the alias itself wrote (S4, "match
    reaches master data": `supplier_code_alias_service.create` also writes a `product_suppliers`
    row); an aliased SET's driver (no link possible for a set) and a stranger out."""
    with pg_session() as db:
        w = World(db)
        w.link("LINKED")
        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=f"{MARKER}-THEIRS-{w.tag}",
            product_id=str(w.product("ALIASED").id),
            actor="Ms Tee",
        )
        driver = w.product("SET-DRIVER")
        product_set = ProductSet(
            id=_uid(), set_code=f"{MARKER}-SET-{w.tag}", name="Aliased set", is_active=True
        )
        db.add(product_set)
        db.flush()
        db.add(
            ProductSetMember(
                id=_uid(), product_set_id=product_set.id, product_id=driver.id,
                quantity=1, sort_order=0,
            )
        )
        db.flush()
        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=f"{MARKER}-SETCODE-{w.tag}",
            product_set_id=str(product_set.id),
            actor="Ms Tee",
        )
        for key in ("LINKED", "ALIASED", "SET-DRIVER", "STRANGER"):
            _retail_need(db, w, key, 10)

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=w.plan("none"))

        assert _codes(out["rows"]) == sorted([w.code("LINKED"), w.code("ALIASED")])


def test_a_file_plan_whose_rows_bound_to_nothing_lists_no_rows():
    """AC-U3. The file IS the ask; an unmatched file asks for nothing yet."""
    with pg_session() as db:
        w = World(db)
        plan = w.plan("stock_list")
        w.stock_row(
            "A", packed=1, plan_id=str(plan.id), item_code=f"{MARKER}-UNKNOWN-{w.tag}", bound=False
        )
        w.link("A")
        _retail_need(db, w, "A", 10)

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=plan)

        assert out["rows"] == []


def test_placement_on_a_file_plan_is_unchanged():
    """AC-U4. Owed = ranked; held only = folded; neither = dropped."""
    with pg_session() as db:
        w = World(db)
        plan = w.plan("stock_list")
        w.stock_row("OWED", packed=5, plan_id=str(plan.id))
        w.stock_row("HELD", packed=7, plan_id=str(plan.id))
        w.stock_row("EMPTY", packed=0, plan_id=str(plan.id))
        _retail_need(db, w, "OWED", 10)

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=plan)

        assert _codes(out["rows"]) == sorted([w.code("OWED"), w.code("HELD")])
        assert _row(out, w.code("OWED"))["rank"] == 1
        held = _row(out, w.code("HELD"))
        assert held["has_demand"] is False and held["rank"] is None
