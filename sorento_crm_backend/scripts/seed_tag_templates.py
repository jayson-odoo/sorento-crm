#!/usr/bin/env python3
"""Seed the eight starter tag templates and the artwork they draw (D32, AC-L.9).

Run from ``sorento_crm_backend/``::

    PYTHONPATH=. venv/bin/python scripts/seed_tag_templates.py --company-code SRT
    PYTHONPATH=. venv/bin/python scripts/seed_tag_templates.py --company-code SRT --dry-run

What it does, in order:

1. Uploads every entry in ``seed-assets/manifest.json`` as a ``dealer_kit.asset``
   through ``asset_service.create_from_bytes`` - the SAME path the upload
   endpoint takes, so one file store, one storage router, one signing rule.
   Entries prefixed ``reference_`` and the header-band sample are visual
   references for whoever draws the templates and are deliberately NOT uploaded.
2. Inserts one ``tag_template`` per family, laid out by
   ``scripts/tag_template_seed_docs.py`` from the PDF's own geometry.

**Idempotent by name, per company.** An asset is matched on
``(company, name)`` and a template on ``(company, name)``; a second run inserts
nothing and uploads nothing. That matters more than it sounds: without it a
rerun would put 28 more objects in the bucket with 28 more rows pointing at
them, and the bucket has already been filled that way once.

A rerun does NOT rewrite an existing template. Marketing edits these in the
editor, and a seed that reimposed its own layout would throw that work away on
the next deploy. To take a new layout, delete the template and rerun.

**Company scope is explicit.** ``Asset`` and ``TagTemplate`` are company-owned
and a script starts with the scope UNSET, under which every scoped read returns
nothing and every scoped write is refused. ``--company-code`` resolves to the
company row and the whole run happens inside that scope.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Allow `from app.*` / `from scripts.*` when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.company import Company
from app.models.dealer_kit import Asset, TagTemplate
from app.schemas.price_tag import TagTemplateDocModel
from app.services.dealer_kit import asset_service

from scripts.tag_template_seed_docs import SEED_TEMPLATES, print_size_of

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("seed_tag_templates")

SEED_ASSETS_DIR = (
    Path(__file__).resolve().parents[2]
    / "documentation"
    / "plans"
    / "dealer-kit"
    / "seed-assets"
)

#: Files in the manifest that exist for a HUMAN to look at while drawing a
#: template - the price badge's composition and the header band's proportions -
#: rather than for a layer to draw. Uploading them would leave marketing picking
#: between a badge and a picture of a badge.
NOT_UPLOADED_PREFIXES = ("reference_", "brand_header_band_sample")

MIME_BY_EXTENSION = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "svg": "image/svg+xml",
}


class SeedResult:
    """What the run did, so the caller can assert on it and a human can read it."""

    def __init__(self) -> None:
        self.assets_created: list[str] = []
        self.assets_existing: list[str] = []
        self.templates_created: list[str] = []
        self.templates_existing: list[str] = []

    def summary(self) -> str:
        return (
            f"assets: {len(self.assets_created)} created, "
            f"{len(self.assets_existing)} already present | "
            f"templates: {len(self.templates_created)} created, "
            f"{len(self.templates_existing)} already present"
        )


def load_manifest() -> list[dict]:
    entries = json.loads((SEED_ASSETS_DIR / "manifest.json").read_text())
    return [
        entry
        for entry in entries
        if not entry["file"].startswith(NOT_UPLOADED_PREFIXES)
    ]


def _mime_of(filename: str) -> str:
    extension = filename.rsplit(".", 1)[-1].lower()
    mime = MIME_BY_EXTENSION.get(extension)
    if not mime:
        raise ValueError(f"No mime known for seed asset '{filename}'.")
    return mime


def seed_assets(db: Session, *, dry_run: bool) -> tuple[dict[str, str], SeedResult]:
    """Upload the manifest, returning ``{asset name: id}`` for the layouts.

    The map covers assets that were ALREADY there as well as ones this run
    created, because the second run of the seed still has to be able to build
    the documents.
    """
    result = SeedResult()
    by_name: dict[str, str] = {}

    existing = {asset.name: asset.id for asset in db.query(Asset).all()}

    for entry in load_manifest():
        name = entry["name"]
        if name in existing:
            by_name[name] = existing[name]
            result.assets_existing.append(name)
            continue

        path = SEED_ASSETS_DIR / entry["file"]
        if not path.exists():
            raise FileNotFoundError(f"Seed asset missing on disk: {path}")

        if dry_run:
            # A placeholder id, so the layouts can still be built and validated
            # on a dry run. Nothing is written and nothing is uploaded.
            by_name[name] = f"dry-run-{entry['file']}"
            result.assets_created.append(name)
            continue

        asset = asset_service.create_from_bytes(
            db,
            content=path.read_bytes(),
            name=name,
            mime=_mime_of(entry["file"]),
            kind=entry["kind"],
            tags=entry.get("tags") or None,
        )
        db.flush()
        by_name[name] = asset.id
        result.assets_created.append(name)
        logger.info("uploaded asset %s (%s)", name, entry["kind"])

    return by_name, result


def seed_templates(
    db: Session, assets: dict[str, str], result: SeedResult, *, dry_run: bool
) -> None:
    existing = {template.name for template in db.query(TagTemplate).all()}

    def lookup(name: str) -> str:
        try:
            return assets[name]
        except KeyError:  # pragma: no cover - guarded by the manifest test
            raise KeyError(
                f"Template asks for asset '{name}', which the manifest does not carry."
            ) from None

    for family, label, builder in SEED_TEMPLATES:
        doc = builder(lookup)
        # Validated on the way IN, every run, not only in the test suite: the
        # seed is the one writer of these documents and a renderer draws nothing
        # for a layer kind it does not know.
        TagTemplateDocModel.model_validate(doc)

        if label in existing:
            result.templates_existing.append(label)
            continue

        if not dry_run:
            db.add(
                TagTemplate(
                    name=label,
                    family=family,
                    doc=doc,
                    print_size=print_size_of(doc),
                )
            )
            db.flush()
        result.templates_created.append(label)
        logger.info("created template %s (%s)", label, family)


def resolve_company(db: Session, code: str) -> Company:
    company = db.query(Company).filter(Company.code == code).first()
    if not company:
        known = ", ".join(sorted(c.code for c in db.query(Company).all())) or "none"
        raise SystemExit(
            f"No company with code '{code}'. Known codes: {known}."
        )
    return company


def run(db: Session, *, company_code: str, dry_run: bool) -> SeedResult:
    # The scope filter and the insert auto-stamp are installed by the API's
    # startup and by ``worker.py``; a plain script gets NEITHER, and the failure
    # is silent in the wrong direction - the inserts succeed with a NULL
    # company_id, which reads as "shared, visible from every company" and so the
    # eight templates were invisible from the one that owns them. Idempotent, so
    # calling it here costs nothing when something already has.
    from app.services.company_scope import register_company_scope_listeners

    register_company_scope_listeners()

    company = resolve_company(db, company_code)

    with company_scope(db, frozenset({company.id})):
        assets, result = seed_assets(db, dry_run=dry_run)
        seed_templates(db, assets, result, dry_run=dry_run)

        if dry_run:
            db.rollback()
        else:
            db.commit()

    return result


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--company-code",
        default="SRT",
        help="Which company owns the seeded assets and templates (default: SRT).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate everything, write and upload nothing.",
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        result = run(db, company_code=args.company_code, dry_run=args.dry_run)
    finally:
        db.close()

    prefix = "[dry run] " if args.dry_run else ""
    logger.info("%s%s", prefix, result.summary())
    for name in result.templates_created:
        logger.info("%s  + template %s", prefix, name)
    for name in result.templates_existing:
        logger.info("%s  = template %s (unchanged)", prefix, name)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
