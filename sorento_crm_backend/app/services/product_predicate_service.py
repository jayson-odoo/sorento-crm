"""Shape B: a described product set intersected with a domain predicate.

"What faucets have certs" cannot be answered by resolving a top-K list and joining
ids across the wire: whenever the qualifying products fall outside K, the answer is
a false "none". So the intersection happens HERE, over the full company-scoped
catalogue - membership and the count are SQL, and the ranker only orders the
products that already qualify (`search_specs(product_ids=...)`).

Extending to a new domain is one function and one `REQUIRE_LEGS` entry - the legs
are a code-side registry on purpose. A predicate leg is behavior (validity logic,
ledger semantics, a join graph), not data, so registering SQL fragments as rows
would be a security surface wearing a config table's clothes.

Two standing rules every leg MUST follow:

- **ORM only, never raw ``text()`` SQL.** Company isolation is injected by the
  ``do_orm_execute`` listener (`app/services/company_scope.py`) into every ORM
  SELECT touching a `CompanyScopedMixin` model; raw SQL bypasses it entirely.
- **Reach unscoped link tables through a scoped side.** `certificate_products`
  carries no `company_id`; the certificate leg joins through `Certificate`
  (scoped), never the link table alone.

Contract: sorento_crm_n8n/n8n-workflows-init/plans/crm-ask-spec-backward-search.md.
Plan: documentation/plans/PLAN-spec-backward-search.md.
"""
from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import String as _String
from sqlalchemy import cast as _cast
from sqlalchemy import exists, func, or_
from sqlalchemy.dialects.postgresql import ARRAY as _ARRAY
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql import ColumnElement

from app.models.access import ContactAccessType
from app.models.certificate import Certificate, CertificateProduct, CertificateRevision
from app.models.inventory import Stock
from app.models.marketing import Promotion, PromotionProduct
from app.models.procurement import InboundShipment, InboundShipmentLine
from app.models.product import Brand, Product, ProductAttachment
from app.models.product_spec import ProductSpecifications
from app.models.resources import Attachment, AttachmentType
from app.services.error_handler import AppException
from app.services.lookup_resolver import LookupResolverService
from app.services.product_spec_search import (
    filter_specs,
    is_generic_free_term,
    search_specs,
    values_only,
)


class _UnrecognizedLabel(Exception):
    """A require value that resolved to nothing - reported, never swallowed.

    Same honesty class as an unrecognized free term: "your word mapped to no
    document type" must reach the customer as a clarify, not as a silent "none".

    ``extra`` merges straight into `resolve_product_set`'s own return dict on
    the miss (D2, AC-1313) - the certificate leg's only use today is
    ``schemes_on_file``, so a scheme miss can still name what IS on file.
    """

    def __init__(self, label: str, *, extra: dict[str, Any] | None = None):
        super().__init__(label)
        self.label = label
        self.extra = extra or {}


def _company_scoped_class_labels(db: Session) -> list[str]:
    """Every distinct class value a product IN THE CALLER'S OWN SCOPE carries
    (SEC-S2/AC-1335). `ProductSpecifications` carries no `company_id` of its
    own, so this joins `Product` (the scoped side) - the `do_orm_execute`
    listener's `with_loader_criteria` scopes ORM entities like `Product`, not
    a bare unjoined `ProductSpecifications` query, which would otherwise read
    every company's class labels. ORM only, never the raw `text()` SQL
    `product_class_signal.stored_class_labels` runs - that helper reads other,
    non-customer-facing callers and is out of scope here."""
    expr = ProductSpecifications.values["class"]["value"].astext
    rows = (
        db.query(expr)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(expr.isnot(None))
        .distinct()
        .all()
    )
    return sorted({row[0] for row in rows if row[0]})


def _nearest_class_labels(db: Session, term: str, *, limit: int = 3) -> list[str]:
    """Nearest class-label suggestions for an unrecognized term (AC-1320): every
    content word in `term` against the class labels products actually carry
    IN THE CALLER'S OWN SCOPE (`_company_scoped_class_labels`) - an exact word
    match first ("tap" out of "water tap" against the label "Tap"), then a
    fuzzy nearest-neighbour for a near-miss spelling. Order-stable, deduped,
    capped at `limit` - the reply names a few candidates, never the whole
    vocabulary.
    """
    import difflib

    from app.services.product_spec_search import _content_words

    labels = _company_scoped_class_labels(db)
    if not labels:
        return []
    lowered = {label.lower(): label for label in labels}
    found: list[str] = []
    for word in _content_words(term):
        if word in lowered:
            if lowered[word] not in found:
                found.append(lowered[word])
            continue
        for match in difflib.get_close_matches(word, lowered.keys(), n=limit, cutoff=0.6):
            label = lowered[match]
            if label not in found:
                found.append(label)
    return found[:limit]


def _common_class_labels(db: Session, *, limit: int = 3) -> list[str]:
    """The class labels the MOST products carry, most-common first (AC-1320's
    last-resort fallback): when a term names nothing `_nearest_class_labels`
    can read at all - no exact word match, no fuzzy near-miss - the reply still
    has to offer SOMETHING real ("Try a product type such as tap, wash basin,
    water closet."), never the contentless "Did you mean the product types I
    know?". SEC-S2/AC-1335: joins `Product` (the scoped side) so a company B
    class label never reaches a company A reply.
    """
    expr = ProductSpecifications.values["class"]["value"].astext
    rows = (
        db.query(expr, func.count())
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(expr.isnot(None))
        .group_by(expr)
        .order_by(func.count().desc())
        .limit(limit)
        .all()
    )
    return [row[0] for row in rows if row[0]]


def _lookup_resolve(db: Session, set_key: str, raw: str) -> str | None:
    """The lookup set's own resolved VALUE, or None on any miss.

    Covers both 404 shapes `LookupResolverService` raises: the set itself is
    missing (an install nobody has run the owner's data entry on yet), and the
    set exists but no option/keyword matches `raw`. Either way a leg reads this
    as "unrecognized", never a 500 (D3, AC-1314).
    """
    try:
        return LookupResolverService(db).resolve(set_key, raw).value
    except AppException:
        return None


def _attachment_type_row(db: Session, label: str) -> AttachmentType | None:
    return (
        db.query(AttachmentType)
        .filter(
            or_(
                func.lower(AttachmentType.code) == label.lower(),
                func.lower(AttachmentType.type_name) == label.lower(),
            )
        )
        .first()
    )


def _attachment_type_names_on_file(db: Session) -> list[str]:
    """Every PRODUCT-FACING `AttachmentType.type_name` on file, sorted (second
    console pass, AC-1329): only types that actually appear in
    `product_attachments` - never the whole `AttachmentType` table, which also
    carries internal document classes (Container Status, Complaint Document, a
    company's GRN/portal-submission attachments, ...) a customer never asks
    about. `AttachmentType` itself carries no company scope, but the join
    through `ProductAttachment`/`Attachment` (both `CompanyScopedMixin`) is
    itself company-scoped by the existing `do_orm_execute` listener, so this
    plain join is correct with no manual filter."""
    rows = (
        db.query(AttachmentType.type_name)
        .join(Attachment, Attachment.attachment_type_id == AttachmentType.id)
        .join(ProductAttachment, ProductAttachment.attachment_id == Attachment.id)
        .distinct()
        .all()
    )
    return sorted({str(row[0]).strip() for row in rows if row[0] and str(row[0]).strip()})


def _access_level_codes(db: Session, access_levels: list[str] | None) -> set[str] | None:
    """Caller-supplied access-level NAMES translated to canonical
    `contact_access_types.code` values - the same case-insensitive name -> code
    translation `references._apply_promotion_access_levels_filter` already
    uses. `None` when `access_levels` itself is empty/falsy (no restriction,
    every tier counts); an EMPTY set when every name failed to translate to a
    known code (a filter that matches nothing, never a silent no-op that lets
    every promotion back in)."""
    names_lower = {str(n).strip().lower() for n in (access_levels or []) if n and str(n).strip()}
    if not names_lower:
        return None
    rows = (
        db.query(ContactAccessType.code)
        .filter(func.lower(ContactAccessType.name).in_(names_lower))
        .all()
    )
    return {r[0] for r in rows}


def _leg_attachment_type(db: Session, value: Any, access_levels: list[str] | None = None) -> ColumnElement:
    """Has an attachment of the type the CUSTOMER NAMED - label in, not code.

    Resolution tries, in order: exact code / type_name (today, mirrors
    `_probe_attachment_type` so "technical drawing" works wherever it already
    works), then the `attachment_type_alias` lookup set (D2, AC-1312) - "photo",
    "picture", "gambar" reach whatever type the owner has aliased them to.
    Resolving server-side is what keeps new document classes out of the parser
    prompt: the parser ships four key names, the labels live in this table.

    R6/AC-1329 (console fix round 2): a miss here carries
    `attachment_types_on_file` - the product-facing AttachmentType names - so
    the reply can clarify the label as a DOCUMENT type ("I don't know 'photo'
    as a document type. Types I know: ...") rather than the product-type
    sentence, which answers the wrong question for a file label.
    """
    label = str(value or "").strip()
    row = _attachment_type_row(db, label)
    if row is None:
        aliased_label = _lookup_resolve(db, "attachment_type_alias", label)
        if aliased_label:
            row = _attachment_type_row(db, aliased_label)
    if row is None:
        raise _UnrecognizedLabel(
            label, extra={"attachment_types_on_file": _attachment_type_names_on_file(db)}
        )
    clause = exists().where(
        ProductAttachment.product_id == Product.id,
        ProductAttachment.company_id == Product.company_id,
        Attachment.id == ProductAttachment.attachment_id,
        Attachment.attachment_type_id == row.id,
    )
    # The echo shows what the label resolved TO, so n8n can render the CRM's
    # reading of the word back to the customer.
    clause._resolved_display = row.type_name or row.code  # type: ignore[attr-defined]
    return clause


def _schemes_on_file(db: Session) -> list[str]:
    """Every distinct scheme the register carries an ACTIVE certificate under,
    sorted, company-scoped (`Certificate` is `__company_shared__` - the
    `do_orm_execute` listener already ORs in the NULL-company shared rows, so a
    plain scoped query is correct here without any manual company_id filter)."""
    rows = db.query(Certificate.scheme).filter(Certificate.status == "active").distinct().all()
    return sorted({str(row[0]).strip() for row in rows if row[0] and str(row[0]).strip()})


def _leg_certificate(db: Session, value: Any, access_levels: list[str] | None = None) -> ColumnElement:
    """In the certificate register. Bare ``true`` = any active-register cert
    (decided); the object form narrows: ``scheme`` through the
    `certificate_scheme` lookup set (D2, AC-1313) then equality on the resolved
    value, ``validity_state: "valid"`` through the current revision's window -
    validity is DERIVED from revision dates, never stored (see the certificate
    model). A scheme with no matching option/keyword raises with
    `schemes_on_file` attached, so the reply can name what IS on file rather
    than answer a silent zero.

    Joins through ``Certificate`` because ``certificate_products`` has no
    company_id - the scoped side is what keeps the leg isolated per company.
    """
    conditions = [
        CertificateProduct.product_id == Product.id,
        Certificate.id == CertificateProduct.certificate_id,
        Certificate.status == "active",
    ]
    resolved_value = value
    if isinstance(value, dict):
        scheme = str(value.get("scheme") or "").strip()
        if scheme:
            # R5/AC-1328 (console fix round 2): the register's OWN active
            # spellings are tried FIRST, by case-insensitive equality - a
            # scheme word that IS a real spelling ("pps" against a register
            # carrying "PPS") must resolve even on a fresh install where the
            # owner has not yet entered it into the `certificate_scheme`
            # lookup set (D3's own empty-set default). The lookup set is the
            # ALIAS mechanism for a word that is NOT itself a register
            # spelling, not the only path to one that already is.
            schemes_on_file = _schemes_on_file(db)
            by_lower = {s.lower(): s for s in schemes_on_file}
            resolved_scheme = by_lower.get(scheme.lower())
            if resolved_scheme is None:
                resolved_scheme = _lookup_resolve(db, "certificate_scheme", scheme)
            if resolved_scheme is None:
                raise _UnrecognizedLabel(scheme, extra={"schemes_on_file": schemes_on_file})
            conditions.append(func.lower(Certificate.scheme) == resolved_scheme.lower())
            resolved_value = {**value, "scheme": resolved_scheme}
        if str(value.get("validity_state") or "").strip().lower() == "valid":
            conditions.extend(
                [
                    CertificateRevision.id == Certificate.current_revision_id,
                    or_(
                        CertificateRevision.valid_until.is_(None),
                        CertificateRevision.valid_until >= func.current_date(),
                    ),
                ]
            )
    clause = exists().where(*conditions)
    if resolved_value is not value:
        clause._resolved_display = resolved_value  # type: ignore[attr-defined]
    return clause


def _leg_promotion(db: Session, value: Any, access_levels: list[str] | None = None) -> ColumnElement:
    """Member of an active promotion: switched on AND inside its date window.

    REV-B1/AC-1310 (third console pass): `with_loader_criteria` (the
    `do_orm_execute` listener's own scoping mechanism) filters ORM entities,
    not a bare `exists().where(...)` subquery, so this EXISTS needs its own
    explicit same-company predicate against `Promotion` - the parent side
    `PromotionProduct` joins through - or a foreign-company promotion linked
    to one of the caller's products still counts.

    SEC-S1/AC-1334: also intersects `Promotion.access_levels` with the
    caller's OWN tier(s) - unfiltered, `qualifying_total` and the named
    products could disclose a tier-restricted promotion the contact cannot
    actually see. `access_levels=None` (or empty) is no restriction; a name
    that fails to translate to any known code is a filter that matches
    nothing, never a silent no-op.
    """
    conditions = [
        PromotionProduct.product_id == Product.id,
        Promotion.id == PromotionProduct.promotion_id,
        Promotion.company_id == Product.company_id,
        Promotion.is_active.is_(True),
        or_(Promotion.start_date.is_(None), Promotion.start_date <= func.current_date()),
        or_(Promotion.end_date.is_(None), Promotion.end_date >= func.current_date()),
    ]
    allowed_codes = _access_level_codes(db, access_levels)
    if allowed_codes is not None:
        conditions.append(
            Promotion.access_levels.op("?|")(_cast(list(allowed_codes), _ARRAY(_String)))
        )
    return exists().where(*conditions)


def _leg_stock(db: Session, value: Any, access_levels: list[str] | None = None) -> ColumnElement:
    """Plain on-hand > 0. Deliberately NOT the MCP's
    ``exclude_zero_system_adjustment`` semantics - that filter answers a
    different question ("hide rows an adjustment zeroed"), this one answers
    "is there any stock at all".

    REV-B1/AC-1310: an explicit `Stock.company_id == Product.company_id`
    predicate - `with_loader_criteria` does not reach a bare `exists()`
    subquery, so without this a `Stock` row stamped to another company still
    counts once its `product_id` matches.
    """
    return exists().where(
        Stock.product_id == Product.id,
        Stock.company_id == Product.company_id,
        Stock.quantity_on_hand > 0,
    )


def _leg_incoming(db: Session, value: Any, access_levels: list[str] | None = None) -> ColumnElement:
    """An open shipment line: shipped minus received is still positive AND the
    shipment has not actually arrived yet (D1, AC-1311). Joins through
    `InboundShipment` for the arrival check AND for company scope (REV-B1/
    AC-1310) - `with_loader_criteria` does not reach a bare `exists()`
    subquery, so an explicit `InboundShipment.company_id == Product.company_id`
    predicate is required; without it a foreign-stamped open shipment line
    still counts (the reviewer's own kill test)."""
    return exists().where(
        InboundShipmentLine.product_id == Product.id,
        InboundShipment.id == InboundShipmentLine.shipment_id,
        InboundShipment.company_id == Product.company_id,
        (
            func.coalesce(InboundShipmentLine.quantity_shipped, 0)
            - func.coalesce(InboundShipmentLine.quantity_received, 0)
        )
        > 0,
        InboundShipment.actual_arrival_date.is_(None),
    )


# One entry per domain. A new domain lands as one function + one line here + one
# noun in the n8n parser - never as another inline block in references.py.
REQUIRE_LEGS: dict[str, Callable[..., ColumnElement]] = {
    "attachment_type": _leg_attachment_type,
    "certificate": _leg_certificate,
    "promotion": _leg_promotion,
    "stock": _leg_stock,
    "incoming": _leg_incoming,
}


def resolve_product_set(
    db: Session,
    *,
    require: dict,
    specs: list[dict] | None = None,
    free_terms: list[str] | None = None,
    scope_terms: list[str] | None = None,
    limit: int | None = None,
    product_ids: list[str] | None = None,
    brand: str | None = None,
    access_levels: list[str] | None = None,
) -> dict:
    """(described set) ∩ (require legs), with an honest count.

    The described set is the UNION of ``product_ids`` (ids LOOKUP already
    matched by name or code prefix) and the ``class`` / ``product_type`` /
    ``brand`` membership `filter_specs` derives from ``specs`` / ``free_terms``
    / ``scope_terms`` - attribute-first asks, work item C3, AC-1306/1308. Either
    alone is enough to describe the set; when both are given a product only
    needs ONE of them. ``brand`` scopes the WHOLE set on top of that union
    (D3): it reads `Product.brand_id` live, not the spec-derived echo, so it is
    correct even when a product's brand changed since its spec row was last
    derived.

    ``scope_terms`` (C2 repair) is membership-ONLY - a caller-derived class word
    ("tap" out of "which tap has cert") that must scope the set but must NEVER
    also drive `search_specs` ranking: a product that qualifies purely through
    `product_ids` and carries no `ProductSpecifications` row at all (routine for
    a LOOKUP-only match) would otherwise be silently evicted by the ranker's own
    evidence floor the moment ANY free term made `rank_by_words` true, even
    though the term named nothing about that specific product's attributes.
    ``free_terms`` keeps its old, dual role (membership AND ranking) for a
    caller that supplies real descriptive text of its own.

    Returns ``{candidates, qualifying_total, truncated, unrecognized_terms,
    require}`` - candidates are ranker-shaped (stage 2 runs `search_specs` over
    the qualifying ids only), ``require`` is the echo with ``attachment_type``
    as-resolved.

    ``qualifying_total`` counts DISTINCT VARIANT FAMILIES, not rows: five
    finishes of one sink are one product to the person asking, and that is also
    exactly what the ranker's display collapse shows. A row count would say "80
    faucets" where 40 models exist.

    ``access_levels`` (SEC-S1/AC-1334): the caller's own tier NAMES, threaded
    into every leg (only `_leg_promotion` reads them today) so a tier the
    contact cannot see never counts toward `qualifying_total` nor names its
    product. `None` is no restriction - the caller is the resolve endpoint
    itself, which always passes its own `payload.access_levels`.
    """
    unknown = sorted(set(require) - set(REQUIRE_LEGS))
    if unknown:
        raise AppException(
            status_code=422,
            message=f"Unknown require key(s): {', '.join(unknown)}",
            code="UNKNOWN_REQUIRE_KEY",
        )

    scoping_terms = [*(free_terms or []), *(scope_terms or [])]
    verdict = filter_specs(db, specs=specs, free_terms=scoping_terms)
    unrecognized = list(verdict["unrecognized_terms"])

    require_echo: dict[str, Any] = {}
    legs: list[ColumnElement] = []
    for key, value in require.items():
        if value in (None, False):
            continue
        try:
            clause = REQUIRE_LEGS[key](db, value, access_levels=access_levels)
        except _UnrecognizedLabel as miss:
            unrecognized.append(miss.label)
            require_echo[key] = miss.label
            # A predicate the CRM could not read qualifies NOTHING - an honest
            # zero plus the unrecognized label is a clarify on the n8n side; a
            # leg silently skipped would be a wrong count presented as truth.
            return {
                "candidates": [],
                "qualifying_total": 0,
                "truncated": False,
                "unrecognized_terms": unrecognized,
                "require": require_echo | {k: v for k, v in require.items() if k != key},
                **miss.extra,
            }
        require_echo[key] = getattr(clause, "_resolved_display", value)
        legs.append(clause)

    # A free term whose every content word is generic ("item", "product",
    # "anything") named NOTHING about what the customer means - "no description
    # given", not "described something unreadable" (AC-1302's honest zero stays
    # for a REAL word like "water tap" that still binds nothing).
    described_given = (
        any(t and t.strip() and not is_generic_free_term(t) for t in scoping_terms)
        or bool(specs)
    )
    # What the caller has to RANK against, not merely what defines membership.
    # `specs`-only calls (structural bindings, no customer words) fall to the
    # deterministic listing below - `search_specs` drops any candidate with no
    # positive evidence, which would silently evict a product that only
    # qualified through `product_ids`, the OTHER half of the union.
    rank_by_words = bool([t for t in (free_terms or []) if t and t.strip()])
    if verdict["clause"] is None and described_given and not product_ids:
        # Words were given and none named a class/product_type/brand, and there
        # is no id set either: the described set is undefined. Answering the
        # predicate over the WHOLE catalogue would be an answer to a question
        # nobody asked.
        # AC-1320/F2: nearest class-label suggestions for the FIRST unrecognized
        # term, so the reply can offer a real "did you mean" instead of naming
        # nothing at all. When NOTHING is near enough either (no exact word
        # match, no fuzzy near-miss), the fallback is the catalogue's own most
        # common class labels under a DIFFERENT sentence template
        # ("common_class_labels", never "suggestions") - the two carry
        # different copy in `answer.not_found_error_message` and must not be
        # conflated into one key.
        nearest = _nearest_class_labels(db, unrecognized[0]) if unrecognized else []
        zero_result: dict[str, Any] = {
            "candidates": [],
            "qualifying_total": 0,
            "truncated": False,
            "unrecognized_terms": unrecognized,
            "require": require_echo,
            "class_labels": verdict["class_labels"],
        }
        if nearest:
            zero_result["suggestions"] = nearest
        elif unrecognized:
            common = _common_class_labels(db)
            if common:
                zero_result["common_class_labels"] = common
        return zero_result

    parent = aliased(Product)
    family = func.coalesce(parent.product_code, Product.product_code)

    def _base(query):
        query = (
            query.select_from(Product)
            .outerjoin(parent, parent.id == Product.variant_of_id)
            .filter(Product.is_active.is_(True), *legs)
        )
        described: list[ColumnElement] = []
        if product_ids:
            described.append(Product.id.in_(list(product_ids)))
        if verdict["clause"] is not None:
            described.append(
                exists().where(
                    ProductSpecifications.product_id == Product.id, verdict["clause"]
                )
            )
        if described:
            query = query.filter(described[0] if len(described) == 1 else or_(*described))
        if brand:
            query = query.join(Brand, Brand.id == Product.brand_id).filter(
                func.lower(Brand.brand_name) == brand.strip().lower()
            )
        return query

    qualifying_total = _base(db.query(func.count(func.distinct(family)))).scalar() or 0

    candidates: list[dict] = []
    if qualifying_total:
        qualifying_ids = [row[0] for row in _base(db.query(Product.id)).all()]
        if rank_by_words:
            # Stage 2: rank INSIDE the qualifying set. Floor 0 on purpose - the
            # floor exists to stop confident nonsense, and membership has
            # already established these products answer the question. Dropped
            # numeric entries re-enter here as boosts, so "1000mm" still orders
            # the shortlist even though it never defined it.
            found = search_specs(
                db,
                specs=specs,
                free_terms=free_terms,
                product_ids=qualifying_ids,
                limit=limit,
                floor=0.0,
            )
            candidates = found["candidates"]
        else:
            # require-only ("what products have certs"): nothing to rank BY, so
            # the shortlist is deterministic - one row per family, by code.
            rows = (
                _base(
                    db.query(
                        Product.id,
                        Product.product_code,
                        Product.product_name,
                        family.label("family"),
                    )
                )
                .order_by(family, Product.product_code)
                .distinct(family)
                .limit(limit or 15)
                .all()
            )
            # The spec block for the rows actually shown, in ONE query. A row that
            # reached the customer through a predicate rather than a description
            # is still a product they will ask questions about, and answering
            # "here are five with certs" with no values to tell them apart is the
            # same dead end `display.specifications` exists to close.
            spec_rows = (
                db.query(ProductSpecifications)
                .filter(ProductSpecifications.product_id.in_([str(r[0]) for r in rows]))
                .all()
                if rows
                else []
            )
            spec_by_product = {str(row.product_id): row for row in spec_rows}
            candidates = []
            for product_id, code, name, _family in rows:
                spec_row = spec_by_product.get(str(product_id))
                values = spec_row.values if spec_row is not None else None
                candidates.append(
                    {
                        "product_id": str(product_id),
                        "product_code": code,
                        "summary": name,
                        "class": ((values or {}).get("class") or {}).get("value"),
                        # None, never {}: nothing was recorded for this product, and
                        # an empty block would read as "recorded, and empty".
                        "specifications": values_only(values) if values is not None else None,
                        "matched_specs": [],
                        # No customer words were scored here, so nothing was
                        # preferred either. Present so the shape matches a ranked row.
                        "preferred_specs": [],
                        "score": 0.0,
                        "is_discontinued": False,
                    }
                )

    # E2/AC-1316: the described set's own class label(s), for the header's noun
    # (`answer.set_noun_for`). Unioned with what the qualifying candidates
    # THEMSELVES carry, not `verdict["class_labels"]` alone - a set scoped
    # purely through `product_ids` (LOOKUP matched "tap" against a product
    # CODE, never through `filter_specs`' own membership binding) still has a
    # real class the header should say, and the candidates already carry it.
    class_labels = set(verdict["class_labels"])
    for row in candidates:
        value = row.get("class")
        if value:
            class_labels.add(str(value))
    if not class_labels:
        # R3 (console fix round 2): a described set whose class derivation
        # reads nothing (a bidet's own class comes from the description's
        # TRAILING noun - "SPRAY", not "BIDET" - so it stays unmapped) still
        # has a real noun to say: the candidates' own `product_type`
        # ("bidet"), never the generic "products" this would otherwise fall
        # back to. Only tried when class named NOTHING at all, so a real
        # class always wins over this fallback.
        for row in candidates:
            # REV-S5: a local named `specs` here shadowed the function's own
            # `specs: list[dict] | None` parameter for the rest of the loop body.
            row_specs = row.get("specifications") or {}
            value = row_specs.get("product_type") if isinstance(row_specs, dict) else None
            if value:
                class_labels.add(str(value))

    return {
        "candidates": candidates,
        "qualifying_total": int(qualifying_total),
        "truncated": int(qualifying_total) > len(candidates),
        "unrecognized_terms": unrecognized,
        "require": require_echo,
        "class_labels": sorted(class_labels),
    }
