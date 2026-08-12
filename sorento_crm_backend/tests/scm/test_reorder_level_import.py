"""The AutoCount reorder level + reorder quantity listing, uploaded.

> "important aspect is the reorder level and reorder quantity, which are set at autocount,
>  and they need to upload to our system"

AutoCount OWNS the level; our system only receives it. No sample export exists yet, so the
columns are ASSUMED (user, 2026-08-10: "you can assume the column first") and resolved
through `import_field_alias` - when the real file arrives with different spellings, the fix
is alias rows, not code.

The reconciliation rule is the house rule: same then skip, diff then update, new then
create. The one wrinkle is ownership inside our own table: a level a person set by hand
(`source` manual / accepted_suggestion) is NOT silently overwritten by an upload - the
upload wins only over its own prior uploads, and a conflict is reported for a person to
settle (AC-S13c.3).
"""
from __future__ import annotations

import io
import uuid

import pytest
from openpyxl import Workbook
from sqlalchemy import text

MARKER = "ZZTRLV"
SORENTO = "00000000-0000-0000-0000-000000000001"


def workbook(rows: list[list], headers=("Item Code", "Location", "Reorder Level", "Reorder Qty")) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(list(headers))
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# reading
# --------------------------------------------------------------------------- #

def test_the_assumed_autocount_columns_resolve_through_the_alias_table(world):
    from app.services.scm.reorder_level_reader import read_workbook

    parsed = read_workbook(
        workbook([[world["code"], world["wh_code"], 120, 40]]), db=world["db"]
    )

    assert parsed.ok
    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert row.item_code == world["code"]
    assert row.location == world["wh_code"]
    assert row.reorder_level == 120
    assert row.reorder_qty == 40


def test_a_file_without_the_level_column_is_unreadable_not_half_read(world):
    from app.services.scm.reorder_level_reader import read_workbook

    parsed = read_workbook(
        workbook([[world["code"], 40]], headers=("Item Code", "Reorder Qty")),
        db=world["db"],
    )

    assert not parsed.ok
    assert "reorder_level" in parsed.missing_columns


def test_location_and_reorder_qty_are_optional(world):
    """AutoCount may keep one level per item with no per-location split. A file that says
    less still says something."""
    from app.services.scm.reorder_level_reader import read_workbook

    parsed = read_workbook(
        workbook([[world["code"], 120]], headers=("Item Code", "Reorder Level")),
        db=world["db"],
    )

    assert parsed.ok
    assert parsed.rows[0].location is None
    assert parsed.rows[0].reorder_qty is None


# --------------------------------------------------------------------------- #
# applying: same / diff / new
# --------------------------------------------------------------------------- #

def test_a_new_item_creates_a_level_owned_by_autocount(world):
    from app.services.scm import reorder_level_import_service as svc

    out = svc.apply(world["db"], workbook([[world["code"], world["wh_code"], 120, 40]]))

    assert out["created"] == 1
    row = world["level_row"]()
    assert float(row["level"]) == 120
    assert float(row["reorder_qty"]) == 40
    assert row["source"] == "autocount"


def test_the_same_figures_again_are_skipped_not_rewritten(world):
    from app.services.scm import reorder_level_import_service as svc

    data = workbook([[world["code"], world["wh_code"], 120, 40]])
    svc.apply(world["db"], data)
    out = svc.apply(world["db"], data)

    assert out["created"] == 0
    assert out["updated"] == 0
    assert out["unchanged"] == 1


def test_a_changed_figure_updates_the_row_it_created(world):
    from app.services.scm import reorder_level_import_service as svc

    svc.apply(world["db"], workbook([[world["code"], world["wh_code"], 120, 40]]))
    out = svc.apply(world["db"], workbook([[world["code"], world["wh_code"], 150, 40]]))

    assert out["updated"] == 1
    assert float(world["level_row"]()["level"]) == 150


def test_an_unknown_item_is_named_and_skipped_never_invented(world):
    from app.services.scm import reorder_level_import_service as svc

    out = svc.apply(world["db"], workbook([["NO-SUCH-ITEM", world["wh_code"], 120, 40]]))

    assert out["created"] == 0
    assert any("NO-SUCH-ITEM" in p["reason"] for p in out["problems"])


def test_an_unknown_location_is_named_and_the_row_is_skipped(world):
    """Half-applying it as a product-wide level would put the number somewhere the file
    did not say."""
    from app.services.scm import reorder_level_import_service as svc

    out = svc.apply(world["db"], workbook([[world["code"], "NO-SUCH-WH", 120, 40]]))

    assert out["created"] == 0
    assert any("NO-SUCH-WH" in p["reason"] for p in out["problems"])


# --------------------------------------------------------------------------- #
# ownership inside our own table
# --------------------------------------------------------------------------- #

def test_a_hand_set_level_is_not_silently_overwritten(world):
    """The upload wins only over its own prior uploads. A buyer's decision beats a feed,
    and the disagreement is REPORTED for a person to settle."""
    from app.services.scm import reorder_level_import_service as svc

    world["set_manual_level"](200)
    out = svc.apply(world["db"], workbook([[world["code"], world["wh_code"], 120, 40]]))

    assert float(world["level_row"]()["level"]) == 200, "a manual level was clobbered"
    assert out["conflicts"] == 1
    assert any(world["code"] in c["item_code"] for c in out["conflict_rows"])


def test_a_matching_hand_set_level_is_no_conflict(world):
    """AutoCount agreeing with the buyer is the happy case, not a report. The quantity
    still lands (NULL -> 40 is a real write, counted honestly as an update), and the row
    stays the buyer's: a quantity landing must not flip ownership to the feed."""
    from app.services.scm import reorder_level_import_service as svc

    world["set_manual_level"](120)
    out = svc.apply(world["db"], workbook([[world["code"], world["wh_code"], 120, 40]]))

    assert out["conflicts"] == 0
    assert out["updated"] == 1
    row = world["level_row"]()
    assert row["source"] == "manual", "a quantity write flipped ownership to the feed"
    assert float(row["reorder_qty"]) == 40


def test_the_upload_still_writes_reorder_qty_beside_a_manual_level(world):
    """The LEVEL is the contested column; the reorder quantity is AutoCount's own figure
    and nothing in our UI edits it, so it lands even when the level stands."""
    from app.services.scm import reorder_level_import_service as svc

    world["set_manual_level"](200)
    svc.apply(world["db"], workbook([[world["code"], world["wh_code"], 120, 40]]))

    row = world["level_row"]()
    assert float(row["reorder_qty"]) == 40
    assert row["source"] == "manual"


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
        code = unique_code("P")
        product = Product(id=_u(), product_code=code, product_name=f"{MARKER} p",
                          category_id=cat.id, base_uom_id=uom.id, list_price=0,
                          is_active=True, is_discontinued=False)
        db.add(product)
        db.flush()

        wid = _u()
        wh_code = unique_code("W")[:20]
        db.execute(text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
            "counts_as_available) VALUES (:id, :c, :c, true, true)"),
            {"id": wid, "c": wh_code})
        db.flush()

        def level_row():
            r = db.execute(text(
                "SELECT level, reorder_qty, source FROM scm.reorder_level "
                "WHERE product_id = :p AND warehouse_id = :w"),
                {"p": product.id, "w": wid}).mappings().first()
            assert r is not None, "no level row written"
            return r

        def set_manual_level(level: float):
            # company_id stamped explicitly: raw SQL bypasses the ORM's company stamp,
            # and the service reads through the company-scoped ORM, which would never see
            # a NULL-company row.
            db.execute(text(
                "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, "
                "source, company_id) VALUES (:id, :p, :w, :l, 'manual', :co)"),
                {"id": _u(), "p": product.id, "w": wid, "l": level, "co": SORENTO})
            db.flush()

        yield {
            "db": db,
            "code": code,
            "wh_code": wh_code,
            "product": product,
            "warehouse_id": wid,
            "level_row": level_row,
            "set_manual_level": set_manual_level,
        }
