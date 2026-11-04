"""PS-QUOTE-MATRIX engine: pure rules of ``app/services/quotation_matrix.py``.

Written BEFORE the implementation (Phase 2, test-first). Contract:
``documentation/plans/project-sales/PLAN-ps-quote-matrix-02nov.md`` ("Contract (Phase 2 ...)").
Examples E1 and E3 come from ``CARD-ps-quote-matrix-02nov.md``. No database is used here.

The coder implements exactly these names in ``app/services/quotation_matrix.py``:

    validate_columns(columns) -> list
        None or [] gives []. Otherwise returns the columns with every label trimmed.
        Raises AppException(422, code="quotation_columns_invalid").
    leaf_keys(columns) -> list[str]
        The quantity columns in order: a header's col keys, or the header's own key when it
        has no cols.
    normalise_cells(columns, cells) -> dict | None
        Decimal strings with 2 dp, zero and blank dropped, {} stored as None. Unknown key,
        negative, or above 9,999,999.99 raises AppException(422, code="quotation_cells_invalid").
        With no columns, any non-empty cells raise the same error.
    cells_total(cells) -> Decimal
        Sum of the cells (Decimal("0") for None / {}).
    cell_label(columns, key) -> str | None
        "<header> / <col>" for a col, the header label for a header's own leaf, None when the
        key is not a leaf.
    matrix_summary(columns, lines) -> dict
        ``lines`` are objects with ``qty_cells``, ``unit_price`` and ``is_rate_only``.
        Returns:
          {"leaf_keys": [...],
           "pair_headers": [header keys that get a QTY/AMOUNT pair],
           "rows": [{"pairs": {header_key: {"qty": Decimal, "amount": Decimal}},
                     "total_qty": Decimal, "amount": Decimal}, ...],   # one per line, in order
           "footer": {"leaf_qty": {leaf_key: Decimal},
                      "pair_qty": {header_key: Decimal},
                      "pair_amount": {header_key: Decimal},
                      "total_qty": Decimal, "total_amount": Decimal}}
        A header gets a pair only when there are >= 2 headers AND that header has >= 2 cols.
        A rate-only line has amount 0 (and adds nothing to any footer amount).
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.error_handler import AppException


def _engine():
    from app.services import quotation_matrix

    return quotation_matrix


def _col(key, label=None):
    return {"key": key, "label": label or key.upper()}


def _hdr(key, cols=(), label=None):
    return {"key": key, "label": label or key.upper(), "cols": [_col(c) for c in cols]}


def _refused(call, code="quotation_columns_invalid"):
    with pytest.raises(AppException) as refused:
        call()
    assert refused.value.status_code == 422, refused.value.detail
    assert refused.value.detail["code"] == code
    return refused.value


# ------------------------------------------------------------------ validate_columns


def test_no_columns_is_an_empty_layout():
    eng = _engine()
    assert eng.validate_columns(None) == []
    assert eng.validate_columns([]) == []


def test_a_valid_layout_comes_back_with_labels_trimmed():
    eng = _engine()
    columns = [
        {"key": "type-a", "label": "  TYPE A - 1 BH ", "cols": [{"key": "a_kit", "label": " KITCHEN "}]}
    ]
    assert eng.validate_columns(columns) == [
        {"key": "type-a", "label": "TYPE A - 1 BH", "cols": [{"key": "a_kit", "label": "KITCHEN"}]}
    ]


@pytest.mark.parametrize(
    "key", ["", "Upper", "has space", "-lead", "_lead", "a" * 41, "dot.key", "tab\tkey"]
)
def test_a_key_outside_the_pattern_is_refused_on_a_header_and_on_a_col(key):
    eng = _engine()
    _refused(lambda: eng.validate_columns([_hdr(key)]))
    _refused(lambda: eng.validate_columns([{"key": "h1", "label": "H", "cols": [_col(key)]}]))


@pytest.mark.parametrize("key", ["a", "0", "a-b_c", "a" * 40, "9lives"])
def test_a_key_inside_the_pattern_is_accepted(key):
    eng = _engine()
    assert eng.leaf_keys(eng.validate_columns([_hdr(key)])) == [key]


def test_keys_are_unique_across_headers_and_cols_together():
    eng = _engine()
    _refused(lambda: eng.validate_columns([_hdr("h1"), _hdr("h1")]))
    _refused(lambda: eng.validate_columns([_hdr("h1", ["c1", "c1"])]))
    _refused(lambda: eng.validate_columns([_hdr("h1", ["c1"]), _hdr("h2", ["c1"])]))
    # A header key may not equal a col key of another header either.
    _refused(lambda: eng.validate_columns([_hdr("h1", ["h2"]), _hdr("h2")]))


@pytest.mark.parametrize("label", ["", "   ", None])
def test_a_blank_label_is_refused(label):
    eng = _engine()
    _refused(lambda: eng.validate_columns([{"key": "h1", "label": label, "cols": []}]))
    _refused(
        lambda: eng.validate_columns(
            [{"key": "h1", "label": "H", "cols": [{"key": "c1", "label": label}]}]
        )
    )


def test_a_label_is_one_to_sixty_characters_after_trimming():
    eng = _engine()
    ok = eng.validate_columns([{"key": "h1", "label": "x" * 60, "cols": []}])
    assert ok[0]["label"] == "x" * 60
    ok = eng.validate_columns([{"key": "h1", "label": " " + "x" * 60 + " ", "cols": []}])
    assert ok[0]["label"] == "x" * 60
    _refused(lambda: eng.validate_columns([{"key": "h1", "label": "x" * 61, "cols": []}]))


def test_the_limits_are_40_headers_60_cols_per_header_and_200_leaves():
    eng = _engine()
    forty = [_hdr(f"h{i}") for i in range(40)]
    assert len(eng.leaf_keys(eng.validate_columns(forty))) == 40
    _refused(lambda: eng.validate_columns([*forty, _hdr("h40")]))

    sixty = [_hdr("h1", [f"c{i}" for i in range(60)])]
    assert len(eng.leaf_keys(eng.validate_columns(sixty))) == 60
    _refused(lambda: eng.validate_columns([_hdr("h1", [f"c{i}" for i in range(61)])]))

    # 40 headers x 5 cols = 200 leaves is the ceiling; one more col is refused.
    at_ceiling = [_hdr(f"h{i}", [f"h{i}c{j}" for j in range(5)]) for i in range(40)]
    assert len(eng.leaf_keys(eng.validate_columns(at_ceiling))) == 200
    over = [_hdr(f"h{i}", [f"h{i}c{j}" for j in range(5)]) for i in range(40)]
    over[0]["cols"].append(_col("extra"))
    _refused(lambda: eng.validate_columns(over))


def test_a_malformed_shape_is_refused_with_the_columns_code():
    eng = _engine()
    _refused(lambda: eng.validate_columns("nope"))
    _refused(lambda: eng.validate_columns([{"label": "no key", "cols": []}]))
    _refused(lambda: eng.validate_columns([{"key": "h1", "label": "H", "cols": "x"}]))


# ------------------------------------------------------------------ leaf_keys / cell_label


def test_leaves_follow_header_order_and_a_header_without_cols_is_one_leaf():
    eng = _engine()
    columns = [
        _hdr("lvl9", ["r1", "r2"], label="LEVEL 9"),
        _hdr("tank", [], label="BREAK TANK"),
        _hdr("lobby", ["l1"], label="LOBBY A"),
    ]
    assert eng.leaf_keys(columns) == ["r1", "r2", "tank", "l1"]
    assert eng.leaf_keys([]) == []
    assert eng.leaf_keys(None) == []


def test_cell_label_is_header_slash_col_or_the_header_label_for_its_own_leaf():
    eng = _engine()
    columns = [
        {"key": "ta", "label": "TYPE A", "cols": [{"key": "ta_kit", "label": "KITCHEN"}]},
        {"key": "tank", "label": "BREAK TANK", "cols": []},
    ]
    assert eng.cell_label(columns, "ta_kit") == "TYPE A / KITCHEN"
    assert eng.cell_label(columns, "tank") == "BREAK TANK"
    assert eng.cell_label(columns, "ta") is None  # a header with cols is not a leaf
    assert eng.cell_label(columns, "ghost") is None


# ------------------------------------------------------------------ normalise_cells


COLS = [_hdr("a", ["a1", "a2"]), _hdr("b", ["b1", "b2"])]


def test_cells_are_stored_as_two_decimal_strings_with_zero_and_blank_dropped():
    eng = _engine()
    got = eng.normalise_cells(COLS, {"a1": 120, "a2": "250.5", "b1": "0", "b2": ""})
    assert got == {"a1": "120.00", "a2": "250.50"}
    assert eng.normalise_cells(COLS, {"a1": Decimal("3.456")}) in ({"a1": "3.46"}, {"a1": "3.45"})
    assert eng.normalise_cells(COLS, {"a1": None}) is None


def test_empty_cells_are_stored_as_none():
    eng = _engine()
    assert eng.normalise_cells(COLS, {}) is None
    assert eng.normalise_cells(COLS, None) is None
    assert eng.normalise_cells(COLS, {"a1": 0, "a2": ""}) is None
    assert eng.normalise_cells([], {}) is None
    assert eng.normalise_cells([], None) is None


def test_an_unknown_key_a_negative_or_a_too_large_cell_is_refused():
    eng = _engine()
    code = "quotation_cells_invalid"
    _refused(lambda: eng.normalise_cells(COLS, {"ghost": 1}), code)
    _refused(lambda: eng.normalise_cells(COLS, {"a": 1}), code)  # a header key with cols is no leaf
    _refused(lambda: eng.normalise_cells(COLS, {"a1": -1}), code)
    _refused(lambda: eng.normalise_cells(COLS, {"a1": "-0.01"}), code)
    _refused(lambda: eng.normalise_cells(COLS, {"a1": "10000000.00"}), code)
    _refused(lambda: eng.normalise_cells(COLS, {"a1": "abc"}), code)
    assert eng.normalise_cells(COLS, {"a1": "9999999.99"}) == {"a1": "9999999.99"}


def test_cells_without_columns_are_refused_unless_empty():
    eng = _engine()
    _refused(lambda: eng.normalise_cells([], {"a1": 1}), "quotation_cells_invalid")


def test_cells_total_is_the_sum_and_zero_when_none():
    eng = _engine()
    assert eng.cells_total({"a1": "120.00", "a2": "250.50"}) == Decimal("370.50")
    assert eng.cells_total(None) == Decimal("0")
    assert eng.cells_total({}) == Decimal("0")


# ------------------------------------------------------------------ matrix_summary


def _line(cells, price, rate_only=False):
    return SimpleNamespace(
        qty_cells=cells, unit_price=Decimal(price), is_rate_only=rate_only, quantity=None
    )


E1_COLUMNS = [
    _hdr("ta", ["ta_bh", "ta_kit", "ta_yard", "ta_bal"], label="TYPE A - 1 BH"),
    _hdr("tb", ["tb_bh", "tb_kit", "tb_yard", "tb_bal"], label="TYPE B - 2 BH"),
    _hdr("tc", ["tc_bh", "tc_kit", "tc_yard", "tc_bal"], label="TYPE C - 3 BH"),
]


def test_e1_the_floor_trap_row_pairs_and_totals():
    eng = _engine()
    trap = _line(
        {
            "ta_bh": "120.00",
            "ta_bal": "120.00",
            "tb_bh": "500.00",
            "tb_bal": "250.00",
            "tc_bh": "399.00",
            "tc_bal": "133.00",
        },
        "45.00",
    )
    summary = eng.matrix_summary(E1_COLUMNS, [trap])
    assert summary["pair_headers"] == ["ta", "tb", "tc"]
    (row,) = summary["rows"]
    assert row["pairs"]["ta"]["qty"] == Decimal("240")
    assert row["pairs"]["ta"]["amount"] == Decimal("10800.00")
    assert row["pairs"]["tb"]["qty"] == Decimal("750")
    assert row["pairs"]["tb"]["amount"] == Decimal("33750.00")
    assert row["pairs"]["tc"]["qty"] == Decimal("532")
    assert row["pairs"]["tc"]["amount"] == Decimal("23940.00")
    assert row["total_qty"] == Decimal("1522")
    assert row["amount"] == Decimal("68490.00")

    footer = summary["footer"]
    assert footer["leaf_qty"]["ta_bh"] == Decimal("120")
    assert footer["leaf_qty"]["ta_kit"] == Decimal("0")
    assert footer["leaf_qty"]["tc_bal"] == Decimal("133")
    assert footer["pair_qty"] == {"ta": Decimal("240"), "tb": Decimal("750"), "tc": Decimal("532")}
    assert footer["pair_amount"]["tb"] == Decimal("33750.00")
    assert footer["total_qty"] == Decimal("1522")
    assert footer["total_amount"] == Decimal("68490.00")


def test_e2_a_row_with_a_blank_header_has_a_zero_pair_for_it():
    eng = _engine()
    basin = _line({"tb_bh": "250.00", "tc_bh": "266.00"}, "180.00")
    (row,) = eng.matrix_summary(E1_COLUMNS, [basin])["rows"]
    assert row["pairs"]["ta"]["qty"] == Decimal("0")
    assert row["pairs"]["ta"]["amount"] == Decimal("0")
    assert row["total_qty"] == Decimal("516")
    assert row["amount"] == Decimal("92880.00")


E3_COLUMNS = [
    _hdr("l9", [f"l9r{i}" for i in range(11)], label="LEVEL 9"),
    _hdr("lba", [f"lba{i}" for i in range(4)], label="LOBBY A (LEVEL 1)"),
    _hdr("lbb", [f"lbb{i}" for i in range(4)], label="LOBBY B (LEVEL 2)"),
    _hdr("tank", [], label="BREAK TANK"),
]


def test_e3_a_header_without_cols_gets_no_pair_and_the_others_do():
    eng = _engine()
    wc = _line(
        {"l9r0": 4, "l9r1": 3, "lba0": 3, "lbb0": 3},
        "600.00",
    )
    summary = eng.matrix_summary(E3_COLUMNS, [wc])
    assert summary["pair_headers"] == ["l9", "lba", "lbb"]
    assert "tank" not in summary["rows"][0]["pairs"]
    assert "tank" not in summary["footer"]["pair_qty"]
    assert "tank" not in summary["footer"]["pair_amount"]
    (row,) = summary["rows"]
    assert row["pairs"]["l9"] == {"qty": Decimal("7"), "amount": Decimal("4200.00")}
    assert row["pairs"]["lba"] == {"qty": Decimal("3"), "amount": Decimal("1800.00")}
    assert row["pairs"]["lbb"] == {"qty": Decimal("3"), "amount": Decimal("1800.00")}
    assert row["total_qty"] == Decimal("13")
    assert row["amount"] == Decimal("7800.00")
    # The BREAK TANK leaf is still a quantity column and is in the footer per leaf.
    assert summary["footer"]["leaf_qty"]["tank"] == Decimal("0")


def test_a_single_header_scope_gets_no_pairs_even_with_many_cols():
    eng = _engine()
    columns = [_hdr("only", ["c1", "c2", "c3"])]
    summary = eng.matrix_summary(columns, [_line({"c1": 2, "c2": 3}, "10.00")])
    assert summary["pair_headers"] == []
    assert summary["rows"][0]["pairs"] == {}
    assert summary["rows"][0]["total_qty"] == Decimal("5")
    assert summary["rows"][0]["amount"] == Decimal("50.00")


def test_a_header_with_one_col_gets_no_pair_when_others_have_many():
    eng = _engine()
    columns = [_hdr("one", ["c1"]), _hdr("many", ["m1", "m2"])]
    summary = eng.matrix_summary(columns, [_line({"c1": 1, "m1": 1}, "5.00")])
    assert summary["pair_headers"] == ["many"]


def test_a_rate_only_line_has_amount_zero_and_adds_to_no_footer_amount():
    eng = _engine()
    columns = [_hdr("a", ["a1", "a2"]), _hdr("b", ["b1", "b2"])]
    priced = _line({"a1": 10, "b1": 5}, "20.00")
    alternate = _line({"a1": 7, "b1": 7}, "99.00", rate_only=True)
    summary = eng.matrix_summary(columns, [priced, alternate])
    first, second = summary["rows"]
    assert first["amount"] == Decimal("300.00")
    assert second["amount"] == Decimal("0")
    assert second["pairs"]["a"]["amount"] == Decimal("0")
    assert second["pairs"]["b"]["amount"] == Decimal("0")
    assert summary["footer"]["total_amount"] == Decimal("300.00")
    assert summary["footer"]["pair_amount"] == {"a": Decimal("200.00"), "b": Decimal("100.00")}


def test_footer_sums_every_row_per_leaf_per_pair_and_overall():
    eng = _engine()
    columns = [_hdr("a", ["a1", "a2"]), _hdr("b", ["b1", "b2"])]
    lines = [
        _line({"a1": 10, "a2": 5, "b1": 1}, "10.00"),
        _line({"a1": 2, "b2": 4}, "100.00"),
    ]
    footer = eng.matrix_summary(columns, lines)["footer"]
    assert footer["leaf_qty"] == {
        "a1": Decimal("12"),
        "a2": Decimal("5"),
        "b1": Decimal("1"),
        "b2": Decimal("4"),
    }
    assert footer["pair_qty"] == {"a": Decimal("17"), "b": Decimal("5")}
    assert footer["pair_amount"] == {"a": Decimal("350.00"), "b": Decimal("410.00")}
    assert footer["total_qty"] == Decimal("22")
    assert footer["total_amount"] == Decimal("760.00")


def test_a_line_with_no_cells_is_all_zero():
    eng = _engine()
    summary = eng.matrix_summary(COLS, [_line(None, "50.00")])
    assert summary["rows"][0]["total_qty"] == Decimal("0")
    assert summary["rows"][0]["amount"] == Decimal("0")
    assert summary["footer"]["total_amount"] == Decimal("0")
