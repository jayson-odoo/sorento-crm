"""Hand-test setup for SPEC-SHEET-V2: the spec sheet templates the script uses, and a quotation to use.

Two jobs, both read-only unless ``--apply`` is given:

1. ``--find`` lists issued quotations whose newest revision has a photo on EVERY item (the frozen line
   photo, else the product's chosen photo), at least four items, with a product set first when there is
   one. The hand test needs a photo on every page to judge image quality.
   ``--with-set`` lists instead the quotations whose newest revision has at least one product-set line,
   whether or not every photo is present, with the photo coverage (items with a photo / items) so one
   with a set can be picked even when some photos are missing.
2. ``--company <id|code|name>`` (with ``--apply``) creates, in that company, the three published
   templates the hand test names, unless a published one with the same name and family is already
   there: ``Catalogue cover`` (Spec sheet cover), ``Item with accessories`` and ``Single item``
   (Spec sheet page), all 338.7 x 190.5 mm. The page templates carry the photo and drawing slots,
   code, name, spec lines, Accessory 1-2 (shown only when the item has them) and the AREA / COMMENT /
   REF / PREPARED BY / DATE fields, so every hand-test step has a field to act on.

Usage (from sorento_crm_backend, with the target database's env loaded):
    venv/bin/python scripts/seed_spec_sheet_handtest.py --find
    venv/bin/python scripts/seed_spec_sheet_handtest.py --with-set [--min-items 7]
    venv/bin/python scripts/seed_spec_sheet_handtest.py --company <company> [--apply]

Idempotent: re-running creates nothing new. It never edits or deletes an existing template.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WIDTH_MM = 338.7
HEIGHT_MM = 190.5
GREEN = "#3f7d3a"


def _text(n: int, x, y, w, h, text, *, size=9.0, weight=400, part=None, show_part=None, color="#111111"):
    props = {
        "kind": "text",
        "text": text,
        "fontFamily": "Inter",
        "fontSize": size,
        "fontWeight": weight,
        "color": color,
        "align": "left",
        "lineHeight": 1.3,
        "letterSpacing": 0,
    }
    if part is not None:
        props["subjectPart"] = part
    return _layer(n, "text", x, y, w, h, props, show_part=show_part)


def _image(n: int, x, y, w, h, slot, *, part=None, show_part=None):
    props = {"kind": "image", "source": None, "fit": "contain", "maskShape": "none"}
    if part is not None:
        props["subjectPart"] = part
    return _layer(n, "image", x, y, w, h, props, slot=slot, show_part=show_part)


def _box(n: int, x, y, w, h):
    props = {
        "kind": "shape",
        "shape": "rect",
        "fill": "transparent",
        "stroke": GREEN,
        "strokeWidth": 0.5,
        "cornerRadius": 0,
    }
    return _layer(n, "shape", x, y, w, h, props)


def _layer(n, kind, x, y, w, h, props, *, slot=None, show_part=None):
    layer = {
        "id": f"ht-{n}",
        "name": f"Layer {n}",
        "type": kind,
        "x_mm": x,
        "y_mm": y,
        "width_mm": w,
        "height_mm": h,
        "rotation_deg": 0,
        "z_index": n,
        "locked": False,
        "visible": True,
        "slot_binding": slot,
        "text_override": None,
        "props": props,
    }
    if show_part is not None:
        layer["show_when"] = {"part": show_part}
    return layer


def _title_block(start: int) -> list:
    """The right-hand band of the owner's sample: project, REF, AREA, PREPARED BY, DATE, COMMENT."""
    x, w = 262.0, 72.0
    return [
        _box(start, x, 4, w, 160),
        _text(start + 1, x + 2, 6, w - 4, 60, "{{doc.project_title}}", size=8),
        _text(start + 2, x + 2, 70, w - 4, 8, "REF : {{doc.ref}}", size=7, weight=600),
        _text(start + 3, x + 2, 80, w - 4, 14, "AREA : {{line.area}}", size=7, weight=600),
        _text(start + 4, x + 2, 96, w - 4, 12, "PREPARED BY : {{doc.prepared_by}} {{doc.prepared_by_phone}}", size=7),
        _text(start + 5, x + 2, 110, w - 4, 8, "DATE : {{doc.date}}", size=7),
        _text(start + 6, x + 2, 120, w - 4, 40, "COMMENT : {{line.comment}}", size=7),
        _text(start + 7, x, 168, w, 14, "SORENTO", size=14, weight=700),
    ]


def _product_block(start: int) -> list:
    return [
        _image(start, 8, 18, 112, 100, "product_image"),
        _image(start + 1, 126, 6, 130, 112, "drawing"),
        _text(start + 2, 20, 124, 100, 7, "{{product.brand}} {{product.code}} {{line.marker}}", size=9, weight=700),
        _text(start + 3, 20, 132, 100, 7, "{{product.name}}", size=9, weight=700),
        _text(start + 4, 20, 140, 100, 40, "{{product.spec_lines}}", size=7),
    ]


def _accessory_rows(start: int) -> list:
    rows = []
    for i, part in enumerate((1, 2)):
        y = 124 + i * 22
        rows += [
            _image(start + i * 3, 126, y, 18, 18, "product_image", part=part, show_part=part),
            _text(start + i * 3 + 1, 148, y, 108, 7, "{{product.brand}} {{product.code}}", size=8, weight=700, part=part, show_part=part),
            _text(start + i * 3 + 2, 148, y + 8, 108, 7, "{{product.name}}", size=7, part=part, show_part=part),
        ]
    return rows


def _docs() -> dict:
    product = _product_block(1)
    return {
        ("spec_cover", "Catalogue cover"): [
            _text(1, 20, 60, 230, 20, "{{doc.project_title}}", size=20, weight=700),
            _text(2, 20, 90, 230, 10, "{{doc.ref}}", size=11),
            _text(3, 20, 104, 230, 10, "{{doc.date}}", size=11),
            _text(4, 20, 160, 230, 16, "SORENTO", size=18, weight=700),
        ],
        ("spec_page", "Item with accessories"): product + _accessory_rows(20) + _title_block(40),
        ("spec_page", "Single item"): product + _title_block(40),
    }


def _company(db, value: str):
    from app.models.base import company_scope
    from app.models.company import Company

    with company_scope(db, None):
        rows = db.query(Company).all()
    for row in rows:
        if value in {str(row.id), str(getattr(row, "code", "") or ""), str(getattr(row, "name", "") or "")}:
            return row
    raise SystemExit(f"No company matches {value!r}. Known: " + ", ".join(
        f"{getattr(r, 'code', '')}/{getattr(r, 'name', '')}" for r in rows
    ))


def seed(db, company, apply: bool) -> None:
    from app.models.base import company_scope
    from app.models.dealer_kit import TagTemplate, TagTemplateVersion

    with company_scope(db, frozenset({company.id})):
        for (family, name), layers in _docs().items():
            existing = (
                db.query(TagTemplate)
                .filter(
                    TagTemplate.company_id == company.id,
                    TagTemplate.family == family,
                    TagTemplate.name == name,
                    TagTemplate.published_version_id.isnot(None),
                )
                .first()
            )
            if existing is not None:
                print(f"keep    {family:<10} {name!r} (already published)")
                continue
            print(f"{'create' if apply else 'would create'} {family:<10} {name!r} {len(layers)} layers")
            if not apply:
                continue
            doc = {"width_mm": WIDTH_MM, "height_mm": HEIGHT_MM, "layers": layers}
            size = {"width_mm": WIDTH_MM, "height_mm": HEIGHT_MM}
            row = TagTemplate(
                id=str(uuid.uuid4()), company_id=company.id, name=name, family=family, doc=doc, print_size=size
            )
            db.add(row)
            db.flush()
            version = TagTemplateVersion(
                id=str(uuid.uuid4()), template_id=row.id, version_no=1, doc=doc, print_size=size
            )
            db.add(version)
            db.flush()
            row.published_version_id = version.id
            db.flush()
        if apply:
            db.commit()


def find(db, limit: int = 8, with_set: bool = False, min_items: int | None = None) -> None:
    from app.models.base import company_scope
    from app.models.projects import Project, ProjectQuotationDocument, ProjectQuotationIssue
    from app.services import product_image_service as images
    from app.services import project_spec_sheet_service as spec
    from app.services.project_quotation_document_service import quotation_no

    found = []
    with company_scope(db, None):
        documents = db.query(ProjectQuotationDocument).all()
        for document in documents:
            issue = (
                db.query(ProjectQuotationIssue)
                .filter(ProjectQuotationIssue.document_id == document.id)
                .order_by(ProjectQuotationIssue.issue_no.desc())
                .first()
            )
            if issue is None:
                continue
            items = spec.snapshot_items(db, document, issue)
            floor = min_items if min_items is not None else (1 if with_set else 4)
            if len(items) < floor:
                continue
            product_ids = [i.get("product_id") for i in items if i.get("product_id")]
            chosen = images.images_for(db, product_ids) if product_ids else {}
            missing = [
                i["code"]
                for i in items
                if not i.get("image_attachment_id")
                and not (
                    i.get("product_id")
                    and chosen.get(str(i["product_id"])) is not None
                    and chosen[str(i["product_id"])].state == images.CHOSEN
                )
            ]
            sets = sum(1 for i in items if i.get("set_parts"))
            if with_set:
                if sets == 0:
                    continue
            elif missing:
                continue
            project = db.query(Project).filter(Project.id == document.project_id).first()
            with_photo = len(items) - len(missing)
            found.append((sets > 0, len(items), document, issue, project, sets, with_photo))
    if with_set:
        found.sort(key=lambda r: (-(r[6] / r[1]), -r[1]))
    else:
        found.sort(key=lambda r: (not r[0], -r[1]))
    if not found:
        print(
            "No issued quotation has a product set line."
            if with_set
            else "No issued quotation has a photo on every item."
        )
        return
    print(
        "Quotations with a product set (best photo coverage first):"
        if with_set
        else "Quotations with a photo on every item (sets first, then most items):"
    )
    for _has_set, count, document, issue, project, sets, with_photo in found[:limit]:
        number = quotation_no(document.document_no, issue.issue_no, issue.revision_label)
        project_no = getattr(project, "project_code", None) or (project.title if project else "")
        coverage = f"  photos {with_photo}/{count}" if with_set else ""
        print(f"  {number:<24} project {project_no:<14} items {count:<3} sets {sets}{coverage}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--find", action="store_true", help="List quotations with a photo on every item.")
    parser.add_argument(
        "--with-set",
        action="store_true",
        help="List quotations with a product set line and their photo coverage (items with a photo / items).",
    )
    parser.add_argument(
        "--min-items",
        type=int,
        help="Only quotations with at least this many items (pages, not counting the cover).",
    )
    parser.add_argument("--company", help="Company id, code or name to create the templates in.")
    parser.add_argument("--apply", action="store_true", help="Write the templates (default: report only).")
    args = parser.parse_args()
    if not args.find and not args.with_set and not args.company:
        parser.error("give --find, --with-set and/or --company")

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        if args.company:
            seed(db, _company(db, args.company), args.apply)
        if args.find:
            find(db, min_items=args.min_items)
        if args.with_set:
            find(db, with_set=True, min_items=args.min_items)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
