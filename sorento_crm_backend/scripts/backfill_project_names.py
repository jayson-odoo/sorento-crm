#!/usr/bin/env python3
"""Propose, then write, a short name for every project that has none (PROJECT-NAME Q2).

Owner answer 10 Nov (card Q2 a): a one-off AI backfill, shown first as a dry-run list for the
owner; it writes only after he approves. Until then the header shows the title, clamped.

Two steps, so what gets written is exactly the list the owner read (and may have edited):

1. Dry run (default). For each project with no name, the EXISTING registration extract
   (`portal.project_registration`, narrowed to its `name` field) reads the title and proposes a
   name. Writes NOTHING to the database; writes a CSV `project_code,title,proposed_name`.
       python scripts/backfill_project_names.py --out names.csv [--limit 20]
2. Apply the reviewed CSV. Only rows whose project still has no name are written; a blank
   `proposed_name` is skipped, so deleting a cell is how a proposal is refused.
       python scripts/backfill_project_names.py --apply names.csv

Read-only count for DBeaver:

    SELECT count(*) FROM projects.projects WHERE name IS NULL OR btrim(name) = '';

Run from sorento_crm_backend/ AFTER `alembic upgrade head`, with the deployment's AI provider
configured (the dry run makes one AI call per project and logs its usage like any extract).
Idempotent: a second `--apply` of the same file writes nothing.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import Callable, Iterable, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, or_  # noqa: E402

from app.models.projects import Project  # noqa: E402

FORM_KEY = "portal.project_registration"
NAME_MAX_LEN = 80
COLUMNS = ("project_code", "title", "proposed_name")


def unnamed(db, limit: Optional[int] = None) -> List[Project]:
    """Coded projects with no name, by code. A draft or waiting portal registration has no code
    and is named by whoever approves it, so it is left out."""
    q = (
        db.query(Project)
        .filter(or_(Project.name.is_(None), func.btrim(Project.name) == ""))
        .filter(Project.project_code.isnot(None), func.btrim(Project.title) != "")
        .order_by(Project.project_code)
    )
    return q.limit(limit).all() if limit else q.all()


def ai_proposer(db) -> Callable[[str], Optional[str]]:
    """The registration extract, asked for the name only."""
    from app.services.ai_extract.extract_service import AIExtractService, ExtractFile
    from app.services.project_service import clean_project_name

    service = AIExtractService(db)

    def propose(title: str) -> Optional[str]:
        result = service.extract(
            FORM_KEY,
            [ExtractFile(filename="title.txt", mime="text/plain", data=title.encode("utf-8"))],
            field_subset=["name"],
        )
        return clean_project_name(str((result.values or {}).get("name") or "")[:NAME_MAX_LEN])

    return propose


def dry_run(db, propose: Callable[[str], Optional[str]], limit: Optional[int] = None) -> List[Tuple[str, str, str]]:
    """One `(code, title, proposed_name)` per unnamed project. Writes nothing; a proposal that
    fails is listed blank, so one provider hiccup does not lose the rest of the list."""
    rows: List[Tuple[str, str, str]] = []
    for project in unnamed(db, limit):
        try:
            name = propose(project.title) or ""
        except Exception as exc:  # noqa: BLE001  one bad row must not stop the list
            print(f"{project.project_code}: no proposal ({type(exc).__name__})", file=sys.stderr)
            name = ""
        rows.append((project.project_code, " ".join(project.title.split()), name))
    db.rollback()
    return rows


def apply(db, rows: Iterable[dict]) -> dict:
    """Write each reviewed name onto its project, only where the project still has none."""
    from app.services.project_service import clean_project_name

    written = skipped = 0
    for row in rows:
        key = (row.get("project_code") or "").strip()
        name = clean_project_name(row.get("proposed_name"))
        if not key or not name or len(name) > NAME_MAX_LEN:
            skipped += 1
            continue
        project = db.query(Project).filter(Project.project_code == key).first()
        if project is None or (project.name or "").strip():
            skipped += 1
            continue
        project.name = name
        written += 1
    db.commit()
    return {"written": written, "skipped": skipped}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", help="Dry run: write the proposals to this CSV.")
    parser.add_argument("--limit", type=int, help="Dry run: propose for at most N projects.")
    parser.add_argument("--apply", metavar="CSV", help="Write the names in this reviewed CSV.")
    args = parser.parse_args()
    if bool(args.out) == bool(args.apply):
        parser.error("give exactly one of --out (dry run) or --apply")

    from app.database import SessionLocal
    from app.models.base import set_company_scope

    db = SessionLocal()
    # No request, no principal: `None` is the sanctioned all-companies scope.
    set_company_scope(db, None)
    try:
        if args.apply:
            with open(args.apply, newline="", encoding="utf-8") as handle:
                result = apply(db, csv.DictReader(handle))
            print(f"Done. {result['written']} project(s) named, {result['skipped']} row(s) skipped.")
            return 0
        rows = dry_run(db, ai_proposer(db), args.limit)
        with open(args.out, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(COLUMNS)
            writer.writerows(rows)
        print(f"[dry-run] {len(rows)} project(s) listed in {args.out}. No database writes.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
