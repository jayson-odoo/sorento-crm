"""The captain's real Kailu packing list, end to end.

`tests/scm/fixtures/kailu_packing_list_sample.xls` is the exact file
(`Sorento装箱单（凯路）260717.xls`) that failed to upload before migration
`375_kailu_packing_list_aliases`: migration 311 alone seeds no `型号`, `体积`, `货名` or
`牌子/LOGO`, so the reader resolved no `item_code`/`qty` column at all. This suite is the
regression guard for that fix.

The resolver under test is built from BOTH migrations' seed lists, imported from the
migration modules themselves (as `tests/scm/test_committed_v_migration_chain.py` does with
its own `_load` helper) rather than retyped here, so a change to either seed list fails this
suite instead of silently drifting from what the file actually needs.

Ground truth for the fixture (sheet `总表`, header row 3, sub-header row 4, data rows 6-22,
totals row 25): 17 lines, total qty 3419, total cartons 256, total cbm 8.36007025. The first
data line (row 6) is item_code `SRTWT7443`, qty 860, product_name `BASIN COLD TAP`, cartons
86, cbm_total 2.10528, brand `Sorento`.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.services.import_alias_service import AliasResolver, normalize_header
from app.services.scm.packing_list_reader import DOC_TYPE, read_workbook
from tests._pg_fixture import blank_session
from tests.scm.conftest import requires_pg

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kailu_packing_list_sample.xls"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture_bytes() -> bytes:
    return _FIXTURE.read_bytes()


def _resolver_from_migrations() -> AliasResolver:
    """The resolver a real database has after both migrations, built from the migrations'
    own seed lists rather than a hand-copied mapping - the whole point of this suite is that
    it fails if either seed list changes under it."""
    m311 = _load("311_scm_purchasing_base")
    m375 = _load("375_kailu_packing_list_aliases")

    mapping: dict[str, str] = {}
    for doc_type, field, alias, _locale in list(m311._ALIASES) + list(m375._ALIASES):
        if doc_type != DOC_TYPE:
            continue
        mapping.setdefault(normalize_header(alias), field)
        mapping.setdefault(normalize_header(field), field)
    return AliasResolver(DOC_TYPE, mapping)


@pytest.fixture()
def resolver() -> AliasResolver:
    return _resolver_from_migrations()


# --- 1. Reader against the real fixture -------------------------------------------------


def test_the_real_kailu_file_reads_as_one_block_of_seventeen_lines(resolver):
    out = read_workbook(_fixture_bytes(), resolver)

    assert out.ok
    assert out.missing_columns == []
    assert len(out.blocks) == 1
    assert out.line_count == 17
    assert out.unmapped_headers == []
    assert out.problems == []

    block = out.blocks[0]
    assert block.header_row == 3
    assert block.total_qty == pytest.approx(3419)
    assert block.total_cartons == pytest.approx(256)
    assert sum(ln.cbm_total for ln in block.lines) == pytest.approx(8.36007025)


# --- 2. Per-line spot checks --------------------------------------------------------------


def test_the_first_line_matches_the_printed_row(resolver):
    out = read_workbook(_fixture_bytes(), resolver)
    first = out.blocks[0].lines[0]

    assert first.item_code == "SRTWT7443"
    assert first.qty == pytest.approx(860)
    assert first.product_name == "BASIN COLD TAP"
    assert first.cartons == pytest.approx(86)
    assert first.cbm_total == pytest.approx(2.10528)
    assert first.brand == "Sorento"
    # Derived by the reader itself: cbm_total / qty, never a column of its own on this file.
    assert first.cbm_per_unit == pytest.approx(0.002448)


def test_an_item_code_with_an_embedded_newline_survives_verbatim(resolver):
    # The supplier's own spelling, newline and all - item codes are never reformatted.
    out = read_workbook(_fixture_bytes(), resolver)
    codes = [ln.item_code for ln in out.blocks[0].lines]

    assert "SRTWT8258\n-GM" in codes


def test_no_line_carries_a_weight_the_file_does_not_actually_give_per_line(resolver):
    # NW/GW on this file are PER-CARTON, aliased to carton_net_weight/carton_gross_weight
    # (migration 375), which nothing reads onto a PackingLine. Believing them as line
    # weights would be wrong by a factor of the carton count.
    out = read_workbook(_fixture_bytes(), resolver)

    for line in out.blocks[0].lines:
        assert line.net_weight is None
        assert line.gross_weight is None


# --- 3. Resolver distinctness and block/sub-header safety ---------------------------------


def test_the_line_total_and_the_per_unit_volume_columns_stay_distinct(resolver):
    # 375's bare `体积` (line total, this file's spelling) must not collide with 311's
    # `体积(cbm)` (per-unit, the PI-format spelling) in the same resolver.
    assert resolver.field_for_header("体积") == "cbm_total"
    assert resolver.field_for_header("体积(cbm)") == "cbm_per_unit"


def test_the_sub_header_and_totals_rows_produce_no_line(resolver):
    # Row 4 (`L W H / KG / NW GW`) and row 25 (the totals) resolve no item_code column and so
    # never become lines - implied by the 17-line count above, and asserted directly here so
    # a future reader change that starts reading them fails on the exact defect it would be.
    out = read_workbook(_fixture_bytes(), resolver)
    codes = {ln.item_code for ln in out.blocks[0].lines}

    assert not codes & {"L", "W", "H", "KG", "NW", "GW"}
    assert not any(code.replace(".", "", 1).isdigit() for code in codes)


# --- 4. Postgres seed test: migration 375 alone -------------------------------------------


@requires_pg
def test_migration_375_seeds_the_bare_kailu_spellings():
    m375 = _load("375_kailu_packing_list_aliases")

    with blank_session() as db:
        inserted = m375.seed(db.connection())
        db.commit()
        assert inserted == len(m375._ALIASES)

        # The blank schema has no 311 rows, so only 375's own spellings resolve here.
        db_resolver = AliasResolver.for_doc_type(db, DOC_TYPE)
        assert db_resolver.field_for_header("型号") == "item_code"
        assert db_resolver.field_for_header("货名") == "product_name"
        assert db_resolver.field_for_header("体积") == "cbm_total"
        assert db_resolver.field_for_header("牌子/LOGO") == "brand"

        # Idempotent: a second run inserts nothing new.
        again = m375.seed(db.connection())
        assert again == 0


# --- 5. End-to-end service check on Postgres ------------------------------------------------


@requires_pg
def test_the_service_preview_reports_every_line_with_no_catalogue_match():
    """`preview()` builds its own resolver from the database (no injected resolver), so this
    proves the seeded rows are what the real upload path actually reads - not just what the
    reader accepts when handed a resolver built by hand.

    The blank schema carries no products, so every one of the 17 item codes is expected to
    come back unmatched: preview REPORTS an unrecognised code rather than dropping the line,
    which is the behaviour this whole feature exists to preserve.
    """
    from app.services.scm import packing_list_service

    m311 = _load("311_scm_purchasing_base")
    m375 = _load("375_kailu_packing_list_aliases")

    with blank_session() as db:
        # The migrations' own seed functions, so this test exercises the same insert path
        # production (and bootstrap_env) runs rather than restating the SQL.
        conn = db.connection()
        m311.seed_import_field_aliases(conn)
        m375.seed(conn)
        db.commit()

        out = packing_list_service.preview(
            db, _fixture_bytes(), source_ref="kailu_packing_list_sample.xls"
        )

        assert out["ok"] is True
        assert out["block_count"] == 1
        assert out["line_count"] == 17
        assert out["missing_columns"] == []
        assert out["problems"] == []

        all_codes = {
            ln.item_code
            for b in packing_list_service._parse(db, _fixture_bytes()).blocks
            for ln in b.lines
        }
        assert set(out["unmatched_item_codes"]) == {c.upper() for c in all_codes}
