"""Score a read customer PO against an expected-matches CSV (read-only).

Used for the live check of PO line matching (PO-UPLOAD-MATCHING): upload the PO on a
project as a person would, let the worker read it, then run this against the version.

    venv/bin/python scripts/po_match_score.py --po-number <printed PO no> \
        --expected <expected-matches.csv> --po <value of the csv's `po` column> \
        [--grand-total 12345.67] [--out score.csv]

The CSV has columns ``po,no,expected,qty_blank_propose_qty`` (an extra
``item_code_as_written`` column is ignored). ``expected`` is a product code, ``none``
(no product should be picked) or ``two options`` (no pick, two or more options offered).
Writes nothing to the database.
"""
from __future__ import annotations

import argparse
import csv
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--po-number")
    group.add_argument("--version-id")
    parser.add_argument("--expected", required=True)
    parser.add_argument("--po", required=True)
    parser.add_argument("--grand-total")
    parser.add_argument("--out")
    args = parser.parse_args()

    from app.database import SessionLocal
    from app.models.product import Product
    from app.models.project_so import ProjectPOLine, ProjectPOVersion
    from app.models.projects import ProjectPurchaseOrder

    with open(args.expected, newline="") as handle:
        expected = {
            int(row["no"]): row
            for row in csv.DictReader(handle)
            if row["po"] == args.po
        }

    db = SessionLocal()
    try:
        if args.version_id:
            version = db.get(ProjectPOVersion, args.version_id)
        else:
            po = (
                db.query(ProjectPurchaseOrder)
                .filter(ProjectPurchaseOrder.po_number == args.po_number)
                .order_by(ProjectPurchaseOrder.created_at.desc())
                .first()
            )
            version = (
                db.query(ProjectPOVersion)
                .filter(ProjectPOVersion.purchase_order_id == po.id)
                .order_by(ProjectPOVersion.version_no.desc())
                .first()
                if po
                else None
            )
        if version is None:
            print("PO version not found")
            return 2

        lines = (
            db.query(ProjectPOLine)
            .filter(ProjectPOLine.po_version_id == version.id)
            .order_by(ProjectPOLine.line_no)
            .all()
        )
        extracted = version.extracted_json or {}
        matches = extracted.get("line_matches") or {}
        ids = {line.resolved_product_id for line in lines if line.resolved_product_id}
        for meta in matches.values():
            ids.update((meta or {}).get("options") or [])
        codes = {
            pid: code
            for pid, code in db.query(Product.id, Product.product_code)
            .filter(Product.id.in_(ids))
            .all()
        } if ids else {}

        rows, ok, wrong, qty_ok, qty_total = [], 0, [], 0, 0
        for line in lines:
            exp = expected.get(line.line_no)
            if exp is None:
                print(f"line {line.line_no} not in the expected file, skipped")
                continue
            meta = matches.get(str(line.line_no)) or {}
            got = codes.get(line.resolved_product_id) if line.resolved_product_id else None
            options = [codes.get(o, o) for o in meta.get("options") or []]
            want = exp.get("expected", "")
            if want == "none":
                good = got is None
            elif want == "two options":
                good = got is None and len(options) >= 2
            else:
                good = bool(got) and got.upper() == want.upper()
            if good:
                ok += 1
            elif got:
                wrong.append(f"{line.line_no}:{got}!={want}")
            proposed = exp.get("qty_blank_propose_qty") or ""
            qty_good = ""
            if proposed:
                qty_total += 1
                qty_good = bool(
                    line.qty is not None
                    and Decimal(str(line.qty)) == Decimal(proposed)
                    and meta.get("qty_suggested")
                )
                qty_ok += int(qty_good)
            rows.append(
                [line.line_no, line.stock_code_raw, line.qty, want, got or "",
                 line.resolution_source or "", meta.get("confidence") or "",
                 "|".join(options), bool(meta.get("qty_suggested")), good, qty_good]
            )

        printed = extracted.get("printed_total")
        print(f"version {version.id} state {version.extraction_state} lines {len(lines)} "
              f"expected {len(expected)}")
        print(f"matched {ok}/{len(expected)}  wrong picks {len(wrong)} {' '.join(wrong)}")
        print(f"qty proposals {qty_ok}/{qty_total}")
        print(f"printed total read {printed} expected {args.grand_total or '-'}")
        if args.out:
            with open(args.out, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["no", "item_code_read", "qty", "expected", "got", "source",
                                 "confidence", "options", "qty_suggested", "ok", "qty_ok"])
                writer.writerows(rows)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
