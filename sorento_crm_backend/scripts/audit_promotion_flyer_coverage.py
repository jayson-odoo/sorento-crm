#!/usr/bin/env python3
"""Compare what each promotion flyer PRINTS against what the extraction LINKED.

Run from sorento_crm_backend/:
    python scripts/audit_promotion_flyer_coverage.py                    # all active
    python scripts/audit_promotion_flyer_coverage.py --all              # include expired
    python scripts/audit_promotion_flyer_coverage.py --out report.md
    python scripts/audit_promotion_flyer_coverage.py --fail-on-missing  # for cron/CI

Why this exists
---------------
The AI extraction behind `POST /api/v1/external/promotions` fails OPEN. When Gemini
reads a flyer and misses half of it, n8n still posts a well-formed payload, the
endpoint still returns 200, and the promotion still looks healthy in the UI - it just
has fewer products than the flyer advertises. Nothing in the pipeline compares the
result against the source, so a silent under-extraction is indistinguishable from a
flyer that genuinely lists three products.

The flyers are vector PDFs with a real text layer, so the source of truth is free to
read: no OCR, no second model, no token cost. This script extracts every product-code
token printed on a promotion's own flyer and diffs it against `promotion_products`.

Three outcomes per code, and the distinction is the whole point:

  MISSING          printed on the flyer, exists in the product master, NOT linked
                   -> a re-extraction can fix this. Resubmit the promotion.
  UNKNOWN CODE     printed on the flyer, absent from the product master
                   -> re-extraction will never help; create the product first.
  OK               printed and linked.

Codes are matched case-insensitively after stripping the separators that differ
between print and master data (spaces, hyphens, slashes), because a flyer that prints
"SRT-LMCB901 BL" and a master row of "SRTLMCB901-BL" are the same product and counting
that as missing would bury the real misses in noise.
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import sys
from datetime import date

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.base import set_company_scope  # noqa: E402

# A product code as printed: at least 3 leading letters then a run of digits, with
# optional separators and an optional suffix (-BL, -SH, ...). Deliberately broad -
# false positives are filtered by the product-master check, false negatives are not
# recoverable.
CODE_RE = re.compile(r"\b[A-Z]{2,}[A-Z0-9]*\d{3,}[A-Z0-9]*(?:[-/ ][A-Z0-9]{1,4})?\b")

# Tokens the regex catches that are never product codes on these flyers.
STOPWORDS = {"RM", "NETT", "PROMO", "PWP", "FOC", "GST", "SST"}


def normalize(code: str) -> str:
    """Fold the separators that differ between print and master data."""
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def extract_codes(pdf_bytes: bytes) -> set[str]:
    import fitz  # PyMuPDF - imported lazily so --help works without it

    codes: set[str] = set()
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            for raw in CODE_RE.findall(page.get_text("text").upper()):
                token = raw.strip()
                if token in STOPWORDS:
                    continue
                codes.add(normalize(token))
    return codes


def fetch_flyer(attachment) -> bytes:
    from app.services import storage_router

    key = storage_router.extract_key(attachment.file_path)
    if not key:
        raise RuntimeError(f"could not derive a storage key from {attachment.file_path!r}")
    backend = storage_router.get_backend(attachment.storage_provider)
    return backend.download_file(key)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="include promotions past end_date")
    ap.add_argument("--out", help="write a markdown report here")
    ap.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="exit 1 when any promotion has fixable missing products (cron/CI guard)",
    )
    args = ap.parse_args()

    db = SessionLocal()
    set_company_scope(db, None)
    try:
        # Every product code in the master, normalized once.
        master = {
            normalize(c)
            for (c,) in db.execute(text("SELECT product_code FROM products")).all()
            if c
        }

        where = "" if args.all else "AND (p.end_date IS NULL OR p.end_date >= :today)"
        rows = db.execute(
            text(
                f"""
                SELECT p.id, p.description, a.id AS attachment_id, a.file_path,
                       a.storage_provider, a.original_filename
                FROM promotions p
                JOIN promotion_attachments pa ON pa.promotion_id = p.id
                JOIN attachments a ON a.id = pa.attachment_id
                WHERE 1=1 {where}
                ORDER BY p.created_at DESC
                """
            ),
            {"today": date.today()},
        ).all()

        linked: dict[str, set[str]] = collections.defaultdict(set)
        for pid, code in db.execute(
            text(
                """
                SELECT pg.promotion_id, pr.product_code
                FROM promotion_groups pg
                JOIN promotion_products pp ON pp.promotion_group_id = pg.id
                JOIN products pr ON pr.id = pp.product_id
                """
            )
        ).all():
            if code:
                linked[str(pid)].add(normalize(code))

        report: list[dict] = []
        for r in rows:
            try:
                pdf = fetch_flyer(r)
                printed = extract_codes(pdf)
            except Exception as exc:  # noqa: BLE001 - one bad flyer must not stop the audit
                print(f"  ! {r.description}: {exc}", file=sys.stderr)
                continue
            have = linked.get(str(r.id), set())
            gap = printed - have
            report.append(
                {
                    "promotion_id": str(r.id),
                    "description": r.description or r.original_filename or "(untitled)",
                    "printed": len(printed),
                    "linked": len(have),
                    "missing": sorted(c for c in gap if c in master),
                    "unknown": sorted(c for c in gap if c not in master),
                }
            )

        report.sort(key=lambda x: -len(x["missing"]))
        fixable = [x for x in report if x["missing"]]
        total_missing = sum(len(x["missing"]) for x in report)

        lines = [
            "# Promotion flyer coverage",
            "",
            f"{len(report)} promotion(s) with a flyer checked.",
            f"**{len(fixable)}** have products printed on their own flyer that are not "
            f"linked but DO exist in the product master ({total_missing} products) - "
            "these are fixable by resubmitting.",
            "",
            "| Missing | Unknown code | Linked | Printed | Promotion |",
            "|--------:|-------------:|-------:|--------:|-----------|",
        ]
        for x in report:
            if not x["missing"] and not x["unknown"]:
                continue
            lines.append(
                f"| {len(x['missing'])} | {len(x['unknown'])} | {x['linked']} | "
                f"{x['printed']} | {x['description']} |"
            )
        out = "\n".join(lines)

        if args.out:
            with open(args.out, "w") as fh:
                fh.write(out + "\n")
            print(f"wrote {args.out}")
        else:
            print(out)

        if args.fail_on_missing and fixable:
            print(
                f"\nFAIL: {len(fixable)} promotion(s) under-extracted.",
                file=sys.stderr,
            )
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
