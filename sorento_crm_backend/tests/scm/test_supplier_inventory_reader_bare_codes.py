"""Stock list bare model codes (S1, `PLAN-stock-list-bare-model-codes.md`) - what the READER
does with a supplier who writes a bare 型号 (`^[-0-9]`), and the proof that a letter-led one
takes today's path byte for byte (D1/D2/AC-R3).

TEST-FIRST (Phase 2): `read_workbook` does not yet accept a `words` keyword, so every test
below is expected to be RED with a `TypeError` (unexpected keyword `words`) until S1 lands.

Fix round 1 (review round 1, item 8): `InventoryRow.model_no` was dropped (no consumer read
it) - every `r.model_no` assertion below was removed, noted at each site.

AC-R8 (the existing reader suites stay green with a word list supplied) is proven by running
`test_supplier_inventory_reader.py` and `test_supplier_inventory_reader_merged_cells.py`
alongside this file, not restated here - re-asserting them would only pin a copy that could
drift from the original.
"""
from __future__ import annotations

from io import BytesIO

from app.services.import_alias_service import AliasResolver, normalize_header
from app.services.scm.supplier_code_composer import WordList
from app.services.scm.supplier_inventory_reader import read_workbook

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


def d7_words() -> WordList:
    return WordList(
        {
            "SORENTO": "SRT",
            "S": "SRT",
            "CABANA": "C",
            "MOCHA": "M",
            "连体马桶": "WC",
            "分体马桶": "WC",
            "座头": "WCX",
            "分体座头": "WCX",
            "水箱": "WCY",
            "盆": "WB",
            "盆小孔": "WB",
            "盖板": "SC",
            "横排": "P",
        }
    )


def workbook(rows: list[list]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def merged_workbook(rows: list[list], merges: list[str]) -> bytes:
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


HEADER = ["型号", "品名", "商标", "规格", "包装好库存", "空瓷", "体积(cbm)", "备注"]


def test_ac_r1_a_merged_bare_model_fills_item_code_on_every_covered_row():
    # 型号/品名/商标 are one merged family (B16:B17-style, the owner's `8613` example);
    # 规格 is each row's own text, so the four siblings compose to four different codes.
    data = merged_workbook(
        [
            HEADER,
            ["8613", "连体马桶", "SORENTO", "250mm", 5, 0, 0.2, ""],
            [None, None, None, "横排180mm", 12, 0, None, None],
        ],
        merges=["A2:A3", "B2:B3", "C2:C3"],
    )

    out = read_workbook(data, resolver(), words=d7_words())

    assert out.ok
    assert [r.item_code for r in out.rows] == ["SRTWC8613-250", "SRTWC8613-P-180"]
    # (item 8: `r.model_no` assertion removed - the field no longer exists)


def test_ac_r2_a_covered_row_with_stock_and_a_merged_model_no_longer_complains():
    data = merged_workbook(
        [
            HEADER,
            ["8613", "连体马桶", "SORENTO", "250mm", 5, 0, 0.2, ""],
            [None, None, None, "横排180mm", 12, 0, None, None],
        ],
        merges=["A2:A3", "B2:B3", "C2:C3"],
    )

    out = read_workbook(data, resolver(), words=d7_words())

    assert out.problems == []
    assert len(out.rows) == 2


def test_ac_r1_a_merge_anchored_on_the_header_never_fills_item_code():
    # The 型号 caption itself merged down into the first data rows - never a model's own
    # value, so those rows carry no model number at all.
    data = merged_workbook(
        [
            ["型号", "包装好库存"],
            [None, 10],
            [None, 20],
        ],
        merges=["A1:A3"],
    )

    out = read_workbook(data, resolver(), words=d7_words())

    assert out.rows == []
    assert len(out.problems) == 2


def test_ac_r3_letter_led_model_ignores_the_word_list_entirely():
    # `SRTWC8357-RL-250` with 规格 `250` stays `SRTWC8357-RL-250` (D1/D2's regression guard) -
    # a word list is supplied here on purpose, to prove it is never even consulted.
    data = workbook(
        [HEADER, ["SRTWC8357-RL-250", "连体马桶", "SORENTO", "250", 5, 0, 0.2, ""]]
    )

    out = read_workbook(data, resolver(), words=d7_words())

    assert out.rows[0].item_code == "SRTWC8357-RL-250"
    # (item 8: `r.model_no` assertion removed - the field no longer exists)


def test_ac_r3_a_letter_led_model_composes_the_same_with_no_word_list_at_all():
    data = workbook([HEADER, ["SRTWC8613", "座厕", "SORENTO", "250", 5, 0, 0.2, ""]])

    out = read_workbook(data, resolver(), words=None)

    assert out.rows[0].item_code == "SRTWC8613"


# AC-R4: bare 型号, every word known - item_code composes.
_CASES = [
    ("8613", "连体马桶", "SORENTO", "250mm", "SRTWC8613-250"),
    ("8613", "连体马桶", "SORENTO", "横排180mm", "SRTWC8613-P-180"),
    ("8066-PP", "连体马桶", "SORENTO", "150mm", "SRTWC8066-PP-150"),
    ("-7055", "盆", "SORENTO", None, "SRTWB7055"),
    ("8605-RL", "水箱", "SORENTO", None, "SRTWCY8605-RL"),
    ("1009", "分体马桶", "CABANA", "250mm", "CWC1009-250"),
    ("888", "盆", "SORENTO", "600*450*200mm", "SRTWB888"),
    ("8613", "连体马桶", "S", "250mm", "SRTWC8613-250"),
]


def test_ac_r4_bare_model_composes_through_the_reader():
    rows = [
        [model, name, brand, spec, 1, 0, 0.1, ""]
        for model, name, brand, spec, _expected in _CASES
    ]
    data = workbook([HEADER] + rows)

    out = read_workbook(data, resolver(), words=d7_words())

    assert [r.item_code for r in out.rows] == [expected for *_, expected in _CASES]
    # (item 8: `r.model_no` assertion removed - the field no longer exists)


def test_ac_r5_bare_model_with_a_blank_brand_falls_back_to_the_raw_join():
    data = workbook([HEADER, ["7609对冲", "连体马桶", None, "150mm", 1, 0, 0.1, ""]])

    out = read_workbook(data, resolver(), words=d7_words())

    assert out.rows[0].item_code == "7609对冲 150mm 连体马桶"
    # (item 8: `r.model_no` assertion removed - the field no longer exists)


def test_ac_r5_bare_model_with_an_unknown_cjk_run_falls_back_to_the_raw_join():
    data = workbook([HEADER, ["7604-RL高压", "座头", "CABANA", "横排180mm", 1, 0, 0.1, ""]])

    out = read_workbook(data, resolver(), words=d7_words())

    assert out.rows[0].item_code == "7604-RL高压 横排180mm CABANA 座头"
    # (item 8: `r.model_no` assertion removed - the field no longer exists)


def test_read_workbook_still_needs_a_resolver_or_a_session_with_words_supplied():
    import pytest

    with pytest.raises(ValueError):
        read_workbook(b"", None, words=d7_words())


def test_a_raw_join_key_over_100_characters_is_a_row_problem_not_a_row():
    # Review round 1, item 7: neither `product_code` nor
    # `supplier_product_code_alias.supplier_code` can hold a key this long, so the row
    # waits as a named problem rather than 500ing the insert - a blank brand aborts
    # composition here, forcing the (long) raw join.
    long_model = "7609" + "对冲" * 50  # far past MAX_KEY_LENGTH once joined with the rest
    data = workbook([HEADER, [long_model, "连体马桶", None, "150mm", 1, 0, 0.1, ""]])

    out = read_workbook(data, resolver(), words=d7_words())

    assert out.rows == []
    assert len(out.problems) == 1
    assert "too long" in out.problems[0].reason
