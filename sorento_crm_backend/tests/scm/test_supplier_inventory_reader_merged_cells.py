"""Loading plan merged-cells unfold (S1) - RED, written before the implementation.

The supplier's own stock list merges 品名 (and sometimes 规格/备注/体积) across a family of
models sharing one row of text, so openpyxl hands the anchor row the value and every covered
row `None`. `outstanding_reader.sheet_merges` and the fill-through in
`supplier_inventory_reader.read_workbook` do not exist yet - see
documentation/plans/scm/PLAN-loading-plan-merged-cells-unfold.md and its UAC file
(loading-plan-merged-cells-unfold-acceptance-criteria.md, AC-M1..AC-M8).

No real supplier file is committed; every workbook here is built with openpyxl so the merge
shape is provable against bytes alone. `test_ac_m7` is the one AC-M7 half that reuses the
committed OLE2 fixture `tests/scm/fixtures/legacy_biff_sample.xls` (test_po_listing_reader.py
uses the same file).
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO
from pathlib import Path

from app.services.import_alias_service import AliasResolver, normalize_header
from app.services.scm.outstanding_reader import _OLE2_MAGIC
from app.services.scm.supplier_inventory_reader import read_workbook
from tests._pg_fixture import pg_session, unique_code

#: The alias rows migration 311 seeds for this document type, as (field, alias). Mirrors
#: tests/scm/test_supplier_inventory_reader.py so parsing is provable against bytes alone.
_ALIASES = [
    ("item_code", "型号"),
    ("item_code", "MODEL"),
    ("brand", "商标"),
    ("spec", "规格"),
    ("product_name", "品名"),
    ("qty_packed", "包装好库存"),
    ("qty_unfinished", "空瓷"),
    ("cbm_per_unit", "体积(cbm)"),
    ("cbm_total", "总体积(cbm)"),
    ("remark", "备注"),
]


def resolver() -> AliasResolver:
    mapping: dict[str, str] = {}
    for field, alias in _ALIASES:
        mapping.setdefault(normalize_header(alias), field)
        mapping.setdefault(normalize_header(field), field)
    return AliasResolver("supplier_inventory", mapping)


def merged_workbook(rows: list[list], merges: list[str]) -> bytes:
    """A workbook whose cells hold values only where the real supplier file would - a merged
    range's anchor carries the value, the covered cells are left blank, and `merges` names the
    ranges the same way the sheet does (`"E3:E5"`)."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    for rng in merges:
        ws.merge_cells(rng)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


#: The real header shape: a title row, then 序号 (unmapped)/型号/商标/规格/品名/包装好库存/
#: 空瓷/体积(cbm)/备注 - columns A..I. Row 3 is the merge anchor (SRTWB247), rows 4-5 are the
#: covered rows (MWB247, CGB247, the owner's actual example), row 6 sits outside the merge
#: with its own text (AC-M5).
_TITLE = ["金百川库存表", None, None, None, None, None, None, None, None]
_HEADER = ["序号", "型号", "商标", "规格", "品名", "包装好库存", "空瓷", "体积(cbm)", "备注"]


def family_workbook() -> bytes:
    rows = [
        _TITLE,
        _HEADER,
        [1, "SRTWB247", "S", "SPEC-A", "盆小孔", 2, 2, 0.03, "REMARK-A"],
        [2, "MWB247", "M", None, None, 12, None, None, None],
        [3, "CGB247", "C", None, None, 256, None, None, None],
        [4, "SRTWB999", "X", "SPEC-OWN", "盆", 5, 0, 0.05, "OWN"],
    ]
    merges = ["E3:E5", "D3:D5", "I3:I5", "H3:H5", "G3:G5"]
    return merged_workbook(rows, merges)


def by_code(rows, code):
    return next(r for r in rows if r.item_code == code)


def test_ac_m1_text_fields_fill_through_a_merged_family():
    out = read_workbook(family_workbook(), resolver())

    assert out.ok
    family = [by_code(out.rows, c) for c in ("SRTWB247", "MWB247", "CGB247")]
    assert [r.product_name for r in family] == ["盆小孔", "盆小孔", "盆小孔"]
    assert [r.spec for r in family] == ["SPEC-A", "SPEC-A", "SPEC-A"]
    assert [r.remark for r in family] == ["REMARK-A", "REMARK-A", "REMARK-A"]
    # Brand is NOT merged in the source sheet - each model keeps its own letter.
    assert [r.brand for r in family] == ["S", "M", "C"]


def test_ac_m2_cbm_per_unit_fills_through_a_merged_family():
    out = read_workbook(family_workbook(), resolver())

    family = [by_code(out.rows, c) for c in ("SRTWB247", "MWB247", "CGB247")]
    assert [r.cbm_per_unit for r in family] == [0.03, 0.03, 0.03]


def test_ac_m3_quantities_stay_on_the_anchor_row_only():
    out = read_workbook(family_workbook(), resolver())

    anchor = by_code(out.rows, "SRTWB247")
    covered = [by_code(out.rows, c) for c in ("MWB247", "CGB247")]
    assert anchor.qty_unfinished == 2.0
    assert [r.qty_unfinished for r in covered] == [0.0, 0.0]
    assert anchor.qty_unfinished + sum(r.qty_unfinished for r in covered) == 2.0
    # 包装好库存 was never merged - each row's own figure is untouched by the fill.
    assert anchor.qty_packed == 2.0
    assert [r.qty_packed for r in covered] == [12.0, 256.0]


def test_ac_m4_a_merged_total_cbm_derives_the_anchors_per_unit_only():
    # No per-unit column at all here - only 型号/包装好库存/空瓷/总体积(cbm), so per_unit is
    # derived from the total the way an unmerged file already does (existing behaviour), and
    # the derivation must not extend to the covered rows' blank total cells.
    data = merged_workbook(
        [
            ["型号", "包装好库存", "空瓷", "总体积(cbm)"],
            ["SRTWB300", 8, 0, 8.16],
            ["MWB300", 12, 0, None],
            ["CGB300", 256, 0, None],
        ],
        merges=["D2:D4"],
    )

    out = read_workbook(data, resolver())

    anchor = by_code(out.rows, "SRTWB300")
    covered = [by_code(out.rows, c) for c in ("MWB300", "CGB300")]
    assert anchor.cbm_per_unit == round(8.16 / 8, 6)
    assert [r.cbm_per_unit for r in covered] == [None, None]


def test_ac_m5_a_rows_own_value_outside_the_merge_is_never_overwritten():
    out = read_workbook(family_workbook(), resolver())

    own = by_code(out.rows, "SRTWB999")
    assert own.product_name == "盆"
    assert own.spec == "SPEC-OWN"
    assert own.remark == "OWN"
    assert own.cbm_per_unit == 0.05


def test_ac_m5b_a_merge_anchored_on_the_header_never_fills():
    # Reviewer's finding: a 品名 HEADER cell merged down into its own column's first data rows
    # anchors the merge on the header row itself. Filling from it would stamp the literal
    # caption "品名" into every covered data row instead of leaving them with no text - the
    # header is never a model's own value.
    data = merged_workbook(
        [
            ["型号", "品名", "包装好库存"],
            ["SRTWB501", None, 10],
            ["SRTWB502", None, 20],
        ],
        merges=["B1:B3"],
    )

    out = read_workbook(data, resolver())

    family = [by_code(out.rows, c) for c in ("SRTWB501", "SRTWB502")]
    assert [r.product_name for r in family] == [None, None]


def test_ac_m6_an_unmerged_sheet_parses_exactly_as_before():
    # A merge exists elsewhere in the sheet (the title spans the header width, as every real
    # stock list does) but none of the three data rows are merged, so each keeps its own text.
    data = merged_workbook(
        [
            ["金百川库存表", None, None],
            ["型号", "品名", "包装好库存"],
            ["SRTWB401", "名称A", 10],
            ["SRTWB402", "名称B", 20],
            ["SRTWB403", "名称C", 30],
        ],
        merges=["A1:C1"],
    )

    out = read_workbook(data, resolver())

    assert out.ok
    assert [r.product_name for r in out.rows] == ["名称A", "名称B", "名称C"]
    assert [r.qty_packed for r in out.rows] == [10.0, 20.0, 30.0]


def test_ac_m7_sheet_merges_on_an_ole2_file_is_empty():
    # Imported inside the test on purpose: `sheet_merges` does not exist yet, and a
    # module-level import would turn every other test in this file into a collection error
    # instead of an individual, readable failure.
    from app.services.scm.outstanding_reader import sheet_merges

    assert sheet_merges(_OLE2_MAGIC + b"\x00" * 64) == {}


def test_ac_m7_read_workbook_on_a_real_legacy_biff_file_does_not_raise():
    fixture = Path(__file__).parent / "fixtures" / "legacy_biff_sample.xls"
    data = fixture.read_bytes()

    # Whatever this particular sample's headers resolve to is not the point - the point is
    # that merge lookup on an `.xls` never raises (sheet_merges returns {} for OLE2 bytes).
    read_workbook(data, resolver())


def test_ac_m8_the_service_writes_the_filled_through_text_for_covered_rows():
    with pg_session() as db:
        from app.models.procurement import Supplier
        from app.models.product import Product, ProductCategory, UnitOfMeasure
        from app.services.scm import supplier_inventory_service as svc
        from app.services.scm.supplier_code_alias_service import unmatched_for_supplier

        cat = ProductCategory(
            id=str(uuid.uuid4()),
            category_code=unique_code("CAT"),
            category_name="merged cells category",
        )
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("U"), uom_name="pcs")
        db.add_all([cat, uom])
        db.flush()
        # Only the anchor model is a known product - MWB247/CGB247 stay unmatched, which is
        # exactly what makes them show up in the Supplier codes queue with the filled text.
        db.add(
            Product(
                id=str(uuid.uuid4()),
                product_code="SRTWB247",
                product_name="SRTWB247",
                category_id=cat.id,
                base_uom_id=uom.id,
                list_price=0,
                is_active=True,
                is_discontinued=False,
            )
        )
        supplier = Supplier(
            id=str(uuid.uuid4()),
            supplier_code=unique_code("SUP"),
            supplier_name="merged cells supplier",
            is_active=True,
        )
        db.add(supplier)
        db.flush()
        supplier_id = str(supplier.id)

        svc.apply(db, family_workbook(), supplier_id=supplier_id, as_of=date(2026, 9, 14))

        queue = {row["item_code"]: row for row in unmatched_for_supplier(db, supplier_id)}
        assert queue["MWB247"]["product_name"] == "盆小孔"
        assert queue["CGB247"]["product_name"] == "盆小孔"


# AC-M9 (`PLAN-stock-list-bare-model-codes.md` D8/item_code fill-through regression, CI
# red on #1000-adjacent): a container-request export's TOTAL row merges its `合计：` label
# HORIZONTALLY - anchored in 序号 (unmapped), spanning into 型号 (and further, in the real
# file, into 商标/品名) - with SUM totals sitting in the quantity cells. `item_code` joining
# `_MERGE_FILL_FIELDS` (D8) made the reader copy that label sideways out of 序号 into 型号,
# so a totals line was returned as a bogus stock row reading model number `合计：`. Every
# existing AC-M1-M8 fixture merges VERTICALLY - one family sharing one column's text down
# several rows - so none of them exercised a horizontal merge at all.
def total_row_workbook() -> bytes:
    rows = [
        _TITLE,
        _HEADER,
        [1, "SRTWB247", "S", "SPEC-A", "盆小孔", 2, 2, 0.03, "REMARK-A"],
        # The anchor (row 4, col A) carries the label; B/C/E (型号/商标/品名) are covered by
        # the SAME horizontal merge and read blank from the sheet - only F/G (quantities)
        # are the totals themselves, never merged at all (quantities are never merge-fill
        # fields, D8).
        ["合计：", None, None, None, None, 100, 50, None, None],
    ]
    merges = ["A4:E4"]
    return merged_workbook(rows, merges)


def test_ac_m9_a_horizontally_merged_total_label_does_not_become_a_row():
    out = read_workbook(total_row_workbook(), resolver())

    # Only the one real stock line (row 3) is a row; the total line is a blank model number
    # carrying stock, which is the SAME "no model number on a row with stock" complaint an
    # ordinary blank-model row already raises - never a row of its own reading `合计：`.
    assert [r.item_code for r in out.rows] == ["SRTWB247"]
    assert any("no model number" in p.reason for p in out.problems)


def test_ac_m9_a_horizontally_merged_total_label_fills_no_field_from_another_column():
    out = read_workbook(total_row_workbook(), resolver())

    # Nothing on file anywhere reads the label text - not as an item_code (covered above),
    # and not as a product_name or brand either (D8's guard is the same one for all three
    # merge-fill text fields, not an item_code-only special case).
    for row in out.rows:
        assert row.item_code != "合计："
        assert row.product_name != "合计："
        assert row.brand != "合计："


def vertical_model_merge_workbook() -> bytes:
    """The AC-R1 case, restated in this file's own vocabulary: a VERTICAL merge - one
    model's own 型号 shared down several rows - must keep filling exactly as before. The
    same-column guard AC-M9 needs must accept this shape, not merely reject the horizontal
    one."""
    rows = [
        _TITLE,
        _HEADER,
        [1, "SRTWB247", "S", "SPEC-A", "盆小孔", 2, 2, 0.03, "REMARK-A"],
        [2, None, "M", None, None, 12, None, None, None],
    ]
    merges = ["B3:B4"]
    return merged_workbook(rows, merges)


def test_ac_m9_a_vertically_merged_model_still_fills_through():
    out = read_workbook(vertical_model_merge_workbook(), resolver())

    assert [r.item_code for r in out.rows] == ["SRTWB247", "SRTWB247"]
