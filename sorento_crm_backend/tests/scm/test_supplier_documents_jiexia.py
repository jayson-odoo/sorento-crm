"""AC-F2/F3/F8/F9 - the Jiexia proforma invoice and packing list, end to end.

`tests/scm/fixtures/jiexia_proforma_invoice_sample.xls` and `jiexia_packing_list_sample.xls`
are the two real files migration `483_supplier_doc_aliases` exists to make readable: neither
resolves `箱号` (only `货柜号` was seeded, migration 311), `封签号`, `客户`, a bare `INVOICE
NO.`/`日期` on the packing-list doc type, or `客户型号`/`洁厦型号`/`JIEXIA MODEL` at all before
this migration - and without `客户型号` -> item_code the proforma invoice's header row does
not even resolve as a header (no item_code column), so the whole file was unreadable.

The resolver under test is built from the migrations' own seed lists (as
`test_packing_list_kailu.py` does with its own `_load` helper), not retyped here, so a change
to any seed list this suite depends on fails it instead of silently drifting from what the
files actually need.

Ground truth (verified against the real fixtures with `xlrd` directly before writing these
assertions):

* PI: 2 documents. Doc 1 container WHSU6243088, seal WHA4528193, 3 lines, qty 366, total
  87710. Doc 2 container WHSU6356079, seal WHA4528173, 2 lines, qty 510, total 122182. Both
  share pi_number 2026JXL0726, invoice_date 2026-07-26, consignee SORENTO SDN BHD.
* PL: 2 blocks, same containers and seals. Block 1: 4 real lines (SRTWCX8840-S-RL 266,
  SRTWCX8840-P-RL 100, SRTWCY8840 366, 8840 366 with 60 cartons - qty 1098 total), 4
  code-less/qty-less accessory rows kept as NOTES, cartons 792, cbm 49.41. A `备注：` footer
  with carton dimensions is captured verbatim.
* Both files' row 0 is the letterhead (`CHAOZHOU CHAOAN JIEXIA CERAMICS INDUSTRY CO.,LTD`) -
  read into `.shipper`, distinct from `.letterhead` on the PI side, which the supplier-check
  warning already uses.
"""
from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pytest

from app.services.import_alias_service import AliasResolver, normalize_header
from app.services.scm.packing_list_reader import DOC_TYPE as PL_DOC_TYPE
from app.services.scm.packing_list_reader import read_workbook as read_pl
from app.services.scm.proforma_invoice_reader import DOC_TYPE as PI_DOC_TYPE
from app.services.scm.proforma_invoice_reader import read_workbook as read_pi
from tests._pg_fixture import blank_session
from tests.scm.conftest import requires_pg

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_PI_FIXTURE = _FIXTURES / "jiexia_proforma_invoice_sample.xls"
_PL_FIXTURE = _FIXTURES / "jiexia_packing_list_sample.xls"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _all_rows():
    """Every (doc_type, field, alias, locale) row from every migration this suite depends
    on - built once, from the migrations' own modules, and filtered per doc type below."""
    m311 = _load("311_scm_purchasing_base")
    mkailu = _load("375_kailu_packing_list_aliases")
    mproforma = _load("375_scm_proforma_invoice")
    m483 = _load("483_supplier_doc_aliases")

    rows: list[tuple[str, str, str, str]] = list(m311._ALIASES)
    rows += list(mkailu._ALIASES)
    rows += [(mproforma.DOC_TYPE, field, alias, "en") for field, alias in mproforma._ALIASES]
    rows += list(m483._ALIASES)
    return rows, m483


def _resolver_for(doc_type: str) -> AliasResolver:
    rows, _m483 = _all_rows()
    mapping: dict[str, str] = {}
    for d, field, alias, _locale in rows:
        if d != doc_type:
            continue
        mapping.setdefault(normalize_header(alias), field)
    for d, field, _alias, _locale in rows:
        if d != doc_type:
            continue
        mapping.setdefault(normalize_header(field), field)
    return AliasResolver(doc_type, mapping)


@pytest.fixture()
def pl_resolver() -> AliasResolver:
    return _resolver_for(PL_DOC_TYPE)


@pytest.fixture()
def pi_resolver() -> AliasResolver:
    return _resolver_for(PI_DOC_TYPE)


def _pi_bytes() -> bytes:
    return _PI_FIXTURE.read_bytes()


def _pl_bytes() -> bytes:
    return _PL_FIXTURE.read_bytes()


# --- AC-F2: the proforma invoice reads as two documents, one per container ----------------


def test_the_proforma_invoice_reads_as_two_documents_sharing_one_invoice_number(pi_resolver):
    out = read_pi(_pi_bytes(), pi_resolver)

    assert out.ok
    assert out.missing_columns == []
    assert len(out.documents) == 2

    first, second = out.documents
    assert first.pi_number == second.pi_number == "2026JXL0726"
    assert first.invoice_date == second.invoice_date == date(2026, 7, 26)
    assert first.consignee == second.consignee == "SORENTO SDN BHD"

    assert first.container_no == "WHSU6243088"
    assert first.seal_no == "WHA4528193"
    assert len(first.lines) == 3
    assert first.total_qty == pytest.approx(366)
    assert first.line_total == pytest.approx(87710)

    assert second.container_no == "WHSU6356079"
    assert second.seal_no == "WHA4528173"
    assert len(second.lines) == 2
    assert second.total_qty == pytest.approx(510)
    assert second.line_total == pytest.approx(122182)


def test_the_proforma_invoice_reports_the_letterhead_as_shipper(pi_resolver):
    out = read_pi(_pi_bytes(), pi_resolver)

    assert out.shipper == "CHAOZHOU CHAOAN JIEXIA CERAMICS INDUSTRY CO.,LTD."


def test_sub_total_and_total_rows_produce_no_third_document(pi_resolver):
    # `SUB TOTAL 1*40HQ` (rows 16/20) and the file's own `TOTAL` (row 22) resolve no
    # item_code and carry no container label, so they can start no new document.
    out = read_pi(_pi_bytes(), pi_resolver)

    assert len(out.documents) == 2
    codes = {ln.item_code for d in out.documents for ln in d.lines}
    assert "SUB TOTAL 1*40HQ" not in codes


# --- AC-F3: the packing list reads as two blocks, four lines and four notes on block 1 ----


def test_the_packing_list_reads_as_two_blocks(pl_resolver):
    out = read_pl(_pl_bytes(), pl_resolver)

    assert out.ok
    assert out.missing_columns == []
    assert len(out.blocks) == 2

    first, second = out.blocks
    assert first.container_no == "WHSU6243088"
    assert first.seal_no == "WHA4528193"
    assert second.container_no == "WHSU6356079"
    assert second.seal_no == "WHA4528173"
    # Consignee is stated once, before the first block, and carries onto the second.
    assert first.consignee == second.consignee == "SORENTO SDN BHD"


def test_block_one_has_four_lines_and_four_accessory_notes(pl_resolver):
    out = read_pl(_pl_bytes(), pl_resolver)
    block = out.blocks[0]

    codes = [ln.item_code for ln in block.lines]
    assert codes == ["SRTWCX8840-S-RL", "SRTWCX8840-P-RL", "SRTWCY8840", "8840"]
    qtys = [ln.qty for ln in block.lines]
    assert qtys == pytest.approx([266, 100, 366, 366])
    assert block.total_qty == pytest.approx(1098)
    assert block.total_cartons == pytest.approx(792)
    assert block.total_cbm == pytest.approx(49.41)

    assert len(block.notes) == 4
    assert any("水箱空瓷" in n for n in block.notes)
    assert any("纸箱" in n for n in block.notes)


def test_the_footer_is_captured_verbatim(pl_resolver):
    out = read_pl(_pl_bytes(), pl_resolver)

    assert out.footer_notes is not None
    assert out.footer_notes.startswith("备注：")
    assert "675*375*485mm" in out.footer_notes
    assert "185*380*430mm" in out.footer_notes


def test_the_packing_list_reports_the_letterhead_as_shipper(pl_resolver):
    out = read_pl(_pl_bytes(), pl_resolver)

    assert out.shipper == "CHAOZHOU CHAOAN JIEXIA CERAMICS INDUSTRY CO.,LTD"


# --- AC-F9: one cell, two labels -----------------------------------------------------------


def test_a_cell_stating_two_block_fields_yields_both(pl_resolver):
    from app.services.scm.packing_list_reader import _labelled

    found = _labelled(["箱号:WHSU6243088 / 封签号:WHA4528193"], pl_resolver)

    assert found == {"container_no": "WHSU6243088", "seal_no": "WHA4528193"}


def test_a_single_labelled_cell_still_works_alone(pl_resolver):
    from app.services.scm.packing_list_reader import _labelled

    found = _labelled(["货柜号：ABCU1234567"], pl_resolver)

    assert found == {"container_no": "ABCU1234567"}


# --- AC-F8: the alias seed is idempotent and resolves every header this batch adds --------


@requires_pg
def test_migration_483_is_idempotent():
    m483 = _load("483_supplier_doc_aliases")

    with blank_session() as db:
        inserted = m483.seed(db.connection())
        db.commit()
        assert inserted == len(m483._ALIASES)

        again = m483.seed(db.connection())
        assert again == 0


def test_every_483_alias_resolves_for_its_doc_type():
    _rows, m483 = _all_rows()
    for doc_type, field, alias, _locale in m483._ALIASES:
        resolver = _resolver_for(doc_type)
        assert resolver.field_for_header(alias) == field, (doc_type, alias)


def test_every_header_cell_in_both_fixtures_resolves_or_is_the_row_serial(pi_resolver, pl_resolver):
    # "ITEM" (the printed row number) is the one column neither doc type aliases - it numbers
    # the paper, not the goods, same convention 375 kailu's `row_no` makes for `No.`. Every
    # OTHER header cell across both fixtures' header rows resolves.
    pi_headers = ["ITEM", "洁厦型号", "客户型号", "品名", "数量", "单价", "总金额", "商标"]
    for h in pi_headers:
        if h == "ITEM":
            continue
        assert pi_resolver.field_for_header(h) is not None, h

    pl_headers = ["JIEXIA MODEL", "客户型号", "品名", "数量", "CARTONS", "CBM"]
    for h in pl_headers:
        assert pl_resolver.field_for_header(h) is not None, h
