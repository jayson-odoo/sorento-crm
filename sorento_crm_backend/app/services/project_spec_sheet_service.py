"""Project spec sheets (PS-SPEC-SHEET, SPEC-SHEET-V2): a cover page plus one page per quoted item.

Cards: ``documentation/plans/project-sales/CARD-ps-spec-sheet-02nov.md`` and
``PLAN-spec-sheet-v2-03nov.md``.

Nothing here draws. The pages are TAG TEMPLATES (families ``spec_cover`` / ``spec_page``) designed
in the Dealer Kit tag template editor, and the PDF is the price tag print pipeline as it stands:
this module builds a ``TagSheetDoc`` with one full-page "tag" per sheet plus the resolved rows the
template's slots and merge fields read, and ``TagSheetRenderer`` draws it in Chromium.

A spec sheet is a SAVED record (``projects.quotation_spec_sheets``, SS1, SS2 ... per quotation
document). It freezes an items snapshot (from an issued revision, or from the draft's lines), the
template VERSIONS it was made with and its per-page layer edits, so a later line edit or a
re-published template never moves a sheet the customer may already hold. The per-item settings
(order, Area, Comment, Marker, Hide, hand-picked accessories) are keyed by product id or
``set:<set id>``.

Price (owner Q-B, 2 Nov): each page row carries the quoted unit price in the same ``list_price``
field a price tag reads, so the price tag designer's own List Price slot and price badge print it.
A template that places no price prints none (the owner's sample has none).
"""
from __future__ import annotations

from app.utils.date_format import fmt_date, fmt_datetime
import io
import json
import logging
import math
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.dealer_kit import TagTemplate, TagTemplateVersion
from app.models.product import Brand, Product
from app.models.projects import (
    Project,
    ProjectQuotationDocument,
    ProjectQuotationIssue,
    ProjectQuotationIssueScope,
    ProjectQuotationLine,
    ProjectQuotationSpecSheet,
)
from app.services.dealer_kit.pricing import DEFAULT_CURRENCY
from app.services.error_handler import AppException
from app.services.pdf_render import in_malaysia
from app.services.storage_router import (
    default_provider as _default_provider,
    extract_key,
    get_backend,
    normalize_provider,
    resolve_signed_url,
)

logger = logging.getLogger(__name__)

#: ``user_downloads.kind`` of a spec sheet PDF. The print payload route answers it.
KIND = "quotation_spec_sheet_pdf"
#: ``user_downloads.source_entity_type`` of a spec sheet PDF (the sheet's own id).
SOURCE_TYPE = "quotation_spec_sheet"

#: A printed picture is the image layer's designed box at this resolution, never upscaled
#: (IMAGE-UNIFY ruling; QUOTE-PERF-HOTFIX 3 Nov).
EXPORT_DPI = 300
#: The export's decode ceiling, in the worker, one picture at a time: a JPEG over it is decoded
#: at reduced scale first (``draft``), so this bounds only a PNG or WebP. Above it the original
#: prints as before.
EXPORT_MAX_PIXELS = 100_000_000
#: How long the print page's signed links stay valid (the render waits up to 15 minutes).
_EXPORT_URL_SECONDS = 60 * 60

COVER_FAMILY = "spec_cover"
PAGE_FAMILY = "spec_page"

COVER_KEY = "cover"
DRAFT = "draft"

#: Free-text limits. Area holds a unit-type list ("TOILET (ALL TYPE, PODIUM FACILITIES & GUARD
#: HOUSE)"), so it is generous; a marker is the sample's ``*`` / ``**`` / ``***``.
AREA_MAX = 200
COMMENT_MAX = 500
MARKER_MAX = 10

#: One preview call serves one window of the reader; more than this is a client bug.
PREVIEW_KEYS_MAX = 12
#: Layers one page edit may carry.
LAYERS_MAX = 300
#: Serialized size of one page's layers, and of every page edit of a sheet together.
PAGE_EDIT_MAX = 512_000
PAGE_EDITS_TOTAL_MAX = 4_000_000
#: Layer types the designer produces (FE `TagLayerType`). The strict `TagLayerDoc` schema is not
#: used: it lacks `barcode` and demands fields a layer may legitimately omit.
LAYER_TYPES = frozenset(
    {"image", "text", "shape", "product_slot", "price_badge", "badge", "barcode", "group"}
)
LAYER_DEPTH_MAX = 8
LAYER_STRING_MAX = 5000

#: A template page outside this range (or not a finite number) is refused before Chromium sees
#: it: zero or negative sizes fail obscurely in the worker, and a huge one ties up the shared
#: render queue until the subprocess times out.
PAGE_MM_MIN = 10.0
PAGE_MM_MAX = 1500.0

NO_LINES_REASON = "Add a line to the quotation first."
#: The page size (mm) a sheet with no usable template reports; nothing is drawn at it.
DEFAULT_PAGE_MM = (338.7, 190.5)


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _row(raw: dict) -> dict:
    accessories = raw.get("accessories") or []
    return {
        "key": str(raw.get("key") or ""),
        "area": _text(raw.get("area"), AREA_MAX),
        "comment": _text(raw.get("comment"), COMMENT_MAX),
        "marker": _text(raw.get("marker"), MARKER_MAX),
        "hidden": bool(raw.get("hidden")),
        "accessories": [str(a) for a in accessories if a],
    }


def _invalid_rows(message: str) -> AppException:
    return AppException(status_code=422, message=message, code="spec_sheet_rows_invalid")


def _check_rows(rows: List[dict]) -> None:
    keys = [r["key"] for r in rows]
    if any(not k for k in keys) or len(set(keys)) != len(keys):
        raise _invalid_rows("Each item can appear once on the spec sheet.")
    hosts: Dict[str, str] = {}
    for row in rows:
        for picked in row["accessories"]:
            if picked == row["key"]:
                raise _invalid_rows("An item cannot be its own accessory.")
            if picked in hosts and hosts[picked] != row["key"]:
                raise _invalid_rows("An accessory can sit on one page only.")
            hosts[picked] = row["key"]
    for row in rows:
        if row["accessories"] and row["key"] in hosts:
            raise _invalid_rows(
                "An item printed as an accessory cannot have accessories of its own."
            )


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


# ----------------------------------------------------------------------------- templates


def _published_template(
    db: Session, template_id: str, family: str, company_id: Optional[str]
) -> TagTemplate:
    """A published template of ``family`` that belongs to the document's own company."""
    template = (
        db.query(TagTemplate)
        .filter(TagTemplate.id == str(template_id), TagTemplate.archived_at.is_(None))
        .first()
        if _is_uuid(template_id)
        else None
    )
    if (
        template is None
        or template.family != family
        or not company_id
        or template.company_id != company_id
        or template.published_version_id is None
        or template.published_version is None
    ):
        label = "Spec sheet cover" if family == COVER_FAMILY else "Spec sheet page"
        raise AppException(
            status_code=422,
            message=f"Pick a published {label} template.",
            code="spec_sheet_template_invalid",
        )
    return template


def _doc_size(name: str, doc: Optional[dict]) -> tuple:
    doc = doc or {}
    try:
        size = (float(doc.get("width_mm") or 0), float(doc.get("height_mm") or 0))
    except (TypeError, ValueError):
        size = (0.0, 0.0)
    if not all(math.isfinite(v) and PAGE_MM_MIN <= v <= PAGE_MM_MAX for v in size):
        raise AppException(
            status_code=422,
            message=(
                f"The template {name} has a page size the PDF cannot print "
                f"({PAGE_MM_MIN:g} to {PAGE_MM_MAX:g} mm)."
            ),
            code="spec_sheet_size_invalid",
        )
    return size


def _same_size(sizes: Sequence[tuple]) -> None:
    if any(size != sizes[0] for size in sizes):
        raise AppException(
            status_code=422,
            message="Page templates must be the same size as the cover.",
            code="spec_sheet_size_mismatch",
        )


def _resolve_templates(
    db: Session,
    company_id: Optional[str],
    cover_id: Optional[str],
    page_id: Optional[str],
    single_id: Optional[str],
) -> dict:
    """The three templates as they publish today, refused with the #2103 codes."""
    if not cover_id or not page_id:
        raise AppException(
            status_code=422,
            message="Pick a cover template and a page template first.",
            code="spec_sheet_templates_missing",
        )
    cover = _published_template(db, cover_id, COVER_FAMILY, company_id)
    page = _published_template(db, page_id, PAGE_FAMILY, company_id)
    single = _published_template(db, single_id, PAGE_FAMILY, company_id) if single_id else None
    used = [cover, page] + ([single] if single is not None else [])
    sizes = [_doc_size(t.name, t.published_version.doc) for t in used]
    _same_size(sizes)
    return {"cover": cover, "page": page, "single": single, "size": sizes[0]}


def _version_of(db: Session, version_id, template_id) -> Optional[TagTemplateVersion]:
    """The pinned version, else (it is gone) its template's published one, else ``None``."""
    version = db.get(TagTemplateVersion, version_id) if version_id else None
    if version is None and template_id:
        template = db.get(TagTemplate, template_id)
        version = template.published_version if template is not None else None
    return version


def _pinned_parts(db: Session, sheet: ProjectQuotationSpecSheet) -> tuple:
    """``(cover, page, single)`` version docs the sheet prints from, ``None`` for one that is
    gone: the pinned versions, never today's published ones. A missing single falls back to the
    page."""
    cover = _version_of(db, sheet.cover_version_id, sheet.cover_template_id)
    page = _version_of(db, sheet.page_version_id, sheet.page_template_id)
    single = _version_of(db, sheet.single_version_id, sheet.single_page_template_id) or page
    return cover, page, single


def templates_missing(db: Session, sheet: ProjectQuotationSpecSheet) -> List[str]:
    """Which of ``cover`` / ``page`` / ``single`` this sheet can no longer draw from (a template
    deleted before the delete was blocked). A missing single alone is not an error: the page
    template stands in for it."""
    cover, page, _single = _pinned_parts(db, sheet)
    missing = [name for name, version in (("cover", cover), ("page", page)) if version is None]
    if (sheet.single_page_template_id or sheet.single_version_id) and _version_of(
        db, sheet.single_version_id, sheet.single_page_template_id
    ) is None:
        missing.append("single")
    return missing


def missing_message(missing: Sequence[str]) -> str:
    names = [m for m in missing if m in ("cover", "page")]
    if not names:
        return ""
    plural = len(names) > 1
    return (
        f"The {' and '.join(names)} template{'s' if plural else ''} of this spec sheet "
        f"{'were' if plural else 'was'} deleted. Pick new templates to show and export it."
    )


def _pinned(db: Session, sheet: ProjectQuotationSpecSheet) -> dict:
    """The version docs the sheet prints from, or 409 `spec_sheet_template_missing` when its cover
    or page template is gone."""
    cover, page, single = _pinned_parts(db, sheet)
    if cover is None or page is None:
        raise AppException(
            status_code=409,
            message=missing_message(
                [n for n, v in (("cover", cover), ("page", page)) if v is None]
            ),
            code="spec_sheet_template_missing",
        )
    sizes = [_doc_size(f"v{v.version_no}", v.doc) for v in (cover, page, single)]
    _same_size(sizes)
    return {"cover": cover, "page": page, "single": single, "size": sizes[0]}


def newer_templates(db: Session, sheet: ProjectQuotationSpecSheet) -> bool:
    """True when a used template has published a version the sheet is not on."""
    for template_id, version_id in (
        (sheet.cover_template_id, sheet.cover_version_id),
        (sheet.page_template_id, sheet.page_version_id),
        (sheet.single_page_template_id, sheet.single_version_id),
    ):
        if not template_id:
            continue
        template = db.get(TagTemplate, template_id)
        if (
            template is not None
            and template.published_version_id
            and template.published_version_id != version_id
        ):
            return True
    return False


# ----------------------------------------------------------------------------- items


def _issue_of(db: Session, document, issue_id: str) -> Optional[ProjectQuotationIssue]:
    if not _is_uuid(issue_id):
        return None
    return (
        db.query(ProjectQuotationIssue)
        .filter(
            ProjectQuotationIssue.id == str(issue_id),
            ProjectQuotationIssue.document_id == document.id,
        )
        .first()
    )


def _newest_issue(db: Session, document) -> Optional[ProjectQuotationIssue]:
    return (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.document_id == document.id)
        .order_by(ProjectQuotationIssue.issue_no.desc())
        .first()
    )


def _version_lines(db: Session, version_ids: Sequence[str]) -> List[tuple]:
    """``(line, section)`` for every line of the given versions, scope order then line order.

    ``section`` is the Section heading the line sits under on the Lines tab: the nearest
    ``band_label`` at or above it in its own scope (a heading never runs into the next scope).
    It is the page's default AREA (owner, mock v5): one rule, typed over on the page when needed.
    """
    lines: List[tuple] = []
    for version_id in version_ids:
        section = ""
        for line in (
            db.query(ProjectQuotationLine)
            .filter(ProjectQuotationLine.version_id == version_id)
            .order_by(ProjectQuotationLine.sort_order, ProjectQuotationLine.created_at)
            .all()
        ):
            heading = (line.band_label or "").strip()
            if heading:
                section = heading
            # A heading row sets the section and is never an item itself (PROPOSAL-FORM-COLLAPSE).
            if line.is_section:
                continue
            lines.append((line, section))
    return lines


def _issue_version_ids(db: Session, issue: ProjectQuotationIssue) -> List[str]:
    return [
        row.version_id
        for row in db.query(ProjectQuotationIssueScope)
        .filter(ProjectQuotationIssueScope.issue_id == issue.id)
        .order_by(ProjectQuotationIssueScope.sort_order, ProjectQuotationIssueScope.id)
        .all()
    ]


def _draft_version_ids(db: Session, document) -> List[str]:
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    return [quotes.current_version(db, scope.id).id for scope in qdocs.list_scopes(db, document)]


def item_key(line: ProjectQuotationLine) -> Optional[str]:
    """What identifies an item across revisions: the product, or the set."""
    if line.product_set_id:
        return f"set:{line.product_set_id}"
    if line.product_id:
        return str(line.product_id)
    code = (line.product_code_snapshot or "").strip().upper()
    return f"code:{code}" if code else None


def _driver_part(line: ProjectQuotationLine) -> Optional[dict]:
    parts = line.set_parts_snapshot or []
    return next((p for p in parts if p.get("is_driver")), parts[0] if parts else None)


def _set_parts(line: ProjectQuotationLine) -> List[dict]:
    driver = _driver_part(line)
    return [p for p in (line.set_parts_snapshot or []) if p is not driver]


def snapshot_items(
    db: Session, document: ProjectQuotationDocument, issue: Optional[ProjectQuotationIssue]
) -> List[dict]:
    """The frozen item list a spec sheet is made from, one per product or set at its first
    position. An issue freezes its scope pairs; ``None`` reads each scope's current version."""
    version_ids = _issue_version_ids(db, issue) if issue is not None else _draft_version_ids(db, document)
    found: Dict[str, dict] = {}
    for line, section in _version_lines(db, version_ids):
        key = item_key(line)
        if key is None or key in found:
            continue
        driver = _driver_part(line) if line.product_set_id else None
        found[key] = {
            "key": key,
            "line_id": line.id,
            "product_id": (driver or {}).get("product_id") or line.product_id,
            "code": (driver or {}).get("product_code") or line.product_code_snapshot or "",
            "description": (driver or {}).get("description") or line.description_snapshot or "",
            "brand": line.brand_snapshot or "",
            "image_attachment_id": line.image_attachment_id,
            "drawing_attachment_id": line.drawing_attachment_id,
            "section": section,
            "unit_price": float(line.unit_price) if line.unit_price is not None else None,
            "set_parts": [
                {
                    "product_id": p.get("product_id"),
                    "product_code": p.get("product_code"),
                    "description": p.get("description"),
                }
                for p in (_set_parts(line) if line.product_set_id else [])
            ],
        }
    # The product's own brand and files fill what the line did not freeze, once, at snapshot time.
    products = _products(db, [i["product_id"] for i in found.values()])
    brands = _brands(db, products)
    files = _files(db, [i["product_id"] for i in found.values() if i["product_id"]])
    for item in found.values():
        product = products.get(str(item["product_id"])) if item["product_id"] else None
        own = files.get(str(item["product_id"]), {}) if item["product_id"] else {}
        if not item["brand"] and product is not None and product.brand_id:
            item["brand"] = brands.get(str(product.brand_id), "")
        item["image_attachment_id"] = item["image_attachment_id"] or own.get("photo")
        item["drawing_attachment_id"] = item["drawing_attachment_id"] or own.get("drawing")
    return list(found.values())


def has_lines(db: Session, document: ProjectQuotationDocument) -> bool:
    """Any line that makes an item (the Create button's only precondition): a heading-only or
    code-less quotation has nothing to print, by the same `item_key` rule the snapshot uses."""
    version_ids = _draft_version_ids(db, document)
    if not version_ids:
        return False
    return any(
        item_key(line) is not None
        for line in db.query(ProjectQuotationLine).filter(ProjectQuotationLine.version_id.in_(version_ids))
    )


# ----------------------------------------------------------------------------- products


def _products(db: Session, ids: Sequence[Optional[str]]) -> Dict[str, Product]:
    wanted = list(dict.fromkeys(str(i) for i in ids if i))
    if not wanted:
        return {}
    return {str(p.id): p for p in db.query(Product).filter(Product.id.in_(wanted)).all()}


def _brands(db: Session, products: Dict[str, Product]) -> Dict[str, str]:
    ids = {p.brand_id for p in products.values() if p.brand_id}
    if not ids:
        return {}
    return {
        str(b.id): b.brand_name or ""
        for b in db.query(Brand).filter(Brand.id.in_(list(ids))).all()
    }


def _files(db: Session, product_ids: Sequence[str]) -> Dict[str, dict]:
    """``{product_id: {"photo": id|None, "drawing": id|None}}`` by the quotation's own rules:
    the chosen photograph (never a drawing), and the first drawing by upload."""
    from app.services import product_image_service as images

    ids = [i for i in dict.fromkeys(product_ids) if i]
    if not ids:
        return {}
    files = images.files_for(db, ids)
    chosen = images.images_for(db, ids, files=files)
    out: Dict[str, dict] = {}
    for pid in ids:
        found = chosen.get(str(pid))
        drawing = next((f for f in files.get(str(pid), []) if f.is_drawing), None)
        out[str(pid)] = {
            "photo": found.attachment_id
            if found is not None and found.state == images.CHOSEN
            else None,
            "drawing": drawing.attachment_id if drawing is not None else None,
        }
    return out


def _sign(
    db: Session, attachment_ids: Sequence[Optional[str]], *, full: bool
) -> Dict[str, str]:
    """Signed URLs, omitting any that cannot be signed. The reader asks for thumbnails; only the
    export asks for the original (SPEC-SHEET-V2 AC-V5)."""
    from app.services import product_image_service as images

    return {k: v for k, v in images.preview_urls(db, attachment_ids, full=full).items() if v}


class _NoSpecRow:
    """Stands in for a product without a reviewed spec row, so the tag helpers do not look again."""

    rendered_text = None
    values: dict = {}


_ROWS = "__spec_rows__"


def _load_spec_rows(db: Session, products: Dict[str, Product], spec_cache: dict) -> None:
    """One query for every product's reviewed spec row (was one per product)."""
    from app.models.product_spec import ProductSpecifications

    ids = list(products)
    found = (
        {
            str(row.product_id): row
            for row in db.query(ProductSpecifications).filter(ProductSpecifications.product_id.in_(ids))
        }
        if ids
        else {}
    )
    spec_cache[_ROWS] = {pid: found.get(pid, _NoSpecRow()) for pid in ids}


def _product_fields(db: Session, product: Optional[Product], spec_cache: dict) -> dict:
    """Dimensions, spec lines and specs off the product master; blank for a gone product."""
    from app.services.dealer_kit import tag_data_service as tags

    if product is None:
        return {"dimensions": "", "spec_lines": [], "specs": [], "barcode": None}
    if product.id not in spec_cache:
        rows = spec_cache.get(_ROWS) or {}
        spec_row = rows[str(product.id)] if str(product.id) in rows else tags._spec_row(db, product)
        spec_cache[product.id] = {
            "dimensions": tags.dimensions_text(product, spec_row) or "",
            "spec_lines": tags.spec_lines(db, product, spec_row),
            "specs": tags.product_specs(db, product, spec_row),
            "barcode": product.barcode or None,
        }
    return spec_cache[product.id]


# ----------------------------------------------------------------------------- pages


def _quoted_price(value: Optional[float]) -> Optional[float]:
    """The quoted unit price (owner Q-B, 2 Nov 23:29). A template prints it only where the
    designer placed a price; a template without one prints no price at all. Zero prints nothing:
    it means "no separate charge" (a component quoted after its priced parent), the same rule as
    the quotation PDF's `_line_money`, and a printed 0 reads as a free product."""
    if value is None or float(value) == 0:
        return None
    return float(value)


def pages(db: Session, sheet: ProjectQuotationSpecSheet) -> List[dict]:
    """The pages after the cover, in print order, hidden ones included (flagged), built from the
    sheet's own snapshot and rows (never from live lines)."""
    items = {i["key"]: i for i in sheet.items or []}
    rows = [_row(r) for r in sheet.rows or [] if isinstance(r, dict)]
    by_key = {r["key"]: r for r in rows}
    edits = sheet.page_edits or {}

    absorbed = {
        picked
        for r in rows
        if r["key"] in items
        for picked in r["accessories"]
        if picked in items
    }
    ordered = [r["key"] for r in rows if r["key"] in items]
    ordered += [k for k in items if k not in by_key]
    ordered = [k for k in ordered if k not in absorbed]

    product_ids: List[str] = []
    for item in items.values():
        product_ids.append(item["product_id"])
        product_ids.extend(p.get("product_id") for p in item["set_parts"])
    products = _products(db, product_ids)
    brands = _brands(db, products)

    def name_of(product_id, fallback):
        product = products.get(str(product_id)) if product_id else None
        return (product.product_name if product is not None else None) or fallback or ""

    def brand_of(product_id):
        product = products.get(str(product_id)) if product_id else None
        return brands.get(str(product.brand_id), "") if product and product.brand_id else ""

    out: List[dict] = []
    for key in ordered:
        item = items[key]
        setting = by_key.get(key) or _row({"key": key})
        accessories = [
            {
                "key": None,
                "source": "set",
                "product_id": part.get("product_id"),
                "code": part.get("product_code") or "",
                "name": name_of(part.get("product_id"), part.get("description")),
                "brand": brand_of(part.get("product_id")),
            }
            for part in item["set_parts"]
        ]
        for picked in setting["accessories"]:
            other = items.get(picked)
            if other is None:
                continue
            accessories.append(
                {
                    "key": picked,
                    "source": "picked",
                    "product_id": other["product_id"],
                    "code": other["code"],
                    "name": name_of(other["product_id"], other["description"]),
                    "brand": other["brand"] or brand_of(other["product_id"]),
                    "image_attachment_id": other["image_attachment_id"],
                    "drawing_attachment_id": other["drawing_attachment_id"],
                    "_price": _quoted_price(other["unit_price"]),
                }
            )
        out.append(
            {
                "key": key,
                "line_id": item["line_id"],
                "product_id": item["product_id"],
                "code": item["code"],
                "name": name_of(item["product_id"], item["description"]),
                "brand": item["brand"] or brand_of(item["product_id"]),
                "image_attachment_id": item["image_attachment_id"],
                "drawing_attachment_id": item["drawing_attachment_id"],
                "accessories": accessories,
                "picked": list(setting["accessories"]),
                # Typed on the page, else the Section heading the line sits under.
                "area": setting["area"] or item["section"],
                "area_default": item["section"],
                "comment": setting["comment"],
                "marker": setting["marker"],
                "hidden": setting["hidden"],
                "edited": key in edits,
                "template": "page" if accessories else "single",
                # Print-only (underscore keys never leave the API): the quoted unit price.
                "_price": _quoted_price(item["unit_price"]),
            }
        )
    return out


def _recount(db: Session, sheet: ProjectQuotationSpecSheet) -> None:
    sheet.page_count = 1 + sum(1 for p in pages(db, sheet) if not p["hidden"])


# ----------------------------------------------------------------------------- print


def _document_of(db: Session, sheet: ProjectQuotationSpecSheet) -> ProjectQuotationDocument:
    document = db.get(ProjectQuotationDocument, sheet.document_id)
    if document is None:
        raise AppException(status_code=404, message="Not found")
    return document


def _doc_fields(db: Session, document, sheet: ProjectQuotationSpecSheet) -> dict:
    from app.models.user import User
    from app.services.project_quotation_document_service import quotation_no

    project = db.query(Project).filter(Project.id == document.project_id).first()
    owner = None
    if project is not None and project.owner_user_id:
        owner = db.query(User).filter(User.id == project.owner_user_id).first()
    issue = db.get(ProjectQuotationIssue, sheet.issue_id) if sheet.issue_id else None
    number = (
        quotation_no(document.document_no, issue.issue_no, issue.revision_label)
        if issue is not None
        else f"{document.document_no}-draft"
    )
    your_ref = (document.your_ref or "").strip()
    # The quotation's own date, as its PDF and cover print it, else the day it was issued.
    issued = document.doc_date or in_malaysia(
        issue.issued_at if issue is not None else sheet.items_taken_at
    )
    return {
        "project_title": ((project.title if project is not None else "") or "").strip(),
        "your_ref": your_ref,
        "quotation_no": number,
        # Q2 (a): the customer's own ref when there is one, else ours.
        "ref": your_ref or number,
        "prepared_by": (document.signatory_name or (owner.name if owner else "") or "").strip(),
        "prepared_by_phone": (
            document.signatory_phone or (getattr(owner, "contact_number", None) if owner else "") or ""
        ).strip(),
        "date": fmt_date(issued, naive_is_utc=False) if issued else "",
    }


def _image(attachment_id: Optional[str], urls: Dict[str, str]) -> Optional[dict]:
    if not attachment_id or attachment_id not in urls:
        return None
    return {"attachment_id": attachment_id, "url": urls[attachment_id], "is_primary": True}


def _blank_row(tag_id: str, label: str, doc: dict) -> dict:
    return {
        "tag_id": tag_id,
        "tag_label": label,
        "line_id": "",
        "code": "",
        "name": "",
        "brand": "",
        "dimensions": "",
        "spec_lines": "",
        "specs": [],
        "images": [],
        "parts": [],
        "own_parts": [],
        "open_groups": [],
        "set_members": "",
        "list_price": None,
        "sell_price": None,
        "show_promo_price": False,
        "included_accessories": "",
        "quantity": 1,
        "barcode": None,
        "price_tag_description": None,
        "drawing": None,
        "area": "",
        "comment": "",
        "marker": "",
        # A layer pointed at a part this page does not have draws nothing, rather than falling
        # back to the main item (which would print it twice).
        "strict_parts": True,
        "doc": doc,
    }


def _sheet(key: str, version: TagTemplateVersion, width: float, height: float, layers=None) -> dict:
    return {
        "id": f"sheet-{key}",
        "tags": [
            {
                "id": f"tag-{key}",
                "template_id": version.template_id,
                "request_tag_id": key,
                "x_mm": 0,
                "y_mm": 0,
                "width_mm": width,
                "height_mm": height,
                "layers": layers if layers is not None else (version.doc or {}).get("layers") or [],
            }
        ],
    }


def _version_asset_ids(pinned: dict) -> set:
    from app.services.dealer_kit import asset_service

    ids: set = set()
    for version in {v.id: v for v in (pinned["cover"], pinned["page"], pinned["single"])}.values():
        ids |= asset_service.tag_sheet_asset_ids(version.doc or {})
    return ids


def _stamp_media(db: Session, chosen: List[dict]) -> tuple:
    """``(products, attachment ids)`` behind ``chosen`` pages, stamping each page's and
    accessory's own ``_photo`` / ``_drawing``: the frozen line photo / drawing first, the
    product's own files as the fallback."""
    part_ids = [a["product_id"] for p in chosen for a in p["accessories"] if a.get("product_id")]
    main_ids = [p["product_id"] for p in chosen if p["product_id"]]
    files = _files(db, part_ids + main_ids)
    products = _products(db, part_ids + main_ids)
    wanted: List[Optional[str]] = []
    for page in chosen:
        own = files.get(str(page["product_id"]), {}) if page["product_id"] else {}
        page["_photo"] = page["image_attachment_id"] or own.get("photo")
        page["_drawing"] = page["drawing_attachment_id"] or own.get("drawing")
        wanted += [page["_photo"], page["_drawing"]]
        for acc in page["accessories"]:
            mine = files.get(str(acc.get("product_id")), {}) if acc.get("product_id") else {}
            acc["_photo"] = acc.get("image_attachment_id") or mine.get("photo")
            acc["_drawing"] = acc.get("drawing_attachment_id") or mine.get("drawing")
            wanted += [acc["_photo"], acc["_drawing"]]
    return products, wanted


def _storage(provider: Optional[str] = None):
    return get_backend(normalize_provider(provider) if provider else _default_provider())


def _asset_rows(db: Session, asset_ids) -> Dict[str, Any]:
    """``{asset_id: Attachment}`` behind library assets (the same rows `urls_for` signs)."""
    from app.models.dealer_kit import Asset
    from app.models.resources import Attachment

    ids = {a for a in asset_ids if a and _is_uuid(a)}
    if not ids:
        return {}
    rows = (
        db.query(Asset, Attachment)
        .join(Attachment, Attachment.id == Asset.attachment_id)
        .filter(Asset.id.in_(ids), Attachment.is_deleted.is_(False))
        .all()
    )
    return {str(asset.id): attachment for asset, attachment in rows}


def _asset_urls(db: Session, asset_ids, *, export: bool, manifest: Optional[dict]) -> Dict[str, str]:
    """``{asset_id: url}`` for the artwork a sheet draws.

    On screen never the original: the attachment's thumbnail when it has one, else a stored
    medium rendition (a pasted 4000 px logo must not reach the browser). The export prints the
    per-box copy from the manifest, the original only when there is none.
    """
    from app.services import product_image_service as images
    from app.services.dealer_kit import asset_service

    rows = _asset_rows(db, asset_ids)
    if not rows:
        return {}
    if export:
        out: Dict[str, str] = {}
        rest: List[str] = []
        for asset_id, attachment in rows.items():
            entry = (manifest or {}).get(str(attachment.id))
            url = (
                resolve_signed_url(
                    entry.get("key"),
                    provider=entry.get("provider"),
                    expires_in=_EXPORT_URL_SECONDS,
                    strict=True,
                )
                if entry
                else None
            )
            if url:
                out[asset_id] = url
            else:
                rest.append(asset_id)
        if rest:
            out.update(asset_service.urls_for(db, rest))
        return out
    return asset_service.screen_urls_for(db, rows.keys())


def _export_urls(
    db: Session, wanted: List[Optional[str]], manifest: Optional[dict]
) -> Dict[str, str]:
    """The export's pictures: the per-box copies ``prepare_export_images`` made, else the
    original (exactly what printed before the cap existed)."""
    urls: Dict[str, str] = {}
    wanted_set = {str(a) for a in wanted if a}
    for attachment_id, entry in (manifest or {}).items():
        if attachment_id not in wanted_set:
            continue
        url = resolve_signed_url(
            entry.get("key"),
            provider=entry.get("provider"),
            expires_in=_EXPORT_URL_SECONDS,
            strict=True,
        )
        if url:
            urls[attachment_id] = url
    rest = [a for a in wanted_set if a not in urls]
    if rest:
        urls.update(_sign(db, rest, full=True))
    return urls


# ----------------------------------------------------------------------------- image caps


def px_for_mm(mm: float) -> int:
    """Pixels a picture needs to print ``mm`` across at ``EXPORT_DPI``."""
    return math.ceil(mm / 25.4 * EXPORT_DPI)


def export_cap_px(size_mm: tuple) -> int:
    """The fallback cap for a picture no image layer is found for: the page's long edge at
    ``EXPORT_DPI``. No picture slot is bigger than the page."""
    return px_for_mm(max(size_mm))


def _page_layers(sheet: ProjectQuotationSpecSheet, pinned: dict, key: str, template: str) -> list:
    """The layers a page prints: its edit, else the pinned version's."""
    edit = (sheet.page_edits or {}).get(key)
    if isinstance(edit, dict) and isinstance(edit.get("layers"), list):
        return edit["layers"]
    return (pinned[template].doc or {}).get("layers") or []


def _image_boxes(sheet: ProjectQuotationSpecSheet, pinned: dict, visible: List[dict]) -> Dict[str, float]:
    """The largest box, in mm, each picture is drawn in on any printed page.

    Keys are attachment ids (a page's product photo / drawing slot, or an accessory part N slot
    through ``subjectPart``) and ``asset:<id>`` (library artwork named by a layer), read from the
    pinned version layers or the page's edit layers, whichever the page prints.
    """
    from app.services.dealer_kit import asset_service

    boxes: Dict[str, float] = {}

    def note(ident: Optional[str], layer: dict) -> None:
        if not ident:
            return
        try:
            box = max(float(layer.get("width_mm") or 0), float(layer.get("height_mm") or 0))
        except (TypeError, ValueError):
            return
        if box > 0:
            boxes[ident] = max(boxes.get(ident, 0.0), box)

    entries: List[tuple] = [(COVER_KEY, "cover", None)] + [(p["key"], p["template"], p) for p in visible]
    for key, template, page in entries:
        for layer in _page_layers(sheet, pinned, key, template):
            if not isinstance(layer, dict):
                continue
            for asset_id in asset_service.tag_sheet_asset_ids({"layers": [layer]}):
                note(f"asset:{asset_id}", layer)
            slot = layer.get("slot_binding")
            if page is None or layer.get("type") != "image" or slot not in ("product_image", "drawing"):
                continue
            attr = "_photo" if slot == "product_image" else "_drawing"
            part = (layer.get("props") or {}).get("subjectPart")
            if isinstance(part, int) and not isinstance(part, bool) and part >= 0:
                accessories = page["accessories"]
                note(accessories[part].get(attr) if part < len(accessories) else None, layer)
            else:
                note(page.get(attr), layer)
    return boxes


def _export_folder(download_id: str) -> str:
    return f"exports/quotation-spec-sheet/{download_id}/img"


def _manifest_key(download_id: str) -> str:
    return f"{_export_folder(download_id)}/manifest.json"


def prepare_export_images(db: Session, download) -> Dict[str, dict]:
    """Downscale every picture the export prints to its own box at ``EXPORT_DPI`` and store the
    copies beside the PDF, with a manifest the print payload reads.

    The cap is PER PICTURE: the largest box (mm) any image layer draws it in, across every
    printed page. A picture with no image layer found uses the page-long-edge fallback. Never
    upscaled: a picture already within its cap prints from its original. Runs in the worker, one
    picture at a time, before Chromium starts; one that cannot be read is left out of the
    manifest and prints from its original.
    """
    from PIL import Image

    from app.models.base import company_scope
    from app.models.resources import Attachment
    from app.services import product_image_service as images

    with company_scope(db, None):
        document, sheet = source_of_download(db, download)
    if not document.company_id:
        raise AppException(status_code=404, message="Not found")
    with company_scope(db, frozenset({document.company_id})):
        pinned = _pinned(db, sheet)
        fallback = export_cap_px(pinned["size"])
        visible = [p for p in pages(db, sheet) if not p["hidden"]]
        _products_unused, wanted = _stamp_media(db, visible)
        boxes = _image_boxes(sheet, pinned, visible)
        caps: Dict[str, int] = {}
        for attachment_id in {str(a) for a in wanted if a}:
            box = boxes.get(attachment_id)
            caps[attachment_id] = px_for_mm(box) if box else fallback
        for asset_id, attachment in _asset_rows(
            db, [k[len("asset:"):] for k in boxes if k.startswith("asset:")]
        ).items():
            box = boxes.get(f"asset:{asset_id}")
            cap = px_for_mm(box) if box else fallback
            caps[str(attachment.id)] = max(caps.get(str(attachment.id), 0), cap)
        ids = list(caps)
        rows = db.query(Attachment).filter(Attachment.id.in_(ids)).all() if ids else []
        sources = [(str(r.id), r.file_path, r.storage_provider) for r in rows]

    out_provider = _default_provider()
    out = _storage(out_provider)
    manifest: Dict[str, dict] = {}
    for attachment_id, file_path, provider in sources:
        key = extract_key(file_path) if file_path else None
        if not key:
            continue
        cap = caps[attachment_id]
        try:
            raw = _storage(provider).download_file(key)
            with Image.open(io.BytesIO(raw)) as opened:
                size = opened.size
            if max(size) <= cap:
                manifest[attachment_id] = {"key": file_path, "provider": normalize_provider(provider)}
                continue
            rendered = images._downscale(
                raw,
                attachment_id,
                box=cap,
                quality=85,
                upright=True,
                draft=True,
                max_pixels=EXPORT_MAX_PIXELS,
            )
            del raw
            if rendered is None:
                continue
            stored, _signed = out.upload_file(
                file_content=rendered.data,
                file_path=f"{_export_folder(str(download.id))}/{attachment_id}.jpg",
                content_type="image/jpeg",
            )
            manifest[attachment_id] = {"key": stored, "provider": out_provider}
        except Exception:  # noqa: BLE001 - that picture prints from its original instead
            logger.warning("spec sheet export: cannot cap %s", attachment_id, exc_info=True)
    try:
        out.upload_file(
            file_content=json.dumps(manifest).encode(),
            file_path=_manifest_key(str(download.id)),
            content_type="application/json",
        )
    except Exception:  # noqa: BLE001 - no manifest: the render prints originals, as before
        logger.warning("spec sheet export: cannot store manifest for %s", download.id, exc_info=True)
    return manifest


def _load_manifest(download_id: str) -> Optional[dict]:
    try:
        data = json.loads(_storage().download_file(_manifest_key(download_id)))
    except Exception:  # noqa: BLE001 - absent or unreadable: originals, as before
        return None
    return data if isinstance(data, dict) else None


def page_images(
    db: Session, sheet: ProjectQuotationSpecSheet, key: str, release=None
) -> Dict[str, Dict[str, str]]:
    """The ONE open page's pictures and artwork at ``MEDIUM_BOX``: the strip and the other pages
    keep thumbnails, the page being read gets a rendition sharp enough for a drawing's figures.
    Only what that page draws, so nothing else can be asked for. ``release`` hands the DB
    connection back before any byte moves."""
    from app.services import product_image_service as images
    from app.services.dealer_kit import asset_service

    ensure_key(db, sheet, key)
    pinned = _pinned(db, sheet)
    page = None if key == COVER_KEY else next(p for p in pages(db, sheet) if p["key"] == key)
    if page is not None and page["hidden"]:
        return {"images": {}, "assets": {}}
    wanted: List[Optional[str]] = []
    if page is not None:
        _p, wanted = _stamp_media(db, [page])
    layers = _page_layers(sheet, pinned, key, "cover" if page is None else page["template"])
    asset_att = {
        a: str(att.id)
        for a, att in _asset_rows(db, asset_service.tag_sheet_asset_ids({"layers": layers})).items()
    }
    medium = images.medium_urls(db, [*wanted, *asset_att.values()], release=release)
    return {
        "images": {str(a): medium[str(a)] for a in wanted if a and str(a) in medium},
        "assets": {a: medium[att] for a, att in asset_att.items() if att in medium},
    }


def _invalid_keys() -> AppException:
    return AppException(
        status_code=422,
        message="Those pages are not on this spec sheet.",
        code="spec_sheet_keys_invalid",
    )


def build_print_payload(
    db: Session,
    sheet: ProjectQuotationSpecSheet,
    *,
    keys: Optional[Sequence[str]] = None,
    full: bool = False,
    manifest: Optional[dict] = None,
) -> dict:
    """Everything ``TagSheetRenderer`` draws.

    Export (``keys=None``): the cover, then one sheet per VISIBLE page. A window (``keys``): just
    those pages, hidden ones included and listed under ``hidden`` so the reader can grey them.
    ``full`` signs the original images (export only); the default signs thumbnails.
    """
    from app.services.dealer_kit import asset_service

    document = _document_of(db, sheet)
    pinned = _pinned(db, sheet)
    width, height = pinned["size"]
    doc_fields = _doc_fields(db, document, sheet)
    every = pages(db, sheet)
    visible = [p for p in every if not p["hidden"]]
    numbers = {COVER_KEY: 1}
    numbers.update({p["key"]: n for n, p in enumerate(visible, start=2)})

    if keys is None:
        chosen, with_cover = visible, True
    else:
        known = {COVER_KEY} | {p["key"] for p in every}
        if any(k not in known for k in keys):
            raise _invalid_keys()
        wanted = set(keys)
        chosen, with_cover = [p for p in every if p["key"] in wanted], COVER_KEY in wanted

    products, wanted_media = _stamp_media(db, chosen)
    # On screen: thumbnails (a library asset: a rendition, never its original). The export prints
    # the per-box copies `prepare_export_images` made, else the originals as before.
    if full:
        urls = _export_urls(db, wanted_media, manifest)
    else:
        urls = _sign(db, wanted_media, full=False)

    edits = sheet.page_edits or {}

    def layers_of(key: str):
        edit = edits.get(key)
        return edit.get("layers") if isinstance(edit, dict) else None

    spec_cache: dict = {}
    _load_spec_rows(db, products, spec_cache)
    resolved: Dict[str, dict] = {}
    sheets: List[dict] = []
    if with_cover:
        resolved[COVER_KEY] = _blank_row(COVER_KEY, "Cover", doc_fields)
        sheets.append(_sheet(COVER_KEY, pinned["cover"], width, height, layers_of(COVER_KEY)))
    for page in chosen:
        product = products.get(str(page["product_id"])) if page["product_id"] else None
        fields = _product_fields(db, product, spec_cache)
        parts = []
        for acc in page["accessories"]:
            part_product = products.get(str(acc["product_id"])) if acc.get("product_id") else None
            part_fields = _product_fields(db, part_product, spec_cache)
            photo = _image(acc["_photo"], urls)
            parts.append(
                {
                    "product_id": acc.get("product_id"),
                    "code": acc["code"],
                    "name": acc["name"],
                    "brand": acc["brand"],
                    "dimensions": part_fields["dimensions"],
                    "spec_lines": part_fields["spec_lines"],
                    "specs": part_fields["specs"],
                    "images": [photo] if photo else [],
                    "drawing": _image(acc["_drawing"], urls),
                    "barcode": part_fields["barcode"],
                    # A set part has no price of its own (the set line carries it); a
                    # hand-picked accessory carries its own quoted line price.
                    "list_price": acc.get("_price"),
                    "sell_price": None,
                    "currency": DEFAULT_CURRENCY,
                }
            )
        photo = _image(page["_photo"], urls)
        row = _blank_row(page["key"], str(numbers.get(page["key"], "")), doc_fields)
        row.update(
            {
                "line_id": page["line_id"],
                "code": page["code"],
                "name": page["name"],
                "brand": page["brand"],
                "dimensions": fields["dimensions"],
                "spec_lines": "\n".join(fields["spec_lines"]),
                "specs": fields["specs"],
                "images": [photo] if photo else [],
                "drawing": _image(page["_drawing"], urls),
                "barcode": fields["barcode"],
                "parts": parts,
                "own_parts": parts,
                "area": page["area"].upper(),
                "comment": page["comment"],
                "marker": page["marker"],
                # The quoted unit price, through the same fields a price tag's List Price
                # slot and price badge read. No promotion on a quotation.
                "list_price": page["_price"],
                "parent_list_price": page["_price"],
                "currency": DEFAULT_CURRENCY,
            }
        )
        resolved[page["key"]] = row
        version = pinned["page"] if parts else pinned["single"]
        sheets.append(_sheet(page["key"], version, width, height, layers_of(page["key"])))

    doc = {
        "kind": "tag_sheet",
        "imposition": {
            "preset": "custom",
            "page_width_mm": width,
            "page_height_mm": height,
            "bleed_mm": 0,
            "gap_mm": 0,
        },
        "sheets": sheets,
    }
    return {
        "doc": doc,
        "resolvedData": resolved,
        # The pinned versions' artwork plus what this sheet's stored page edits name (checked
        # against the company's library when the edit was saved).
        "assets": _asset_urls(
            db, asset_service.tag_sheet_asset_ids(doc), export=full, manifest=manifest
        ),
        "images": urls,
        "fonts": asset_service.font_assets(db),
        "requestDocNumber": doc_fields["quotation_no"],
        "version": sheet.sheet_no,
        "page_size": {"width_mm": width, "height_mm": height},
        "hidden": [p["key"] for p in chosen if p["hidden"]],
    }


# ----------------------------------------------------------------------------- sheets


def label_of(sheet: ProjectQuotationSpecSheet) -> str:
    return f"SS{sheet.sheet_no}"


def _issue_date(issue: ProjectQuotationIssue) -> str:
    return fmt_date(issue.issued_at) if issue.issued_at else ""


def _revision_name(issue: ProjectQuotationIssue) -> str:
    """The revision as the customer reads it: A / B for a proposal, R<n> when none is stored."""
    return issue.revision_label or f"R{issue.issue_no}"


def _issue_label(document, issue: ProjectQuotationIssue) -> str:
    from app.services.project_quotation_document_service import quotation_no

    return quotation_no(document.document_no, issue.issue_no, issue.revision_label)


def sources(db: Session, document: ProjectQuotationDocument) -> List[dict]:
    """The revisions a sheet can be made from: the draft first when it is ahead of the newest
    issue (or nothing was issued), then every issue newest first. No signature is required."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    issues = qdocs.list_issues(db, document)
    out: List[dict] = []
    if not issues:
        out.append({"value": DRAFT, "label": "Current draft", "hint": "not issued yet"})
    else:
        newest = issues[0]
        pairs = {
            row.quotation_id: row.version_id
            for row in db.query(ProjectQuotationIssueScope).filter(
                ProjectQuotationIssueScope.issue_id == newest.id
            )
        }
        scopes = qdocs.list_scopes(db, document)
        changed = bool(set(pairs) - {scope.id for scope in scopes}) or any(
            pairs.get(scope.id) != quotes.current_version(db, scope.id).id for scope in scopes
        )
        if changed:
            out.append(
                {
                    "value": DRAFT,
                    "label": "Current draft",
                    "hint": f"changed after {_revision_name(newest)} · not issued",
                }
            )
    for issue in issues:
        out.append(
            {
                "value": issue.id,
                "label": _issue_label(document, issue),
                "hint": f"issued {_issue_date(issue)}".strip(),
            }
        )
    return out


def source_text(db: Session, document, sheet: ProjectQuotationSpecSheet, issues: Optional[dict] = None) -> tuple:
    """``(label, hint)`` of the revision a sheet was made from."""
    if sheet.issue_id:
        issue = (issues or {}).get(sheet.issue_id)
        if issue is None and issues is None:
            issue = db.get(ProjectQuotationIssue, sheet.issue_id)
        if issue is not None:
            return _issue_label(document, issue), f"issued {_issue_date(issue)}".strip()
        return "Revision", ""
    taken = (
        fmt_datetime(sheet.items_taken_at) if sheet.items_taken_at else ""
    )
    if sheet.based_on_issue_no is None:
        return "Draft", f"lines taken {taken}".strip()
    if issues is not None:
        # The caller already holds this document's issues: no query per row.
        based_on = next((i for i in issues.values() if i.issue_no == sheet.based_on_issue_no), None)
    else:
        based_on = (
            db.query(ProjectQuotationIssue)
            .filter(
                ProjectQuotationIssue.document_id == document.id,
                ProjectQuotationIssue.issue_no == sheet.based_on_issue_no,
            )
            .first()
        )
    name = _revision_name(based_on) if based_on is not None else f"R{sheet.based_on_issue_no}"
    return f"Draft after {name}", f"lines taken {taken}".strip()


def _next_sheet_no(db: Session, document: ProjectQuotationDocument) -> int:
    return (
        db.query(func.max(ProjectQuotationSpecSheet.sheet_no))
        .filter(ProjectQuotationSpecSheet.document_id == document.id)
        .scalar()
        or 0
    ) + 1


def create_sheet(
    db: Session,
    document: ProjectQuotationDocument,
    *,
    source: str,
    cover_template_id: Optional[str],
    page_template_id: Optional[str],
    single_page_template_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> ProjectQuotationSpecSheet:
    """Save a new spec sheet: the items snapshot, the three templates and their published versions
    as of now. Page rows start clean (nothing is copied from another sheet)."""
    if source == DRAFT:
        issue = None
    else:
        issue = _issue_of(db, document, source) if source else None
        if issue is None:
            raise AppException(
                status_code=422,
                message="That revision is not on this quotation.",
                code="spec_sheet_issue_invalid",
            )
    templates = _resolve_templates(db, document.company_id, cover_template_id, page_template_id, single_page_template_id)
    items = snapshot_items(db, document, issue)
    if not items:
        raise AppException(status_code=422, message=NO_LINES_REASON, code="spec_sheet_no_lines")

    newest = _newest_issue(db, document)
    now = datetime.utcnow()
    sheet = ProjectQuotationSpecSheet(
        id=str(uuid.uuid4()),
        company_id=document.company_id,
        document_id=document.id,
        issue_id=issue.id if issue is not None else None,
        based_on_issue_no=(newest.issue_no if newest is not None else None) if issue is None else None,
        sheet_no=0,
        cover_template_id=templates["cover"].id,
        page_template_id=templates["page"].id,
        single_page_template_id=templates["single"].id if templates["single"] is not None else None,
        cover_version_id=templates["cover"].published_version_id,
        page_version_id=templates["page"].published_version_id,
        single_version_id=(
            templates["single"].published_version_id if templates["single"] is not None else None
        ),
        items=items,
        rows=[],
        page_edits={},
        items_taken_at=now,
        created_by=str(user_id) if user_id else None,
        created_at=now,
        updated_at=now,
        page_count=0,
    )
    _recount(db, sheet)
    # Two creates reading the same max would both take it; the unique (document, number) pair
    # refuses the second, which retries once with a fresh number instead of failing.
    for attempt in (1, 2):
        sheet.sheet_no = _next_sheet_no(db, document)
        try:
            with db.begin_nested():
                db.add(sheet)
                db.flush()
            return sheet
        except IntegrityError:
            if attempt == 2:
                raise AppException(
                    status_code=409,
                    message="Another spec sheet was just created. Try again.",
                    code="spec_sheet_number_taken",
                )
            if sheet in db:
                db.expunge(sheet)
    return sheet


def update_sheet(
    db: Session, sheet: ProjectQuotationSpecSheet, payload: dict, user_id: Optional[str] = None
) -> ProjectQuotationSpecSheet:
    """``rows`` MERGES: the payload's rows come first, in the payload's order, and every stored
    row whose item the payload does not mention is kept after them. The reader only sends the
    rows it shows, and it does not show an item printed as another page's accessory; replacing
    the list would wipe their Area, Comment and order. ``use_latest_templates`` moves the sheet to
    the templates' current published versions and keeps its page edits."""
    if "rows" in payload:
        rows = [_row(r) for r in payload.get("rows") or [] if isinstance(r, dict)]
        keys = [r["key"] for r in rows]
        if any(not k for k in keys) or len(set(keys)) != len(keys):
            raise _invalid_rows("Each item can appear once on the spec sheet.")
        stored = [_row(r) for r in sheet.rows or [] if isinstance(r, dict)]
        rows += [r for r in stored if r["key"] not in set(keys)]
        _check_rows(rows)
        sheet.rows = rows
    pick = ("cover_template_id", "page_template_id", "single_page_template_id")
    if any(k in payload for k in pick):
        # Pick templates again (e.g. after one was deleted): the same checks as create, the rows
        # and page edits stay.
        templates = _resolve_templates(
            db,
            sheet.company_id,
            payload.get("cover_template_id", sheet.cover_template_id),
            payload.get("page_template_id", sheet.page_template_id),
            payload.get("single_page_template_id", sheet.single_page_template_id),
        )
        sheet.cover_template_id = templates["cover"].id
        sheet.page_template_id = templates["page"].id
        sheet.single_page_template_id = templates["single"].id if templates["single"] is not None else None
        sheet.cover_version_id = templates["cover"].published_version_id
        sheet.page_version_id = templates["page"].published_version_id
        sheet.single_version_id = (
            templates["single"].published_version_id if templates["single"] is not None else None
        )
    if payload.get("use_latest_templates"):
        templates = _resolve_templates(
            db, sheet.company_id, sheet.cover_template_id, sheet.page_template_id, sheet.single_page_template_id
        )
        sheet.cover_version_id = templates["cover"].published_version_id
        sheet.page_version_id = templates["page"].published_version_id
        sheet.single_version_id = (
            templates["single"].published_version_id if templates["single"] is not None else None
        )
    _recount(db, sheet)
    _stamp(sheet, user_id)
    db.flush()
    return sheet


def _stamp(sheet: ProjectQuotationSpecSheet, user_id: Optional[str]) -> None:
    sheet.updated_at = datetime.utcnow()
    if user_id:
        sheet.updated_by = str(user_id)


def ensure_key(db: Session, sheet: ProjectQuotationSpecSheet, key: str) -> None:
    """404 unless ``key`` is the cover or a page of this sheet (hidden ones included)."""
    if key != COVER_KEY and key not in {p["key"] for p in pages(db, sheet)}:
        raise AppException(status_code=404, message="Page not found.", code="spec_sheet_page_missing")


def _check_assets(
    db: Session, sheet: ProjectQuotationSpecSheet, layers: list, pinned: Optional[dict] = None
) -> None:
    """A layer may name a library asset only if a pinned template version already does, or it is
    an asset of the document's own company."""
    from app.models.dealer_kit import Asset
    from app.services.dealer_kit import asset_service

    named = asset_service.tag_sheet_asset_ids({"layers": layers})
    if not named:
        return
    allowed = _version_asset_ids(pinned if pinned is not None else _pinned(db, sheet))
    unknown = named - allowed
    if unknown:
        owned = {
            str(row.id)
            for row in db.query(Asset.id).filter(
                Asset.id.in_([a for a in unknown if _is_uuid(a)]), Asset.company_id == sheet.company_id
            )
        } if sheet.company_id else set()
        if unknown - owned:
            raise _invalid_layer("A layer uses artwork that is not in your library.")


def _invalid_layer(message: str) -> AppException:
    return AppException(status_code=422, message=message, code="spec_sheet_page_edit_invalid")


def _check_value(value: Any, depth: int) -> None:
    if depth > LAYER_DEPTH_MAX:
        raise _invalid_layer("A layer is nested too deeply.")
    if isinstance(value, str):
        if len(value) > LAYER_STRING_MAX:
            raise _invalid_layer("A layer holds text that is too long.")
    elif isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str) or len(k) > 200:
                raise _invalid_layer("A layer has an invalid property name.")
            _check_value(v, depth + 1)
    elif isinstance(value, float):
        # Postgres rejects NaN / Infinity in jsonb: refused here, not a 500 on the write.
        if not math.isfinite(value):
            raise _invalid_layer("A layer holds a number that is not finite.")
    elif isinstance(value, list):
        for v in value:
            _check_value(v, depth + 1)


def _check_layer(layer: Any) -> None:
    """A bound check, not a schema: a dict with a known designer `type`, bounded depth and text."""
    if not isinstance(layer, dict) or layer.get("type") not in LAYER_TYPES:
        raise _invalid_layer("A layer is not one the designer produces.")
    props = layer.get("props")
    if props is not None:
        if not isinstance(props, dict):
            raise _invalid_layer("A layer's properties are malformed.")
        source = props.get("source")
        if source is not None and not isinstance(source, (dict, str)):
            raise _invalid_layer("A layer's artwork source is malformed.")
        # `_layer_asset_ids` reads these two places; each must be a plain id.
        holders = [props] + ([source] if isinstance(source, dict) else [])
        for holder in holders:
            if holder.get("assetId") is not None and not isinstance(holder["assetId"], str):
                raise _invalid_layer("A layer's artwork id is malformed.")
    _check_value(layer, 1)


def _too_large() -> AppException:
    return AppException(
        status_code=422,
        message="That page edit is too large to keep.",
        code="spec_sheet_page_edit_too_large",
    )


def _validate_page_edit(
    db: Session,
    sheet: ProjectQuotationSpecSheet,
    layers: Any,
    *,
    pinned: Optional[dict] = None,
) -> int:
    """Check one page's layers (shape, bounds, artwork) and return their serialized size. Writes
    nothing; the page key is the caller's to have checked."""
    if not isinstance(layers, list) or len(layers) > LAYERS_MAX:
        raise AppException(
            status_code=422,
            message=f"A page holds at most {LAYERS_MAX} layers.",
            code="spec_sheet_layers_invalid",
        )
    for layer in layers:
        _check_layer(layer)
    _check_assets(db, sheet, layers, pinned)
    size = len(json.dumps(layers, default=str))
    if size > PAGE_EDIT_MAX:
        raise _too_large()
    return size


def _edit_size(edit: Any) -> int:
    return len(json.dumps(edit.get("layers"), default=str)) if isinstance(edit, dict) else 0


def save_page_edit(
    db: Session,
    sheet: ProjectQuotationSpecSheet,
    key: str,
    layers: Any,
    user_id: Optional[str] = None,
) -> ProjectQuotationSpecSheet:
    """Store ``layers`` as this page's override. The template and its versions are untouched."""
    ensure_key(db, sheet, key)
    size = _validate_page_edit(db, sheet, layers)
    others = sum(_edit_size(v) for k, v in (sheet.page_edits or {}).items() if k != key)
    if others + size > PAGE_EDITS_TOTAL_MAX:
        raise _too_large()
    sheet.page_edits = {**(sheet.page_edits or {}), key: {"layers": layers}}
    _stamp(sheet, user_id)
    db.flush()
    return sheet


#: Keys "Apply to every page" may change on a layer: where it sits, how big, turned, stacked and
#: shown, plus its STYLE props. Never what it says or which data it binds (text, source, fieldKey,
#: slot_binding, text_override ...): those stay each page's own.
APPLY_TOP_KEYS = frozenset({"x_mm", "y_mm", "width_mm", "height_mm", "rotation_deg", "z_index", "visible"})
APPLY_PROPS_KEYS = frozenset(
    {
        "fontFamily",
        "fontSize",
        "fontWeight",
        "color",
        "align",
        "lineHeight",
        "letterSpacing",
        "italic",
        "underline",
        "strikethrough",
        "fit",
        "fill",
        "stroke",
        "strokeWidth",
        "cornerRadius",
        "maskShape",
    }
)


def _invalid_apply(message: str) -> AppException:
    return AppException(status_code=422, message=message, code="spec_sheet_apply_invalid")


def _check_apply(changes: Any) -> dict:
    """The allowed, plain-valued subset of a layer change; anything else is refused."""
    if not isinstance(changes, dict) or not changes:
        raise _invalid_apply("Say what to change.")
    clean: dict = {}
    for key, value in changes.items():
        if key == "props":
            if not isinstance(value, dict) or not value:
                raise _invalid_apply("A layer's style must be a set of values.")
            for pkey, pvalue in value.items():
                if pkey not in APPLY_PROPS_KEYS:
                    raise _invalid_apply(f"{pkey} cannot be applied to every page.")
                if (
                    isinstance(pvalue, (dict, list))
                    or (isinstance(pvalue, str) and len(pvalue) > 200)
                    or (isinstance(pvalue, float) and not math.isfinite(pvalue))
                ):
                    raise _invalid_apply(f"{pkey} must be a plain value.")
            clean["props"] = dict(value)
        elif key in APPLY_TOP_KEYS:
            ok = isinstance(value, bool) if key == "visible" else (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and (not isinstance(value, float) or math.isfinite(value))
            )
            if not ok:
                raise _invalid_apply(f"{key} has an invalid value.")
            clean[key] = value
        else:
            raise _invalid_apply(f"{key} cannot be applied to every page.")
    return clean


def apply_to_all_pages(
    db: Session,
    sheet: ProjectQuotationSpecSheet,
    layer_id: str,
    changes: Any,
    user_id: Optional[str] = None,
    origin_page_key: Optional[str] = None,
) -> ProjectQuotationSpecSheet:
    """Merge ``changes`` into the layer ``layer_id`` on every printed page whose effective layers
    (its edit, else the pinned version) hold it. Other pages are untouched. Each page's edit goes
    through the same checks and size bounds as a single page edit."""
    clean = _check_apply(changes)
    pinned = _pinned(db, sheet)
    # Pages and the pinned versions are read ONCE; every merged page is validated in memory and the
    # sheet is written once, not once per page (each write rewrites the whole page_edits column).
    # An apply from the cover reaches the cover only; from an item page (or with no origin), the
    # item pages only: a cover that happens to share a layer id is a different design.
    if origin_page_key is not None:
        ensure_key(db, sheet, origin_page_key)
    if origin_page_key == COVER_KEY:
        entries = [(COVER_KEY, "cover")]
    else:
        entries = [(p["key"], p["template"]) for p in pages(db, sheet) if not p["hidden"]]
    edits = dict(sheet.page_edits or {})
    touched = 0
    for key, template in entries:
        layers = _page_layers(sheet, pinned, key, template)
        if not any(isinstance(layer, dict) and layer.get("id") == layer_id for layer in layers):
            continue
        merged = []
        for layer in layers:
            if isinstance(layer, dict) and layer.get("id") == layer_id:
                layer = {**layer, **{k: v for k, v in clean.items() if k != "props"}}
                if "props" in clean:
                    layer["props"] = {**(layer.get("props") or {}), **clean["props"]}
            merged.append(layer)
        _validate_page_edit(db, sheet, merged, pinned=pinned)
        edits[key] = {"layers": merged}
        touched += 1
    if not touched:
        raise AppException(status_code=404, message="No page has that layer.", code="spec_sheet_layer_missing")
    if sum(_edit_size(v) for v in edits.values()) > PAGE_EDITS_TOTAL_MAX:
        raise _too_large()
    sheet.page_edits = edits
    _stamp(sheet, user_id)
    db.flush()
    return sheet


def reset_page_edit(
    db: Session, sheet: ProjectQuotationSpecSheet, key: str, user_id: Optional[str] = None
) -> ProjectQuotationSpecSheet:
    """Drop the page's override so it draws the template version again."""
    edits = dict(sheet.page_edits or {})
    if edits.pop(key, None) is not None:
        sheet.page_edits = edits
        _stamp(sheet, user_id)
        db.flush()
    return sheet


def _with_medium_urls(row: dict, medium: Dict[str, str]) -> dict:
    """The page's resolved row with its pictures' urls swapped for the medium renditions: the
    designer draws the bound row's own image dicts, not the payload's `images` map."""

    def swap(image):
        if isinstance(image, dict) and image.get("attachment_id") in medium:
            return {**image, "url": medium[image["attachment_id"]]}
        return image

    out = dict(row)
    out["images"] = [swap(i) for i in row.get("images") or []]
    out["drawing"] = swap(row.get("drawing"))
    out["parts"] = [
        {**part, "images": [swap(i) for i in part.get("images") or []], "drawing": swap(part.get("drawing"))}
        for part in row.get("parts") or []
    ]
    out["own_parts"] = out["parts"]
    return out


def design(db: Session, sheet: ProjectQuotationSpecSheet, key: str) -> dict:
    """What the page designer opens: the page's layers (its override, else the frozen template
    version's), bound to that page's data; thumbnails, with the open page at medium size."""
    ensure_key(db, sheet, key)
    payload = build_print_payload(db, sheet, keys=[key])
    tag = payload["doc"]["sheets"][0]["tags"][0]
    template = db.get(TagTemplate, tag["template_id"]) if tag.get("template_id") else None
    # The designer shows ONE page large: medium renditions over the thumbnails.
    sharp = page_images(db, sheet, key)
    bound = _with_medium_urls(payload["resolvedData"][key], sharp["images"])
    return {
        "layers": tag["layers"],
        "bound": bound,
        "images": {**payload["images"], **sharp["images"]},
        "assets": {**payload["assets"], **sharp["assets"]},
        "fonts": payload["fonts"],
        "width_mm": payload["page_size"]["width_mm"],
        "height_mm": payload["page_size"]["height_mm"],
        "template_name": template.name if template is not None else "",
        "template_id": template.id if template is not None else None,
        "edited": key in (sheet.page_edits or {}),
    }


# ----------------------------------------------------------------------------- views


def _public(page: dict) -> dict:
    """A page without its print-only (underscore) keys, accessories included."""
    out = {k: v for k, v in page.items() if not k.startswith("_")}
    out["accessories"] = [
        {k: v for k, v in acc.items() if not k.startswith("_")} for acc in page["accessories"]
    ]
    return out


def published_templates(db: Session) -> dict:
    rows = (
        db.query(TagTemplate)
        .options(joinedload(TagTemplate.published_version))
        .filter(
            TagTemplate.family.in_([COVER_FAMILY, PAGE_FAMILY]),
            TagTemplate.published_version_id.isnot(None),
            TagTemplate.archived_at.is_(None),
        )
        .order_by(TagTemplate.name)
        .all()
    )
    out: dict = {"cover": [], "page": []}
    for row in rows:
        doc = (row.published_version.doc if row.published_version else None) or {}
        out["cover" if row.family == COVER_FAMILY else "page"].append(
            {
                "id": row.id,
                "name": row.name,
                "width_mm": doc.get("width_mm"),
                "height_mm": doc.get("height_mm"),
            }
        )
    return out


def _user_names(db: Session, ids: Sequence[Optional[str]]) -> Dict[str, str]:
    from app.models.user import User

    wanted = list({str(i) for i in ids if i})
    if not wanted:
        return {}
    return {str(u.id): u.name or "" for u in db.query(User).filter(User.id.in_(wanted)).all()}


def sheets_of(db: Session, document: ProjectQuotationDocument) -> List[ProjectQuotationSpecSheet]:
    """Newest first."""
    return (
        db.query(ProjectQuotationSpecSheet)
        .filter(ProjectQuotationSpecSheet.document_id == document.id)
        .order_by(ProjectQuotationSpecSheet.sheet_no.desc())
        .all()
    )


def list_view(db: Session, document: ProjectQuotationDocument, user_id: str) -> dict:
    rows = sheets_of(db, document)
    issues = {i.id: i for i in db.query(ProjectQuotationIssue).filter(
        ProjectQuotationIssue.document_id == document.id
    )}
    template_ids = {
        t
        for r in rows
        for t in (r.cover_template_id, r.page_template_id, r.single_page_template_id)
        if t
    }
    names = (
        {t.id: t.name for t in db.query(TagTemplate).filter(TagTemplate.id.in_(template_ids)).all()}
        if template_ids
        else {}
    )
    users = _user_names(db, [r.created_by for r in rows])
    items = []
    for r in rows:
        source_label, source_hint = source_text(db, document, r, issues)
        items.append(
            {
                "id": r.id,
                "sheet_no": r.sheet_no,
                "label": label_of(r),
                "source_label": source_label,
                "source_hint": source_hint,
                "is_draft": r.issue_id is None,
                "cover_name": names.get(r.cover_template_id, ""),
                "page_name": names.get(r.page_template_id, ""),
                "single_name": names.get(r.single_page_template_id) if r.single_page_template_id else None,
                "page_count": r.page_count,
                "edited_count": len(r.page_edits or {}),
                "created_by_name": users.get(str(r.created_by), ""),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "last_exported_at": r.last_exported_at.isoformat() if r.last_exported_at else None,
                "newer_templates": newer_templates(db, r),
            }
        )
    options = sources(db, document)
    templates = published_templates(db)
    published = {t["id"] for group in templates.values() for t in group}
    mine = (
        db.query(ProjectQuotationSpecSheet)
        .filter(ProjectQuotationSpecSheet.created_by == str(user_id))
        .order_by(ProjectQuotationSpecSheet.created_at.desc(), ProjectQuotationSpecSheet.sheet_no.desc())
        .first()
    )

    def default(field: str) -> Optional[str]:
        value = getattr(mine, field, None) if mine is not None else None
        return value if value in published else None

    reason = None
    if not rows and not has_lines(db, document) and not issues:
        reason = NO_LINES_REASON
    return {
        "items": items,
        "sources": options,
        "templates": templates,
        "defaults": {
            "source": options[0]["value"] if options else None,
            "cover_template_id": default("cover_template_id"),
            "page_template_id": default("page_template_id"),
            "single_page_template_id": default("single_page_template_id"),
        },
        "create_disabled_reason": reason,
    }


def detail_view(
    db: Session, document: ProjectQuotationDocument, sheet: ProjectQuotationSpecSheet, *, can_edit: bool
) -> dict:
    # A sheet whose template was deleted still opens: it says which one, and the reader asks for
    # new templates instead of drawing.
    missing = templates_missing(db, sheet)
    blocked = any(m in ("cover", "page") for m in missing)
    if blocked:
        cover_v, page_v, single_v = _pinned_parts(db, sheet)
        pinned = {"cover": cover_v, "page": page_v, "single": single_v}
        known = next((v for v in (cover_v, page_v, single_v) if v is not None), None)
        try:
            width, height = _doc_size("", known.doc) if known is not None else DEFAULT_PAGE_MM
        except AppException:
            width, height = DEFAULT_PAGE_MM
    else:
        pinned = _pinned(db, sheet)
        width, height = pinned["size"]
    source_label, source_hint = source_text(db, document, sheet)
    edits = sheet.page_edits or {}
    page_rows = pages(db, sheet)
    visible_no = {p["key"]: n for n, p in enumerate([p for p in page_rows if not p["hidden"]], start=2)}
    out_pages = [
        {
            "key": COVER_KEY,
            "number": 1,
            "code": "",
            "name": "Cover",
            "brand": "",
            "area": "",
            "area_default": "",
            "comment": "",
            "marker": "",
            "hidden": False,
            "picked": [],
            "accessories": [],
            "edited": COVER_KEY in edits,
            "template": "cover",
        }
    ]
    for page in page_rows:
        public = _public(page)
        public["number"] = visible_no.get(page["key"])
        out_pages.append(public)
    for page in out_pages:
        page.pop("line_id", None)
        page.pop("product_id", None)
        page.pop("image_attachment_id", None)
        page.pop("drawing_attachment_id", None)

    def template_ref(template_id, version: Optional[TagTemplateVersion]):
        template = db.get(TagTemplate, template_id) if template_id else None
        if template is None or version is None:
            return None
        return {"id": template.id, "name": template.name, "version_no": version.version_no}

    siblings = [
        row.id
        for row in db.query(ProjectQuotationSpecSheet.id)
        .filter(ProjectQuotationSpecSheet.document_id == document.id)
        .order_by(ProjectQuotationSpecSheet.sheet_no.desc())
        .all()
    ]
    at = siblings.index(sheet.id) if sheet.id in siblings else -1
    return {
        "id": sheet.id,
        "sheet_no": sheet.sheet_no,
        "label": label_of(sheet),
        "source_label": source_label,
        "source_hint": source_hint,
        "is_draft": sheet.issue_id is None,
        "templates": {
            "cover": template_ref(sheet.cover_template_id, pinned["cover"]),
            "page": template_ref(sheet.page_template_id, pinned["page"]),
            "single": template_ref(sheet.single_page_template_id, pinned["single"])
            if sheet.single_page_template_id
            else None,
        },
        "templates_missing": missing,
        "newer_templates": newer_templates(db, sheet),
        "page_size": {"width_mm": width, "height_mm": height},
        "pages": out_pages,
        "prev_id": siblings[at - 1] if at > 0 else None,
        "next_id": siblings[at + 1] if 0 <= at < len(siblings) - 1 else None,
        "can_edit": can_edit,
    }


# ----------------------------------------------------------------------------- export


def request_export(db: Session, sheet: ProjectQuotationSpecSheet, user_id: str):
    """Check it can print, then queue the render; the file lands in My Downloads."""
    from app.services.download_service import DownloadService
    from app.services.queue_service import enqueue_job
    from app.tasks.dealer_kit_export_tasks import generate_spec_sheet_pdf

    document = _document_of(db, sheet)
    # Refuse NOW what would fail in the worker: a gone template, or templates of two sizes.
    _pinned(db, sheet)
    number = _doc_fields(db, document, sheet)["quotation_no"]
    filename = f"spec-sheet-{number}-{label_of(sheet)}.pdf"

    downloads = DownloadService(db)
    download = downloads.create(
        user_id=str(user_id),
        kind=KIND,
        source_entity_type=SOURCE_TYPE,
        source_entity_id=str(sheet.id),
        filename=filename,
    )
    sheet.last_exported_at = datetime.utcnow()
    db.flush()
    try:
        enqueue_job(
            generate_spec_sheet_pdf,
            str(download.id),
            queue_name="catalogue_render",
            job_timeout=900,
        )
    except Exception as exc:  # noqa: BLE001 - a queue outage is a failed row, not a 500
        downloads.mark_failed(str(download.id), f"Could not queue the export: {exc}")
    return downloads.get(str(download.id)) or download


def source_of_download(db: Session, download) -> tuple:
    """``(document, sheet)`` behind a spec sheet download, or 404 (a legacy ``quotation_issue``
    source and a deleted sheet both answer 404)."""
    sheet = (
        db.get(ProjectQuotationSpecSheet, str(download.source_entity_id))
        if download.source_entity_type == SOURCE_TYPE and _is_uuid(download.source_entity_id)
        else None
    )
    document = db.get(ProjectQuotationDocument, sheet.document_id) if sheet is not None else None
    if sheet is None or document is None:
        raise AppException(status_code=404, message="Not found")
    return document, sheet


def print_payload_for_download(db: Session, download) -> dict:
    """The public print route's answer for a spec sheet download, pinned to its company."""
    from app.models.base import company_scope

    with company_scope(db, None):
        document, sheet = source_of_download(db, download)
    # Fail closed: a document with no company would otherwise be read with no company filter.
    if not document.company_id:
        raise AppException(status_code=404, message="Not found")
    manifest = _load_manifest(str(download.id))
    with company_scope(db, frozenset({document.company_id})):
        return build_print_payload(db, sheet, full=True, manifest=manifest)


def page_size_for_download(db: Session, download) -> tuple:
    """The PDF page size (mm) a spec sheet download prints at, without building the payload."""
    from app.models.base import company_scope

    with company_scope(db, None):
        document, sheet = source_of_download(db, download)
    if not document.company_id:
        raise AppException(status_code=404, message="Not found")
    with company_scope(db, frozenset({document.company_id})):
        return _pinned(db, sheet)["size"]
