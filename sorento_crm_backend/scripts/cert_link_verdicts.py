#!/usr/bin/env python3
"""CERT-LINK-CLEANUP: verdicts of one certificate's links against a PDF on disk. READ-ONLY.

For proving the verdict rule offline on a real certificate file (crew ruling 8 Nov, SPAN
BPAI/1327-2024). Reads the certificate's links from the database the env file points at, reads the PDF
from the path given (never from storage), and prints the counts and every link's verdict. Writes
nothing: no verdict is stamped, no session is committed.

    venv/bin/python scripts/cert_link_verdicts.py --certificate "BPAI/1327-2024" --pdf /path/to/span.pdf
    venv/bin/python scripts/cert_link_verdicts.py --certificate "BPAI/1327-2024" --pdf span.pdf --only check,found

Use SORENTO_ENV_FILE=<file> to point it at a database other than `.env`'s.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models.base import set_company_scope  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--certificate", required=True, help="Certificate number, any punctuation (e.g. BPAI/1327-2024).")
    parser.add_argument("--pdf", required=True, help="Path to the certificate PDF on disk.")
    parser.add_argument("--only", default="", help="Comma-separated verdicts to list (counts always cover all).")
    args = parser.parse_args()

    from app.models.certificate import Certificate, CertificateProduct
    from app.models.product import Product
    from app.services import certificate_link_check as link_check
    from app.services.certificate_link_report_service import _set_codes_by_product
    from app.services.certificate_service import normalize_identity

    with open(args.pdf, "rb") as handle:
        data = handle.read()

    db = SessionLocal()
    try:
        set_company_scope(db, None)  # every company: a read-only look at one certificate
        wanted_number = normalize_identity("", args.certificate)
        certificates = [
            c for c in db.query(Certificate).all() if normalize_identity("", c.certificate_number) == wanted_number
        ]
        if not certificates:
            print(f"No certificate numbered {args.certificate!r}.")
            return 1
        only = {v.strip() for v in args.only.split(",") if v.strip()}
        for certificate in certificates:
            links = (
                db.query(CertificateProduct, Product.product_code, Product.product_name)
                .join(Product, Product.id == CertificateProduct.product_id)
                .filter(CertificateProduct.certificate_id == certificate.id)
                .order_by(Product.product_code)
                .all()
            )
            wanted = link_check.wanted_for_links((cp.model_code, code) for cp, code, _name in links)
            text = link_check.read_text(data, wanted)
            sets_of = _set_codes_by_product(db, [cp.product_id for cp, _code, _name in links])
            counts: Counter = Counter()
            rows = []
            for cp, code, name in links:
                value, used = link_check.verdict(
                    text,
                    model_code=cp.model_code,
                    model_code_source=cp.model_code_source,
                    product_code=code,
                    set_codes=sets_of.get(str(cp.product_id), ()),
                )
                counts[value] += 1
                rows.append((value, code, cp.model_code or "", used or "", cp.source, (name or "")[:40]))
            print(f"\n{certificate.scheme} {certificate.certificate_number}: {len(links)} links")
            print("  " + ", ".join(f"{v} {counts.get(v, 0)}" for v in link_check.VERDICTS))
            print(f"  {'verdict':<10} {'product':<20} {'code on cert':<14} {'matched':<12} {'source':<7} name")
            for value, code, model_code, used, source, name in rows:
                if only and value not in only:
                    continue
                print(f"  {value:<10} {code:<20} {model_code:<14} {used:<12} {source:<7} {name}")
        db.rollback()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
