#!/usr/bin/env python3
"""CERT-LINK-CLEANUP: verdicts of certificate links against PDFs on disk. READ-ONLY.

Proves the verdict rule offline on real certificate files (crew rulings 8 Nov). It reads the links from
the database the env file points at and the PDFs from disk (never from storage), then prints counts and
verdicts. It writes nothing: no verdict is stamped and the session is rolled back.

One certificate:
    venv/bin/python scripts/cert_link_verdicts.py --certificate "BPAI/1327-2024" --pdf /path/to/span.pdf

Every certificate that has a file in a folder, listing each Found reached through a code that starts
with a digit (the crew's false-Found sweep):
    venv/bin/python scripts/cert_link_verdicts.py --pdf-dir state/files/quote-cert-8nov/prod-certs --digit-led-found

A certificate's file is matched in the folder by a filename containing its certificate id, current
revision id or any revision's attachment id (how crew's prod-cert files are named), then by the current
attachment's stored filename, original filename or storage key basename, and last by a filename
containing the normalised certificate number (skipped, and named, when several files match). Add `--only found,check` to list only some verdicts. Use SORENTO_ENV_FILE=<file> to point at a
database other than `.env`'s.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models.base import set_company_scope  # noqa: E402


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _index_folder(folder: str) -> dict[str, str]:
    """{normalised filename without extension, and with it: path} for every PDF in the folder tree."""
    out: dict[str, str] = {}
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if not name.lower().endswith(".pdf"):
                continue
            path = os.path.join(root, name)
            out.setdefault(_key(name), path)
            out.setdefault(_key(os.path.splitext(name)[0]), path)
    return out


def _file_for(certificate, folder_index: dict[str, str]):
    revision = certificate.current_revision
    attachment = revision.attachment if revision is not None else None
    # Crew's prod-cert files are named by certificate or attachment id: an id is unique, so a file
    # whose name CONTAINS one (`<id>.pdf`, `<id>_scan.pdf`) is that certificate's.
    ids = [str(certificate.id)]
    if revision is not None:
        ids.append(str(revision.id))
    ids += [str(r.attachment_id) for r in (certificate.revisions or []) if r.attachment_id]
    for raw_id in ids:
        key = _key(raw_id)
        hits = {path for name, path in folder_index.items() if key and key in name}
        if len(hits) == 1:
            return hits.pop()
    candidates = []
    if attachment is not None:
        candidates += [
            str(attachment.id),
            attachment.stored_filename or "",
            attachment.original_filename or "",
            os.path.basename(attachment.file_path or ""),
        ]
    for candidate in candidates:
        for variant in (_key(candidate), _key(os.path.splitext(candidate)[0])):
            if variant and variant in folder_index:
                return folder_index[variant]
    number = _key(certificate.certificate_number)
    if len(number) >= 4:
        paths = {path for name, path in folder_index.items() if number in name}
        if len(paths) == 1:
            return paths.pop()
        if paths:
            # Ambiguous (`qc12` also names `qc123.pdf`): never guess, say which.
            names = ", ".join(sorted(os.path.basename(p) for p in paths))
            print(f"skipped {certificate.scheme} {certificate.certificate_number}: several files match ({names})")
    return None


def _verdicts(db, certificate, data, families):
    from app.models.certificate import CertificateProduct
    from app.models.product import Product
    from app.services import certificate_link_check as link_check
    from app.services.certificate_link_report_service import _set_codes_by_product

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
    rows = []
    for cp, code, name in links:
        value, used = link_check.verdict(
            text,
            model_code=cp.model_code,
            model_code_source=cp.model_code_source,
            product_code=code,
            set_codes=sets_of.get(str(cp.product_id), ()),
            source=cp.source,
            families=families,
        )
        rows.append(
            (value, code, cp.model_code or "", used or "", cp.source, (name or "")[:40], sets_of.get(str(cp.product_id), set()))
        )
    return rows


def _digit_led(used: str, product_code: str, set_codes) -> bool:
    """A Found through a digit-led code that the rule does not explain: not the full product code and
    not one of the product's set codes (those are Found by design)."""
    norm = _key(used)
    return bool(norm) and norm[0].isdigit() and norm != _key(product_code) and norm not in set_codes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--certificate", help="Certificate number, any punctuation (e.g. BPAI/1327-2024).")
    parser.add_argument("--pdf", help="Path to that certificate's PDF.")
    parser.add_argument("--pdf-dir", help="Folder of certificate PDFs: check every certificate that has a file there.")
    parser.add_argument("--only", default="", help="Comma-separated verdicts to list (counts always cover all).")
    parser.add_argument(
        "--digit-led-found",
        action="store_true",
        help="List only AI links read Found through a code that starts with a digit, plus a total "
        "(manual links are a person's decision and are only counted).",
    )
    args = parser.parse_args()
    if args.pdf_dir and (args.certificate or args.pdf):
        parser.error("give either --certificate with --pdf, or --pdf-dir, not both")
    if not args.pdf_dir and not (args.certificate and args.pdf):
        parser.error("give either --certificate with --pdf, or --pdf-dir")

    from app.models.certificate import Certificate
    from app.services import certificate_link_check as link_check
    from app.services.certificate_service import normalize_identity

    only = {v.strip() for v in args.only.split(",") if v.strip()}
    db = SessionLocal()
    try:
        set_company_scope(db, None)  # every company: a read-only look
        if args.pdf_dir:
            folder_index = _index_folder(args.pdf_dir)
            targets = []
            for certificate in db.query(Certificate).order_by(Certificate.scheme, Certificate.certificate_number):
                path = _file_for(certificate, folder_index)
                if path:
                    targets.append((certificate, path))
            print(f"{len(targets)} certificates have a file in {args.pdf_dir} ({len(folder_index)} names indexed)")
        else:
            wanted_number = normalize_identity("", args.certificate)
            targets = [
                (c, args.pdf)
                for c in db.query(Certificate).all()
                if normalize_identity("", c.certificate_number) == wanted_number
            ]
            if not targets:
                print(f"No certificate numbered {args.certificate!r}.")
                return 1

        from app.services.certificate_link_report_service import catalogue_families

        families = catalogue_families(db)  # rule B-cat, once for the whole run
        totals: Counter = Counter()
        digit_led_found = []
        manual_digit_led = 0
        for certificate, path in targets:
            with open(path, "rb") as handle:
                data = handle.read()
            rows = _verdicts(db, certificate, data, families)
            counts = Counter(row[0] for row in rows)
            totals.update(counts)
            label = f"{certificate.scheme} {certificate.certificate_number}"
            digit_found = [r for r in rows if r[0] == link_check.VERDICT_FOUND and _digit_led(r[3], r[1], r[6])]
            hits = [r for r in digit_found if r[4] != "manual"]
            manual_digit_led += len(digit_found) - len(hits)
            digit_led_found += [(label, *r[:6]) for r in hits]
            if args.digit_led_found:
                if hits:
                    print(f"\n{label} ({os.path.basename(path)}): {len(hits)} digit-led Found")
                    for value, code, model_code, used, source, name, _sets in hits:
                        print(f"  {code:<20} {model_code:<14} {used:<12} {source:<7} {name}")
                continue
            print(f"\n{label} ({os.path.basename(path)}): {len(rows)} links")
            print("  " + ", ".join(f"{v} {counts.get(v, 0)}" for v in link_check.VERDICTS))
            print(f"  {'verdict':<10} {'product':<20} {'code on cert':<14} {'matched':<12} {'source':<7} name")
            for value, code, model_code, used, source, name, _sets in rows:
                if only and value not in only:
                    continue
                print(f"  {value:<10} {code:<20} {model_code:<14} {used:<12} {source:<7} {name}")

        print("\nTOTAL " + ", ".join(f"{v} {totals.get(v, 0)}" for v in link_check.VERDICTS))
        print(f"digit-led Found (AI links): {len(digit_led_found)}")
        print(f"digit-led Found on manual or confirmed links (a person's decision): {manual_digit_led}")
        db.rollback()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
