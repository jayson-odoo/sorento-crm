"""PROJECT-RELATED-RECORDS red tests: the D1 one-off review sheet (AC-C8).

`scripts/project_link_review.py` never links anything by itself. `--export` lists each unlinked
SI (`project_name`), complaint, purchase request and sponsorship form (`project_title`) whose
trimmed, case-insensitive typed name equals the title of EXACTLY ONE approved project; `--apply`
links only the rows a person ticked, through `set_record_project`, skipping a record that already
has a project.

Testable entry points assumed here (the contract names only the CLI flags; the script convention
is `run(db, ...)`-style functions, see scripts/autocount_cancel_redecide.py):
    export_review(db, path) -> int        rows written
    apply_review(db, path) -> dict        counts, at least {"linked": n, "skipped": n}

Postgres only (`blank_session`); every row fake (marker `zzt-prr`).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from app.models.projects import Project

from ._own_scope_support import sorento, uid
from ._pg_fixture import blank_session

MARKER = "zzt-prr"
HEADERS = [
    "Link?", "Type", "Number", "Date", "Typed project name", "Proposed project code",
    "Proposed project title", "record id", "project id",
]


def _second_company(db) -> str:
    company_id = uid()
    db.execute(
        text("insert into companies (id, code, name, is_active) values (:i, :c, :n, true)"),
        {"i": company_id, "c": f"Z{uuid.uuid4().hex}".upper(), "n": f"{MARKER} other co"},
    )
    db.flush()
    return company_id


def _project(db, company_id, title, *, approval_state=None) -> Project:
    row = Project(
        id=uid(), company_id=company_id, project_code=f"ZZT-PRR-{uuid.uuid4().hex[:6]}",
        title=title, normalised_title=title.lower(), approval_state=approval_state,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def scene():
    from app.models.complaints import Complaint
    from app.models.procurement import PurchaseRequestHeader, StockInquiry

    with blank_session() as db:
        srt = sorento(db)
        other = _second_company(db)
        unique = _project(db, srt, "Zzt Prr Harbour View")
        _project(db, srt, "Zzt Prr Twin Peaks")
        _project(db, other, "Zzt Prr Twin Peaks")  # same title, second company: two matches
        _project(db, srt, "Zzt Prr Pending Place", approval_state="pending")  # not a project yet
        already = _project(db, srt, "Zzt Prr Already There")

        rows = {
            "si_match": StockInquiry(id=uid(), inquiry_number="ZZT-SI-M", status="responded",
                                     project_name="  zzt prr HARBOUR view "),
            "cx_match": Complaint(id=uid(), complaint_number="ZZT-CX-M", status="closed",
                                  complaint_date=date(2026, 3, 4), project_title="Zzt Prr Harbour View"),
            "pr_match": PurchaseRequestHeader(id=uid(), request_type="purchase_request",
                                              request_number="ZZT-PR-M", status="submitted",
                                              project_title="zzt prr harbour view"),
            "sf_match": PurchaseRequestHeader(id=uid(), request_type="sponsorship_form",
                                              request_number="ZZT-SF-M", status="submitted",
                                              project_title="ZZT PRR HARBOUR VIEW"),
            "two": StockInquiry(id=uid(), inquiry_number="ZZT-SI-TWO", status="new",
                                project_name="Zzt Prr Twin Peaks"),
            "none": Complaint(id=uid(), complaint_number="ZZT-CX-NONE", status="closed",
                              project_title="Zzt Prr Nowhere Tower"),
            "pending": PurchaseRequestHeader(id=uid(), request_type="purchase_request",
                                             request_number="ZZT-PR-PEND", status="submitted",
                                             project_title="Zzt Prr Pending Place"),
            "near": StockInquiry(id=uid(), inquiry_number="ZZT-SI-NEAR", status="new",
                                 project_name="Zzt Prr Harbour View Phase 2"),
            "linked": Complaint(id=uid(), complaint_number="ZZT-CX-LINKED", status="closed",
                                project_title="Zzt Prr Harbour View", project_id=str(already.id)),
        }
        db.add_all(rows.values())
        db.flush()
        yield db, unique, already, rows


def _sheet(path):
    sheet = load_workbook(path).active
    values = [list(r) for r in sheet.iter_rows(values_only=True)]
    header_at = next(i for i, r in enumerate(values) if r and "Link?" in [str(c).strip() if c else c for c in r])
    header = [str(c).strip() if c is not None else "" for c in values[header_at]]
    body = [dict(zip(header, r)) for r in values[header_at + 1:] if any(c not in (None, "") for c in r)]
    return sheet, header_at, header, body


def test_ac_c8_export_lists_only_exact_single_project_matches(scene, tmp_path):
    from scripts.project_link_review import export_review

    db, unique, _already, rows = scene
    out = tmp_path / "review.xlsx"
    export_review(db, str(out))
    _sheet_, _at, header, body = _sheet(out)
    assert header[: len(HEADERS)] == HEADERS
    listed = {str(r["record id"]) for r in body}
    expected = {str(rows[k].id) for k in ("si_match", "cx_match", "pr_match", "sf_match")}
    assert listed == expected
    for r in body:
        assert str(r["project id"]) == str(unique.id)
        assert r["Proposed project code"] == unique.project_code
        assert r["Proposed project title"] == unique.title
        assert r["Link?"] in (None, "")
    cx = next(r for r in body if str(r["record id"]) == str(rows["cx_match"].id))
    assert cx["Date"] == "04/03/2026"
    assert cx["Number"] == "ZZT-CX-M"


def test_ac_c8_export_writes_nothing(scene, tmp_path):
    from scripts.project_link_review import export_review

    db, _unique, _already, rows = scene
    export_review(db, str(tmp_path / "review.xlsx"))
    db.expire_all()
    for key in ("si_match", "cx_match", "pr_match", "sf_match"):
        assert db.get(type(rows[key]), rows[key].id).project_id is None, key


def _tick(path, record_ids, mark="y"):
    sheet, header_at, header, _body = _sheet(path)
    link_col = header.index("Link?") + 1
    id_col = header.index("record id") + 1
    for row in range(header_at + 2, sheet.max_row + 1):
        if str(sheet.cell(row=row, column=id_col).value) in record_ids:
            sheet.cell(row=row, column=link_col).value = mark
    sheet.parent.save(path)


def test_ac_c8_apply_links_only_ticked_rows(scene, tmp_path):
    from scripts.project_link_review import apply_review, export_review

    db, unique, _already, rows = scene
    path = tmp_path / "review.xlsx"
    export_review(db, str(path))
    _tick(str(path), {str(rows["si_match"].id)}, "y")
    _tick(str(path), {str(rows["sf_match"].id)}, "X")
    counts = apply_review(db, str(path))
    assert counts["linked"] == 2
    db.expire_all()
    assert str(db.get(type(rows["si_match"]), rows["si_match"].id).project_id) == str(unique.id)
    assert str(db.get(type(rows["sf_match"]), rows["sf_match"].id).project_id) == str(unique.id)
    assert db.get(type(rows["cx_match"]), rows["cx_match"].id).project_id is None
    assert db.get(type(rows["pr_match"]), rows["pr_match"].id).project_id is None


def test_ac_c8_apply_skips_a_record_linked_since_the_export(scene, tmp_path):
    from scripts.project_link_review import apply_review, export_review

    db, unique, already, rows = scene
    path = tmp_path / "review.xlsx"
    export_review(db, str(path))
    _tick(str(path), {str(rows["cx_match"].id)}, "yes")
    rows["cx_match"].project_id = str(already.id)  # someone linked it by hand in between
    db.flush()
    counts = apply_review(db, str(path))
    assert counts["linked"] == 0
    assert counts["skipped"] == 1
    db.expire_all()
    assert str(db.get(type(rows["cx_match"]), rows["cx_match"].id).project_id) == str(already.id)
