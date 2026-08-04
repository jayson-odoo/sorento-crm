"""Container status workbook parser (slice 3, part 1).

The parser is the part of this feature most likely to be wrong quietly, because
the workbook does not look like the flat sheet-per-tab file it appears to be:

* Several tabs STACK more than one titled section, each with its own header row.
  `Fitting` has a second section at row 31, `Ceramic` at 69 and 75,
  `Arrived - Joint Mocha` at 22. A reader that treats a repeated header as a data
  row reports four bogus ISO 6346 rejects, which is exactly what the first draft
  of the prototype did.
* Header names drift between tabs. `Ceramic` calls its liner column **RL**, every
  other tab calls it `LINER`. Reading column 4 by position mislabels 55 liners
  and nothing complains.
* Hundreds of numbered rows carry no container number at all. They are blank
  scaffolding, not errors.

Every assertion below is measured against the real committed workbook, so a
regression in block detection or alias handling fails loudly here.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

from app.services.container_status_import import (
    HEADER_ALIASES,
    ContainerStatusParseError,
    normalize_container,
    parse_container_status_workbook,
)


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "sorento_crm_frontend"
    / "e2e"
    / "fixtures"
    / "container-status-2026.xlsx"
)

requires_fixture = pytest.mark.skipif(
    not FIXTURE.exists(), reason="real workbook fixture not present in this checkout"
)


@pytest.fixture(scope="module")
def parsed():
    return parse_container_status_workbook(FIXTURE.read_bytes())


def _build_workbook(sheets: dict[str, list[list]]) -> bytes:
    """A synthetic workbook, for the shapes the real file does not contain."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ------------------------------------------------------------ real workbook


@requires_fixture
def test_finds_every_stacked_section_not_just_one_per_tab(parsed):
    """9 blocks across 5 tabs, at the header rows measured in the real file."""
    found = [(b.sheet, b.header_row) for b in parsed.blocks]
    assert found == [
        ("Fitting", 2),
        ("Fitting", 31),
        ("Ceramic", 2),
        ("Ceramic", 69),
        ("Ceramic", 75),
        ("Arrived", 2),
        ("Arrived - Joint Mocha Container", 2),
        ("Arrived - Joint Mocha Container", 22),
        ("Arrived (Mocha) Joint BL", 2),
    ]


@requires_fixture
def test_reads_every_container_and_no_duplicates(parsed):
    assert len(parsed.rows) == 407
    keys = [r.container_key for r in parsed.rows]
    assert len(set(keys)) == 407, "the real file has no cross-tab duplicates"


@requires_fixture
def test_per_block_counts_match_the_file(parsed):
    """The stacked sections are mostly empty scaffolding, and that is fine."""
    counts = {(b.sheet, b.header_row): b.row_count for b in parsed.blocks}
    assert counts == {
        ("Fitting", 2): 17,
        ("Fitting", 31): 2,
        ("Ceramic", 2): 55,
        ("Ceramic", 69): 0,
        ("Ceramic", 75): 0,
        ("Arrived", 2): 318,
        ("Arrived - Joint Mocha Container", 2): 15,
        ("Arrived - Joint Mocha Container", 22): 0,
        ("Arrived (Mocha) Joint BL", 2): 0,
    }


@requires_fixture
def test_a_repeated_header_is_never_offered_as_a_data_row(parsed):
    """The four rows an earlier draft called ISO 6346 rejects."""
    assert parsed.rejected == []
    assert not any(r.container.upper() == "CONTAINER" for r in parsed.rows)


@requires_fixture
def test_blank_numbered_rows_are_skipped_without_an_error(parsed):
    assert parsed.blank_row_count == 475
    assert parsed.errors == []


@requires_fixture
def test_ceramic_liner_resolves_through_the_rl_alias(parsed):
    """Ceramic's column 4 is headed RL. By position it would be read as text
    with no meaning; by name it is the liner, and all 407 rows carry one."""
    ceramic = [r for r in parsed.rows if r.sheet == "Ceramic"]
    assert len(ceramic) == 55
    assert all(r.values.get("liner_code") for r in ceramic)
    assert {r.values["liner_code"] for r in ceramic} <= {
        "CMA", "WHL", "OOCL", "SITC", "EMC", "ONE", "YML",
    }
    assert sum(1 for r in parsed.rows if r.values.get("liner_code")) == 407


@requires_fixture
def test_source_sheet_is_recorded_for_traceability(parsed):
    """A2: the tab name is carried on every row and never derives status."""
    assert {r.values["source_sheet"] for r in parsed.rows} == {
        "Fitting",
        "Ceramic",
        "Arrived",
        "Arrived - Joint Mocha Container",
    }


@requires_fixture
def test_dates_come_back_as_dates_not_strings(parsed):
    """Excel hands back datetimes, serial numbers and the occasional string."""
    dated = [r for r in parsed.rows if r.values.get("eta_delay_date")]
    assert dated, "the file certainly has ETA delays"
    assert all(isinstance(r.values["eta_delay_date"], date) for r in dated)


@requires_fixture
def test_warns_about_header_drift_it_had_to_alias(parsed):
    """An alias is worth telling the operator about; a block boundary is not."""
    joined = " ".join(parsed.warnings)
    assert "RL" in joined and "LINER" in joined


# ------------------------------------------------------------ synthetic shapes


def test_container_normalization_matches_the_shipment_matcher():
    """Same normalization the packing-list matcher uses, or a row found in SQL
    fails the Python-side comparison."""
    assert normalize_container(" temu 123-4567 ") == "TEMU1234567"
    assert normalize_container(None) == ""
    assert normalize_container("") == ""


def test_a_genuinely_bad_container_is_rejected_with_its_row():
    """A6: rejected, not silently skipped, and locatable in the sheet."""
    data = _build_workbook(
        {
            "Sheet1": [
                ["TITLE"],
                ["NO", "CONTAINER", "LINER"],
                [1, "GXYU5106903", "CMA"],
                [2, "NOTACONTAINER", "CMA"],
                [3, "", "CMA"],
            ]
        }
    )
    parsed = parse_container_status_workbook(data)

    assert [r.container for r in parsed.rows] == ["GXYU5106903"]
    assert len(parsed.rejected) == 1
    rejected = parsed.rejected[0]
    assert rejected.container == "NOTACONTAINER"
    assert rejected.sheet == "Sheet1"
    assert rejected.excel_row == 4
    assert "6346" in rejected.reason
    assert parsed.blank_row_count == 1


def test_a_duplicate_container_in_one_run_is_reported_not_last_write_wins():
    """A6a. Zero collisions in today's file; the assertion is what keeps it so."""
    data = _build_workbook(
        {
            "Fitting": [
                ["TITLE"],
                ["NO", "CONTAINER", "LINER"],
                [1, "GXYU5106903", "CMA"],
            ],
            "Ceramic": [
                ["TITLE"],
                ["NO", "CONTAINER", "RL"],
                [1, "GXYU-5106903", "WHL"],
            ],
        }
    )
    parsed = parse_container_status_workbook(data)

    assert len(parsed.collisions) == 1
    collision = parsed.collisions[0]
    assert collision.container_key == "GXYU5106903"
    assert {o.sheet for o in collision.occurrences} == {"Fitting", "Ceramic"}


def test_an_unrecognised_header_is_reported_rather_than_guessed_at():
    data = _build_workbook(
        {
            "Sheet1": [
                ["TITLE"],
                ["NO", "CONTAINER", "LINER", "SOME NEW COLUMN"],
                [1, "GXYU5106903", "CMA", "x"],
            ]
        }
    )
    parsed = parse_container_status_workbook(data)

    assert any("SOME NEW COLUMN" in w for w in parsed.warnings)
    # ...and the row still imports. An unknown column is not a reason to fail.
    assert len(parsed.rows) == 1


def test_a_workbook_with_no_container_header_anywhere_is_an_error():
    data = _build_workbook({"Sheet1": [["NO", "SHIPMENT"], [1, "SHP-1"]]})
    with pytest.raises(ContainerStatusParseError) as excinfo:
        parse_container_status_workbook(data)
    assert "CONTAINER" in str(excinfo.value)


def test_remarks_are_collected_separately_from_the_column_values():
    """B4: remarks become activity feed entries, never columns."""
    data = _build_workbook(
        {
            "Sheet1": [
                ["TITLE"],
                ["NO", "CONTAINER", "REMARKS 1", "REMARKS 2", "REMARKS 3"],
                [1, "GXYU5106903", "held at port", "", "released 12/7"],
            ]
        }
    )
    parsed = parse_container_status_workbook(data)

    row = parsed.rows[0]
    assert row.remarks == ["held at port", "released 12/7"]
    assert "remarks_1" not in row.values


def test_cost_columns_are_not_imported():
    """D9: costs stay in the retained original file only."""
    data = _build_workbook(
        {
            "Sheet1": [
                ["TITLE"],
                ["NO", "CONTAINER", "TOTAL FREIGHT", "SST AMOUNT"],
                [1, "GXYU5106903", 12345.67, 890.12],
            ]
        }
    )
    parsed = parse_container_status_workbook(data)

    assert parsed.rows[0].values.get("total_freight") is None
    assert not any("freight" in k for k in parsed.rows[0].values)


def test_every_alias_target_is_a_real_field_or_a_declared_ignore():
    """A typo in the alias table would silently drop a whole column."""
    from app.services.container_status_import import FIELD_MAP, IGNORED_HEADERS

    for canonical in HEADER_ALIASES:
        assert (
            canonical in FIELD_MAP or canonical in IGNORED_HEADERS
        ), f"{canonical} is aliased but maps to nothing"
