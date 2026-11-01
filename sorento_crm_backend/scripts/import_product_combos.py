#!/usr/bin/env python3
"""Load flyer combos (name, description, free items, parts, cover picture) from a seed file.

WHY
---
Marketing's flyer holds the combos a dealer orders as one package. The price tag now prints a
combo's own picture, description and options (PLAN-price-tag-combo-template-fields), so the
combos have to exist on their host product first. This loads them once, through the same
`ProductComboService` the Combos card uses.

SEED FORMAT
-----------
A JSON list. Per entry: `id`, `family`, `host_code`, `combo_name` (or `title`),
`combo_description`, `free_items` [{code, label, note}], `components` [{code, role}],
`choice_groups` [{role, options: [{code, descr}]}], `topups` [{code, descr}], `photo` (a file
name relative to --photos) and `guess` (text, listed in the report). Every price in the seed
(`lp`, `sp`, option `sp`, `topup`) is IGNORED: no price is loaded, so a combo prints the summed
price until marketing fills one in.

RULES
-----
* Host lookup is under the chosen company's scope only (--company, default SRT). A host code
  with no product: the combo is not loaded, status `not_loaded_host_missing`.
* A part code with no product (in that company), or a component with no code: the part is
  dropped and listed; the combo still loads.
* Components become fixed parts, `choice_groups` become parts sharing a `choice_group`,
  `topups` become parts with `is_upgrade`.
* Re-running changes nothing already there: a combo is matched on host + name; a description,
  free items or cover already set stays; parts missing are added, parts present are never
  removed; combos under other names are not touched.
* A missing photo file is listed in the report; the combo still loads.
* `--templates` also creates and publishes the two starter templates (Bathroom furniture combo,
  Kitchen sink combo), skipping any that already exist by name.

Dry run is the default: nothing is written, photos and templates included. A report CSV (one
row per seed entry: id, status, dropped parts, guess, notes) is written either way.

USAGE
-----
    cd sorento_crm_backend
    venv/bin/python scripts/import_product_combos.py --file seed.json --photos DIR --report out.csv
    venv/bin/python scripts/import_product_combos.py --file seed.json --photos DIR --report out.csv --apply [--templates]

The seed and the photos are real business data and stay outside this repository.
"""
from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence, TextIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func  # noqa: E402

from app.audit_context import AuditActor, clear_actor, stamp_actor  # noqa: E402
from app.models.base import company_scope  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.dealer_kit import TagTemplate  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.product_combo import ProductCombo  # noqa: E402
from app.services.audit_service import register_audit_listeners  # noqa: E402
from app.services.error_handler import AppException  # noqa: E402
from app.services.product_combo_service import ProductComboService  # noqa: E402

JOB_ID = "import_product_combos"
MAX_SEED_BYTES = 20 * 1024 * 1024
REPORT_COLUMNS = ["id", "status", "dropped_parts", "guess", "notes"]

S_HOST_MISSING = "not_loaded_host_missing"


# --------------------------------------------------------------------------- seed


def free_items_text(items) -> str:
    """`ZZTTAP1 Tap, Waste`: the code prefixes the label, a code-less item is its label alone."""
    out = []
    for item in items or []:
        text = f"{(item.get('code') or '').strip()} {(item.get('label') or '').strip()}".strip()
        if text:
            out.append(text)
    return ", ".join(out)


def wanted_parts(entry) -> list[dict]:
    """The parts the entry asks for, in seed order: `{code, role, group, upgrade}`."""
    parts = []
    for item in entry.get("components") or []:
        parts.append(
            {"code": (item.get("code") or "").strip(), "role": item.get("role") or "",
             "group": None, "upgrade": False}
        )
    for group in entry.get("choice_groups") or []:
        role = (group.get("role") or "").strip()
        for option in group.get("options") or []:
            parts.append(
                {"code": (option.get("code") or "").strip(), "role": role,
                 "group": role or None, "upgrade": False}
            )
    for item in entry.get("topups") or []:
        parts.append(
            {"code": (item.get("code") or "").strip(), "role": "Upgrade",
             "group": None, "upgrade": True}
        )
    return parts


def read_seed(path: str) -> list[dict]:
    if os.path.getsize(path) > MAX_SEED_BYTES:
        raise ValueError(f"file is over {MAX_SEED_BYTES} bytes")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("the seed must be a JSON list")
    return data


def photo_path(photos: Optional[Path], name: str) -> Optional[Path]:
    """The photo file for an entry, only when it sits inside the photos folder."""
    if not photos or not name:
        return None
    root = photos.resolve()
    path = (root / name).resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path


# --------------------------------------------------------------------------- products


def products_by_code(db, company_id: str, codes: set[str]) -> dict[str, Product]:
    """Products of THIS company by upper-cased code. Another company's product is not found."""
    wanted = {code.upper() for code in codes if code}
    if not wanted:
        return {}
    with company_scope(db, frozenset({company_id})):
        rows = (
            db.query(Product)
            .filter(Product.company_id == company_id, func.upper(Product.product_code).in_(wanted))
            .all()
        )
    return {row.product_code.upper(): row for row in rows}


# --------------------------------------------------------------------------- entry


def process_entry(db, entry, host, parts_by_code, photos, apply: bool) -> dict:
    """Load (or, on a dry run, only judge) one seed entry. Returns its report row."""
    row = {
        "id": str(entry.get("id") or ""),
        "status": "",
        "dropped_parts": "",
        "guess": entry.get("guess") or "",
        "notes": "",
    }
    if host is None:
        row["status"] = S_HOST_MISSING
        return row

    name = ((entry.get("combo_name") or entry.get("title") or "").strip())[:100]
    notes: list[str] = []
    dropped: list[str] = []
    keep: list[dict] = []
    for part in wanted_parts(entry):
        if not part["code"]:
            dropped.append(f"no code ({part['role'] or 'part'})")
        elif part["code"].upper() not in parts_by_code:
            dropped.append(part["code"])
        else:
            keep.append(part)
    row["dropped_parts"] = "; ".join(dropped)

    photo_name = (entry.get("photo") or "").strip()
    photo = photo_path(photos, photo_name)
    if photo_name and photo is None:
        notes.append(f"photo file missing: {photo_name}")

    if not name:
        row["status"] = "skipped_no_name"
        row["notes"] = "; ".join(notes)
        return row

    service = ProductComboService(db)
    existing = (
        db.query(ProductCombo)
        .filter(ProductCombo.host_product_id == host.id, func.lower(ProductCombo.name) == name.lower())
        .first()
    )
    present = {part.part_product_id for part in existing.parts} if existing else set()

    # What apply would add, judged the same way on a dry run. The host listed among the
    # components is the flyer's own layout, not a drop: it is skipped silently, as is a
    # product named twice.
    to_add: list[dict] = []
    for part in keep:
        product = parts_by_code[part["code"].upper()]
        if product.id == host.id:
            continue
        elif product.id in present or any(a["product"].id == product.id for a in to_add):
            continue
        else:
            to_add.append({**part, "product": product})

    description = (entry.get("combo_description") or "").strip()
    free_items = free_items_text(entry.get("free_items"))
    fill = {}
    if description and not (existing and (existing.description or "").strip()):
        fill["description"] = description
    if free_items and not (existing and (existing.free_items or "").strip()):
        fill["free_items"] = free_items
    want_photo = photo is not None and not (existing and existing.image_attachment_id)
    changes = existing is None or bool(fill) or bool(to_add) or want_photo
    row["dropped_parts"] = "; ".join(dropped)

    if not apply:
        row["status"] = "would_create" if existing is None else ("would_update" if changes else "unchanged")
        row["notes"] = "; ".join(notes)
        return row

    combo_id = (
        service.create(host.id, name, created_by=None)["id"] if existing is None else existing.id
    )
    if fill:
        service.update(combo_id, fill)
    for part in to_add:
        # `is_upgrade` goes in with the part, so a crash cannot leave an upgrade as a fixed part.
        service.add_part(combo_id, part["product"].id, part["group"], is_upgrade=part["upgrade"])
    if want_photo:
        content_type = mimetypes.guess_type(photo.name)[0]
        try:
            service.upload_image(
                combo_id, content=photo.read_bytes(), filename=photo.name,
                content_type=content_type, user_id=None,
            )
        except AppException as exc:
            notes.append(f"photo not loaded: {photo.name} ({exc.message})")

    row["status"] = "created" if existing is None else ("updated" if changes else "unchanged")
    row["notes"] = "; ".join(notes)
    return row


# --------------------------------------------------------------------------- templates

#: The approved mock's type, in points: name bold 14, description 10, list price 11, sell price the
#: biggest thing on the tag (38 bold, muted brown), choices and top-ups 9.5, free items 10.
SELL_COLOUR = "#8c7355"
STYLES = {
    "combo_name": {"size": 14, "weight": 700},
    "combo_description": {"size": 10},
    "list_price": {"size": 11},
    "sell_price": {"size": 38, "weight": 700, "color": SELL_COLOUR, "align": "right"},
    "combo_choices": {"size": 9.5},
    "included_accessories": {"size": 10},
    "combo_topups": {"size": 9.5},
}

#: (name, family, [(slug, slot, kind, x, y, w, h)]) in mm on A5 portrait 148 x 210.
STARTER_TEMPLATES = [
    (
        "Bathroom furniture combo",
        "furniture_set",
        [
            ("combo-image", "combo_image", "image", 6, 6, 70, 110),
            ("combo-name", "combo_name", "text", 80, 8, 62, 14),
            ("combo-description", "combo_description", "text", 80, 24, 62, 62),
            ("list-price", "list_price", "text", 80, 90, 62, 8),
            ("sell-price", "sell_price", "text", 80, 99, 62, 16),
            ("combo-choices", "combo_choices", "text", 6, 120, 136, 46),
            ("accessories", "included_accessories", "text", 6, 168, 136, 10),
            ("combo-topups", "combo_topups", "text", 6, 180, 136, 24),
        ],
    ),
    (
        "Kitchen sink combo",
        "sink_combo",
        [
            ("combo-image", "combo_image", "image", 6, 6, 64, 42),
            ("combo-name", "combo_name", "text", 74, 8, 68, 8),
            ("combo-description", "combo_description", "text", 74, 17, 68, 16),
            ("list-price", "list_price", "text", 74, 35, 68, 8),
            ("sell-price", "sell_price", "text", 74, 43, 68, 14),
            ("combo-choices", "combo_choices", "text", 6, 60, 136, 76),
            ("accessories", "included_accessories", "text", 6, 138, 136, 12),
            ("combo-topups", "combo_topups", "text", 6, 152, 136, 54),
        ],
    ),
]

#: Placeholders are empty on purpose: a combo with no price, or no free items, must print
#: nothing - never a stray figure, `RM` or label. Prices print as the bare figure the text
#: slot gives; a `price_badge` would print "Price TBC" for a blank price, and a label ("LP:",
#: "SP RM", "FREE:") in front of a text slot cannot be made conditional with the layer kinds
#: that exist, so none is drawn.
PLACEHOLDERS = {
    "combo_name": "Combo name",
    "combo_description": "Combo description",
    "list_price": "",
    "sell_price": "",
    "combo_choices": "Choices",
    "included_accessories": "",
    "combo_topups": "Upgrade",
}


def starter_doc(family: str, layers) -> dict:
    """A published-ready document in the shape the eight seeded templates use."""
    from scripts.tag_template_seed_docs import _Doc

    doc = _Doc(family, 148, 210)
    for slug, slot, kind, x, y, w, h in layers:
        if kind == "image":
            doc.image(slug, x, y, w, h, slot=slot, fit="contain")
        else:
            style = STYLES[slot]
            doc.text(
                slug, x, y, w, h, PLACEHOLDERS[slot],
                size=style["size"], weight=style.get("weight", 400),
                color=style.get("color", "#231f20"), align=style.get("align", "left"), slot=slot,
            )
    return doc.build()


def create_templates(db, company_id: str, apply: bool, out: TextIO) -> None:
    """Create and publish the two starters in the chosen company.

    This script runs as its own process and never installs the company-scope listeners, so
    nothing stamps `company_id` or filters a query here: both are done explicitly. A starter
    already in this company is left exactly as it is. One of that name with NO company (an
    earlier run wrote them that way) is claimed for this company, its doc and versions
    untouched. A starter of that name in another company is not touched and not claimed.
    """
    from app.services.dealer_kit import tag_template_service
    from scripts.tag_template_seed_docs import print_size_of

    for name, family, layers in STARTER_TEMPLATES:
        with company_scope(db, None):
            rows = db.query(TagTemplate).filter(TagTemplate.name == name).all()
        mine = [row for row in rows if row.company_id == company_id]
        unowned = [row for row in rows if row.company_id is None]
        if mine:
            out.write(f"template exists, left alone: {name}\n")
        elif unowned:
            if apply:
                with company_scope(db, None):
                    unowned[0].company_id = company_id
                    db.commit()
            out.write(f"{'claimed' if apply else 'would claim'} template with no company: {name}\n")
        elif not apply:
            out.write(f"would create and publish template: {name}\n")
        else:
            doc = starter_doc(family, layers)
            with company_scope(db, frozenset({company_id})):
                created = tag_template_service.create_and_publish(
                    db, name=name, family=family, doc=doc, print_size=print_size_of(doc)
                )
                # create_and_publish builds the row with no company; stamp it here too, since
                # this process has no auto-stamp.
                created.company_id = company_id
                db.commit()
            out.write(f"created and published template: {name}\n")


# --------------------------------------------------------------------------- report / main


def write_report(path: Path, rows: list[dict]) -> None:
    def safe(cell):
        # A cell a spreadsheet would run as a formula gets a leading quote.
        if isinstance(cell, str) and cell[:1] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + cell
        return cell

    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(REPORT_COLUMNS)
        for row in rows:
            writer.writerow(safe(row[column]) for column in REPORT_COLUMNS)


def main(argv: Optional[Sequence[str]] = None, db=None, out: Optional[TextIO] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--file", required=True, help="the combos seed (JSON list)")
    parser.add_argument("--photos", default=None, help="folder the seed's photo names are relative to")
    parser.add_argument("--company", default="SRT", help="company code (default SRT)")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument("--report", default=None, help="report CSV path (default: next to the seed)")
    parser.add_argument("--templates", action="store_true", help="also create the two starter templates")
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = out or sys.stdout

    try:
        entries = read_seed(args.file)
    except Exception as exc:
        out.write(f"cannot read {args.file}: {exc}\n")
        return 1

    owns_session = db is None
    if owns_session:
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        with company_scope(db, None):
            company = db.query(Company).filter(func.upper(Company.code) == args.company.upper()).first()
            company_id = company.id if company else None
        if company_id is None:
            out.write(f"unknown company code: {args.company}\n")
            return 1

        photos = Path(args.photos) if args.photos else None
        codes: set[str] = set()
        for entry in entries:
            codes.add((entry.get("host_code") or "").strip())
            codes.update(part["code"] for part in wanted_parts(entry))
        found = products_by_code(db, company_id, codes)

        register_audit_listeners()
        stamp_actor(AuditActor(actor_type="system", job_id=JOB_ID), db=db)
        rows = []
        try:
            with company_scope(db, frozenset({company_id})):
                for entry in entries:
                    host = found.get((entry.get("host_code") or "").strip().upper())
                    try:
                        rows.append(process_entry(db, entry, host, found, photos, args.apply))
                    except Exception as exc:  # one bad entry must not stop the rest
                        db.rollback()
                        rows.append(
                            {"id": str(entry.get("id") or ""), "status": "failed", "dropped_parts": "",
                             "guess": entry.get("guess") or "", "notes": str(exc)[:300]}
                        )
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            report = Path(args.report) if args.report else Path(args.file).with_name(
                f"{Path(args.file).stem}-report-{'apply' if args.apply else 'dryrun'}-{stamp}.csv"
            )
            # The report first: a template failure must not lose it.
            write_report(report, rows)
            if args.templates:
                create_templates(db, company_id, args.apply, out)
            if not args.apply:
                db.rollback()
        finally:
            clear_actor(db)

        for status in sorted({row["status"] for row in rows}):
            out.write(f"{status}: {sum(1 for row in rows if row['status'] == status)}\n")
        guesses = sum(1 for row in rows if row["guess"])
        out.write(f"entries with a guess: {guesses}\nreport: {report}\n")
        if not args.apply:
            out.write("DRY RUN: nothing written. Run with --apply to load.\n")
        return 0
    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    sys.exit(main())
