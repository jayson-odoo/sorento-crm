"""Shape B: a described product set intersected with a domain predicate.

"What faucets have certs" cannot be answered by resolving a top-K list and joining
ids across the wire: whenever the qualifying products fall outside K, the answer is
a false "none". So the intersection happens HERE, over the full company-scoped
catalogue — membership and the count are SQL, and the ranker only orders the
products that already qualify (`search_specs(product_ids=...)`).

Extending to a new domain is one function and one `REQUIRE_LEGS` entry — the legs
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

from sqlalchemy import exists, func, or_
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql import ColumnElement

from app.models.certificate import Certificate, CertificateProduct, CertificateRevision
from app.models.inventory import Stock
from app.models.marketing import Promotion, PromotionProduct
from app.models.product import Product, ProductAttachment
from app.models.product_spec import ProductSpecifications
from app.models.resources import Attachment, AttachmentType
from app.services.error_handler import AppException
from app.services.product_spec_search import filter_specs, search_specs


class _UnrecognizedLabel(Exception):
    """A require value that resolved to nothing — reported, never swallowed.

    Same honesty class as an unrecognized free term: "your word mapped to no
    document type" must reach the customer as a clarify, not as a silent "none".
    """

    def __init__(self, label: str):
        super().__init__(label)
        self.label = label


def _leg_attachment_type(db: Session, value: Any) -> ColumnElement:
    """Has an attachment of the type the CUSTOMER NAMED — label in, not code.

    Resolution mirrors `_probe_attachment_type` (exact case-insensitive on code OR
    type_name) so "technical drawing" works wherever it already works. Resolving
    server-side is what keeps new document classes out of the parser prompt: the
    parser ships four key names, the labels live in this table.
    """
    label = str(value or "").strip()
    row = (
        db.query(AttachmentType)
        .filter(
            or_(
                func.lower(AttachmentType.code) == label.lower(),
                func.lower(AttachmentType.type_name) == label.lower(),
            )
        )
        .first()
    )
    if row is None:
        raise _UnrecognizedLabel(label)
    clause = exists().where(
        ProductAttachment.product_id == Product.id,
        Attachment.id == ProductAttachment.attachment_id,
        Attachment.attachment_type_id == row.id,
    )
    # The echo shows what the label resolved TO, so n8n can render the CRM's
    # reading of the word back to the customer.
    clause._resolved_display = row.type_name or row.code  # type: ignore[attr-defined]
    return clause


def _leg_certificate(db: Session, value: Any) -> ColumnElement:
    """In the certificate register. Bare ``true`` = any active-register cert
    (decided); the object form narrows: ``scheme`` by equality,
    ``validity_state: "valid"`` through the current revision's window — validity
    is DERIVED from revision dates, never stored (see the certificate model).

    Joins through ``Certificate`` because ``certificate_products`` has no
    company_id — the scoped side is what keeps the leg isolated per company.
    """
    conditions = [
        CertificateProduct.product_id == Product.id,
        Certificate.id == CertificateProduct.certificate_id,
        Certificate.status == "active",
    ]
    if isinstance(value, dict):
        scheme = str(value.get("scheme") or "").strip()
        if scheme:
            conditions.append(func.lower(Certificate.scheme) == scheme.lower())
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
    return exists().where(*conditions)


def _leg_promotion(db: Session, value: Any) -> ColumnElement:
    """Member of an active promotion: switched on AND inside its date window."""
    return exists().where(
        PromotionProduct.product_id == Product.id,
        Promotion.id == PromotionProduct.promotion_id,
        Promotion.is_active.is_(True),
        or_(Promotion.start_date.is_(None), Promotion.start_date <= func.current_date()),
        or_(Promotion.end_date.is_(None), Promotion.end_date >= func.current_date()),
    )


def _leg_stock(db: Session, value: Any) -> ColumnElement:
    """Plain on-hand > 0. Deliberately NOT the MCP's
    ``exclude_zero_system_adjustment`` semantics — that filter answers a
    different question ("hide rows an adjustment zeroed"), this one answers
    "is there any stock at all".
    """
    return exists().where(Stock.product_id == Product.id, Stock.quantity_on_hand > 0)


# One entry per domain. A new domain lands as one function + one line here + one
# noun in the n8n parser — never as another inline block in references.py.
REQUIRE_LEGS: dict[str, Callable[[Session, Any], ColumnElement]] = {
    "attachment_type": _leg_attachment_type,
    "certificate": _leg_certificate,
    "promotion": _leg_promotion,
    "stock": _leg_stock,
}


def resolve_product_set(
    db: Session,
    *,
    require: dict,
    specs: list[dict] | None = None,
    free_terms: list[str] | None = None,
    limit: int | None = None,
) -> dict:
    """(described set) ∩ (require legs), with an honest count.

    Returns ``{candidates, qualifying_total, truncated, unrecognized_terms,
    require}`` — candidates are ranker-shaped (stage 2 runs `search_specs` over
    the qualifying ids only), ``require`` is the echo with ``attachment_type``
    as-resolved.

    ``qualifying_total`` counts DISTINCT VARIANT FAMILIES, not rows: five
    finishes of one sink are one product to the person asking, and that is also
    exactly what the ranker's display collapse shows. A row count would say "80
    faucets" where 40 models exist.
    """
    unknown = sorted(set(require) - set(REQUIRE_LEGS))
    if unknown:
        raise AppException(
            status_code=422,
            message=f"Unknown require key(s): {', '.join(unknown)}",
            code="UNKNOWN_REQUIRE_KEY",
        )

    verdict = filter_specs(db, specs=specs, free_terms=free_terms)
    unrecognized = list(verdict["unrecognized_terms"])

    require_echo: dict[str, Any] = {}
    legs: list[ColumnElement] = []
    for key, value in require.items():
        if value in (None, False):
            continue
        try:
            clause = REQUIRE_LEGS[key](db, value)
        except _UnrecognizedLabel as miss:
            unrecognized.append(miss.label)
            require_echo[key] = miss.label
            # A predicate the CRM could not read qualifies NOTHING — an honest
            # zero plus the unrecognized label is a clarify on the n8n side; a
            # leg silently skipped would be a wrong count presented as truth.
            return {
                "candidates": [],
                "qualifying_total": 0,
                "truncated": False,
                "unrecognized_terms": unrecognized,
                "require": require_echo | {k: v for k, v in require.items() if k != key},
            }
        require_echo[key] = getattr(clause, "_resolved_display", value)
        legs.append(clause)

    terms_given = bool([t for t in (free_terms or []) if t and t.strip()]) or bool(specs)
    if verdict["clause"] is None and terms_given:
        # Words were given and none named a class: the described set is
        # undefined. Answering the predicate over the WHOLE catalogue would be
        # an answer to a question nobody asked.
        return {
            "candidates": [],
            "qualifying_total": 0,
            "truncated": False,
            "unrecognized_terms": unrecognized,
            "require": require_echo,
        }

    parent = aliased(Product)
    family = func.coalesce(parent.product_code, Product.product_code)

    def _base(query):
        query = (
            query.select_from(Product)
            .outerjoin(parent, parent.id == Product.variant_of_id)
            .filter(Product.is_active.is_(True), *legs)
        )
        if verdict["clause"] is not None:
            query = query.join(
                ProductSpecifications, ProductSpecifications.product_id == Product.id
            ).filter(verdict["clause"])
        return query

    qualifying_total = _base(db.query(func.count(func.distinct(family)))).scalar() or 0

    candidates: list[dict] = []
    if qualifying_total:
        qualifying_ids = [row[0] for row in _base(db.query(Product.id)).all()]
        if terms_given:
            # Stage 2: rank INSIDE the qualifying set. Floor 0 on purpose — the
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
            # the shortlist is deterministic — one row per family, by code.
            rows = (
                _base(db.query(Product.product_code, Product.product_name, family.label("family")))
                .order_by(family, Product.product_code)
                .distinct(family)
                .limit(limit or 15)
                .all()
            )
            candidates = [
                {
                    "product_id": str(
                        db.query(Product.id).filter(Product.product_code == code).scalar()
                    ),
                    "product_code": code,
                    "summary": name,
                    "class": None,
                    "matched_specs": [],
                    "score": 0.0,
                    "is_discontinued": False,
                }
                for code, name, _family in rows
            ]

    return {
        "candidates": candidates,
        "qualifying_total": int(qualifying_total),
        "truncated": int(qualifying_total) > len(candidates),
        "unrecognized_terms": unrecognized,
        "require": require_echo,
    }
