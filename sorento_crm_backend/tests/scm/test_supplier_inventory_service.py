"""S7a - what the supplier stock upload writes, and what it deliberately refuses to write.

Everything is seeded by this file under codes it generates, and the workbook is built from the
SAME codes, so the file and the rows cannot drift apart and nothing is borrowed off a table
that is empty in CI. Runs inside `pg_session()`, which rolls back.
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO

import pytest
from sqlalchemy import text

from app.models.scm import SupplierInventory
from app.services.scm import supplier_inventory_service as svc
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import MARKER, require_aliases

HEADER = ["型号", "品名", "包装好库存", "空瓷", "体积(cbm)", "备注"]


def workbook(rows, header=None) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(header or HEADER))
    for r in rows:
        ws.append(list(r))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


class Codes:
    def __init__(self):
        tag = uuid.uuid4().hex[:8].upper()
        self.known = f"{MARKER}-SI1-{tag}"
        self.also_known = f"{MARKER}-SI2-{tag}"
        self.stranger = f"{MARKER}-SIX-{tag}"
        self.supplier = f"{MARKER}-CRSI-{tag}"


def seed(db, codes: Codes) -> str:
    """The two catalogue products and the one supplier this file names. Returns supplier id."""
    from app.models.procurement import Supplier
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    require_aliases(db, "supplier_inventory")

    cat = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=f"{MARKER}-CAT-{uuid.uuid4().hex[:8]}".upper(),
        category_name=f"{MARKER} category",
    )
    uom = UnitOfMeasure(
        id=str(uuid.uuid4()),
        uom_code=f"{MARKER}-U-{uuid.uuid4().hex[:6]}".upper(),
        uom_name="pcs",
    )
    db.add_all([cat, uom])
    db.flush()
    for code in (codes.known, codes.also_known):
        db.add(
            Product(
                id=str(uuid.uuid4()),
                product_code=code,
                product_name=code,
                category_id=cat.id,
                base_uom_id=uom.id,
                list_price=0,
                is_active=True,
                is_discontinued=False,
            )
        )
    supplier = Supplier(
        id=str(uuid.uuid4()),
        supplier_code=codes.supplier,
        supplier_name=f"{MARKER} supplier",
        is_active=True,
    )
    db.add(supplier)
    db.flush()
    return str(supplier.id)


def held(db, supplier_id: str):
    return (
        db.query(SupplierInventory)
        .filter(SupplierInventory.supplier_id == supplier_id)
        .order_by(SupplierInventory.item_code)
        .all()
    )


def test_a_matched_model_lands_with_its_product_and_both_quantities():
    with pg_session() as db:
        codes = Codes()
        supplier_id = seed(db, codes)
        data = workbook([[codes.known, "座厕", 120, 340, 0.21, ""]])

        out = svc.apply(db, data, supplier_id=supplier_id, as_of=date(2026, 7, 31))

        assert out["rows_written"] == 1
        row = held(db, supplier_id)[0]
        assert row.product_id is not None
        assert float(row.qty_packed) == 120
        assert float(row.qty_unfinished) == 340
        assert float(row.cbm_per_unit) == 0.21
        assert row.as_of == date(2026, 7, 31)


def test_an_unknown_model_is_kept_and_reported_but_never_invents_a_product():
    # It is real stock at the supplier, so hiding it would misstate what they hold. It just
    # cannot join a loading plan, whose lines hang off our own purchase orders.
    with pg_session() as db:
        codes = Codes()
        supplier_id = seed(db, codes)
        before = db.execute(
            text("SELECT count(*) FROM products WHERE product_code = :c"), {"c": codes.stranger}
        ).scalar()
        data = workbook([[codes.stranger, "unknown", 5, 0, 0.1, ""]])

        out = svc.apply(db, data, supplier_id=supplier_id)

        assert out["rows_written"] == 1
        assert held(db, supplier_id)[0].product_id is None
        assert out["summary"]["items_unmatched"] == 1
        assert codes.stranger in out["summary"]["unmatched_item_codes"]
        after = db.execute(
            text("SELECT count(*) FROM products WHERE product_code = :c"), {"c": codes.stranger}
        ).scalar()
        assert after == before


def test_the_second_upload_replaces_the_first_rather_than_adding_to_it():
    # An item the new file no longer lists is stock the supplier no longer holds. Merging
    # would leave it loadable forever.
    with pg_session() as db:
        codes = Codes()
        supplier_id = seed(db, codes)
        svc.apply(
            db,
            workbook([[codes.known, "a", 10, 0, 0.2, ""], [codes.also_known, "b", 4, 0, 0.3, ""]]),
            supplier_id=supplier_id,
        )

        out = svc.apply(db, workbook([[codes.known, "a", 25, 0, 0.2, ""]]), supplier_id=supplier_id)

        assert out["rows_replaced"] == 2
        rows = held(db, supplier_id)
        assert [r.item_code for r in rows] == [codes.known]
        assert float(rows[0].qty_packed) == 25


def test_replacing_touches_only_the_supplier_the_file_is_from():
    with pg_session() as db:
        codes, other = Codes(), Codes()
        supplier_id = seed(db, codes)
        other_id = seed(db, other)
        svc.apply(db, workbook([[other.known, "x", 9, 0, 0.2, ""]]), supplier_id=other_id)

        svc.apply(db, workbook([[codes.known, "a", 1, 0, 0.2, ""]]), supplier_id=supplier_id)

        assert len(held(db, other_id)) == 1


def test_one_model_listed_twice_becomes_one_row_with_the_quantities_added():
    # Suppliers split a body across spec lines. Two rows would answer "how many can I load"
    # twice, and the unique identity index would reject the second anyway.
    with pg_session() as db:
        codes = Codes()
        supplier_id = seed(db, codes)
        data = workbook(
            [[codes.known, "白色", 10, 0, 0.2, ""], [codes.known, "米色", 6, 3, None, ""]]
        )

        out = svc.apply(db, data, supplier_id=supplier_id)

        assert out["rows_written"] == 1
        assert out["duplicate_models_merged"] == 1
        row = held(db, supplier_id)[0]
        assert float(row.qty_packed) == 16
        assert float(row.qty_unfinished) == 3
        assert float(row.cbm_per_unit) == 0.2


def test_a_row_with_no_volume_is_stored_as_unknown_not_zero():
    with pg_session() as db:
        codes = Codes()
        supplier_id = seed(db, codes)

        svc.apply(db, workbook([[codes.known, "a", 8, 0, None, ""]]), supplier_id=supplier_id)

        assert held(db, supplier_id)[0].cbm_per_unit is None


def test_a_file_with_no_packed_column_writes_nothing_and_says_which_column():
    with pg_session() as db:
        codes = Codes()
        supplier_id = seed(db, codes)
        data = workbook([[codes.known, 3]], header=["型号", "空瓷"])

        out = svc.apply(db, data, supplier_id=supplier_id)

        assert out["readable"] is False
        assert out["missing_columns"] == ["qty_packed"]
        assert held(db, supplier_id) == []


def test_the_test_button_blocks_on_an_unreadable_file_and_names_the_column():
    with pg_session() as db:
        codes = Codes()
        supplier_id = seed(db, codes)

        verdict = svc.validate(
            db, workbook([[codes.known, 3]], header=["型号", "空瓷"]), supplier_id=supplier_id
        )

        assert verdict["valid"] is False
        assert any("qty_packed" in e for e in verdict["errors"])


def test_the_test_button_warns_about_unmatched_models_without_blocking():
    # A warning the operator sees and ignores is a decision. An error would stop a load that
    # is mostly fine.
    with pg_session() as db:
        codes = Codes()
        supplier_id = seed(db, codes)
        data = workbook(
            [[codes.known, "a", 5, 0, 0.2, ""], [codes.stranger, "b", 2, 0, 0.2, ""]]
        )

        verdict = svc.validate(db, data, supplier_id=supplier_id)

        assert verdict["valid"] is True
        assert any(codes.stranger in w for w in verdict["warnings"])


def test_a_header_with_no_rows_under_it_is_an_error_not_a_silent_wipe():
    # This one matters because apply REPLACES: an empty file that validated would delete the
    # supplier's whole snapshot and report success.
    with pg_session() as db:
        codes = Codes()
        supplier_id = seed(db, codes)

        verdict = svc.validate(db, workbook([]), supplier_id=supplier_id)

        assert verdict["valid"] is False


def test_the_preview_says_how_much_is_loadable_and_what_it_would_replace():
    with pg_session() as db:
        codes = Codes()
        supplier_id = seed(db, codes)
        svc.apply(db, workbook([[codes.known, "a", 1, 0, 0.2, ""]]), supplier_id=supplier_id)

        out = svc.preview(
            db,
            workbook([[codes.known, "a", 10, 5, 0.2, ""], [codes.also_known, "b", 4, 0, None, ""]]),
            supplier_id=supplier_id,
        )

        assert out["readable"] is True
        assert out["rows_held_now"] == 1
        assert out["summary"]["qty_packed"] == 14
        assert out["summary"]["qty_unfinished"] == 5
        # Only the measured, packed half is loadable: 10 x 0.2. The unmeasured row contributes
        # nothing rather than zero-volume free capacity.
        assert out["summary"]["loadable_cbm"] == pytest.approx(2.0)
        assert out["summary"]["items_unmeasured"] == 1


def _plan(db, supplier_id: str):
    from app.services.scm import loading_plan_service as plan_svc

    return plan_svc.create_record(
        db,
        supplier_id=supplier_id,
        plan_horizon_date=None,
        document_kind="stock_list",
        source_attachment_id=None,
        actor="Ms Tee",
    )


def test_rows_held_now_counts_only_this_plans_own_rows_not_the_whole_supplier():
    """`rows_held_now` used to count every row on file for the supplier, plan or none - so a
    fresh plan's preview claimed it would replace rows belonging to OTHER plans and the
    standalone snapshot, none of which `apply` (given the same `loading_plan_id`) would ever
    touch."""
    with pg_session() as db:
        codes = Codes()
        supplier_id = seed(db, codes)
        # The standalone snapshot, and another plan's own - neither is this plan's business.
        svc.apply(db, workbook([[codes.known, "a", 1, 0, 0.2, ""]]), supplier_id=supplier_id)
        other = _plan(db, supplier_id)
        svc.apply(
            db,
            workbook([[codes.also_known, "b", 2, 0, 0.2, ""]]),
            supplier_id=supplier_id,
            loading_plan_id=str(other.id),
        )

        fresh = _plan(db, supplier_id)
        out = svc.preview(
            db,
            workbook([[codes.known, "a", 10, 0, 0.2, ""]]),
            supplier_id=supplier_id,
            loading_plan_id=str(fresh.id),
        )

        assert out["rows_held_now"] == 0


def test_rows_held_now_counts_a_plans_own_stamped_rows():
    with pg_session() as db:
        codes = Codes()
        supplier_id = seed(db, codes)
        plan = _plan(db, supplier_id)
        svc.apply(
            db,
            workbook(
                [
                    [f"{codes.known}-{i}", "a", 1, 0, 0.2, ""]
                    for i in range(5)
                ]
            ),
            supplier_id=supplier_id,
            loading_plan_id=str(plan.id),
        )

        out = svc.preview(
            db,
            workbook([[codes.known, "a", 10, 0, 0.2, ""]]),
            supplier_id=supplier_id,
            loading_plan_id=str(plan.id),
        )

        assert out["rows_held_now"] == 5


def test_rows_held_now_with_no_plan_id_reads_the_loading_plan_id_is_null_count_only():
    """The standalone page's own scope, exactly as `apply` reads it (BL-1): a plan's stamped
    rows are not "held now" for the page that has no plan at all."""
    with pg_session() as db:
        codes = Codes()
        supplier_id = seed(db, codes)
        svc.apply(db, workbook([[codes.known, "a", 1, 0, 0.2, ""]]), supplier_id=supplier_id)
        plan = _plan(db, supplier_id)
        svc.apply(
            db,
            workbook([[codes.also_known, "b", 2, 0, 0.2, ""]]),
            supplier_id=supplier_id,
            loading_plan_id=str(plan.id),
        )

        out = svc.preview(
            db,
            workbook([[codes.known, "a", 10, 0, 0.2, ""]]),
            supplier_id=supplier_id,
        )

        assert out["rows_held_now"] == 1
