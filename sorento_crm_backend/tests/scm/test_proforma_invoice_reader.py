"""AC-P2 - the proforma reader reads both real shapes, against real-shape fixtures.

TEST-FIRST: `app/services/scm/proforma_invoice_reader.py` does not exist yet at the time
this file is written. Every test here is expected to be red (ImportError) until the
reader lands, then green against the exact numbers the two real files produce.

The resolver is built from the aliases migration 374 seeds (mirrored below as `_ALIASES`,
same style as `test_packing_list_reader.py`), so the Chinese/English spellings under test
are the ones actually agreed with the two suppliers rather than ones invented here. A
migration-import check pins that the copy is a true one.

Fixture builders live in `tests/scm/fixtures/proforma_shapes.py` and reproduce the two
real files (Jinbaichuan pre-loading list, Kailu single proforma) cell-for-cell.

AC-P2.5 (a document with no stated number gets a derived, positional, re-upload-stable
`PI-<file stem>-<block index>`) is NOT asserted here: deriving it needs a filename, and
`read_workbook` (per the pinned signature) does not take one. That mirrors
`packing_list_reader`, whose blocks likewise carry no shipment name of their own -
`packing_list_service.shipment_number_for` derives it from `source_ref` at the SERVICE
layer. This suite instead pins that an UNSTATED pi_number reads as `None` (never
invented in the reader); the derived, positional name is pinned in
`tests/scm/test_proforma_invoice_import.py` against the applied header.
"""
from __future__ import annotations

import os
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest

from app.services.import_alias_service import AliasResolver, normalize_header
from app.services.scm.proforma_invoice_reader import DOC_TYPE, read_workbook
from tests.scm.fixtures.proforma_shapes import (
    kailu_proforma_workbook,
    preloading_list_workbook,
)

#: The aliases migration 374 seeds for `proforma_invoice`, so this suite fails if that
#: seed changes under it rather than passing against a mapping only the test believes in.
#: Copied verbatim from PLAN-scm-proforma-invoice.md's Aliases table.
_ALIASES = [
    ("item_code", "产品型号"),
    ("item_code", "编号"),
    ("item_code", "型号"),
    ("item_code", "ITEM CODE"),
    ("item_code", "MODEL"),
    ("item_code", "Item No"),
    ("description", "品名"),
    ("description", "DESCRIPTION"),
    ("description", "Description"),
    ("description", "货名"),
    ("spec", "规格"),
    ("qty", "数量"),
    ("qty", "产品数量"),
    ("qty", "QTY"),
    ("qty", "Quantity"),
    ("uom", "单位"),
    ("uom", "UOM"),
    ("uom", "Unit"),
    ("unit_price", "RMB"),
    ("unit_price", "单价(元)"),
    ("unit_price", "单价"),
    ("unit_price", "UNIT PRICE"),
    ("unit_price", "Unit Price"),
    ("unit_price", "PRICE"),
    ("amount", "金额（rmb）"),
    ("amount", "金额"),
    ("amount", "总价（元）"),
    ("amount", "总价"),
    ("amount", "AMOUNT"),
    ("amount", "Amount"),
    ("amount", "TOTAL"),
    ("po_ref", "其他"),
    ("po_ref", "PO NO"),
    ("po_ref", "PO No."),
    ("po_ref", "PO"),
    ("po_ref", "订单号"),
    ("po_ref", "客户订单号"),
    ("po_ref", "Order No"),
    ("remark", "备注"),
    ("remark", "REMARK"),
    ("remark", "Remarks"),
    ("brand", "商标"),
    ("cartons", "箱数"),
    ("pi_number", "货单号"),
    ("pi_number", "发票号"),
    ("pi_number", "PI NO"),
    ("pi_number", "Invoice No"),
    ("pi_number", "Proforma No"),
    ("pi_number", "PI No."),
    ("invoice_date", "日期"),
    ("invoice_date", "Date"),
    ("invoice_date", "Date 日期"),
    ("invoice_date", "Invoice Date"),
    ("container_no", "货柜号"),
    ("container_no", "Container No"),
    ("container_no", "Container No 货柜号"),
    ("bl_no", "提单号"),
    ("bl_no", "B/L NO"),
    ("bl_no", "BL No"),
    ("currency", "币种"),
    ("currency", "Currency"),
    ("currency", "CURRENCY"),
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


# --------------------------------------------------------------------------------- #
# AC-P2.2 - Jinbaichuan multi-block pre-loading list
# --------------------------------------------------------------------------------- #


def test_the_preloading_list_reads_as_5_documents_30_priced_lines(resolver):
    out = read_workbook(preloading_list_workbook(), resolver)

    assert out.ok
    assert len(out.documents) == 5
    assert sum(len(d.lines) for d in out.documents) == 30

    for doc in out.documents:
        assert doc.invoice_date == date(2026, 7, 31)
        assert doc.currency_hint == "CNY"
        assert doc.container_no is None
        # No PI number is stated anywhere in this file; the reader never invents one.
        assert doc.pi_number is None
        for line in doc.lines:
            assert line.unit_price is not None
            assert line.amount is not None


def test_the_preloading_list_states_no_bill_of_lading(resolver):
    # AC-P2.2. "提单号：" is present as a label on every block but always blank.
    out = read_workbook(preloading_list_workbook(), resolver)

    assert [doc.bl_no for doc in out.documents] == [None] * 5


def test_preloading_list_block_line_counts_match_the_real_file(resolver):
    out = read_workbook(preloading_list_workbook(), resolver)

    assert [len(d.lines) for d in out.documents] == [1, 1, 19, 5, 4]


# --------------------------------------------------------------------------------- #
# AC-P2.3 - Kailu single proforma
# --------------------------------------------------------------------------------- #


def test_the_kailu_proforma_reads_as_1_document_19_lines(resolver):
    out = read_workbook(kailu_proforma_workbook(), resolver)

    assert out.ok
    assert len(out.documents) == 1
    doc = out.documents[0]
    assert doc.pi_number == "KL20260717"
    assert doc.invoice_date == date(2026, 7, 17)
    assert doc.currency_hint == "CNY"
    assert len(doc.lines) == 19


def test_the_kailu_proforma_carries_exactly_3_po_refs(resolver):
    # AC-P1.2 / AC-P2.3: 19 lines of which exactly 3 carry a PO reference.
    out = read_workbook(kailu_proforma_workbook(), resolver)
    doc = out.documents[0]

    po_refs = [ln.po_ref for ln in doc.lines if ln.po_ref]
    assert po_refs == ["202605-S0060", "202605-S0084", "202605-S0060"]


def test_the_kailu_item_code_newline_survives_verbatim(resolver):
    # AC-P2.3: item code with an embedded newline, trimmed of outer whitespace only.
    out = read_workbook(kailu_proforma_workbook(), resolver)
    doc = out.documents[0]

    codes = [ln.item_code for ln in doc.lines]
    assert "SRTWT8258\n-GM" in codes


def test_the_kailu_totals_and_bank_rows_are_not_lines(resolver):
    out = read_workbook(kailu_proforma_workbook(), resolver)
    doc = out.documents[0]

    codes = {ln.item_code for ln in doc.lines}
    # "合 计" (totals) and every placeholder bank-detail row have no item code column
    # populated and must never be mistaken for a line.
    assert "合 计" not in codes
    assert not any("Beneficiary" in c or "Swift" in c or "CNAPS" in c for c in codes)
    assert len(doc.lines) == 19


# --------------------------------------------------------------------------------- #
# AC-P2.4 - a blank labelled value stays blank, does not swallow the next label
# --------------------------------------------------------------------------------- #


def test_a_blank_bill_of_lading_does_not_read_the_next_label(resolver):
    # The exact defect the gap report recorded: `提单号：` (blank) immediately followed
    # by the label `Date 日期：` must not make bl_no read as "Date 日期：".
    rows = [
        ["Customer Name 客户名：", None, None, None, None, "SORENTO SDN BHD", None,
         None, None, None, "提单号：", None, None, None, "Date 日期：", None, None,
         "2026-07-31"],
        [None, "产品型号", "品名", "数量", "单价(元)", "总价（元）"],
        # Leading None on the line too: the header itself starts one column in, and a line
        # that did not would read its item code out of the description column.
        [None, "A-1", "座厕", 5, 100, 500],
    ]

    out = read_workbook(workbook(rows), resolver)

    assert out.ok
    assert len(out.documents) == 1
    doc = out.documents[0]
    assert doc.bl_no is None
    assert doc.invoice_date == date(2026, 7, 31)


# --------------------------------------------------------------------------------- #
# AC-P2.6 - unreadable file names what is missing
# --------------------------------------------------------------------------------- #


def test_a_file_with_no_recognisable_header_says_what_is_missing(resolver):
    out = read_workbook(workbook([["something", "else"], ["a", "b"]]), resolver)

    assert not out.ok
    assert set(out.missing_columns) >= {"item_code", "qty", "unit_price"}


# --------------------------------------------------------------------------------- #
# The alias mapping this suite assumes is the one migration 374 actually seeds.
# --------------------------------------------------------------------------------- #


# --------------------------------------------------------------------------------- #
# Optional: against the ORIGINAL two files, not the reproduced fixtures. Skipped
# unless SCM_PROFORMA_SAMPLES_DIR points at a directory holding both (they are not
# committed - Kailu's carries real bank details).
# --------------------------------------------------------------------------------- #

_SAMPLES_DIR = os.environ.get("SCM_PROFORMA_SAMPLES_DIR")
_JINBAICHUAN_NAME = "2026-7-31 SORENTO 预装清单.xlsx"
_KAILU_NAME = "KAILU形式发票(Sorento)260717.xlsx"


def _both_real_files_present() -> bool:
    if not _SAMPLES_DIR:
        return False
    d = Path(_SAMPLES_DIR)
    return (d / _JINBAICHUAN_NAME).exists() and (d / _KAILU_NAME).exists()


@pytest.mark.skipif(
    not _both_real_files_present(),
    reason="set SCM_PROFORMA_SAMPLES_DIR to a directory holding both original files",
)
def test_the_real_files_read_the_same_as_the_reproduced_fixtures(resolver):
    d = Path(_SAMPLES_DIR)
    jinbaichuan = (d / _JINBAICHUAN_NAME).read_bytes()
    kailu = (d / _KAILU_NAME).read_bytes()

    jb_out = read_workbook(jinbaichuan, resolver)
    assert len(jb_out.documents) == 5
    assert sum(len(d_.lines) for d_ in jb_out.documents) == 30

    kl_out = read_workbook(kailu, resolver)
    assert len(kl_out.documents) == 1
    assert kl_out.documents[0].pi_number == "KL20260717"
    assert len(kl_out.documents[0].lines) == 19


def test_the_seeded_aliases_are_the_ones_this_suite_assumes():
    """The mapping above is a copy. This is the check that it is still a true one.

    Migration 374's `_ALIASES` is a flat ``(field, alias)`` list - unlike migration 311's
    packing_list seeder, `proforma_invoice` is the only doc type in that module, so there
    is no ``doc``/``locale`` column to unpack (see the migration's own `seed()`).
    """
    import importlib.util

    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "374_scm_proforma_invoice.py"
    )
    spec = importlib.util.spec_from_file_location("m374", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    assert m.DOC_TYPE == DOC_TYPE
    seeded = set(m._ALIASES)
    assert seeded, "migration 374 seeds no proforma_invoice aliases"

    for field, alias in _ALIASES:
        assert (field, alias) in seeded, f"{field}/{alias} is not seeded"


# --------------------------------------------------------------------------------- #
# AC-P3.1 - what counts as a document STATING a currency (the reader's hint source)
# --------------------------------------------------------------------------------- #


def test_a_short_currency_token_inside_a_longer_word_is_not_a_currency():
    """`rm` matched inside `FORM`, so a price column called `Unit Price (FORM)` denominated
    the whole invoice in Malaysian ringgit - a Chinese proforma read as MYR, with nothing on
    screen to say where that came from."""
    from app.services.scm.currency_resolution import currency_from_text

    assert currency_from_text(["Unit Price (FORM)"]) is None
    assert currency_from_text(["PLATFORM"]) is None
    # Still read where it IS the word: bracketed, standalone, or in front of a figure.
    assert currency_from_text(["Unit Price (RM)"]) == "MYR"
    assert currency_from_text(["RM"]) == "MYR"
    assert currency_from_text(["金额（rmb）"]) == "CNY"
    assert currency_from_text(["单价(元)"]) == "CNY"
    assert currency_from_text(["US$"]) == "USD"


def test_a_day_first_slash_date_reads_day_first():
    # `%d/%m/%Y` is Kailu's `17.07.2026` written with slashes. Year-first stays year-first.
    from app.services.scm.proforma_invoice_reader import _parse_date

    assert _parse_date("31/07/2026") == date(2026, 7, 31)
    assert _parse_date("2026/07/31") == date(2026, 7, 31)
    assert _parse_date("nonsense") is None
