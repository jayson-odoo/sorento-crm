"""Project spec sheet (PS-SPEC-SHEET): a cover page plus one page per quoted item.

Card: ``documentation/plans/project-sales/CARD-ps-spec-sheet-02nov.md``.

Nothing here draws. The pages are TAG TEMPLATES (families ``spec_cover`` / ``spec_page``) designed
in the Dealer Kit tag template editor, and the PDF is the price tag print pipeline as it stands:
this module builds a ``TagSheetDoc`` with one full-page "tag" per sheet plus the resolved rows the
template's slots and merge fields read, and ``TagSheetRenderer`` draws it in Chromium. So a page
looks exactly like the template the designer published, through the one renderer that already
prints price tags.

What it prints is an ISSUED revision, the same doctrine as the quotation PDF: what the customer
received. The per-item settings (order, Area, Comment, Marker, Hide, hand-picked accessories) are
keyed by product id or ``set:<set id>``, not by line id, so they survive the next revision.

No price is ever placed in a row: a spec sheet is a catalogue of what was quoted, not of the money.
"""
from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.dealer_kit import TagTemplate
from app.models.product import Brand, Product
from app.models.projects import (
    Project,
    ProjectQuotationDocument,
    ProjectQuotationIssue,
    ProjectQuotationIssueScope,
    ProjectQuotationLine,
)
from app.services.error_handler import AppException

#: ``user_downloads.kind`` of a spec sheet PDF. The print payload route answers it.
KIND = "quotation_spec_sheet_pdf"

COVER_FAMILY = "spec_cover"
PAGE_FAMILY = "spec_page"

COVER_KEY = "cover"

#: Free-text limits. Area holds a unit-type list ("TOILET (ALL TYPE, PODIUM FACILITIES & GUARD
#: HOUSE)"), so it is generous; a marker is the sample's ``*`` / ``**`` / ``***``.
AREA_MAX = 200
COMMENT_MAX = 500
MARKER_MAX = 10

#: A template page outside this range (or not a finite number) is refused before Chromium sees
#: it: zero or negative sizes fail obscurely in the worker, and a huge one ties up the shared
#: render queue until the subprocess times out.
PAGE_MM_MIN = 10.0
PAGE_MM_MAX = 1500.0

_TEMPLATE_FIELDS = {
    "cover_template_id": COVER_FAMILY,
    "page_template_id": PAGE_FAMILY,
    "single_page_template_id": PAGE_FAMILY,
}


# ----------------------------------------------------------------------------- settings


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


def settings_of(document: ProjectQuotationDocument) -> dict:
    """The document's spec sheet settings, every key present."""
    raw = document.spec_sheet or {}
    return {
        "cover_template_id": raw.get("cover_template_id"),
        "page_template_id": raw.get("page_template_id"),
        "single_page_template_id": raw.get("single_page_template_id"),
        "issue_id": raw.get("issue_id"),
        "rows": [_row(r) for r in raw.get("rows") or [] if isinstance(r, dict)],
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


def _published_template(db: Session, template_id: str, family: str) -> TagTemplate:
    template = db.query(TagTemplate).filter(TagTemplate.id == str(template_id)).first()
    if (
        template is None
        or template.family != family
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


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def save_settings(db: Session, document: ProjectQuotationDocument, payload: dict) -> dict:
    """Write the settings the payload names; a key it leaves out keeps its saved value.

    ``rows`` MERGES: the payload's rows come first, in the payload's order, and every stored row
    whose item the payload does not mention is kept after them. The tab only sends the rows it
    shows, and it does not show an item printed as another page's accessory or an item of a
    different revision; replacing the list would wipe their Area, Comment and order.
    """
    current = settings_of(document)
    for field, family in _TEMPLATE_FIELDS.items():
        if field not in payload:
            continue
        value = payload.get(field) or None
        if value is not None:
            if not _is_uuid(value):
                raise AppException(
                    status_code=422,
                    message="Pick a published template.",
                    code="spec_sheet_template_invalid",
                )
            _published_template(db, value, family)
        current[field] = value
    if "issue_id" in payload:
        issue_id = payload.get("issue_id") or None
        if issue_id is not None and (
            not _is_uuid(issue_id) or _issue_of(db, document, issue_id) is None
        ):
            raise AppException(
                status_code=422,
                message="That revision is not on this quotation.",
                code="spec_sheet_issue_invalid",
            )
        current["issue_id"] = issue_id
    if "rows" in payload:
        rows = [_row(r) for r in payload.get("rows") or [] if isinstance(r, dict)]
        keys = [r["key"] for r in rows]
        if any(not k for k in keys) or len(set(keys)) != len(keys):
            raise _invalid_rows("Each item can appear once on the spec sheet.")
        rows += [r for r in current["rows"] if r["key"] not in set(keys)]
        _check_rows(rows)
        current["rows"] = rows
    document.spec_sheet = current
    db.flush()
    return current


# ----------------------------------------------------------------------------- items


def _issue_of(db: Session, document, issue_id: str) -> Optional[ProjectQuotationIssue]:
    return (
        db.query(ProjectQuotationIssue)
        .filter(
            ProjectQuotationIssue.id == str(issue_id),
            ProjectQuotationIssue.document_id == document.id,
        )
        .first()
    )


def issue_for(
    db: Session, document: ProjectQuotationDocument, issue_id: Optional[str] = None
) -> Optional[ProjectQuotationIssue]:
    """The revision to print: the one asked for, else the saved pick, else the latest."""
    wanted = issue_id or settings_of(document)["issue_id"]
    if wanted:
        found = _issue_of(db, document, wanted)
        if found is not None:
            return found
    return (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.document_id == document.id)
        .order_by(ProjectQuotationIssue.issue_no.desc())
        .first()
    )


def _issue_lines(db: Session, issue: ProjectQuotationIssue) -> List[ProjectQuotationLine]:
    """Every line the issue froze, scope order then line order."""
    scopes = (
        db.query(ProjectQuotationIssueScope)
        .filter(ProjectQuotationIssueScope.issue_id == issue.id)
        .order_by(ProjectQuotationIssueScope.sort_order, ProjectQuotationIssueScope.id)
        .all()
    )
    lines: List[ProjectQuotationLine] = []
    for scope in scopes:
        lines.extend(
            db.query(ProjectQuotationLine)
            .filter(ProjectQuotationLine.version_id == scope.version_id)
            .order_by(ProjectQuotationLine.sort_order, ProjectQuotationLine.created_at)
            .all()
        )
    return lines


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


def _items(db: Session, issue: ProjectQuotationIssue) -> Dict[str, dict]:
    """Ordered ``{key: item}``, one per product or set, at its first position."""
    items: Dict[str, dict] = {}
    for line in _issue_lines(db, issue):
        key = item_key(line)
        if key is None or key in items:
            continue
        driver = _driver_part(line) if line.product_set_id else None
        items[key] = {
            "key": key,
            "line": line,
            "product_id": (driver or {}).get("product_id") or line.product_id,
            "code": (driver or {}).get("product_code") or line.product_code_snapshot or "",
            "description": (driver or {}).get("description") or line.description_snapshot or "",
            "set_parts": _set_parts(line) if line.product_set_id else [],
        }
    return items


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


def _sign(db: Session, attachment_ids: Sequence[Optional[str]]) -> Dict[str, str]:
    """Full-size signed URLs, omitting any that cannot be signed (a print needs the original)."""
    from app.services import product_image_service as images

    return {k: v for k, v in images.preview_urls(db, attachment_ids, full=True).items() if v}


def _product_fields(db: Session, product: Optional[Product], spec_cache: dict) -> dict:
    """Dimensions, spec lines and specs off the product master; blank for a gone product."""
    from app.services.dealer_kit import tag_data_service as tags

    if product is None:
        return {"dimensions": "", "spec_lines": [], "specs": [], "barcode": None}
    if product.id not in spec_cache:
        spec_row = tags._spec_row(db, product)
        spec_cache[product.id] = {
            "dimensions": tags.dimensions_text(product, spec_row) or "",
            "spec_lines": tags.spec_lines(db, product, spec_row),
            "specs": tags.product_specs(db, product, spec_row),
            "barcode": product.barcode or None,
        }
    return spec_cache[product.id]


# ----------------------------------------------------------------------------- pages


def _row_settings(document) -> Dict[str, dict]:
    return {r["key"]: r for r in settings_of(document)["rows"]}


def pages(
    db: Session, document: ProjectQuotationDocument, issue: Optional[ProjectQuotationIssue]
) -> List[dict]:
    """The pages after the cover, in print order, hidden ones included (flagged)."""
    if issue is None:
        return []
    items = _items(db, issue)
    rows = settings_of(document)["rows"]
    by_key = {r["key"]: r for r in rows}

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

    def brand_of(product_id, fallback=None):
        product = products.get(str(product_id)) if product_id else None
        if fallback:
            return fallback
        return brands.get(str(product.brand_id), "") if product and product.brand_id else ""

    out: List[dict] = []
    for key in ordered:
        item = items[key]
        line = item["line"]
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
                    "brand": brand_of(other["product_id"], other["line"].brand_snapshot),
                    "image_attachment_id": other["line"].image_attachment_id,
                    "drawing_attachment_id": other["line"].drawing_attachment_id,
                }
            )
        out.append(
            {
                "key": key,
                "line_id": line.id,
                "product_id": item["product_id"],
                "code": item["code"],
                "name": name_of(item["product_id"], item["description"]),
                "brand": brand_of(item["product_id"], line.brand_snapshot),
                "image_attachment_id": line.image_attachment_id,
                "drawing_attachment_id": line.drawing_attachment_id,
                "accessories": accessories,
                "picked": list(setting["accessories"]),
                "area": setting["area"],
                "comment": setting["comment"],
                "marker": setting["marker"],
                "hidden": setting["hidden"],
            }
        )
    return out


# ----------------------------------------------------------------------------- print


def _doc_fields(db: Session, document, issue) -> dict:
    from app.models.user import User
    from app.services.project_quotation_document_service import quotation_no

    project = db.query(Project).filter(Project.id == document.project_id).first()
    owner = None
    if project is not None and project.owner_user_id:
        owner = db.query(User).filter(User.id == project.owner_user_id).first()
    number = quotation_no(document.document_no, issue.issue_no)
    your_ref = (document.your_ref or "").strip()
    # The quotation's own date, as its PDF and cover print it, else the day it was issued.
    issued = document.doc_date or issue.issued_at
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
        "date": issued.strftime("%d %b %Y").upper() if issued else "",
    }


def _template_size(template: TagTemplate) -> tuple:
    doc = template.published_version.doc or {}
    try:
        size = (float(doc.get("width_mm") or 0), float(doc.get("height_mm") or 0))
    except (TypeError, ValueError):
        size = (0.0, 0.0)
    if not all(math.isfinite(v) and PAGE_MM_MIN <= v <= PAGE_MM_MAX for v in size):
        raise AppException(
            status_code=422,
            message=(
                f"The template {template.name} has a page size the PDF cannot print "
                f"({PAGE_MM_MIN:g} to {PAGE_MM_MAX:g} mm)."
            ),
            code="spec_sheet_size_invalid",
        )
    return size


def _templates_for(db: Session, settings: dict) -> dict:
    if not settings["cover_template_id"] or not settings["page_template_id"]:
        raise AppException(
            status_code=422,
            message="Pick a cover template and a page template first.",
            code="spec_sheet_templates_missing",
        )
    cover = _published_template(db, settings["cover_template_id"], COVER_FAMILY)
    page = _published_template(db, settings["page_template_id"], PAGE_FAMILY)
    single = (
        _published_template(db, settings["single_page_template_id"], PAGE_FAMILY)
        if settings["single_page_template_id"]
        else page
    )
    size = _template_size(cover)
    if any(_template_size(t) != size for t in (page, single)):
        raise AppException(
            status_code=422,
            message="Page templates must be the same size as the cover.",
            code="spec_sheet_size_mismatch",
        )
    return {"cover": cover, "page": page, "single": single, "size": size}


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


def build_print_payload(
    db: Session, document: ProjectQuotationDocument, issue: ProjectQuotationIssue
) -> dict:
    """Everything ``TagSheetRenderer`` draws: cover, then one sheet per visible page."""
    from app.services.dealer_kit import asset_service

    settings = settings_of(document)
    templates = _templates_for(db, settings)
    width, height = templates["size"]
    doc_fields = _doc_fields(db, document, issue)
    visible = [p for p in pages(db, document, issue) if not p["hidden"]]

    # Media: the frozen line photo / drawing first, the product's own files for accessories.
    part_ids = [a["product_id"] for p in visible for a in p["accessories"] if a.get("product_id")]
    main_ids = [p["product_id"] for p in visible if p["product_id"]]
    files = _files(db, part_ids + main_ids)
    products = _products(db, part_ids + main_ids)
    wanted: List[Optional[str]] = []
    for page in visible:
        own = files.get(str(page["product_id"]), {}) if page["product_id"] else {}
        page["_photo"] = page["image_attachment_id"] or own.get("photo")
        page["_drawing"] = page["drawing_attachment_id"] or own.get("drawing")
        wanted += [page["_photo"], page["_drawing"]]
        for acc in page["accessories"]:
            mine = files.get(str(acc.get("product_id")), {}) if acc.get("product_id") else {}
            acc["_photo"] = acc.get("image_attachment_id") or mine.get("photo")
            acc["_drawing"] = acc.get("drawing_attachment_id") or mine.get("drawing")
            wanted += [acc["_photo"], acc["_drawing"]]
    urls = _sign(db, wanted)

    spec_cache: dict = {}
    resolved: Dict[str, dict] = {COVER_KEY: _blank_row(COVER_KEY, "Cover", doc_fields)}
    sheets: List[dict] = [_sheet(COVER_KEY, templates["cover"], width, height)]
    for number, page in enumerate(visible, start=2):
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
                    "list_price": None,
                    "sell_price": None,
                }
            )
        photo = _image(page["_photo"], urls)
        row = _blank_row(page["key"], str(number), doc_fields)
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
            }
        )
        resolved[page["key"]] = row
        template = templates["page"] if parts else templates["single"]
        sheets.append(_sheet(page["key"], template, width, height))

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
        "assets": asset_service.urls_for(db, asset_service.tag_sheet_asset_ids(doc)),
        "images": urls,
        "fonts": asset_service.font_assets(db),
        "requestDocNumber": doc_fields["quotation_no"],
        "version": issue.issue_no,
        "page_size": {"width_mm": width, "height_mm": height},
    }


def _sheet(key: str, template: TagTemplate, width: float, height: float) -> dict:
    version = template.published_version
    return {
        "id": f"sheet-{key}",
        "tags": [
            {
                "id": f"tag-{key}",
                "template_id": template.id,
                "request_tag_id": key,
                "x_mm": 0,
                "y_mm": 0,
                "width_mm": width,
                "height_mm": height,
                "layers": (version.doc or {}).get("layers") or [],
            }
        ],
    }


# ----------------------------------------------------------------------------- export


def export_filename(document, issue) -> str:
    from app.services.project_quotation_document_service import quotation_no

    return f"spec-sheet-{quotation_no(document.document_no, issue.issue_no)}.pdf".replace("/", "-")


def request_export(
    db: Session,
    document: ProjectQuotationDocument,
    issue: ProjectQuotationIssue,
    *,
    user_id: str,
):
    """Check it can print, then queue the render; the file lands in My Downloads."""
    from app.services.download_service import DownloadService
    from app.services.queue_service import enqueue_job
    from app.tasks.dealer_kit_export_tasks import generate_spec_sheet_pdf

    # Refuse NOW what would fail in the worker: no templates, or templates of two sizes.
    _templates_for(db, settings_of(document))

    downloads = DownloadService(db)
    download = downloads.create(
        user_id=str(user_id),
        kind=KIND,
        source_entity_type="quotation_issue",
        source_entity_id=str(issue.id),
        filename=export_filename(document, issue),
    )
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
    """``(document, issue)`` behind a spec sheet download, or 404."""
    issue = (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.id == str(download.source_entity_id))
        .first()
    )
    document = (
        db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.id == issue.document_id)
        .first()
        if issue is not None
        else None
    )
    if issue is None or document is None:
        raise AppException(status_code=404, message="Not found")
    return document, issue


def print_payload_for_download(db: Session, download) -> dict:
    """The public print route's answer for a spec sheet download, pinned to its company."""
    from app.models.base import company_scope

    with company_scope(db, None):
        document, issue = source_of_download(db, download)
    # Fail closed: a document with no company would otherwise be read with no company filter.
    if not document.company_id:
        raise AppException(status_code=404, message="Not found")
    with company_scope(db, frozenset({document.company_id})):
        return build_print_payload(db, document, issue)


def page_size_for_download(db: Session, download) -> tuple:
    """The PDF page size (mm) a spec sheet download prints at, without building the payload."""
    from app.models.base import company_scope

    with company_scope(db, None):
        document, _issue = source_of_download(db, download)
    if not document.company_id:
        raise AppException(status_code=404, message="Not found")
    with company_scope(db, frozenset({document.company_id})):
        return _templates_for(db, settings_of(document))["size"]
