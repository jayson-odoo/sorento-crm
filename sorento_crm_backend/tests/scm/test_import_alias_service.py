"""Header resolution, tested against the header shapes the real files actually carry.

Header normalisation is the whole value of the alias table: if two headers a human reads
as identical resolve differently, the table has only moved the problem. So these cases are
taken from the three real sample workbooks, including the packing list's header cells that
contain embedded newlines ("净重\\n(kg)") and full-width brackets ("金额（rmb）").

Every test seeds its own aliases with a marker doc_type and cleans them up, so the suite
does not depend on the migration's seed rows being present - CI's database has no data.
"""
from __future__ import annotations

import pytest

from app.models.import_alias import ImportFieldAlias
from app.services.import_alias_service import AliasResolver, normalize_header
from tests._pg_fixture import pg_session

_DOC = "zzt_alias_spec"


@pytest.fixture()
def db():
    # pg_session rolls its whole transaction back, so the seeded aliases never persist and
    # no cleanup is needed. Nothing here reads a pre-existing row.
    with pg_session() as s:
        yield s


@pytest.fixture()
def seeded(db):
    rows = [
        ("item_code", "ITEM CODE", "en"),
        ("item_code", "型号", "zh"),
        ("qty_outstanding", "QTY", "en"),
        ("required_date", "DELIVERY DATE", "en"),
        ("net_weight", "净重\n(kg)", "zh"),
        ("amount", "金额（rmb）", "zh"),
        ("cbm_per_unit", "体积(cbm)", "zh"),
    ]
    for field, alias, locale in rows:
        db.add(ImportFieldAlias(doc_type=_DOC, field=field, alias=alias, locale=locale))
    db.flush()
    yield AliasResolver.for_doc_type(db, _DOC)
    db.rollback()


# -- normalisation -------------------------------------------------------------

@pytest.mark.parametrize(
    "a,b",
    [
        ("ITEM CODE", "item code"),
        ("ITEM CODE", " Item  Code "),
        ("ITEM CODE", "ITEM_CODE"),
        ("净重\n(kg)", "净重(kg)"),
        ("净重\n(kg)", "净重 (KG)"),
        ("金额（rmb）", "金额(rmb)"),   # full-width brackets fold via NFKC
        ("体积(cbm)", "体积 cbm"),
        ("总体积(cbm)", "总体积（CBM）"),
    ],
)
def test_headers_a_human_reads_as_the_same_header_resolve_the_same(a, b):
    assert normalize_header(a) == normalize_header(b)


@pytest.mark.parametrize(
    "a,b",
    [
        ("体积(cbm)", "总体积(cbm)"),      # per-unit volume is NOT total volume
        ("净重(kg)", "毛重(kg)"),          # net weight is NOT gross weight
        ("QTY ORDERED", "QTY RECEIVED"),
        ("型号", "商标"),
    ],
)
def test_headers_that_differ_must_not_collide(a, b):
    """The dangerous direction. Folding "体积" into "总体积" would silently multiply a
    per-unit volume by the line quantity twice over."""
    assert normalize_header(a) != normalize_header(b)


def test_blank_and_none_headers_normalise_to_empty_and_never_match():
    assert normalize_header(None) == ""
    assert normalize_header("   ") == ""
    assert normalize_header("\n") == ""


# -- resolution ----------------------------------------------------------------

def test_resolves_english_and_chinese_aliases_of_one_field(seeded):
    assert seeded.field_for_header("ITEM CODE") == "item_code"
    assert seeded.field_for_header("型号") == "item_code"
    assert seeded.field_for_header("item code") == "item_code"


def test_canonical_field_name_is_always_its_own_alias(seeded):
    """A file whose headers already match the canonical names needs no configuration."""
    assert seeded.field_for_header("qty_outstanding") == "qty_outstanding"
    assert seeded.field_for_header("required_date") == "required_date"


def test_get_reads_a_value_through_the_alias(seeded):
    row = {"ITEM CODE": "SRTWC8613-RL", "QTY": 135, "DELIVERY DATE": "2026-07-01"}
    assert seeded.get(row, "item_code") == "SRTWC8613-RL"
    assert seeded.get(row, "qty_outstanding") == 135


def test_get_returns_none_for_an_absent_or_blank_column(seeded):
    row = {"ITEM CODE": "X", "QTY": "   "}
    assert seeded.get(row, "required_date") is None
    assert seeded.get(row, "qty_outstanding") is None


def test_when_two_aliases_of_one_field_are_present_the_populated_one_wins(seeded):
    """A workbook carrying both "ITEM CODE" and "型号" must not depend on dict ordering."""
    assert seeded.get({"ITEM CODE": None, "型号": "CB6633"}, "item_code") == "CB6633"
    assert seeded.get({"型号": "", "ITEM CODE": "CB6633"}, "item_code") == "CB6633"


def test_index_row_rekeys_to_canonical_fields(seeded):
    out = seeded.index_row({"型号": "CWB242", "QTY": 200, "UNKNOWN COL": "x"})
    assert out == {"item_code": "CWB242", "qty_outstanding": 200}


def test_embedded_newline_header_resolves(seeded):
    """The packing list really does have a newline inside this header cell."""
    assert seeded.get({"净重\n(kg)": 40}, "net_weight") == 40
    assert seeded.get({"净重(kg)": 40}, "net_weight") == 40


# -- diagnostics ---------------------------------------------------------------

def test_unmapped_headers_are_reported_not_dropped(seeded):
    """An unmapped header is usually the first sign an export changed. It has to be
    visible, because it is a one-row fix once somebody can see it."""
    row = {"ITEM CODE": "X", "SOME NEW COLUMN": 1, "另一个新列": 2}
    unmapped = seeded.unmapped_headers(row)
    assert set(unmapped) == {"SOME NEW COLUMN", "另一个新列"}


def test_missing_required_reports_what_this_file_lacks(seeded):
    seeded.index_row({"ITEM CODE": "X", "QTY": 1})
    missing = seeded.missing_required(["item_code", "qty_outstanding", "required_date"])
    assert missing == ["required_date"]


def test_missing_required_is_empty_when_the_file_is_complete(seeded):
    seeded.index_row({"ITEM CODE": "X", "QTY": 1, "DELIVERY DATE": "2026-07-01"})
    assert seeded.missing_required(["item_code", "qty_outstanding", "required_date"]) == []


def test_a_doc_type_with_no_aliases_resolves_nothing_rather_than_crashing(db):
    r = AliasResolver.for_doc_type(db, "zzt_doc_type_that_has_no_rows")
    assert r.field_for_header("ITEM CODE") is None
    assert r.known_fields == set()
    assert r.missing_required(["item_code"]) == ["item_code"]
