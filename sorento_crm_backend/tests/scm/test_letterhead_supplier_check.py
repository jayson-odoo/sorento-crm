"""S7 - the statement in use is named, and a wrong supplier is caught.

`PLAN-scm-loading-plan-feedback-2sep.md` section 3.7, AC-G3 (BE/T; AC-G4 is the browser [E2E]
counterpart, verified separately with the fixture and a live catalogue).

TEST-FIRST: `ProformaReadResult.letterhead` / `InventoryReadResult.letterhead`,
`app.services.scm.supplier_scope.supplier_check` and the `supplier_check` key on both
services' `_summarise` do not exist when this file is written - a missing attribute or a
missing key, never a wrong warning quietly accepted.

Matching is deterministic: NFKC-normalised, case-folded, exact substring of a MASTER-DATA
`suppliers.supplier_name`, never fuzzy. Every seeded row is `ZZTLH`-marked, inside
`pg_session` (rolled back at teardown) - nothing here is borrowed from the shared prod-copy
database, and the fixture-driven assertions below deliberately avoid depending on its current
catalogue or supplier table (see `test_the_captains_own_fixture_names_a_supplier_prod_does_not`
for why that matters).
"""
from __future__ import annotations

import uuid
from io import BytesIO

import pytest

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.procurement import Supplier
from app.services.scm import proforma_invoice_service as pi_svc
from app.services.scm import supplier_inventory_service as stock_svc
from app.services.scm.proforma_invoice_reader import read_workbook as read_proforma
from app.services.scm.supplier_inventory_reader import read_workbook as read_stock_list
from app.services.scm.supplier_scope import supplier_check, supplier_mismatch_warning
from app.services.import_alias_service import AliasResolver, normalize_header
from tests._pg_fixture import pg_session
from tests.scm.fixtures.proforma_shapes import preloading_list_workbook

MARKER = "ZZTLH"

#: The real letterhead the captain's fixture states, copied verbatim from
#: `tests/scm/fixtures/proforma_shapes.py`'s `_TITLE` (not imported - that constant is
#: private to the fixture module, and a literal here is what a substring test has to compare
#: against anyway).
JINBAICHUAN_LETTERHEAD = (
    "潮州市金百川卫浴科技有限公司 \n CHAOZHOU JINBAICHUAN SANITARY WARE TECHNOLOGY "
    "CO.,LTD\nTEL：13308786682  18144411999\nProforma Invoice\n\n"
)

#: The real master-data supplier name (as it exists on the shared prod-copy database at the
#: time this file was written): "CHAOZHOU JINBAICHUAN SANITARY WARE CO., LTD" - no
#: "TECHNOLOGY", and "CO., LTD" with a space where the letterhead has none. NOT a substring of
#: `JINBAICHUAN_LETTERHEAD`, and this test pins that as the honest answer rather than loosen
#: the match to make it one (AC-G3: "exact substring... never fuzzy").
PROD_JINBAICHUAN_MASTER_NAME = "CHAOZHOU JINBAICHUAN SANITARY WARE CO., LTD"


def _tag() -> str:
    return uuid.uuid4().hex[:8].upper()


def _supplier(db, name: str, *, active: bool = True, company_id: str | None = None) -> Supplier:
    s = Supplier(
        id=str(uuid.uuid4()),
        supplier_code=f"{MARKER}-{_tag()}",
        supplier_name=name,
        is_active=active,
    )
    if company_id is not None:
        s.company_id = company_id
    db.add(s)
    db.flush()
    return s


def _stock_workbook(letterhead: str | None, rows: list[tuple[str, float]]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    if letterhead is not None:
        ws.append([letterhead])
        ws.append([])
    ws.append(["型号", "品名", "包装好库存", "空瓷", "体积(cbm)", "备注"])
    for code, qty in rows:
        ws.append([code, code, qty, 0, None, None])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _proforma_workbook(letterhead: str | None, rows: list[tuple[str, float, float]]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    if letterhead is not None:
        ws.append([letterhead])
        ws.append([])
    ws.append(["产品型号", "数量", "RMB"])
    for code, qty, price in rows:
        ws.append([code, qty, price])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------------- #
# The readers capture the letterhead (AC-G3)
# --------------------------------------------------------------------------------- #


def test_proforma_reader_captures_the_first_text_cell_above_the_first_block():
    resolver = AliasResolver("proforma_invoice", {})
    out = read_proforma(preloading_list_workbook(), resolver)

    assert out.letterhead is not None
    assert "CHAOZHOU JINBAICHUAN" in out.letterhead


def test_proforma_reader_states_no_letterhead_when_the_header_is_row_1():
    mapping = {}
    for f, alias in (("item_code", "产品型号"), ("qty", "数量"), ("unit_price", "RMB")):
        mapping[normalize_header(alias)] = f
        mapping[normalize_header(f)] = f
    resolver = AliasResolver("proforma_invoice", mapping)

    out = read_proforma(_proforma_workbook(None, [(f"{MARKER}-A", 10, 5)]), resolver)

    assert out.ok
    assert out.letterhead is None


def test_stock_list_reader_captures_the_letterhead_above_its_header():
    resolver = AliasResolver(
        "supplier_inventory",
        {
            normalize_header("型号"): "item_code",
            normalize_header("包装好库存"): "qty_packed",
        },
    )
    out = read_stock_list(
        _stock_workbook("SOME SUPPLIER'S OWN LETTERHEAD", [(f"{MARKER}-A", 10)]), resolver
    )

    assert out.letterhead == "SOME SUPPLIER'S OWN LETTERHEAD"


def test_stock_list_reader_states_no_letterhead_when_the_header_is_row_1():
    resolver = AliasResolver(
        "supplier_inventory",
        {
            normalize_header("型号"): "item_code",
            normalize_header("包装好库存"): "qty_packed",
        },
    )
    out = read_stock_list(_stock_workbook(None, [(f"{MARKER}-A", 10)]), resolver)

    assert out.ok
    assert out.letterhead is None


# --------------------------------------------------------------------------------- #
# `supplier_check` - the comparison itself
# --------------------------------------------------------------------------------- #


def test_supplier_check_is_none_with_no_letterhead():
    with pg_session() as db:
        chosen = _supplier(db, f"{MARKER} chosen {_tag()}")

        assert supplier_check(db, None, supplier_id=str(chosen.id)) is None
        assert supplier_check(db, "", supplier_id=str(chosen.id)) is None


def test_no_warning_shape_when_the_chosen_suppliers_own_name_occurs():
    with pg_session() as db:
        tag = _tag()
        chosen = _supplier(db, f"{MARKER} KAIPING KAIXIN {tag}")
        letterhead = f"{chosen.supplier_name}\nTEL: 12345"

        out = supplier_check(db, letterhead, supplier_id=str(chosen.id))

        assert out == {
            "letterhead": letterhead,
            "chosen_supplier_name": chosen.supplier_name,
            "other_supplier_name": None,
        }


def test_another_active_suppliers_name_in_the_letterhead_names_both():
    with pg_session() as db:
        tag = _tag()
        chosen = _supplier(db, f"{MARKER} chosen KAIPING KAIXIN SANITARY {tag}")
        other = _supplier(db, f"{MARKER} JINBAICHUAN SANITARY WARE TECHNOLOGY {tag}")
        letterhead = f"{other.supplier_name} CO.,LTD\nProforma Invoice"

        out = supplier_check(db, letterhead, supplier_id=str(chosen.id))

        assert out == {
            "letterhead": letterhead,
            "chosen_supplier_name": chosen.supplier_name,
            "other_supplier_name": other.supplier_name,
        }


def test_no_supplier_name_occurring_at_all_is_silence_not_a_warning():
    with pg_session() as db:
        tag = _tag()
        chosen = _supplier(db, f"{MARKER} chosen {tag}")
        _supplier(db, f"{MARKER} somebody else entirely {tag}")
        letterhead = "A completely unrelated letterhead naming nobody on file"

        out = supplier_check(db, letterhead, supplier_id=str(chosen.id))

        assert out == {
            "letterhead": letterhead,
            "chosen_supplier_name": chosen.supplier_name,
            "other_supplier_name": None,
        }


def test_an_inactive_suppliers_name_is_not_a_match():
    with pg_session() as db:
        tag = _tag()
        chosen = _supplier(db, f"{MARKER} chosen {tag}")
        dormant = _supplier(db, f"{MARKER} DORMANT SUPPLIER {tag}", active=False)
        letterhead = f"{dormant.supplier_name}\nProforma Invoice"

        out = supplier_check(db, letterhead, supplier_id=str(chosen.id))

        assert out["other_supplier_name"] is None


def test_matching_is_case_and_width_insensitive_but_still_exact_substring():
    """NFKC + casefold (AC-G3): a different case or full-width spelling still matches; a
    name that is merely SIMILAR - one word inserted - does not (pinned by the JINBAICHUAN
    fixture test below, never loosened here to make that one pass)."""
    with pg_session() as db:
        tag = _tag()
        chosen = _supplier(db, f"{MARKER} chosen {tag}")
        other = _supplier(db, f"{MARKER} sanitary ware co {tag}")
        letterhead = f"{MARKER} SANITARY WARE CO {tag}\nInvoice"

        out = supplier_check(db, letterhead, supplier_id=str(chosen.id))

        assert out["other_supplier_name"] == other.supplier_name


def test_supplier_check_is_company_scoped():
    """Another company's supplier, even with a matching name, is invisible here - the same
    fail-closed rule every raw-SQL owned read in this codebase follows."""
    with pg_session() as db:
        tag = _tag()
        set_company_scope(db, None)
        foreign_company = Company(
            id=str(uuid.uuid4()), code=f"{MARKER}-CO-{tag}"[:20], name=f"{MARKER} foreign co"
        )
        db.add(foreign_company)
        db.flush()
        foreign_supplier = _supplier(
            db, f"{MARKER} FOREIGN JINBAICHUAN {tag}", company_id=foreign_company.id
        )
        chosen = _supplier(db, f"{MARKER} chosen {tag}", company_id=None)
        # Restore the ambient test scope (default Sorento company) for the read under test.
        from tests.conftest import _SORENTO_TEST_SCOPE  # type: ignore

        set_company_scope(db, _SORENTO_TEST_SCOPE)
        chosen.company_id = list(_SORENTO_TEST_SCOPE)[0]
        db.flush()
        letterhead = f"{foreign_supplier.supplier_name}\nInvoice"

        out = supplier_check(db, letterhead, supplier_id=str(chosen.id))

        assert out["other_supplier_name"] is None


# --------------------------------------------------------------------------------- #
# `supplier_mismatch_warning` - one sentence, shared by both channels
# --------------------------------------------------------------------------------- #


def test_supplier_mismatch_warning_is_none_with_no_check_or_no_mismatch():
    assert supplier_mismatch_warning(None) is None
    assert supplier_mismatch_warning({"other_supplier_name": None}) is None


def test_supplier_mismatch_warning_names_both_suppliers():
    check = {
        "letterhead": "irrelevant here",
        "chosen_supplier_name": "KAIPING KAIXIN SANITARY CO., LTD",
        "other_supplier_name": "CHAOZHOU JINBAICHUAN SANITARY WARE CO., LTD",
    }

    assert supplier_mismatch_warning(check) == (
        "File header names CHAOZHOU JINBAICHUAN SANITARY WARE CO., LTD, you picked "
        "KAIPING KAIXIN SANITARY CO., LTD."
    )


def test_supplier_mismatch_warning_does_not_double_a_trailing_full_stop():
    """A master-data name that already ends in a period ("KAIPING KAIXIN SANITARY CO.,
    LTD.") reads as a typo with a second one appended - pinned against the real prod
    spelling rather than a synthetic one, since that is where this was actually seen."""
    check = {
        "letterhead": "irrelevant here",
        "chosen_supplier_name": "KAIPING KAIXIN SANITARY CO., LTD.",
        "other_supplier_name": "CHAOZHOU JINBAICHUAN SANITARY WARE CO., LTD",
    }

    warning = supplier_mismatch_warning(check)

    assert warning.endswith("KAIPING KAIXIN SANITARY CO., LTD.")
    assert not warning.endswith("LTD..")


# --------------------------------------------------------------------------------- #
# The wired-in warning (proforma + stock list channels)
# --------------------------------------------------------------------------------- #


def test_proforma_validate_carries_the_supplier_mismatch_warning():
    with pg_session() as db:
        tag = _tag()
        chosen = _supplier(db, f"{MARKER} KAIPING KAIXIN {tag}")
        other = _supplier(db, f"{MARKER} JINBAICHUAN SANITARY {tag}")
        letterhead = f"{other.supplier_name} CO.,LTD"
        data = _proforma_workbook(letterhead, [(f"{MARKER}-A", 10, 5)])

        result = pi_svc.validate(db, data, supplier_id=str(chosen.id))

        assert result["valid"] is True  # a warning, not a refusal
        assert any(
            other.supplier_name in w and chosen.supplier_name in w
            for w in result["warnings"]
        )
        assert result["summary"]["supplier_check"]["other_supplier_name"] == other.supplier_name


def test_proforma_validate_has_no_warning_when_the_chosen_supplier_matches():
    with pg_session() as db:
        tag = _tag()
        chosen = _supplier(db, f"{MARKER} KAIPING KAIXIN {tag}")
        letterhead = f"{chosen.supplier_name}\nProforma Invoice"
        data = _proforma_workbook(letterhead, [(f"{MARKER}-A", 10, 5)])

        result = pi_svc.validate(db, data, supplier_id=str(chosen.id))

        assert not any("File header names" in w for w in result["warnings"])
        assert result["summary"]["supplier_check"]["other_supplier_name"] is None


def test_stock_list_validate_carries_the_supplier_mismatch_warning():
    with pg_session() as db:
        tag = _tag()
        chosen = _supplier(db, f"{MARKER} chosen supplier {tag}")
        other = _supplier(db, f"{MARKER} JINBAICHUAN {tag}")
        letterhead = f"{other.supplier_name} CO.,LTD"
        data = _stock_workbook(letterhead, [(f"{MARKER}-A", 10)])

        result = stock_svc.validate(db, data, supplier_id=str(chosen.id))

        assert result["valid"] is True
        assert any(
            other.supplier_name in w and chosen.supplier_name in w
            for w in result["warnings"]
        )


def test_stock_list_validate_has_no_warning_when_no_name_occurs():
    with pg_session() as db:
        tag = _tag()
        chosen = _supplier(db, f"{MARKER} chosen {tag}")
        data = _stock_workbook("Nobody's name is here at all", [(f"{MARKER}-A", 10)])

        result = stock_svc.validate(db, data, supplier_id=str(chosen.id))

        assert not any("File header names" in w for w in result["warnings"])
        assert result["summary"]["supplier_check"]["other_supplier_name"] is None


# --------------------------------------------------------------------------------- #
# The verdict-card counts (AC-G4's numbers; the fixture read alone, no live catalogue)
# --------------------------------------------------------------------------------- #


def test_proforma_verdict_block_and_line_counts_match_the_real_fixture():
    """AC-G4's shape ("N invoice blocks - L lines - U codes unknown"). `document_count` and
    `line_count` are read off the fixture alone and cannot drift; `unmatched_items` is
    deliberately only bounded, not pinned to an exact number - the fixture's item codes are
    the SUPPLIER'S real spellings, not `ZZTLH`-marked, and some of them already resolve
    against whatever products this environment's catalogue happens to hold (this ran 23
    unmatched on the shared prod-copy dev database, 29 on an empty CI one). Pinning it here
    would make the assertion about the database's current contents, which this suite's own
    convention (see `test_proforma_invoice_import.py`) forbids.
    """
    with pg_session() as db:
        chosen = _supplier(db, f"{MARKER} chosen {_tag()}")

        result = pi_svc.validate(
            db, preloading_list_workbook(), supplier_id=str(chosen.id), currency="CNY"
        )

        summary = result["summary"]
        assert summary["document_count"] == 5
        assert summary["line_count"] == 30
        # 29 distinct codes on the fixture (SRTWC8354-SH-250 repeats across two blocks,
        # AC-F5), so "unknown" can be at most 29 and is never negative or the raw line count.
        assert 0 <= summary["unmatched_items"] <= 29


def test_stock_list_verdict_row_count_matches_the_file():
    """The stock-list channel's half of AC-G4 ("L rows - U codes unknown"), with marker
    codes so the unmatched count IS pinned - unlike the proforma test above, these codes
    cannot coincidentally exist in any environment's catalogue."""
    with pg_session() as db:
        chosen = _supplier(db, f"{MARKER} chosen {_tag()}")
        codes = [(f"{MARKER}-R{i}-{_tag()}", 10) for i in range(4)]

        result = stock_svc.validate(db, _stock_workbook(None, codes), supplier_id=str(chosen.id))

        summary = result["summary"]
        assert summary["rows"] == 4
        assert summary["items_unmatched"] == 4


def test_the_captains_own_fixture_names_a_supplier_prod_does_not_hold():
    """Documents the finding the brief asked to state honestly: the real prod master-data
    name for this supplier ("CHAOZHOU JINBAICHUAN SANITARY WARE CO., LTD") is NOT a
    substring of the real fixture's own letterhead, because the letterhead inserts
    "TECHNOLOGY" between "WARE" and "CO." and drops the space in "CO., LTD". AC-G3 requires
    an exact substring, so uploading the real fixture under the real JINBAICHUAN supplier in
    prod raises no `supplier_mismatch` warning today - a captain's-call gap, not a bug in
    this matcher, and this test pins the gap rather than loosening the match to paper over it.
    """
    haystack = JINBAICHUAN_LETTERHEAD.replace("\n", " ").casefold()
    assert PROD_JINBAICHUAN_MASTER_NAME.casefold() not in haystack
