"""One upload sets the item master AND the planning level.

The reorder level has one owner (AutoCount) and two readers: the product master, which the
buyer sees on the item, and `scm.reorder_level`, which the planning engine buys against.
Feeding them from two different uploads is how they come to disagree, so the product list
upload hands its levels to the service that owns the planning table.

It DELEGATES rather than restating the rule: a level a person set by hand is never silently
overwritten, and that rule lives in one place. What is tested here is the seam - that the
product import reaches it, and that the one deliberate asymmetry (a blank clears the item
master but does not touch a planning level) holds.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

MARKER = "ZZTPRL"
SORENTO = "00000000-0000-0000-0000-000000000001"
USER_ID = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _isolate_side_effects(monkeypatch):
    from app.services import product_service as product_service_mod

    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_bulk_publish_product_embedding_events",
        lambda self, *a, **kw: None,
    )
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_resolve_default_supplier_for_new_product",
        lambda self: None,
    )
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_default_standard_lead_time_days",
        lambda self: None,
    )


@pytest.fixture
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
        code = unique_code("P")
        product = Product(id=_u(), product_code=code, product_name=f"{MARKER} p",
                          category_id=cat.id, base_uom_id=uom.id, list_price=0,
                          is_active=True, is_discontinued=False)
        db.add(product)
        db.flush()

        def planning_row():
            return db.execute(text(
                "SELECT level, reorder_qty, source FROM scm.reorder_level "
                "WHERE product_id = :p AND warehouse_id IS NULL"),
                {"p": product.id}).mappings().first()

        def set_manual_level(level: float):
            # company_id stamped explicitly: raw SQL bypasses the ORM's company stamp, and
            # the service reads through the company-scoped ORM.
            db.execute(text(
                "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, "
                "source, company_id) VALUES (:id, :p, NULL, :l, 'manual', :co)"),
                {"id": _u(), "p": product.id, "l": level, "co": SORENTO})
            db.flush()

        def row(**over):
            r = {
                "Item Code": code,
                "Description": f"{MARKER} desc",
                "Item Group": cat.category_code,
                "Price": "10",
                "Is Active": "T",
            }
            r.update(over)
            return r

        yield {
            "db": db,
            "code": code,
            "product": product,
            "row": row,
            "planning_row": planning_row,
            "set_manual_level": set_manual_level,
        }


def _import(world, rows):
    from app.services.product_service import ProductService

    return ProductService(world["db"]).bulk_import_products(rows, USER_ID)


def test_a_level_from_the_product_upload_lands_on_the_planning_table(world):
    """No location column in the AutoCount stock list, which is already how that table
    scopes a product-wide level (`warehouse_id` NULL)."""
    _import(world, [world["row"](**{"Reorder Level": 250, "Reorder Qty": 100})])

    row = world["planning_row"]()
    assert row is not None, "the product upload did not reach scm.reorder_level"
    assert float(row["level"]) == 250
    assert float(row["reorder_qty"]) == 100
    assert row["source"] == "autocount"


def test_zero_reaches_the_plan_as_zero(world):
    _import(world, [world["row"](**{"Reorder Level": 0, "Reorder Qty": 0})])

    row = world["planning_row"]()
    assert row is not None
    assert float(row["level"]) == 0


def test_a_level_a_person_set_stands_and_is_reported(world):
    world["set_manual_level"](250)

    result = _import(world, [world["row"](**{"Reorder Level": 400, "Reorder Qty": 100})])

    row = world["planning_row"]()
    assert float(row["level"]) == 250, "an upload silently overwrote a hand-set level"
    assert row["source"] == "manual", "a quantity flipped ownership to autocount"
    # AutoCount's own quantity still lands - nothing in our UI edits it.
    assert float(row["reorder_qty"]) == 100
    assert result["level_conflicts"] == 1
    assert any("was set by hand" in w for w in result["level_conflict_warnings"])
    assert any(world["code"] in w for w in result["level_conflict_warnings"])


def test_the_item_master_still_takes_the_file_value_while_the_plan_holds(world):
    """The two stores hold different numbers here, on purpose: the item master mirrors
    AutoCount, the plan keeps what a person decided until they settle the conflict."""
    world["set_manual_level"](250)

    _import(world, [world["row"](**{"Reorder Level": 400})])

    world["db"].refresh(world["product"])
    assert world["product"].reorder_level == 400
    assert float(world["planning_row"]()["level"]) == 250


def test_a_blank_cell_clears_the_item_master_but_not_the_plan(world):
    """The one deliberate asymmetry. A blank carries no value for a hand-set level to
    disagree with, so a filtered export full of blanks must not empty the planning basis
    with no conflict reported. Clearing a planning level stays an act on the SCM screen."""
    world["product"].reorder_level = 250
    world["db"].flush()
    world["set_manual_level"](250)

    _import(world, [
        world["row"](**{"Reorder Level": ""}),
        world["row"](**{"Item Code": f"{world['code']}-OTHER", "Reorder Level": 9}),
    ])

    world["db"].refresh(world["product"])
    assert world["product"].reorder_level is None
    assert float(world["planning_row"]()["level"]) == 250


def test_a_file_with_no_reorder_column_writes_no_planning_row(world):
    _import(world, [world["row"]()])

    assert world["planning_row"]() is None


def test_a_second_upload_of_the_same_numbers_changes_nothing(world):
    _import(world, [world["row"](**{"Reorder Level": 250, "Reorder Qty": 100})])
    first = world["planning_row"]()

    _import(world, [world["row"](**{"Reorder Level": 250, "Reorder Qty": 100})])
    second = world["planning_row"]()

    assert float(second["level"]) == float(first["level"])
    count = world["db"].execute(text(
        "SELECT count(*) FROM scm.reorder_level WHERE product_id = :p"),
        {"p": world["product"].id}).scalar()
    assert count == 1, "a re-upload created a duplicate planning row"


def _validate(world, rows):
    from app.services.product_service import ProductService

    return ProductService(world["db"]).validate_products_import(rows)


def test_test_reports_the_levels_before_anything_is_written(world):
    world["product"].reorder_level = 250
    world["db"].flush()

    result = _validate(world, [
        world["row"](**{"Reorder Level": ""}),
        world["row"](**{"Item Code": f"{world['code']}-NEW", "Reorder Level": 9}),
    ])

    assert result["summary"]["levels_applied"] == 1
    assert result["summary"]["levels_cleared"] == 1
    assert any("take a reorder level" in w for w in result["warnings"])
    assert any("cleared" in w for w in result["warnings"])
    assert world["planning_row"]() is None, "the Test button wrote to the planning table"


def test_test_names_a_conflict_it_would_hit(world):
    world["set_manual_level"](250)

    result = _validate(world, [world["row"](**{"Reorder Level": 400})])

    assert result["summary"]["level_conflicts"] == 1
    assert any(world["code"] in w and "set by hand" in w for w in result["warnings"])


def test_test_and_confirm_agree_about_the_same_file(world):
    """The whole reason the preview runs through the same service: a Test that promises
    one thing and a Confirm that does another is worse than no Test."""
    world["set_manual_level"](250)
    rows = [world["row"](**{"Reorder Level": 400, "Reorder Qty": 100})]

    preview = _validate(world, rows)
    applied = _import(world, rows)

    assert preview["summary"]["levels_applied"] == applied["levels_applied"]
    assert preview["summary"]["level_conflicts"] == applied["level_conflicts"]


def test_a_file_with_no_reorder_column_previews_nothing(world):
    result = _validate(world, [world["row"]()])

    assert result["summary"]["levels_applied"] == 0
    assert result["summary"]["levels_cleared"] == 0
    assert not any("reorder level" in w.lower() for w in result["warnings"])


def test_a_failure_writing_the_plan_does_not_fail_the_product_import(world, monkeypatch):
    """The products are already committed by then. Raising here would hand the caller a
    500 for work that succeeded, and the retry would redo the first half.

    Only the returned result is asserted, deliberately. The recovery path rolls the
    session back to discard the half-written planning work, which in this fixture also
    unwinds the outer transaction the products were committed into - so re-reading them
    here would measure the harness, not the code. That the item master IS written is
    `test_a_level_from_the_product_upload_lands_on_the_planning_table` and the item-master
    suite; what this test owns is that the failure stays swallowed.
    """
    from app.services.scm import reorder_level_import_service as rl

    def boom(*a, **kw):
        raise RuntimeError("planning table unavailable")

    monkeypatch.setattr(rl, "apply_rows", boom)

    result = _import(world, [world["row"](**{"Reorder Level": 250})])

    assert result["errors"] == []
    assert result["created"] + result["updated"] == 1
    assert result["levels_applied"] == 1
    assert result["level_conflicts"] == 0
    assert result["level_conflict_warnings"] == []
