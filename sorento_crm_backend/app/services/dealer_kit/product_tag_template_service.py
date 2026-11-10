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

PRICETAG-LPSP: a link can be the DEFAULT. PRICETAG-COMBO-FORMAT: one default LP and one
default SP per product / combo (``default_list`` / ``default_selling``), and a template carries a
hand-picked price type (list / selling / both / unset). A line is offered only the links that FIT
its price type (an unset template fits both). Pick order is the sent pick if allowed -> that
type's default -> the only fitting link -> (preview only) the first fitting link.
A combo line whose combo has published links uses THOSE (the combo must hang off the line's
host product); otherwise the host product's.

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

from sqlalchemy import and_, false, func
from sqlalchemy.orm import Query, Session

from app.models.dealer_kit import ComboTagTemplate, ProductTagTemplate, TagTemplate
from app.models.product import Product
from app.models.product_combo import ProductCombo
from app.services.dealer_kit.template_needs import (
    combo_shape,
    doc_reads_variants,
    fit_reason,
    template_needs,
)
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
    if model is TagTemplate:
        # An archived template (TAG-TEMPLATE-DELETE-CONFIRM) keeps its links for a restore, but
        # no product, combo or request picker offers it and nothing new can link to it.
        query = query.filter(TagTemplate.archived_at.is_(None))
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


# A linked template with its two default flags: (template, default_list, default_selling).
Link = tuple[TagTemplate, bool, bool]

PRICE_TYPES = ("list", "selling")

_FITS = {"list": ("list", "both", None), "selling": ("selling", "both", None)}


def fits_type(template_price_type: Optional[str], price_type: Optional[str]) -> bool:
    """A template of this price type is offered on a line of ``price_type``. An unset template
    fits both; a line with no price type (pre-LPSP data) fits everything."""
    if price_type not in _FITS:
        return True
    return template_price_type in _FITS[price_type]


def fits(template: TagTemplate, price_type: Optional[str]) -> bool:
    return fits_type(template.price_type, price_type)


def _flag(link: Link, price_type: str) -> bool:
    return link[1] if price_type == "list" else link[2]


def _defaults_for(links: list[Link], price_type: str) -> set[str]:
    """Ids that count as the default for one type: the stored one, else a lone fitting link."""
    # R1: a saved flag counts only while its template still fits that type.
    stored = {link[0].id for link in links if _flag(link, price_type) and fits(link[0], price_type)}
    if stored:
        return stored
    fitting = [link[0].id for link in links if fits(link[0], price_type)]
    return {fitting[0]} if len(fitting) == 1 else set()


def line_label(price_type: str) -> str:
    return "LP" if price_type == "list" else "SP"


def pick_template(
    allowed: list[Link],
    sent: Optional[str] = None,
    *,
    price_type: Optional[str] = None,
    first_fallback: bool = False,
) -> Optional[TagTemplate]:
    """Sent pick if allowed -> that type's default -> the only fitting link -> (preview) the
    first fitting one. With no ``price_type`` every link counts and either default stands in."""
    sent_id = _uuid_or_none(sent)
    by_id = {link[0].id: link[0] for link in allowed}
    if sent_id and sent_id in by_id:
        # A saved pick keeps printing even if the template stopped fitting (AC-37); whether a
        # NEW pick may be saved is `line_template_id`'s check.
        return by_id[sent_id]
    candidates = [link for link in allowed if fits(link[0], price_type)]
    if price_type in PRICE_TYPES:
        defaults = _defaults_for(candidates, price_type)
    else:
        stored = {link[0].id for link in candidates if link[1] or link[2]}
        defaults = stored or ({candidates[0][0].id} if len(candidates) == 1 else set())
    for link in candidates:
        if link[0].id in defaults:
            return link[0]
    if first_fallback and candidates:
        return candidates[0][0]
    return None


def _links_of(db: Session, link_model, owner_col, owner_id: str) -> list[Link]:
    rows = (
        _scoped(db, TagTemplate)
        .join(link_model, link_model.template_id == TagTemplate.id)
        .filter(owner_col == owner_id)
        .with_entities(TagTemplate, link_model.default_list, link_model.default_selling)
        .order_by(TagTemplate.name, TagTemplate.id)
        .all()
    )
    return [(t, bool(dl), bool(ds)) for t, dl, ds in rows]


def linked_templates(db: Session, product_id: str) -> list[TagTemplate]:
    """Every template linked to this product, published or not, by name."""
    return [l[0] for l in _links_of(db, ProductTagTemplate, ProductTagTemplate.product_id, product_id)]


def linked_items(db: Session, product_id: str) -> list[dict]:
    """``linked_templates`` as wire items, each with its defaults per type."""
    return _items(_links_of(db, ProductTagTemplate, ProductTagTemplate.product_id, product_id))


def linked_combo_templates(db: Session, combo_id: str) -> list[TagTemplate]:
    return [l[0] for l in _links_of(db, ComboTagTemplate, ComboTagTemplate.combo_id, combo_id)]


def linked_combo_items(db: Session, combo_id: str) -> list[dict]:
    return _items(_links_of(db, ComboTagTemplate, ComboTagTemplate.combo_id, combo_id))


def _items(links: list[Link]) -> list[dict]:
    default_list = _defaults_for(links, "list")
    default_selling = _defaults_for(links, "selling")
    return [
        template_item(
            link[0],
            default_list=link[0].id in default_list,
            default_selling=link[0].id in default_selling,
        )
        for link in links
    ]


def _published(db: Session, link_model, owner_col, owner_ids: set[str]) -> dict[str, list[Link]]:
    rows = (
        _price_tag_only(_scoped(db, TagTemplate))
        .join(link_model, link_model.template_id == TagTemplate.id)
        .filter(owner_col.in_(owner_ids), TagTemplate.published_version_id.isnot(None))
        .with_entities(owner_col, TagTemplate, link_model.default_list, link_model.default_selling)
        .order_by(TagTemplate.name, TagTemplate.id)
        .all()
    )
    out: dict[str, list[Link]] = {}
    for owner_id, template, dl, ds in rows:
        out.setdefault(str(owner_id), []).append((template, bool(dl), bool(ds)))
    return out


def published_links(db: Session, product_ids: Iterable[str]) -> dict[str, list[TagTemplate]]:
    """product id -> its linked PUBLISHED templates, by name. A product with
    none is absent from the map."""
    ids = {pid for pid in (_uuid_or_none(p) for p in product_ids) if pid}
    if not ids:
        return {}
    found = _published(db, ProductTagTemplate, ProductTagTemplate.product_id, ids)
    return {pid: [link[0] for link in links] for pid, links in found.items()}


LineLinks = dict[tuple[str, Optional[str]], list[Link]]


def line_links(db: Session, pairs: Iterable[tuple[Optional[str], Optional[str]]]) -> LineLinks:
    """(product_id, combo_id) -> the PUBLISHED links that line may print with: the
    combo's own when it has any and hangs off that product, else the product's."""
    clean = [
        (str(pid), _uuid_or_none(cid)) for pid, cid in pairs if _uuid_or_none(pid)
    ]
    pids = {pid for pid, _ in clean}
    if not pids:
        return {}
    product = _published(db, ProductTagTemplate, ProductTagTemplate.product_id, pids)
    cids = {cid for _, cid in clean if cid}
    combo: dict[tuple[str, str], list[Link]] = {}
    if cids:
        rows = (
            _price_tag_only(_scoped(db, TagTemplate))
            .join(ComboTagTemplate, ComboTagTemplate.template_id == TagTemplate.id)
            .join(ProductCombo, ProductCombo.id == ComboTagTemplate.combo_id)
            .filter(
                ComboTagTemplate.combo_id.in_(cids),
                ProductCombo.host_product_id.in_(pids),
                TagTemplate.published_version_id.isnot(None),
            )
            .with_entities(
                ComboTagTemplate.combo_id,
                ProductCombo.host_product_id,
                TagTemplate,
                ComboTagTemplate.default_list,
                ComboTagTemplate.default_selling,
            )
            .order_by(TagTemplate.name, TagTemplate.id)
            .all()
        )
        for combo_id, host_id, template, dl, ds in rows:
            combo.setdefault((str(combo_id), str(host_id)), []).append((template, bool(dl), bool(ds)))
    shapes = (
        {c.id: combo_shape(c) for c in db.query(ProductCombo).filter(ProductCombo.id.in_(cids)).all()}
        if cids
        else {}
    )

    def fitting(links: list[Link], cid: Optional[str]) -> list[Link]:
        """M1b: a template that cannot print every fixed part of the combo never draws it. An
        existing non-fitting link is ignored here, at read; nothing is migrated."""
        shape = shapes.get(cid) if cid else None
        if shape is None:
            return links
        return [
            link
            for link in links
            if link[0].published_version is None
            or fit_reason(template_needs(link[0].published_version.doc), shape) is None
        ]

    return {
        (pid, cid): fitting((combo.get((cid, pid)) if cid else None) or product.get(pid, []), cid)
        for pid, cid in clean
    }


def links_for(links: LineLinks, product_id: Optional[str], combo_id: Optional[str]) -> list[Link]:
    if not product_id:
        return []
    return links.get((str(product_id), _uuid_or_none(combo_id)), [])


def published_items(
    db: Session,
    product_id: str,
    combo_id: Optional[str] = None,
    price_type: Optional[str] = None,
) -> list[dict]:
    """The portal lookup: the line's PUBLISHED links as wire items. With ``price_type`` only the
    templates that fit it (the defaults are judged over all the links first)."""
    links = line_links(db, [(product_id, combo_id)])
    items = _items(links_for(links, product_id, combo_id))
    return [item for item in items if fits_type(item["price_type"], price_type)]


# ---------------------------------------------------------------------------
# Product page: replace the set
# ---------------------------------------------------------------------------


def _mismatch(template: TagTemplate, price_type: str) -> AppException:
    return AppException(
        status_code=422,
        message=f"{template.name} is not an {line_label(price_type)} template.",
        code="TEMPLATE_PRICE_TYPE_MISMATCH",
    )


def _check_templates(
    db: Session,
    template_ids: list[str],
    default_list_template_id,
    default_selling_template_id,
    default_template_id=None,
) -> tuple[list[str], dict[str, TagTemplate], Optional[str], Optional[str]]:
    """The clean ordered ids, the templates by id, and the two defaults (None = none). 404 for a
    template outside scope, 422 for a non price tag family, a default that is not among the ids
    or one whose price type does not fit its kind. The legacy ``default_template_id`` sets BOTH
    defaults when neither new key is sent."""
    wanted: list[str] = []
    for raw in template_ids:
        tid = _uuid_or_none(raw)
        if tid is None:
            raise _not_found("Tag template")
        if tid not in wanted:
            wanted.append(tid)
    found: dict[str, TagTemplate] = {}
    if wanted:
        found = {
            row.id: row
            for row in _scoped(db, TagTemplate).filter(TagTemplate.id.in_(wanted)).all()
        }
        if len(found) != len(wanted):
            raise _not_found("Tag template")
        if any(not is_price_tag_family(row.family) for row in found.values()):
            raise _not_a_price_tag()

    legacy = default_list_template_id in (None, "") and default_selling_template_id in (None, "")
    if legacy:
        default_list_template_id = default_selling_template_id = default_template_id

    def resolve(raw, price_type: str) -> Optional[str]:
        if raw in (None, ""):
            return None
        default_id = _uuid_or_none(raw)
        if default_id is None or default_id not in wanted:
            raise AppException(
                status_code=422,
                message="The default template must be one of the linked templates.",
                code="INVALID_DEFAULT_TEMPLATE",
            )
        if not fits(found[default_id], price_type):
            # R12: the legacy single default sets only the types it fits; an explicit one is 422.
            if legacy:
                return None
            raise _mismatch(found[default_id], price_type)
        return default_id

    return (
        wanted,
        found,
        resolve(default_list_template_id, "list"),
        resolve(default_selling_template_id, "selling"),
    )


def _replace_links(
    db: Session, link_model, owner_attr: str, owner_id: str, wanted: list[str],
    found: dict[str, TagTemplate], list_id: Optional[str], selling_id: Optional[str],
    user_id: Optional[str],
) -> None:
    owner_col = getattr(link_model, owner_attr)
    existing = {}
    for link, archived_at in (
        db.query(link_model, TagTemplate.archived_at)
        .join(TagTemplate, TagTemplate.id == link_model.template_id)
        .filter(owner_col == owner_id)
        .all()
    ):
        if archived_at is None:
            existing[link.template_id] = link
        elif link.default_list or link.default_selling:
            # A link to an archived template stays for a restore (TAG-TEMPLATE-DELETE-CONFIRM),
            # out of sight of the picker that sent `wanted`; it just cannot hold a default.
            link.default_list = False
            link.default_selling = False
    # Crew pass on bb5954ce: a 1 -> 2 link change must never drop the default. A lone link IS
    # the default, stored or not, so it stays the default when others are added; and a single
    # wanted link is the default. Clearing on purpose (None with 2+ links before and after)
    # still clears. Judged per type: a link is only ever the default of a type it fits.
    chosen = {"list": list_id, "selling": selling_id}
    for kind in PRICE_TYPES:
        if chosen[kind] is not None:
            continue
        if len(existing) == 1 and next(iter(existing)) in wanted:
            candidate = next(iter(existing))
        elif len(wanted) == 1:
            candidate = wanted[0]
        else:
            continue
        if fits(found[candidate], kind):
            chosen[kind] = candidate
    for template_id, link in existing.items():
        if template_id not in wanted:
            db.delete(link)
        else:
            if link.default_list and template_id != chosen["list"]:
                link.default_list = False
            if link.default_selling and template_id != chosen["selling"]:
                link.default_selling = False
    # The partial unique indexes allow one default per type: clear before the new ones are set.
    db.flush()
    for template_id in wanted:
        is_list = template_id == chosen["list"]
        is_selling = template_id == chosen["selling"]
        if template_id in existing:
            existing[template_id].default_list = is_list
            existing[template_id].default_selling = is_selling
        else:
            db.add(
                link_model(
                    **{owner_attr: owner_id},
                    template_id=template_id,
                    default_list=is_list,
                    default_selling=is_selling,
                    created_by=user_id,
                )
            )
    db.flush()


def set_product_templates(
    db: Session,
    product_id: str,
    template_ids: list[str],
    *,
    user_id: Optional[str],
    default_list_template_id: Optional[str] = None,
    default_selling_template_id: Optional[str] = None,
    default_template_id: Optional[str] = None,
) -> list[TagTemplate]:
    """Make the product's links exactly ``template_ids``, with one default LP and one default
    SP (each one of them, or None) preselected on a line of that type.

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
    wanted, found, list_id, selling_id = _check_templates(
        db, template_ids, default_list_template_id, default_selling_template_id, default_template_id
    )
    _replace_links(
        db, ProductTagTemplate, "product_id", product.id, wanted, found, list_id, selling_id, user_id
    )
    return linked_templates(db, product.id)


def combo_exists(db: Session, combo_id: str) -> bool:
    """A combo is scoped through its host product (it has no company column)."""
    cid = _uuid_or_none(combo_id)
    return bool(cid) and (
        _scoped(db, Product)
        .join(ProductCombo, ProductCombo.host_product_id == Product.id)
        .filter(ProductCombo.id == cid)
        .first()
        is not None
    )


def _require_fit(db: Session, combo_id: str, template_ids: list[str]) -> None:
    """422 naming the reason when a template cannot print the combo (`fit_reason`); a template
    with no published document has no needs yet and is let through."""
    combo = db.get(ProductCombo, _uuid_or_none(combo_id))
    if combo is None or not template_ids:
        return
    shape = combo_shape(combo)
    for template in db.query(TagTemplate).filter(TagTemplate.id.in_(template_ids)).all():
        version = template.published_version
        reason = fit_reason(template_needs(version.doc), shape) if version is not None else None
        if reason:
            raise AppException(
                status_code=422,
                message=f"{template.name}: {reason}",
                code="TAG_TEMPLATE_DOES_NOT_FIT",
            )


def set_combo_templates(
    db: Session,
    combo_id: str,
    template_ids: list[str],
    *,
    user_id: Optional[str],
    default_list_template_id: Optional[str] = None,
    default_selling_template_id: Optional[str] = None,
    default_template_id: Optional[str] = None,
) -> list[TagTemplate]:
    """``set_product_templates`` for a combo."""
    if not combo_exists(db, combo_id):
        raise _not_found("Combo")
    wanted, found, list_id, selling_id = _check_templates(
        db, template_ids, default_list_template_id, default_selling_template_id, default_template_id
    )
    _require_fit(db, combo_id, wanted)
    _replace_links(
        db, ComboTagTemplate, "combo_id", _uuid_or_none(combo_id), wanted, found,
        list_id, selling_id, user_id,
    )
    return linked_combo_templates(db, combo_id)


def product_exists(db: Session, product_id: str) -> bool:
    """In this session's scope: a product in another company reads as missing."""
    pid = _uuid_or_none(product_id)
    return bool(pid) and _scoped(db, Product).filter(Product.id == pid).first() is not None


def _lone_link_is_default(db: Session, link_model, owner_attr: str, owner_ids) -> None:
    """Every owner left with exactly one link gets that link as the default of each type it fits
    (crew pass on bb5954ce: an unlink down to one must not leave a default-less owner, or the
    next add would start with none)."""
    owner_col = getattr(link_model, owner_attr)
    ids = [oid for oid in owner_ids if oid]
    if not ids:
        return
    by_owner: dict[str, list] = {}
    for link, template in (
        db.query(link_model, TagTemplate)
        .join(TagTemplate, TagTemplate.id == link_model.template_id)
        .filter(owner_col.in_(ids))
        .all()
    ):
        by_owner.setdefault(str(getattr(link, owner_attr)), []).append((link, template))
    changed = False
    for rows in by_owner.values():
        if len(rows) != 1:
            continue
        link, template = rows[0]
        if not link.default_list and fits(template, "list"):
            link.default_list = True
            changed = True
        if not link.default_selling and fits(template, "selling"):
            link.default_selling = True
            changed = True
    if changed:
        db.flush()


def _freeze_shown_defaults(db: Session, link_model, owner_attr: str, owner_ids) -> None:
    """Save each owner's Default LP / SP exactly as the card shows it (`_defaults_for`), before
    links are added in bulk (PRICETAG-TEMPLATE-PRODUCTS, crew pass on c6e3e014: AC-7).

    A default the card shows can be implicit, "the only template that fits this type", with no
    saved flag. Adding a second template that fits the type would silently empty it. Saving it
    first means a bulk add can never change a default the product already shows. An owner with
    no shown default for a type keeps none; archived links are not on the card and are skipped.
    """
    owner_col = getattr(link_model, owner_attr)
    ids = [oid for oid in owner_ids if oid]
    if not ids:
        return
    by_owner: dict[str, list] = {}
    for link, template in (
        db.query(link_model, TagTemplate)
        .join(TagTemplate, TagTemplate.id == link_model.template_id)
        .filter(owner_col.in_(ids), TagTemplate.archived_at.is_(None))
        .all()
    ):
        by_owner.setdefault(str(getattr(link, owner_attr)), []).append((link, template))
    wanted: list[tuple[object, str]] = []
    for rows in by_owner.values():
        shown = [(template, link.default_list, link.default_selling) for link, template in rows]
        for kind, flag in (("list", "default_list"), ("selling", "default_selling")):
            defaults = _defaults_for(shown, kind)
            if len(defaults) != 1:
                continue
            target = next(iter(defaults))
            for link, template in rows:
                if getattr(link, flag) and template.id != target:
                    # A stale flag (its template no longer fits): the card already ignores it.
                    setattr(link, flag, False)
                elif template.id == target and not getattr(link, flag):
                    wanted.append((link, flag))
    if not wanted:
        return
    # One default per type per owner (partial unique indexes): clear before setting.
    db.flush()
    for link, flag in wanted:
        setattr(link, flag, True)
    db.flush()


def unlink_product_templates(db: Session, product_id: str, template_ids: list[str]) -> dict:
    """The product page's Remove, committed after its countdown (an unlink, so
    it parks: ``product.unlink_tag_templates``). Only links of a product in
    scope are touched; ids it does not hold are ignored."""
    if not product_exists(db, product_id):
        raise _not_found("Product")
    ids = [tid for tid in (_uuid_or_none(t) for t in template_ids or []) if tid]
    if not ids:
        return {"changed": 0}
    changed = (
        db.query(ProductTagTemplate)
        .filter(
            ProductTagTemplate.product_id == _uuid_or_none(product_id),
            ProductTagTemplate.template_id.in_(ids),
        )
        .delete(synchronize_session=False)
    )
    db.flush()
    _lone_link_is_default(db, ProductTagTemplate, "product_id", [_uuid_or_none(product_id)])
    return {"changed": changed}


def unlink_combo_templates(db: Session, combo_id: str, template_ids: list[str]) -> dict:
    """A combo's Remove, committed after its countdown (``combo.unlink_tag_templates``), the
    combo twin of ``unlink_product_templates``. Only links of a combo in scope are touched
    (scope = its host product's company); ids it does not hold are ignored."""
    if not combo_exists(db, combo_id):
        raise _not_found("Combo")
    ids = [tid for tid in (_uuid_or_none(t) for t in template_ids or []) if tid]
    if not ids:
        return {"changed": 0}
    changed = (
        db.query(ComboTagTemplate)
        .filter(
            ComboTagTemplate.combo_id == _uuid_or_none(combo_id),
            ComboTagTemplate.template_id.in_(ids),
        )
        .delete(synchronize_session=False)
    )
    db.flush()
    _lone_link_is_default(db, ComboTagTemplate, "combo_id", [_uuid_or_none(combo_id)])
    return {"changed": changed}


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
    # PRICETAG-TEMPLATE-PRODUCTS: picked ids; junk ids are dropped here, foreign ones by `_scoped`.
    raw_product_ids = [v for v in (filters.get("product_ids") or []) if v]
    product_ids = _clean_ids(raw_product_ids)
    if not (brand_ids or category_ids or item_class_ids or family_codes or raw_product_ids):
        raise AppException(
            status_code=422,
            message="Pick at least one product, brand, category, item class or model family.",
            code="FILTER_REQUIRED",
        )
    conditions = []
    if raw_product_ids:
        # Ids were sent, so they narrow even when none of them is a valid id.
        conditions.append(Product.id.in_(product_ids) if product_ids else false())
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


def linked_product_ids(db: Session, template_id: str) -> list[str]:
    """Ids of this company's products that use the template (PRICETAG-TEMPLATE-PRODUCTS: the
    designer's Products dialog ticks them on open). A link from a product outside the session's
    scope is never listed."""
    template = _template_or_404(db, template_id)
    rows = (
        _scoped(db, Product)
        .join(ProductTagTemplate, ProductTagTemplate.product_id == Product.id)
        .filter(ProductTagTemplate.template_id == template.id)
        .with_entities(Product.id)
        .all()
    )
    return [row.id for row in rows]


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
        # Same as the product page's unlink: the removed template's defaults go with it, and a
        # product left with one template has it as its saved default for the types it fits.
        _lone_link_is_default(db, ProductTagTemplate, "product_id", list(linked))
        return {"changed": changed}
    missing = [pid for pid in product_ids if pid not in linked]
    # A bulk add never changes a default the product already shows, saved or implicit.
    _freeze_shown_defaults(db, ProductTagTemplate, "product_id", missing)
    db.add_all(
        ProductTagTemplate(product_id=pid, template_id=template.id, created_by=user_id)
        for pid in missing
    )
    db.flush()
    # ...and a product whose first link this was has it as its default.
    _lone_link_is_default(db, ProductTagTemplate, "product_id", missing)
    return {"changed": len(missing)}


# ---------------------------------------------------------------------------
# Request lines
# ---------------------------------------------------------------------------


def line_template_id(
    db: Session,
    *,
    line_type: str,
    product_id: Optional[str],
    sent: Optional[str],
    combo_id: Optional[str] = None,
    price_type: Optional[str] = None,
    kept: Optional[set[str]] = None,
) -> Optional[str]:
    """What a saved line stores in ``tag_template_id`` (see module docstring).

    A sent pick that is linked but does not fit the line's price type is refused (422
    ``TEMPLATE_PRICE_TYPE_MISMATCH``), unless it is ``kept``: the template already stored on this
    line for the same price type (it may have stopped fitting since; it keeps printing)."""
    if line_type != "product" or not product_id:
        return None
    allowed = links_for(line_links(db, [(product_id, combo_id)]), product_id, combo_id)
    sent_id = _uuid_or_none(sent)
    if sent_id and price_type in PRICE_TYPES and sent_id not in (kept or set()):
        picked = next((link[0] for link in allowed if link[0].id == sent_id), None)
        if picked is not None and not fits(picked, price_type):
            raise _mismatch(picked, price_type)
    chosen = pick_template(allowed, sent, price_type=price_type)
    return chosen.id if chosen is not None else None


def require_line_templates(db: Session, request) -> None:
    """Submit's (and Approve's) own gate. A product line whose product (or combo) has published
    links but none that fits the line's LP / SP is refused (``NO_TEMPLATE_FOR_PRICE_TYPE``);
    one that allows several fitting templates must carry one of them, unless a default stands in
    for the pick. 422 naming the first such line by its form index, like the other line refusals."""
    lines = sorted(request.lines or [], key=lambda l: (l.sort_order or 0, l.id))
    links = line_links(
        db,
        [(l.product_id, l.combo_id) for l in lines if l.line_type == "product" and l.product_id],
    )
    for idx, line in enumerate(lines):
        if line.line_type != "product" or not line.product_id:
            continue
        allowed = links_for(links, line.product_id, line.combo_id)
        price_type = line.price_type if line.price_type in PRICE_TYPES else None
        fitting = [link for link in allowed if fits(link[0], price_type)]
        # R5 (AC-37 wins over AC-36): a line keeping its stored template, which is still linked,
        # passes even if that template no longer fits and nothing fitting is linked.
        kept = bool(line.tag_template_id) and any(link[0].id == line.tag_template_id for link in allowed)
        if allowed and not fitting and not kept:
            raise AppException(
                status_code=422,
                message=f"{_line_item_label(db, line)}: No {line_label(price_type)} template linked",
                detail=f"line:{idx}",
                code="NO_TEMPLATE_FOR_PRICE_TYPE",
            )
        if len(fitting) > 1 and pick_template(allowed, line.tag_template_id, price_type=price_type) is None:
            raise AppException(
                status_code=422,
                message=TEMPLATE_REQUIRED_MESSAGE,
                detail=f"line:{idx}",
                code="TAG_TEMPLATE_REQUIRED",
            )


def _line_item_label(db: Session, line) -> str:
    """The combo's name for a combo line, else the product code."""
    if line.combo_id:
        combo = db.get(ProductCombo, line.combo_id)
        if combo is not None:
            return combo.name
    product = _scoped(db, Product).filter(Product.id == line.product_id).first()
    return product.product_code if product is not None else "This item"


def template_item(
    template: TagTemplate, default_list: bool = False, default_selling: bool = False
) -> dict:
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
        "price_type": template.price_type,
        "default_list": default_list,
        "default_selling": default_selling,
        "is_default": default_list or default_selling,
        "needs": template_needs(version.doc) if version is not None else None,
        # PRICETAG-UPGRADE-VARIANTS: the line shows "Variants on this tag" only for such a template.
        "reads_variants": doc_reads_variants(version.doc) if version is not None else False,
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

    request = PriceTagRequest(
        price_mode="selling" if price_mode == "selling" else "list", status="new"
    )
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
        # PRICETAG-LPSP: each line's own LP/SP; none sent = the header's mode.
        price_type = raw.get("price_type") if raw.get("price_type") in ("list", "selling") else None
        price_type = price_type or request.price_mode
        selling = price_type == "selling"

        basis = "list"
        # Run whenever a promotion is named, in BOTH modes (security review):
        # the resolver below prices with the staff viewer, so a promotion
        # outside this contact's audience must be dropped here, exactly as a
        # real save refuses it, or its price would come back in `sell_price`.
        if selling or promotion_id:
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
            price_type=price_type,
            quantity=1,
            combo_id=combo_id,
            promotion_id=promotion_id,
            manual_sell_price=manual,
            sort_order=idx,
            tag_template_id=_uuid_or_none(raw.get("tag_template_id")),
            # Only narrows the member list, so an id outside the tree simply matches nothing.
            excluded_variant_ids=[str(i) for i in raw.get("excluded_variant_ids") or []],
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
    one of the product's published links, else its first link.

    A PRODUCT line with no published link gets NO template (#2101 browser
    pass): since the salesperson approves his own tag, a silent family
    fallback let him approve another product's layout (CKS821 drew a
    template carrying bathroom furniture text). The preview says which items
    have none and #2101's Approve refuses them (NO_TEMPLATE, escalate). A SET
    line keeps the family rule (card Q4), but only an exact
    ``furniture_set`` template, never the ala carte / first-template chain.
    """
    from app.services.dealer_kit import tag_sheet_export_service

    code_by_line = {}
    for row in rows:
        code_by_line.setdefault(row["line_id"], row.get("code"))
    links = line_links(db, [(line.product_id, line.combo_id) for _, line in keyed_lines])
    everything: Optional[list[TagTemplate]] = None
    templates: dict[str, dict] = {}
    for key, line in keyed_lines:
        allowed = links_for(links, line.product_id, line.combo_id)
        chosen = pick_template(
            allowed, line.tag_template_id, price_type=line.price_type, first_fallback=True
        )
        if chosen is None and line.line_type == "product_set":
            if everything is None:
                everything = _published_templates(db)
            family = family_for(line.line_type, code_by_line.get(key))
            chosen = next((t for t in everything if t.family == family), None)
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


def clear_unfit_defaults(db: Session, template: TagTemplate) -> None:
    """R1: after a template's price type changes, the default flags it no longer fits go, on every
    product and combo link (the flag would otherwise sit unseen and come back with the type)."""
    for model in (ProductTagTemplate, ComboTagTemplate):
        for link in db.query(model).filter(model.template_id == template.id).all():
            if link.default_list and not fits(template, "list"):
                link.default_list = False
            if link.default_selling and not fits(template, "selling"):
                link.default_selling = False
    db.flush()
