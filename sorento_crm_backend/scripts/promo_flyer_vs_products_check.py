"""Cross-check every ACTIVE promotion's own flyer PDF against its linked products.

Run this INSIDE a live container that already has the app code + real
DATABASE_URL (the backend or worker container - they share one image, see
Dockerfile). It never touches anything outside this process: read-only DB
queries + read-only storage downloads (the same `get_backend(...).download_file`
call `promotions_pdf_service` already uses to build the printable PDF), so no
separate credentials or CSV hand-off are needed.

    docker compose exec worker python scripts/promo_flyer_vs_products_check.py
    # or, if the worker is down: docker compose exec backend_blue python scripts/promo_flyer_vs_products_check.py
    # (check `docker compose ps` for whichever of backend_blue/backend_green is live)

"Active" mirrors the exact same definition the Promotions list and n8n
active-first lookups use (`_promotion_active_clause` in marketing_service.py):
is_active is True AND (no date window at all OR today falls within
[start_date, end_date]).

For each active promotion:
 - no flyer attachment linked at all -> flagged, nothing to check
 - flyer isn't a PDF (image) -> flagged, text-check skipped
 - flyer is a PDF -> extract text per page (PyMuPDF, already a dependency),
    find product codes printed on it, diff against what's actually linked in
    promotion_products. Any code printed on the flyer, known to the product
    master, and NOT linked = a real gap a Resubmit (AI re-extraction) can fix.

Output: a CSV at /tmp/promo_flyer_gap_<today>.csv (every active promotion, one
row per gap) and a plain-English "resubmit these" list printed to stdout,
ranked by how many products each one is missing.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date

import fitz  # PyMuPDF

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.marketing import Promotion, PromotionAttachment, PromotionProduct
from app.models.product import Product
from app.services.marketing_service import _promotion_active_clause
from app.services.storage_router import extract_key, get_backend, normalize_provider

# ---------------------------------------------------------------- code extraction
# Mirrors the heuristic already validated against a real prod export
# (promo_crosscheck_v2, 2026-08-04): generic token scan, then classify each
# token as a known product code, or a plausible-but-unknown one (right shape/
# prefix, absent from the product master - no amount of resubmit fixes those,
# the product needs creating first).
STRICT = re.compile(r"^[A-Z]{1,8}\d{2,}[A-Z0-9\-./]*$")
TOK = re.compile(r"[A-Za-z][A-Za-z0-9./\-]{3,}")
PREFIX = (
    "SRT", "CB", "CG", "CK", "CW", "CS", "CL", "MB", "MK", "MC", "MR", "MW",
    "MS", "MPW", "MAB", "NL", "BR", "SP", "UM", "VD", "WB", "GB", "HS", "KS",
    "M", "FG", "BK",
)
JUNK = {"BATHTUB", "SAMPLE", "SUS304", "PROMO"}


def _repair(text: str) -> str:
    text = re.sub(r"-\n(?=[A-Za-z0-9])", "-", text)
    text = re.sub(r"\n(?=-[A-Za-z0-9])", "", text)
    return text


def _codes_on(text: str, known: set[str]) -> tuple[set[str], set[str]]:
    """(codes matching the product master, codes that merely look like one)."""
    known_hits, unknown_hits = set(), set()
    for m in TOK.finditer(text):
        token = m.group(0).upper().strip(".-/")
        if token in JUNK or not re.search(r"\d", token):
            continue
        if token in known:
            known_hits.add(token)
        elif STRICT.match(token) and token.startswith(PREFIX) and len(token) >= 6:
            unknown_hits.add(token)
    return known_hits, unknown_hits


def _pick_flyer_attachment(db, promotion_id: str):
    return (
        db.query(PromotionAttachment)
        .filter(PromotionAttachment.promotion_id == promotion_id)
        .order_by(
            PromotionAttachment.is_primary.desc(),
            PromotionAttachment.sort_order.asc().nullslast(),
            PromotionAttachment.created_at.asc(),
        )
        .first()
    )


def _is_pdf(att) -> bool:
    mime = (getattr(att, "mime_type", None) or "").lower()
    name = (getattr(att, "original_filename", None) or getattr(att, "stored_filename", None) or "").lower()
    return mime == "application/pdf" or name.endswith(".pdf")


def main() -> int:
    db = SessionLocal()
    today = date.today()
    try:
        active_promotions = (
            db.query(Promotion).filter(_promotion_active_clause(today)).all()
        )
        print(f"{len(active_promotions)} active promotion(s) as of {today.isoformat()}")

        known = {
            (row[0] or "").strip().upper()
            for row in db.query(Product.product_code).filter(Product.product_code.isnot(None))
        }

        report = []
        summary = []  # (promotion, missing_count, unknown_count, description)

        for promo in active_promotions:
            linked = {
                (code or "").strip().upper()
                for (code,) in (
                    db.query(Product.product_code)
                    .join(PromotionProduct, PromotionProduct.product_id == Product.id)
                    .filter(PromotionProduct.promotion_id == promo.id)
                    .all()
                )
                if code
            }
            known |= linked  # a linked code is trivially "known" even off-catalogue

            link = _pick_flyer_attachment(db, promo.id)
            if link is None or link.attachment is None:
                report.append({
                    "promotion_id": promo.id, "description": promo.description,
                    "flyer": "", "issue": "NO FLYER ATTACHED", "product_code": "",
                })
                summary.append((promo, None, None, promo.description))
                continue

            att = link.attachment
            label = att.original_filename or att.stored_filename or str(att.id)
            if not _is_pdf(att):
                report.append({
                    "promotion_id": promo.id, "description": promo.description,
                    "flyer": label, "issue": "FLYER IS NOT A PDF - TEXT CHECK SKIPPED",
                    "product_code": "",
                })
                summary.append((promo, None, None, promo.description))
                continue

            try:
                provider = normalize_provider(getattr(att, "storage_provider", None))
                key = extract_key(getattr(att, "file_path", None))
                raw = get_backend(provider).download_file(key) if key else None
            except Exception as exc:  # noqa: BLE001 - one bad attachment must not kill the run
                raw = None
                print(f"  ! could not download flyer for {promo.description!r}: {exc}", file=sys.stderr)

            if raw is None:
                report.append({
                    "promotion_id": promo.id, "description": promo.description,
                    "flyer": label, "issue": "COULD NOT DOWNLOAD FLYER", "product_code": "",
                })
                summary.append((promo, None, None, promo.description))
                continue

            printed_known, printed_unknown = set(), set()
            try:
                with fitz.open(stream=raw, filetype="pdf") as pdf:
                    for page in pdf:
                        a, b = _codes_on(_repair(page.get_text()), known)
                        printed_known |= a
                        printed_unknown |= b
            except Exception as exc:  # noqa: BLE001
                report.append({
                    "promotion_id": promo.id, "description": promo.description,
                    "flyer": label, "issue": f"COULD NOT READ PDF: {exc}", "product_code": "",
                })
                summary.append((promo, None, None, promo.description))
                continue

            missing = sorted(printed_known - linked)
            unknown_only = sorted(printed_unknown - linked)
            for code in missing:
                report.append({
                    "promotion_id": promo.id, "description": promo.description,
                    "flyer": label, "issue": "ON FLYER, NOT LINKED", "product_code": code,
                })
            for code in unknown_only:
                report.append({
                    "promotion_id": promo.id, "description": promo.description,
                    "flyer": label,
                    "issue": "ON FLYER, NOT LINKED (code unknown to product master)",
                    "product_code": code,
                })
            summary.append((promo, len(missing), len(unknown_only), promo.description))

        out_path = f"/tmp/promo_flyer_gap_{today.isoformat()}.csv"
        import csv as _csv

        with open(out_path, "w", newline="") as fh:
            w = _csv.DictWriter(fh, fieldnames=["promotion_id", "description", "flyer", "issue", "product_code"])
            w.writeheader()
            w.writerows(report)

        resubmit = sorted(
            [(p, m, u, d) for (p, m, u, d) in summary if m],
            key=lambda row: row[1],
            reverse=True,
        )
        total_missing = sum(m for (_p, m, _u, _d) in resubmit)

        print(f"\nFull row-level detail written to {out_path}\n")
        if not resubmit:
            print("Nothing to resubmit - every active promotion with a readable PDF flyer "
                  "is fully linked.")
        else:
            print(f"RESUBMIT THESE {len(resubmit)} active promotion(s) - {total_missing} product(s) fixable:\n")
            for promo, missing_n, unknown_n, desc in resubmit:
                extra = f" (+{unknown_n} unknown-code, needs product created first)" if unknown_n else ""
                print(f"  {missing_n:4d}  {desc}{extra}")

        no_flyer = [d for (p, m, u, d) in summary if m is None]
        if no_flyer:
            print(f"\n{len(no_flyer)} active promotion(s) skipped (no flyer / not a PDF / unreadable) - see CSV.")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
