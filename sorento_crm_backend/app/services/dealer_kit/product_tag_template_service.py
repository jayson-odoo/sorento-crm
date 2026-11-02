"""Which tag templates a product may print with (PRICETAG-TEMPLATE-PER-PRODUCT).

Plan: documentation/plans/dealer-kit/PLAN-pricetag-template-per-product-02nov.md.

A product carries zero, one or many links (``ProductTagTemplate``). Only a
PUBLISHED template counts on a request: an unpublished one stays linked, so a
republish brings it back, but nothing offers it meanwhile.

On a request line (``line_template_id``):

* one published link   -> that template, filled in on save without asking;
* several              -> the salesperson's pick, required at submit
                          (``require_line_templates``);
* none, or a set line  -> NULL, and the designer's family rule applies as it
                          always has.

A sent ``tag_template_id`` that is not one of the line's product's published
links is DROPPED, never stored and never answered with its own error: the
same "no pick" a salesperson gets for an unlinked or unpublished template,
and no way to probe whether some other template id exists.

Every template and product read goes through the session's company scope
explicitly (``_scoped``), the same rule ``tag_template_service`` follows.
"""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Query, Session

from app.models.dealer_kit import ProductTagTemplate, TagTemplate
from app.models.product import Product
from app.services.company_scope import build_company_predicate, get_company_scope
from app.services.error_handler import AppException

TEMPLATE_REQUIRED_MESSAGE = "Pick a tag template for this line."

# PS-SPEC-SHEET (#2103) keeps its project spec sheet pages (`spec_cover`,
# `spec_page`, 16:9) in the same table. They are never a price tag: not
# linkable, not assignable, never auto-picked or used as a family default.
NON_PRICE_TAG_FAMILY_PREFIX = "spec_"


def is_price_tag_family(family: Optional[str]) -> bool:
    return not (family or "").startswith(NON_PRICE_TAG_FAMILY_PREFIX)


def _price_tag_only(query: Query) -> Query:
    return query.filter(~TagTemplate.family.startswith(NON_PRICE_TAG_FAMILY_PREFIX))


def _not_a_price_tag() -> AppException:
    return AppException(
        status_code=422,
        message="This template is not a price tag template.",
        code="NOT_A_PRICE_TAG_TEMPLATE",
    )


def _scoped(db: Session, model) -> Query:
    query = db.query(model)
    predicate = build_company_predicate(model, get_company_scope(db))
    return query if predicate is None else query.filter(predicate)


def _uuid_or_none(value) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def _not_found(what: str) -> AppException:
    return AppException(status_code=404, message=f"{what} not found.", code="NOT_FOUND")


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def linked_templates(db: Session, product_id: str) -> list[TagTemplate]:
    """Every template linked to this product, published or not, by name."""
    return (
        _scoped(db, TagTemplate)
        .join(ProductTagTemplate, ProductTagTemplate.template_id == TagTemplate.id)
        .filter(ProductTagTemplate.product_id == product_id)
        .order_by(TagTemplate.name, TagTemplate.id)
        .all()
    )


def published_links(db: Session, product_ids: Iterable[str]) -> dict[str, list[TagTemplate]]:
    """product id -> its linked PUBLISHED templates, by name. A product with
    none is absent from the map."""
    ids = {pid for pid in (_uuid_or_none(p) for p in product_ids) if pid}
    if not ids:
        return {}
    rows = (
        _price_tag_only(_scoped(db, TagTemplate))
        .join(ProductTagTemplate, ProductTagTemplate.template_id == TagTemplate.id)
        .filter(
            ProductTagTemplate.product_id.in_(ids),
            TagTemplate.published_version_id.isnot(None),
        )
        .with_entities(ProductTagTemplate.product_id, TagTemplate)
        .order_by(TagTemplate.name, TagTemplate.id)
        .all()
    )
    out: dict[str, list[TagTemplate]] = {}
    for product_id, template in rows:
        out.setdefault(str(product_id), []).append(template)
    return out


# ---------------------------------------------------------------------------
# Product page: replace the set
# ---------------------------------------------------------------------------


def set_product_templates(
    db: Session, product_id: str, template_ids: list[str], *, user_id: Optional[str]
) -> list[TagTemplate]:
    """Make the product's links exactly ``template_ids``.

    404 for a product or any template outside this session's scope - one
    message for missing and foreign alike, and nothing is written.
    """
    product_id = _uuid_or_none(product_id)
    product = (
        _scoped(db, Product).filter(Product.id == product_id).first()
        if product_id
        else None
    )
    if product is None:
        raise _not_found("Product")

    wanted: list[str] = []
    for raw in template_ids:
        tid = _uuid_or_none(raw)
        if tid is None:
            raise _not_found("Tag template")
        if tid not in wanted:
            wanted.append(tid)
    if wanted:
        found = {
            row.id: row
            for row in _scoped(db, TagTemplate).filter(TagTemplate.id.in_(wanted)).all()
        }
        if len(found) != len(wanted):
            raise _not_found("Tag template")
        if any(not is_price_tag_family(row.family) for row in found.values()):
            raise _not_a_price_tag()

    existing = {
        link.template_id: link
        for link in db.query(ProductTagTemplate)
        .filter(ProductTagTemplate.product_id == product.id)
        .all()
    }
    for template_id, link in existing.items():
        if template_id not in wanted:
            db.delete(link)
    for template_id in wanted:
        if template_id not in existing:
            db.add(
                ProductTagTemplate(
                    product_id=product.id, template_id=template_id, created_by=user_id
                )
            )
    db.flush()
    return linked_templates(db, product.id)


# ---------------------------------------------------------------------------
# Bulk assignment (Tag Templates list)
# ---------------------------------------------------------------------------


def _clean_ids(values: Iterable) -> list[str]:
    return [v for v in (_uuid_or_none(x) for x in (values or [])) if v]


def _clean_codes(values: Iterable) -> list[str]:
    return [str(v).strip() for v in (values or []) if str(v or "").strip()]


def _bulk_products_query(db: Session, filters: dict) -> Query:
    """Products matching the bulk filter: AND across kinds, OR within one.

    An all-empty filter is refused (422) so one click can never touch every
    product in the company.
    """
    brand_ids = _clean_ids(filters.get("brand_ids"))
    category_ids = _clean_ids(filters.get("category_ids"))
    item_class_ids = _clean_ids(filters.get("item_class_ids"))
    family_codes = _clean_codes(filters.get("family_codes"))
    if not (brand_ids or category_ids or item_class_ids or family_codes):
        raise AppException(
            status_code=422,
            message="Pick at least one brand, category, item class or model family.",
            code="FILTER_REQUIRED",
        )
    conditions = []
    if brand_ids:
        conditions.append(Product.brand_id.in_(brand_ids))
    if category_ids:
        conditions.append(Product.category_id.in_(category_ids))
    if item_class_ids:
        conditions.append(Product.item_class_id.in_(item_class_ids))
    if family_codes:
        conditions.append(Product.family_code.in_(family_codes))
    return _scoped(db, Product).filter(and_(*conditions))


def _template_or_404(db: Session, template_id: str) -> TagTemplate:
    tid = _uuid_or_none(template_id)
    template = (
        _scoped(db, TagTemplate).filter(TagTemplate.id == tid).first() if tid else None
    )
    if template is None:
        raise _not_found("Tag template")
    if not is_price_tag_family(template.family):
        raise _not_a_price_tag()
    return template


def family_codes(db: Session, query: Optional[str], limit: int = 50) -> list[str]:
    """Model families (``Product.family_code``) for the bulk dialog's filter."""
    q = _scoped(db, Product).filter(Product.family_code.isnot(None))
    if query and query.strip():
        q = q.filter(Product.family_code.ilike(f"%{query.strip()}%"))
    rows = (
        q.with_entities(Product.family_code)
        .distinct()
        .order_by(Product.family_code)
        .limit(limit)
        .all()
    )
    return [row[0] for row in rows if row[0]]


def bulk_preview(db: Session, template_id: str, filters: dict) -> dict:
    template = _template_or_404(db, template_id)
    product_ids = [row.id for row in _bulk_products_query(db, filters).with_entities(Product.id)]
    already = 0
    if product_ids:
        already = (
            db.query(ProductTagTemplate)
            .filter(
                ProductTagTemplate.template_id == template.id,
                ProductTagTemplate.product_id.in_(product_ids),
            )
            .count()
        )
    return {"matched": len(product_ids), "already_linked": already}


def bulk_assign(
    db: Session, template_id: str, filters: dict, action: str, *, user_id: Optional[str]
) -> dict:
    """Add the template to every matching product that lacks it, or remove it
    from every matching product that has it. Answers ``{changed}``."""
    template = _template_or_404(db, template_id)
    product_ids = [row.id for row in _bulk_products_query(db, filters).with_entities(Product.id)]
    if not product_ids:
        return {"changed": 0}
    linked = {
        row.product_id
        for row in db.query(ProductTagTemplate.product_id).filter(
            ProductTagTemplate.template_id == template.id,
            ProductTagTemplate.product_id.in_(product_ids),
        )
    }
    if action == "remove":
        if not linked:
            return {"changed": 0}
        changed = (
            db.query(ProductTagTemplate)
            .filter(
                ProductTagTemplate.template_id == template.id,
                ProductTagTemplate.product_id.in_(list(linked)),
            )
            .delete(synchronize_session=False)
        )
        db.flush()
        return {"changed": changed}
    missing = [pid for pid in product_ids if pid not in linked]
    db.add_all(
        ProductTagTemplate(product_id=pid, template_id=template.id, created_by=user_id)
        for pid in missing
    )
    db.flush()
    return {"changed": len(missing)}


# ---------------------------------------------------------------------------
# Request lines
# ---------------------------------------------------------------------------


def line_template_id(
    db: Session, *, line_type: str, product_id: Optional[str], sent: Optional[str]
) -> Optional[str]:
    """What a saved line stores in ``tag_template_id`` (see module docstring)."""
    if line_type != "product" or not product_id:
        return None
    allowed = [t.id for t in published_links(db, [product_id]).get(str(product_id), [])]
    sent_id = _uuid_or_none(sent)
    if sent_id and sent_id in allowed:
        return sent_id
    if len(allowed) == 1:
        return allowed[0]
    return None


def require_line_templates(db: Session, request) -> None:
    """Submit's own gate: a product line whose product allows several
    published templates must carry one of them. 422 naming the first such
    line by its form index, like the other line refusals."""
    lines = sorted(request.lines or [], key=lambda l: (l.sort_order or 0, l.id))
    links = published_links(
        db, [l.product_id for l in lines if l.line_type == "product" and l.product_id]
    )
    for idx, line in enumerate(lines):
        if line.line_type != "product" or not line.product_id:
            continue
        allowed = {t.id for t in links.get(str(line.product_id), [])}
        if len(allowed) > 1 and line.tag_template_id not in allowed:
            raise AppException(
                status_code=422,
                message=TEMPLATE_REQUIRED_MESSAGE,
                detail=f"line:{idx}",
                code="TAG_TEMPLATE_REQUIRED",
            )


def template_item(template: TagTemplate) -> dict:
    """``ProductTagTemplateItem``: what the product page and the line read."""
    version = template.published_version
    size = (version.print_size if version is not None else template.print_size) or {}
    return {
        "id": template.id,
        "name": template.name,
        "family": template.family,
        "published": template.published_version_id is not None,
        "width_mm": size.get("width_mm"),
        "height_mm": size.get("height_mm"),
    }


def template_names(db: Session, template_ids: Iterable[str]) -> dict[str, str]:
    ids = {tid for tid in (_uuid_or_none(t) for t in template_ids) if tid}
    if not ids:
        return {}
    return {
        row.id: row.name
        for row in _scoped(db, TagTemplate).filter(TagTemplate.id.in_(ids)).all()
    }


# ---------------------------------------------------------------------------
# Live preview (the request form, before proof ready)
# ---------------------------------------------------------------------------

# The same table as `lib/dealer-kit/line-family.ts`, longest prefix first, so
# a preview and marketing's designer start a link-less line on the same
# family template. Kept in step by `test_family_for_matches_frontend_table`.
_FAMILY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("lmcb", "mirror_cabinet"),
    ("mcb", "mirror_cabinet"),
    ("mr", "mirror"),
    ("ks", "sink_combo"),
    ("wb", "art_basin"),
    ("gb", "art_basin"),
    ("wt", "shower"),
    ("wc", "wc"),
    ("sp", "wc"),
    ("ub", "urinal"),
    ("bf", "furniture_set"),
)


def family_for(line_type: str, code: Optional[str]) -> str:
    if line_type == "product_set":
        return "furniture_set"
    body = (code or "").lower()
    if body.startswith("srt"):
        body = body[3:]
    for prefix, family in _FAMILY_PREFIXES:
        if body.startswith(prefix):
            return family
    return "ala_carte"


def _published_templates(db: Session) -> list[TagTemplate]:
    """Every published template, in the request designer's own order
    (``list_tag_templates``: family, then name)."""
    return (
        _price_tag_only(_scoped(db, TagTemplate))
        .filter(TagTemplate.published_version_id.isnot(None))
        .order_by(TagTemplate.family, TagTemplate.name)
        .all()
    )


def _family_default(templates: list[TagTemplate], family: str) -> Optional[TagTemplate]:
    """`defaultTemplateFor` in lib/dealer-kit/request-tags.ts, server side."""
    if not templates:
        return None
    return (
        next((t for t in templates if t.family == family), None)
        or next((t for t in templates if t.family == "ala_carte"), None)
        or templates[0]
    )


def template_payload(template: TagTemplate) -> dict:
    """A template as the request designer reads it: the PUBLISHED version's
    doc and print size, never the draft."""
    version = template.published_version
    return {
        "id": template.id,
        "name": template.name,
        "family": template.family,
        "doc": version.doc if version is not None else template.doc,
        "print_size": version.print_size if version is not None else template.print_size,
    }


def preview(db: Session, *, price_mode: str, lines: list[dict], viewer) -> dict:
    """What the request form's live preview draws, with nothing written.

    Builds TRANSIENT request / line / part / tag objects (never added to the
    session) and resolves them through ``tag_data_service.resolve_tags_live``
    and ``tag_sheet_export_service.design_media`` - the same two calls behind
    the proof - so the preview cannot quote a price the proof would not.

    Each line's template: its pick when that is one of the product's
    published links, else its first link, else the family default among all
    published templates. Answers ``{lines, templates, assets, images, fonts}``
    with ``templates`` keyed by the client's line key.
    """
    from app.models.price_tag import (
        PriceTagRequest,
        PriceTagRequestLine,
        PriceTagRequestLinePart,
        PriceTagRequestTag,
    )
    from app.services.dealer_kit import tag_data_service
    from app.services.dealer_kit.pricing import line_pricing

    selling = price_mode == "selling"
    request = PriceTagRequest(price_mode="selling" if selling else "list", status="new")
    request.id = str(uuid.uuid4())

    built: list[tuple[str, PriceTagRequestLine]] = []
    for idx, raw in enumerate(lines):
        key = str(raw.get("key") or idx)[:64]
        line_type = "product_set" if raw.get("line_type") == "product_set" else "product"
        product_id = _uuid_or_none(raw.get("product_id")) if line_type == "product" else None
        product_set_id = (
            _uuid_or_none(raw.get("product_set_id")) if line_type == "product_set" else None
        )
        if not (product_id or product_set_id):
            continue
        promotion_id = _uuid_or_none(raw.get("promotion_id"))
        manual = raw.get("manual_sell_price")
        if promotion_id:
            manual = None
        parts = []
        for p_idx, part in enumerate(raw.get("parts") or []):
            pid = _uuid_or_none(part.get("product_id"))
            candidates = [c for c in (_uuid_or_none(x) for x in part.get("candidates") or []) if c]
            if not pid and not candidates:
                continue
            row = PriceTagRequestLinePart(
                product_id=pid,
                role=part.get("role"),
                candidates=[] if pid else candidates,
                sort_order=p_idx,
            )
            row.id = f"{key}:part:{p_idx}"
            parts.append(row)
        combo_id = _uuid_or_none(raw.get("combo_id"))

        basis = "list"
        if selling:
            pricing_row = line_pricing(
                db,
                lines=[
                    {
                        "key": "_p",
                        "product_id": product_id,
                        "part_product_ids": [p.product_id for p in parts if p.product_id]
                        if product_id
                        else [],
                        "candidate_product_ids": [c for p in parts for c in p.candidates]
                        if product_id
                        else [],
                        "combo_id": combo_id,
                        "promotion_id": promotion_id,
                        "manual_sell_price": manual,
                    }
                ],
                viewer=viewer,
                auto_pick=False,
            )[0]
            if promotion_id and promotion_id not in {
                option["id"] for option in pricing_row["promotion_options"]
            }:
                # Not this contact's promotion, or not this line's: drawn at
                # list price rather than at a figure the save would refuse.
                promotion_id = None
            basis = pricing_row["sell_price_basis"]

        line = PriceTagRequestLine(
            line_type=line_type,
            product_id=product_id,
            product_set_id=product_set_id,
            show_promo_price=selling and basis != "list",
            quantity=1,
            combo_id=combo_id,
            promotion_id=promotion_id,
            manual_sell_price=manual,
            sort_order=idx,
            tag_template_id=_uuid_or_none(raw.get("tag_template_id")),
        )
        line.id = key
        line.parts = parts
        tag = PriceTagRequestTag(quantity=1, choices={}, sort_order=0)
        tag.id = key
        line.tags = [tag]
        built.append((key, line))

    request.lines = [line for _, line in built]
    rows = tag_data_service.resolve_tags_live(db, request) if built else []
    return _with_templates(db, rows, built)


def _with_templates(db: Session, rows: list[dict], keyed_lines: list[tuple[str, object]]) -> dict:
    """Pick each line's template, then the media maps for rows + templates.

    ``keyed_lines`` is ``(key, line)``: the client's key on the form, the real
    line id for a saved request. Pick order: the line's own pick when it is
    one of the product's published links, else its first link, else the
    family default among every published price tag template.
    """
    from app.services.dealer_kit import tag_sheet_export_service

    code_by_line = {}
    for row in rows:
        code_by_line.setdefault(row["line_id"], row.get("code"))
    links = published_links(db, [line.product_id for _, line in keyed_lines if line.product_id])
    everything: Optional[list[TagTemplate]] = None
    templates: dict[str, dict] = {}
    for key, line in keyed_lines:
        allowed = links.get(str(line.product_id), []) if line.product_id else []
        chosen = next((t for t in allowed if t.id == line.tag_template_id), None)
        if chosen is None and allowed:
            chosen = allowed[0]
        if chosen is None:
            if everything is None:
                everything = _published_templates(db)
            chosen = _family_default(
                everything, family_for(line.line_type, code_by_line.get(key))
            )
        if chosen is not None:
            templates[key] = template_payload(chosen)

    combined_doc = {
        "layers": [
            layer
            for payload in templates.values()
            for layer in (payload["doc"] or {}).get("layers", [])
        ]
    }
    rows, media = tag_sheet_export_service.design_media(db, None, combined_doc, rows=rows)
    return {"lines": rows, "templates": templates, **media}


def preview_for_request(db: Session, request) -> dict:
    """The same answer for a SAVED request (PRICETAG-SELF-APPROVAL #2101's
    approve screen): rows carry the request's real line and tag ids,
    ``templates`` is keyed by the real line id, and the data is the
    resolver's own (pins included), exactly what the proof would draw."""
    from app.services.dealer_kit import tag_data_service

    rows = list(tag_data_service.resolve_request_line_data(db, request))
    return _with_templates(db, rows, [(line.id, line) for line in request.lines or []])
