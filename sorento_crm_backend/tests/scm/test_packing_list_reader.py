"""S9 AC-G1/G2 - one shipment per container block, whichever shape the file is written in.

The resolver is built from the alias rows migration 311 seeds, so the Chinese spellings under
test are the ones actually agreed with the supplier rather than ones invented here.
"""
from __future__ import annotations

from io import BytesIO

import pytest

from app.services.import_alias_service import AliasResolver, normalize_header
from app.services.scm.packing_list_reader import DOC_TYPE, read_workbook

#: The aliases migration 311 seeds for `packing_list`, so this suite fails if that seed changes
#: under it rather than passing against a mapping only the test believes in.
_ALIASES = [
    ("item_code", "产品型号"),
    ("product_name", "品名"),
    ("spec", "规格"),
    ("qty", "数量"),
    ("cartons", "箱数"),
    ("net_weight", "净重"),
    ("gross_weight", "毛重"),
    ("cbm_per_unit", "体积(cbm)"),
    ("cbm_total", "总体积(cbm)"),
    ("unit_price", "RMB"),
    ("amount", "金额（rmb）"),
    ("brand", "商标"),
    ("container_no", "货柜号"),
    ("bl_no", "提单号"),
    ("remark", "备注"),
]


@pytest.fixture()
def resolver() -> AliasResolver:
    mapping: dict[str, str] = {}
    for field, alias in _ALIASES:
        mapping.setdefault(normalize_header(alias), field)
        mapping.setdefault(normalize_header(field), field)
    return AliasResolver(DOC_TYPE, mapping)


def workbook(rows: list[list]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


HEADER = ["产品型号", "品名", "数量", "箱数", "体积(cbm)"]


def _block(container: str, items: list[tuple[str, float]]) -> list[list]:
    out: list[list] = [[f"货柜号：{container}"], HEADER]
    out.extend([code, "座厕", qty, 2, 0.21] for code, qty in items)
    out.append([])
    return out


def test_several_stacked_blocks_become_several_shipments(resolver):
    # AC-G1. The file is not one table; it is one per container, stacked.
    rows: list[list] = []
    for i, container in enumerate(["ABCU1000001", "ABCU1000002", "ABCU1000003"], start=1):
        rows.extend(_block(container, [(f"SRT-{i}A", 10), (f"SRT-{i}B", 20)]))

    out = read_workbook(workbook(rows), resolver)

    assert out.ok
    assert [b.container_no for b in out.blocks] == [
        "ABCU1000001", "ABCU1000002", "ABCU1000003",
    ]
    assert [len(b.lines) for b in out.blocks] == [2, 2, 2]
    assert out.line_count == 6


def test_a_block_carries_its_own_bill_of_lading(resolver):
    rows = [
        ["货柜号：ABCU1000001"], ["提单号：BL-778"], HEADER,
        ["SRT-1", "座厕", 5, 1, 0.2],
    ]

    out = read_workbook(workbook(rows), resolver)

    assert out.blocks[0].container_no == "ABCU1000001"
    assert out.blocks[0].bl_no == "BL-778"


def test_a_pre_load_list_with_no_container_and_no_bill_of_lading_still_reads(resolver):
    # AC-G2. At pre-load stage the container has not been assigned. A reader that insisted on
    # one would reject the exact file this feature exists to read.
    rows = [HEADER, ["SRT-1", "座厕", 5, 1, 0.2], ["SRT-2", "面盆", 7, 2, 0.3]]

    out = read_workbook(workbook(rows), resolver)

    assert out.ok
    assert len(out.blocks) == 1
    assert out.blocks[0].container_no is None
    assert out.blocks[0].bl_no is None
    assert out.blocks[0].total_qty == 12


def test_the_label_may_be_two_cells_rather_than_one(resolver):
    rows = [["货柜号", "ABCU1000009"], HEADER, ["SRT-1", "座厕", 5, 1, 0.2]]

    out = read_workbook(workbook(rows), resolver)

    assert out.blocks[0].container_no == "ABCU1000009"


def test_one_table_with_a_container_column_splits_into_blocks(resolver):
    # The other shape in the wild: a single table whose rows name their own container.
    header = ["货柜号", "产品型号", "数量"]
    rows = [
        header,
        ["ABCU1", "SRT-1", 5],
        ["ABCU1", "SRT-2", 6],
        ["ABCU2", "SRT-3", 7],
    ]

    out = read_workbook(workbook(rows), resolver)

    assert [b.container_no for b in out.blocks] == ["ABCU1", "ABCU2"]
    assert [len(b.lines) for b in out.blocks] == [2, 1]


def test_a_single_container_reads_as_one_block_in_either_shape(resolver):
    # The two readings must not disagree about the simple case, or the same file imports as one
    # shipment or two depending on how the supplier chose to write it.
    stacked = read_workbook(workbook(_block("ABCU1", [("SRT-1", 5)])), resolver)
    columnar = read_workbook(
        workbook([["货柜号", "产品型号", "数量"], ["ABCU1", "SRT-1", 5]]), resolver
    )

    assert len(stacked.blocks) == len(columnar.blocks) == 1
    assert stacked.blocks[0].container_no == columnar.blocks[0].container_no == "ABCU1"


def test_a_labelled_item_code_does_not_start_a_block(resolver):
    # `产品型号: SRT-1` resolves the item-code alias. Treating that as a header would start a
    # block whose header row is its own data, and the real table would then be read as lines of
    # a one-column table. A header names an item column AND a quantity column.
    rows = [["产品型号：SRT-9"], HEADER, ["SRT-1", "座厕", 5, 1, 0.2]]

    out = read_workbook(workbook(rows), resolver)

    assert len(out.blocks) == 1
    assert [ln.item_code for ln in out.blocks[0].lines] == ["SRT-1"]


def test_per_unit_volume_falls_back_to_the_line_total(resolver):
    # The supplier writes both columns and fills only one about half the time.
    header = ["产品型号", "数量", "总体积(cbm)"]
    out = read_workbook(workbook([header, ["SRT-1", 4, 0.84]]), resolver)

    assert out.blocks[0].lines[0].cbm_per_unit == 0.21
    assert out.blocks[0].lines[0].cbm_total == 0.84


def test_an_unmeasured_line_stays_unmeasured_rather_than_zero(resolver):
    out = read_workbook(workbook([["产品型号", "数量"], ["SRT-1", 4]]), resolver)

    assert out.blocks[0].lines[0].cbm_per_unit is None


def test_a_row_with_no_quantity_is_skipped_not_guessed(resolver):
    out = read_workbook(workbook([HEADER, ["SRT-1", "座厕", None, 1, 0.2],
                                  ["SRT-2", "面盆", 3, 1, 0.2]]), resolver)

    assert [ln.item_code for ln in out.blocks[0].lines] == ["SRT-2"]


def test_a_file_with_no_recognisable_header_says_what_is_missing(resolver):
    out = read_workbook(workbook([["something", "else"], ["a", "b"]]), resolver)

    assert not out.ok
    assert set(out.missing_columns) == {"item_code", "qty"}


def test_a_header_with_nothing_under_it_is_not_a_container(resolver):
    # The shape of an empty template. Importing it would create a shipment with no lines.
    rows = [["货柜号：ABCU1"], HEADER, [], ["货柜号：ABCU2"], HEADER, ["SRT-1", "座厕", 5, 1, 0.2]]

    out = read_workbook(workbook(rows), resolver)

    assert len(out.blocks) == 1
    assert out.blocks[0].container_no == "ABCU2"


def test_blocks_remember_where_they_started(resolver):
    # A pre-load block has no container number, so its position in the file is part of what
    # tells two of them apart.
    rows = _block("", [("SRT-1", 5)]) + _block("", [("SRT-2", 6)])
    out = read_workbook(workbook(rows), resolver)

    assert len(out.blocks) == 2
    assert out.blocks[0].header_row < out.blocks[1].header_row


def test_the_seeded_aliases_are_the_ones_this_suite_assumes():
    """The mapping above is a copy. This is the check that it is still a true one.

    Every other test here builds its own resolver, which makes them fast and database-free and
    also makes them agree with a mapping only they believe in. Running migration 311's own
    seeder proves the Chinese spellings under test are the ones the supplier actually agreed.
    """
    import importlib.util

    from tests._pg_fixture import pg_session

    spec = importlib.util.spec_from_file_location(
        "m311", "alembic/versions/311_scm_purchasing_base.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    seeded = {
        (doc, field, alias)
        for doc, field, alias, _lang in m._ALIASES
        if doc == DOC_TYPE
    }
    assert seeded, "migration 311 seeds no packing_list aliases"

    for field, alias in _ALIASES:
        assert (DOC_TYPE, field, alias) in seeded, f"{field}/{alias} is not seeded"
