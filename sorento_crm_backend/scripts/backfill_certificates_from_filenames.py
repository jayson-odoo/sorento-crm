"""Backfill the certificate register from existing Certification attachment filenames.

The nine certification PDFs already in the system encode everything the register
needs in their filename:

    PPS - IKRAM 04424FC - EXP 23 DEC 2026.pdf
    SPAN - IKRAM 04124FC - IWC - EXP 05 APRIL 2029.pdf
    PPS - JBC WCM PC 000321 - EXP 07 JAN 2027.pdf

so the parse is deterministic and no model is involved (BF-1). Coverage is adopted
from the `product_attachments` rows those files already have (BF-2), and every
revision is stamped `needs_review` with reason `backfilled_from_filename` (BF-3) -
a filename-derived date is never presented as verified.

DRY RUN BY DEFAULT (BF-7). Without `--apply` this prints the parse table, writes
nothing and assigns no ids. Idempotent: re-running with `--apply` adopts existing
rows instead of duplicating them (BF-6).

    venv/bin/python scripts/backfill_certificates_from_filenames.py
    venv/bin/python scripts/backfill_certificates_from_filenames.py --apply
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.base import set_company_scope  # noqa: E402
from app.services.certificate_service import CertificateService  # noqa: E402
from app.services.company_scope import (  # noqa: E402
    DEFAULT_COMPANY_ID,
    register_company_scope_listeners,
)

# This script never imports app.main, so the company-scope listeners that stamp
# company_id on every owned insert have not been registered. Without this call the
# insert goes in with a NULL company_id and dies on the NOT NULL constraint.
register_company_scope_listeners()

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# "PPS - IKRAM 04424FC - EXP 23 DEC 2026" -> scheme, body + number, date tail.
_HEAD = re.compile(r"^\s*([A-Za-z]+)\s*-\s*(.+?)\s*$")
_DATE = re.compile(r"(?:EXP\s*)?(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", re.IGNORECASE)
_BODIES = ("IKRAM", "JBC", "SIRIM", "TUV")


@dataclass
class Parsed:
    attachment_id: str
    filename: str
    scheme: Optional[str]
    certifying_body: Optional[str]
    certificate_number: Optional[str]
    valid_until: Optional[date]
    coverage: int
    problem: Optional[str] = None


def _parse_date(chunk: str) -> Optional[date]:
    m = _DATE.search(chunk)
    if not m:
        return None
    day, month_name, year = m.group(1), m.group(2).upper()[:3], m.group(3)
    month = MONTHS.get(month_name)
    if not month:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def parse_filename(name: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[date]]:
    """-> (scheme, certifying_body, certificate_number, valid_until)."""
    stem = re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE)
    parts = [p.strip() for p in stem.split(" - ") if p.strip()]
    if not parts:
        return None, None, None, None

    scheme = parts[0].upper() if re.fullmatch(r"[A-Za-z]+", parts[0]) else None
    valid_until = _parse_date(stem)

    body = number = None
    for chunk in parts[1:]:
        if _DATE.search(chunk):
            continue
        words = chunk.split()
        if words and words[0].upper() in _BODIES:
            body = words[0].upper()
            rest = " ".join(words[1:]).strip()
            if rest:
                number = rest
            break
    return scheme, body, number, valid_until


def collect(db) -> list[Parsed]:
    rows = db.execute(
        text(
            """
            SELECT a.id::text AS attachment_id,
                   COALESCE(a.stored_filename, a.original_filename) AS filename,
                   (SELECT count(*) FROM product_attachments pa
                     WHERE pa.attachment_id = a.id) AS coverage
              FROM attachments a
              JOIN attachment_types t ON t.id = a.attachment_type_id
             WHERE t.type_name = 'Certification'
               AND a.is_deleted = false
             ORDER BY filename
            """
        )
    ).mappings().all()

    out: list[Parsed] = []
    for r in rows:
        scheme, body, number, valid_until = parse_filename(r["filename"])
        problem = None
        if not scheme or not number:
            problem = "unparseable scheme or number"
        out.append(
            Parsed(
                attachment_id=r["attachment_id"],
                filename=r["filename"],
                scheme=scheme,
                certifying_body=body,
                certificate_number=number,
                valid_until=valid_until,
                coverage=int(r["coverage"] or 0),
                problem=problem,
            )
        )
    return out


def _print_table(parsed: list[Parsed]) -> None:
    print(f"{'SCHEME':<7} {'BODY':<7} {'NUMBER':<16} {'VALID UNTIL':<12} {'COVER':>5}  FILENAME")
    print("-" * 110)
    for p in parsed:
        print(
            f"{(p.scheme or '?'):<7} {(p.certifying_body or '?'):<7} "
            f"{(p.certificate_number or '?'):<16} "
            f"{(p.valid_until.isoformat() if p.valid_until else '-'):<12} "
            f"{p.coverage:>5}  {p.filename}"
            + (f"   <-- {p.problem}" if p.problem else "")
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply",
        action="store_true",
        help="actually write. Without this the script is a dry run and assigns nothing.",
    )
    args = ap.parse_args()

    db = SessionLocal()
    try:
        parsed = collect(db)
        if not parsed:
            print("No Certification attachments found. Nothing to do.")
            return 0

        _print_table(parsed)
        usable = [p for p in parsed if not p.problem]
        print(
            f"\n{len(parsed)} certification attachment(s); "
            f"{len(usable)} parse cleanly, {len(parsed) - len(usable)} need a human."
        )

        if not args.apply:
            print("\nDRY RUN - nothing was written and no ids were assigned.")
            print("Re-run with --apply to create the certificates.")
            return 0

        created = adopted = 0
        for p in usable:
            company_id = db.execute(
                text("SELECT company_id::text FROM attachments WHERE id = :i"),
                {"i": p.attachment_id},
            ).scalar()
            # Owned insert: pin the scope so company_id is stamped from the
            # attachment rather than left to a resolver that never ran here.
            # `attachments` is a company-SHARED table, so company_id is legitimately
            # NULL on the older rows. Fall back to the incumbent company, which is
            # what the auto-stamp itself does for an all-companies scope.
            set_company_scope(db, frozenset({company_id or DEFAULT_COMPANY_ID}))

            service = CertificateService(db)
            existing = service.find_by_identity(p.scheme, p.certificate_number)
            if existing is not None:
                adopted += 1
                continue

            # BF-2: coverage is adopted from the product_attachments rows this file
            # already has, so the register starts out agreeing with what the product
            # pages already serve. Passed as product UUIDs - upsert_from_extraction
            # resolves them through the scoped Product query, so a row belonging to
            # another company simply does not resolve and is left out.
            codes = [
                str(r[0])
                for r in db.execute(
                    text(
                        "SELECT pa.product_id FROM product_attachments pa "
                        "WHERE pa.attachment_id = :a"
                    ),
                    {"a": p.attachment_id},
                ).all()
            ]

            service.upsert_from_extraction(
                scheme=p.scheme,
                certificate_number=p.certificate_number,
                certifying_body=p.certifying_body,
                issuer=None,
                title=None,
                attachment_id=p.attachment_id,
                attachment_type_id=None,
                issued_at=None,
                valid_from=None,
                valid_until=p.valid_until,
                product_ids=codes,
                unmatched_products=[],
                extra_review_reasons=[{"code": "backfilled_from_filename"}],
                created_by=None,
                commit=False,
            )
            created += 1

        db.commit()
        print(f"\nApplied: {created} created, {adopted} already present.")
        print("Every backfilled revision is flagged needs_review (backfilled_from_filename).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
