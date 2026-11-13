#!/usr/bin/env python3
"""One-off review sheet for linking EXISTING records to a project (PROJECT-RELATED-RECORDS D1, AC-C8).

Why: stock inquiries, complaints, purchase requests and sponsorship forms raised before the
Project picker carry only the typed project name. Nothing is ever linked automatically (no
joining by similar names); a person ticks each link on a reviewed list.

What:
- ``--export out.xlsx`` (read-only): every unlinked stock inquiry (``project_name``), complaint,
  purchase request and sponsorship form (``project_title``) whose trimmed, case-insensitive typed
  name equals the title of EXACTLY ONE approved project. These records carry no company, so
  the match runs across every company (two companies with the same title is two matches, not
  listed). Columns: Link? (blank), Type, Number, Date, Typed project name, Proposed project code,
  Proposed project title, record id, project id. Shared Excel style.
- ``--apply ticked.xlsx``: links only the rows whose Link? cell reads y / yes / x / 1, each through
  ``project_related_records.set_record_project`` (so each lands in that record's History, naming
  ``--actor``; the sheet's project id is checked again by ``assert_linkable_project`` there), and
  skips a row whose record has a project by now. Prints the counts. Commits.

Crew-run, never by a lane against a shared database. Run from sorento_crm_backend/ with the
deployment's env:
    venv/bin/python scripts/project_link_review.py --export review.xlsx
    venv/bin/python scripts/project_link_review.py --apply review-ticked.xlsx --actor <user id>
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HEADERS = [
    "Link?",
    "Type",
    "Number",
    "Date",
    "Typed project name",
    "Proposed project code",
    "Proposed project title",
    "record id",
    "project id",
]
_WIDTHS = {"A": 8, "B": 20, "C": 18, "D": 12, "E": 40, "F": 18, "G": 40, "H": 38, "I": 38}
_TICKED = {"y", "yes", "x", "1"}


def _key(text: Optional[str]) -> str:
    return (text or "").strip().lower()


def _dmy(value: Any) -> str:
    return value.strftime("%d/%m/%Y") if value is not None else ""


def _sources():
    """(kind, model, typed-name column, number column, date column, extra filter)."""
    from app.models.complaints import Complaint
    from app.models.procurement import PurchaseRequestHeader, StockInquiry
    from app.services.project_related_records import _malaysia_date, request_record_date

    # Stored timestamps are naive UTC: the sheet's Date is the Malaysia day, as on the screen,
    # and a request's date is the Related grid's own expression.
    request_date = request_record_date()
    return [
        ("stock_inquiry", StockInquiry, StockInquiry.project_name, StockInquiry.inquiry_number,
         _malaysia_date(StockInquiry.created_at), None),
        ("complaint", Complaint, Complaint.project_title, Complaint.complaint_number,
         Complaint.complaint_date, None),
        ("purchase_request", PurchaseRequestHeader, PurchaseRequestHeader.project_title,
         PurchaseRequestHeader.request_number, request_date,
         PurchaseRequestHeader.request_type == "purchase_request"),
        ("sponsorship_form", PurchaseRequestHeader, PurchaseRequestHeader.project_title,
         PurchaseRequestHeader.request_number, request_date,
         PurchaseRequestHeader.request_type == "sponsorship_form"),
    ]


def _single_title_matches(db) -> Dict[str, Tuple[str, str, str]]:
    """Normalised title -> (project id, code, title), for titles held by exactly ONE project."""
    from app.models.projects import Project
    from app.services.project_service import approved_projects

    seen: Dict[str, List[Tuple[str, str, str]]] = {}
    for pid, code, title in approved_projects(
        db.query(Project.id, Project.project_code, Project.title)
    ).all():
        if _key(title):
            seen.setdefault(_key(title), []).append((str(pid), code, title))
    return {key: rows[0] for key, rows in seen.items() if len(rows) == 1}


def review_rows(db) -> List[List[Any]]:
    """The sheet's body rows, in type order then number. Read across every company (the
    caller sets no scope): these records carry none of their own."""
    from app.services.project_related_records import RELATED_TYPES

    matches = _single_title_matches(db)
    rows: List[List[Any]] = []
    for kind, model, typed, number, dated, extra in _sources():
        q = db.query(model.id, number, dated, typed).filter(
            model.project_id.is_(None), typed.isnot(None)
        )
        if extra is not None:
            q = q.filter(extra)
        found = []
        for rid, num, when, name in q.all():
            match = matches.get(_key(name))
            if match:
                found.append([
                    None, RELATED_TYPES[kind].label, num, _dmy(when), name,
                    match[1], match[2], str(rid), match[0],
                ])
        rows.extend(sorted(found, key=lambda r: (r[2] or "")))
    return rows


def export_review(db, path: str) -> int:
    """Write the review sheet; reads only. Returns the number of rows listed."""
    from openpyxl import Workbook

    from app.services import excel_style

    from app.models.base import company_scope

    with company_scope(db, None):
        rows = review_rows(db)
    wb = Workbook()
    ws = wb.active
    ws.title = "Project links"
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    excel_style.style_table(ws, widths=_WIDTHS)
    wb.save(path)
    return len(rows)


def apply_review(db, path: str, *, actor: Optional[str] = None) -> Dict[str, int]:
    """Link the ticked rows through `set_record_project`; a record linked since the export is
    skipped. Does not commit (the CLI does). Returns {"linked", "skipped"}."""
    from openpyxl import load_workbook

    from app.services.project_related_records import RELATED_TYPES

    kind_of = {rt.label: kind for kind, rt in RELATED_TYPES.items()}
    sheet = load_workbook(path).active
    values = [list(r) for r in sheet.iter_rows(values_only=True)]
    at = next(
        i for i, r in enumerate(values) if r and "Link?" in [str(c).strip() if c else c for c in r]
    )
    header = [str(c).strip() if c is not None else "" for c in values[at]]
    col = {name: header.index(name) for name in ("Link?", "Type", "record id", "project id")}
    counts = {"linked": 0, "skipped": 0}
    from app.models.base import company_scope

    with company_scope(db, None):
        _apply_rows(db, values[at + 1:], col, kind_of, counts, actor)
    return counts


def _apply_rows(db, rows, col, kind_of, counts, actor) -> None:
    from app.services.error_handler import AppException
    from app.services.project_related_records import get_record, set_record_project

    for row in rows:
        if not row or str(row[col["Link?"]] or "").strip().lower() not in _TICKED:
            continue
        kind = kind_of.get(str(row[col["Type"]] or "").strip())
        record_id, project_id = row[col["record id"]], row[col["project id"]]
        if not kind or not record_id or not project_id:
            counts["skipped"] += 1
            continue
        try:
            record = get_record(db, kind, str(record_id))
            if record.project_id:
                counts["skipped"] += 1  # someone linked it by hand since the export
                continue
            set_record_project(
                db, kind=kind, record_id=str(record_id), project_id=str(project_id), actor=actor
            )
            counts["linked"] += 1
        except AppException:
            counts["skipped"] += 1  # gone, or its project is no longer approved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--export", metavar="OUT.xlsx", help="write the review sheet (read-only)")
    group.add_argument("--apply", metavar="TICKED.xlsx", help="link the ticked rows")
    parser.add_argument("--actor", metavar="USER_ID", help="the user the History names (needed with --apply)")
    args = parser.parse_args()
    if args.apply and not args.actor:
        # AC-C8: each link's History line names who linked it.
        parser.error("--apply needs --actor USER_ID (the person who ticked the sheet)")

    from app.database import SessionLocal
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()
    db = SessionLocal()
    try:
        if args.export:
            listed = export_review(db, args.export)
            db.rollback()
            print(f"Listed {listed} record(s) in {args.export}")
        else:
            counts = apply_review(db, args.apply, actor=args.actor)
            db.commit()
            print(f"Linked {counts['linked']}, skipped {counts['skipped']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
