"""The local-only 2025 sponsorship workbook loader (AC-F1 to AC-F5).

The workbook is the client's own JAN-DEC'25 register, committed verbatim as
`tests/fixtures/sponsorship_2025.xlsx` (AC-F5, real-sample rule). It is the input of
AC-D5, so what is under test here is that the numbers survive the trip: the parser's
per-month totals equal the workbook's own GRAND TOTAL for the same rows, and the loader
writes those rows once no matter how many times it runs.

The loader half runs ONLY on a blank scratch schema. It writes 214 rows and is meant to be
pointed at a developer's copy of the database; a test that let it touch the shared local
one would be indistinguishable from the accident the localhost guard exists to prevent.

Run: pytest tests/test_sponsorship_2025_fixture.py -q
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest
from sqlalchemy import select

import scripts.dev.load_sponsorship_2025_fixture as loader
from app.models.access import RespondContact
from app.models.procurement import PurchaseRequestHeader, PurchaseRequestLine

from tests._pg_fixture import blank_session

WORKBOOK = Path(__file__).resolve().parent / "fixtures" / "sponsorship_2025.xlsx"

#: What the client's workbook holds, counted by hand off the 12 monthly sheets.
EXPECTED_SHEETS = 12
EXPECTED_ROWS = 214


@pytest.fixture(scope="module")
def sheets():
    return loader.parse_workbook(WORKBOOK)


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# --------------------------------------------------------------------------- AC-F5 parser


def test_workbook_is_committed_next_to_the_test():
    assert WORKBOOK.exists(), "tests/fixtures/sponsorship_2025.xlsx must be committed (AC-F5)"


def test_parser_reads_every_monthly_sheet(sheets):
    assert len(sheets) == EXPECTED_SHEETS
    assert [s["month"] for s in sheets] == [date(2025, m, 1) for m in range(1, 13)]
    assert sum(len(s["rows"]) for s in sheets) == EXPECTED_ROWS


def test_december_sheet_month_comes_from_the_tab_name_not_the_title_cell(sheets):
    """The client's Dec'25 sheet carries a November date in A4. The tab name wins.

    Trusting A4 would file all 24 December forms under November and quietly double one
    month while emptying another, which is invisible in a total and wrong in every cell.
    """
    december = sheets[11]
    assert december["sheet"] == "Dec'25"
    assert december["month"] == date(2025, 12, 1)
    assert december["month_cell"] == date(2025, 11, 1)
    assert december["month_cell_disagrees"] is True
    assert [s["sheet"] for s in sheets if s["month_cell_disagrees"]] == ["Dec'25"]


def test_month_totals_match_the_workbooks_own_sum_ranges(sheets):
    """Parser totals vs the same cells added up straight off the sheet (AC-D5's input).

    Read from the cells rather than the `=SUM(F8:F24)` text, and cross-checked against the
    value Excel cached in the GRAND TOTAL cell, so a parsing rule that silently dropped a
    row (a blank line inside the table, the "-" in a value column) cannot agree with both.
    """
    workbook = openpyxl.load_workbook(WORKBOOK, data_only=True)
    for sheet in sheets:
        worksheet = workbook[sheet["sheet"]]
        grand_total_row = sheet["grand_total_row"]

        for column, key, cached_key in (
            (6, "project_value", "sheet_total_project_value"),
            (7, "sample_price", "sheet_total_sample_price"),
        ):
            from_cells = Decimal("0")
            for row in range(loader.FIRST_DATA_ROW, grand_total_row):
                value = worksheet.cell(row, column).value
                if isinstance(value, (int, float)):
                    from_cells += Decimal(str(value))

            parsed = sum(
                (r[key] for r in sheet["rows"] if r[key] is not None), Decimal("0")
            )
            assert parsed == from_cells, f"{sheet['sheet']} {key}"

            # Excel's own cached total for the same range, to 1 cent (the workbook stores
            # a few of them with binary-float noise).
            cached = sheet[cached_key]
            assert cached is not None
            assert abs(parsed - cached) < Decimal("0.01"), f"{sheet['sheet']} {key} cached"


def test_request_numbers_are_normalised_to_the_crm_rule(sheets):
    numbers = [r["request_number"] for s in sheets for r in s["rows"]]
    assert numbers[0] == "PSSF25-0001"
    assert numbers[-1] == "PSSF25-0214"
    assert len(set(numbers)) == EXPECTED_ROWS
    assert all(len(n) == len("PSSF25-0001") for n in numbers)


def test_project_value_dash_is_blank_on_both_columns(sheets):
    """The workbook's "-" means "no value", not "text worth keeping" (AC-F2)."""
    dashes = [
        r
        for s in sheets
        for r in s["rows"]
        if r["project_value"] is None and r["project_value_text"] is None
    ]
    assert dashes, "the workbook holds rows whose PROJECT VALUE is a dash"
    assert all(r["sample_price"] is not None for r in dashes[:1])


def test_sponsor_subject_maps_onto_the_crm_lookup(sheets):
    rows = {r["request_number"]: r for s in sheets for r in s["rows"]}
    assert set(r["sponsor_subject"] for r in rows.values()) <= {
        "showroom",
        "mockup",
        "others",
    }
    # "SHOWROOM" -> showroom, and nothing parked in the free-text column.
    assert rows["PSSF25-0003"]["sponsor_subject"] == "showroom"
    assert rows["PSSF25-0003"]["sponsor_subject_other"] is None
    # "MOCK UP" -> mockup (the lookup's own keyword list, migration 243).
    assert rows["PSSF25-0012"]["sponsor_subject"] == "mockup"
    # Anything else keeps its raw text under `others`.
    assert rows["PSSF25-0004"]["sponsor_subject"] == "others"
    assert rows["PSSF25-0004"]["sponsor_subject_other"] == "MID JAN"
    # ... except when that text is the label itself, which would read "Others: OTHERS".
    assert rows["PSSF25-0015"]["sponsor_subject"] == "others"
    assert rows["PSSF25-0015"]["sponsor_subject_other"] is None
    # A blank cell is still a subject the CRM can store, and parks nothing.
    assert rows["PSSF25-0026"]["sponsor_subject"] == "others"
    assert rows["PSSF25-0026"]["sponsor_subject_other"] is None


def test_no_row_ticks_a_delivery_year(sheets):
    """Recorded, not assumed: the 2025 workbook leaves H..K empty on every row.

    S4's export still renders the tick group; this asserts the fixture year has nothing to
    tick, so an S4 expectation of "no year columns for 2025" is a fact and not a bug.
    """
    assert all(r["expected_delivery_year"] is None for s in sheets for r in s["rows"])


# ------------------------------------------------------------------------------- AC-F1


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@db.prod.internal:5432/sorento",
        "postgresql://u:p@10.0.0.7/sorento",
        "postgresql+psycopg2://u:p@sorento-crm.example.com:5432/sorento",
    ],
)
def test_loader_refuses_a_non_local_database(url):
    with pytest.raises(loader.FixtureRefused) as excinfo:
        loader.assert_local_database(url)
    message = str(excinfo.value)
    assert "fixture" in message.lower()
    assert "localhost" in message
    # The refusal names the host it saw, so the reason is readable without a rerun.
    assert message.count("://") == 0 or "password" not in message


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@localhost:5432/sorento",
        "postgresql://u:p@127.0.0.1:5432/sorento",
        "postgresql+psycopg2://u:p@[::1]:5432/sorento",
    ],
)
def test_loader_accepts_a_local_database(url):
    assert loader.assert_local_database(url) in {"localhost", "127.0.0.1", "::1"}


def test_loader_refuses_when_database_url_is_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(loader.FixtureRefused):
        loader.assert_local_database()


def test_loader_reads_the_env_when_no_url_is_passed(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/sorento")
    assert loader.assert_local_database() == "127.0.0.1"


# ------------------------------------------------------------------- AC-F2 / F3 / F4 load


def _seed_contact(db, name: str) -> str:
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6011{uuid.uuid4().hex[:8]}",
        name=name,
        session_vars={},
    )
    db.add(contact)
    db.flush()
    return str(contact.id)


@pytest.fixture
def loaded(db, sheets):
    justin = _seed_contact(db, "Justin")
    cindy = _seed_contact(db, "Cindy Lee")
    result = loader.load(db, sheets)
    return {"result": result, "justin": justin, "cindy": cindy}


def _forms(db):
    return db.execute(
        select(PurchaseRequestHeader).where(
            PurchaseRequestHeader.source == loader.SOURCE
        )
    ).scalars().all()


def test_every_workbook_row_becomes_a_form(loaded, db):
    result = loaded["result"]
    assert result["sheets"] == EXPECTED_SHEETS
    assert result["rows_seen"] == EXPECTED_ROWS
    assert result["inserted"] == EXPECTED_ROWS
    assert result["updated"] == 0
    assert len(_forms(db)) == EXPECTED_ROWS


def test_forms_are_stamped_as_the_fixture_and_approved_on_the_sheets_month(loaded, db):
    form = db.execute(
        select(PurchaseRequestHeader).where(
            PurchaseRequestHeader.request_number == "PSSF25-0002"
        )
    ).scalar_one()
    assert form.request_type == "sponsorship_form"
    assert form.source == "fixture_2025"
    assert form.status == "approved"
    assert form.approval_status == "approved"
    assert form.request_date == date(2025, 1, 1)
    assert form.approved_at == datetime(2025, 1, 1)
    assert form.submitted_at == datetime(2025, 1, 1)
    assert form.customer_name == "TUAH LEBAR DEVELOPMENT"
    assert form.project_title == "TUNJUNG KB"
    assert form.total_project_value == Decimal("500000.00")
    assert form.total_project_value_text is None
    assert form.expected_delivery_date is None


def test_a_dash_project_value_lands_on_neither_column(loaded, db):
    form = db.execute(
        select(PurchaseRequestHeader).where(
            PurchaseRequestHeader.request_number == "PSSF25-0004"
        )
    ).scalar_one()
    assert form.total_project_value is None
    assert form.total_project_value_text is None


def test_sample_price_becomes_exactly_one_line(loaded, db):
    result = loaded["result"]
    lines = db.execute(
        select(PurchaseRequestLine)
        .join(
            PurchaseRequestHeader,
            PurchaseRequestHeader.id == PurchaseRequestLine.purchase_request_id,
        )
        .where(PurchaseRequestHeader.source == loader.SOURCE)
    ).scalars().all()
    assert len(lines) == result["lines_written"]
    assert result["lines_written"] < EXPECTED_ROWS, "blank / zero sample prices write no line"

    form = db.execute(
        select(PurchaseRequestHeader).where(
            PurchaseRequestHeader.request_number == "PSSF25-0001"
        )
    ).scalar_one()
    line = db.execute(
        select(PurchaseRequestLine).where(
            PurchaseRequestLine.purchase_request_id == form.id
        )
    ).scalar_one()
    assert line.item_code == "SAMPLE"
    assert line.quantity == Decimal("1.00")
    assert line.unit_price == Decimal("1000.00")
    assert line.total == Decimal("1000.00")
    assert line.remark == loader.SOURCE


def test_a_blank_or_zero_sample_price_writes_no_line(loaded, db, sheets):
    blanks = [
        r["request_number"]
        for s in sheets
        for r in s["rows"]
        if not r["sample_price"]
    ]
    assert blanks, "the workbook holds rows with no sample price"
    for number in blanks:
        form = db.execute(
            select(PurchaseRequestHeader).where(
                PurchaseRequestHeader.request_number == number
            )
        ).scalar_one()
        assert (
            db.execute(
                select(PurchaseRequestLine).where(
                    PurchaseRequestLine.purchase_request_id == form.id
                )
            ).scalars().all()
            == []
        )


def test_the_sample_price_lines_add_up_to_the_sheet_total(loaded, db, sheets):
    """What the report will read equals what the client's sheet prints (AC-D5's premise)."""
    for sheet in sheets:
        forms = db.execute(
            select(PurchaseRequestHeader).where(
                PurchaseRequestHeader.source == loader.SOURCE,
                PurchaseRequestHeader.request_date == sheet["month"],
            )
        ).scalars().all()
        total = Decimal("0")
        for form in forms:
            for line in db.execute(
                select(PurchaseRequestLine).where(
                    PurchaseRequestLine.purchase_request_id == form.id
                )
            ).scalars():
                total += line.total
        assert abs(total - sheet["sheet_total_sample_price"]) < Decimal("0.01"), sheet["sheet"]

        value_total = sum(
            (f.total_project_value for f in forms if f.total_project_value is not None),
            Decimal("0"),
        )
        assert abs(value_total - sheet["sheet_total_project_value"]) < Decimal("0.01"), sheet["sheet"]


def test_agents_are_matched_to_contacts_and_the_rest_are_reported(loaded, db):
    result = loaded["result"]

    justin = db.execute(
        select(PurchaseRequestHeader).where(
            PurchaseRequestHeader.request_number == "PSSF25-0003"
        )
    ).scalar_one()
    assert justin.requested_by == "JUSTIN"
    assert justin.requested_by_contact_id == loaded["justin"]

    # The alias map is what carries the workbook's short spelling onto the real contact.
    cindy = db.execute(
        select(PurchaseRequestHeader).where(
            PurchaseRequestHeader.request_number == "PSSF25-0144"
        )
    ).scalar_one()
    assert cindy.requested_by == "CINDY"
    assert cindy.requested_by_contact_id == loaded["cindy"]

    # No contact exists for these, so the row keeps the typed name and nothing else.
    unmatched = db.execute(
        select(PurchaseRequestHeader).where(
            PurchaseRequestHeader.request_number == "PSSF25-0001"
        )
    ).scalar_one()
    assert unmatched.requested_by == "ACT"
    assert unmatched.requested_by_contact_id is None

    assert result["unmatched"]["ACT"] == 13
    assert "JUSTIN" not in result["unmatched"]
    assert "CINDY" not in result["unmatched"]
    assert result["matched"] + sum(result["unmatched"].values()) == EXPECTED_ROWS


def test_a_second_run_updates_and_never_duplicates(db, sheets, loaded):
    before = len(_forms(db))
    lines_before = loaded["result"]["lines_written"]

    again = loader.load(db, sheets)

    assert again["rows_seen"] == EXPECTED_ROWS
    assert again["inserted"] == 0
    assert again["updated"] == EXPECTED_ROWS
    assert again["lines_written"] == lines_before
    assert len(_forms(db)) == before

    lines = db.execute(
        select(PurchaseRequestLine)
        .join(
            PurchaseRequestHeader,
            PurchaseRequestHeader.id == PurchaseRequestLine.purchase_request_id,
        )
        .where(PurchaseRequestHeader.source == loader.SOURCE)
    ).scalars().all()
    assert len(lines) == lines_before


def test_a_second_run_repairs_an_edited_row(db, sheets, loaded):
    form = db.execute(
        select(PurchaseRequestHeader).where(
            PurchaseRequestHeader.request_number == "PSSF25-0002"
        )
    ).scalar_one()
    form.customer_name = "EDITED BY HAND"
    form.total_project_value = Decimal("1.00")
    db.flush()

    loader.load(db, sheets)
    db.refresh(form)

    assert form.customer_name == "TUAH LEBAR DEVELOPMENT"
    assert form.total_project_value == Decimal("500000.00")


def test_a_form_the_fixture_does_not_own_is_never_overwritten(db, sheets):
    """PSSF25-0001 raised by a human is left exactly as it is, and reported."""
    stranger = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_type="sponsorship_form",
        request_number="PSSF25-0001",
        customer_name="A REAL FORM",
        source="portal",
        status="draft",
    )
    db.add(stranger)
    db.flush()

    result = loader.load(db, sheets)

    # Re-read, so this asserts what is in the table rather than what is in the session.
    survivor = db.execute(
        select(PurchaseRequestHeader).where(
            PurchaseRequestHeader.request_number == "PSSF25-0001"
        )
    ).scalar_one()
    assert survivor.customer_name == "A REAL FORM"
    assert survivor.source == "portal"
    assert result["skipped_foreign"] == ["PSSF25-0001"]
    assert result["inserted"] == EXPECTED_ROWS - 1


def test_a_dry_run_writes_nothing(db, sheets):
    result = loader.load(db, sheets, dry_run=True)
    assert result["rows_seen"] == EXPECTED_ROWS
    assert result["inserted"] == EXPECTED_ROWS
    assert _forms(db) == []


def test_the_summary_names_the_month_totals_and_the_unmatched_agents(loaded, sheets):
    text = loader.format_summary(sheets, loaded["result"])
    assert "Sheets read: 12" in text
    assert "ACT" in text
    assert "Jan'25" in text
    assert "Dec'25" in text
    # Every month prints the parsed total beside the sheet's own GRAND TOTAL.
    assert text.count("match") + text.count("DIFFERS") >= EXPECTED_SHEETS
