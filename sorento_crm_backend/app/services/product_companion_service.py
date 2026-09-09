""""Supplied with" companion rule CRUD (PLAN-scm-supplied-with-companions.md S4).

Company scope is NOT an argument - every query is ORM, so `do_orm_execute` applies the
caller's scope (UAC A7): a rule belonging to another company simply is not returned.

The route contract (frontend already mocks it, Phase 1, `productCompanionService.ts`):

    GET    /api/v1/master-data/product-companion-rules?companion_product_id={id}
    GET    /api/v1/master-data/product-companion-rules?host_product_id={id}
    POST   /api/v1/master-data/product-companion-rules
    DELETE /api/v1/master-data/product-companion-rules/{id}
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.product import Product
from app.models.product_companion import ProductCompanionRule, ProductCompanionRuleHost
from app.services.error_handler import AppException, handle_conflict, handle_not_found
from app.services.uuid_path_param import UUID_PATTERN

_UUID_RE = re.compile(UUID_PATTERN)


def _require_uuid_shape(value: Any, *, field: str) -> str:
    """422, not 404 - this is a body field failing validation, not a path id that
    reads as a guaranteed-missing row (review round 1 item 9)."""
    s = str(value or "").strip()
    if not _UUID_RE.match(s):
        raise AppException(status_code=422, message=f"{field} must be a valid id")
    return s.lower()


def _serialize(rule: ProductCompanionRule) -> Dict[str, Any]:
    companion = rule.companion_product
    supplier = rule.supplier
    return {
        "id": rule.id,
        "companion_product_id": rule.companion_product_id,
        "companion_item_code": companion.product_code if companion else None,
        "companion_product_name": companion.product_name if companion else None,
        "supplier_id": rule.supplier_id,
        "supplier_code": supplier.supplier_code if supplier else None,
        "supplier_name": supplier.supplier_name if supplier else None,
        "ratio": rule.ratio,
        "is_active": rule.is_active,
        "hosts": [
            {
                "product_id": host.host_product_id,
                "item_code": host.host_product.product_code if host.host_product else None,
                "product_name": (
                    host.host_product.product_name if host.host_product else None
                ),
            }
            for host in rule.hosts
        ],
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


class ProductCompanionService:
    def __init__(self, db: Session):
        self.db = db

    def _query(self):
        return self.db.query(ProductCompanionRule).options(
            joinedload(ProductCompanionRule.companion_product),
            joinedload(ProductCompanionRule.supplier),
            joinedload(ProductCompanionRule.hosts).joinedload(
                ProductCompanionRuleHost.host_product
            ),
        )

    def list_for_companion(self, companion_product_id: str) -> List[Dict[str, Any]]:
        rows = (
            self._query()
            .filter(ProductCompanionRule.companion_product_id == companion_product_id)
            .order_by(ProductCompanionRule.created_at.asc())
            .all()
        )
        return [_serialize(rule) for rule in rows]

    def list_for_host(self, host_product_id: str) -> List[Dict[str, Any]]:
        """Every rule naming this product as ONE of its hosts - a pair rule (SC-RL with
        X + Y) is returned by BOTH hosts' own queries, each time naming every host on
        it, not only the one asked about (UAC A5)."""
        rows = (
            self._query()
            .join(ProductCompanionRuleHost, ProductCompanionRuleHost.rule_id == ProductCompanionRule.id)
            .filter(ProductCompanionRuleHost.host_product_id == host_product_id)
            .order_by(ProductCompanionRule.created_at.asc())
            .all()
        )
        return [_serialize(rule) for rule in rows]

    def create(self, payload: Dict[str, Any], *, created_by: Optional[str]) -> Dict[str, Any]:
        companion_product_id = payload.get("companion_product_id")
        host_product_ids = list(payload.get("host_product_ids") or [])
        supplier_id = payload.get("supplier_id")
        ratio = payload.get("ratio", 1)

        if not companion_product_id:
            raise AppException(status_code=422, message="A companion product is required")
        if not host_product_ids:
            raise AppException(
                status_code=422, message="At least one host product is required"
            )
        companion_product_id = _require_uuid_shape(
            companion_product_id, field="companion_product_id"
        )
        host_product_ids = [
            _require_uuid_shape(hid, field="host_product_ids") for hid in host_product_ids
        ]
        if companion_product_id in host_product_ids:
            raise AppException(
                status_code=422,
                message="A product cannot be its own host - the companion and every host must differ",
            )
        try:
            ratio_dec = Decimal(str(ratio))
        except Exception as exc:  # noqa: BLE001 - surfaced as a plain validation message
            raise AppException(status_code=422, message="Ratio must be a number") from exc
        if ratio_dec <= 0:
            raise AppException(status_code=422, message="Ratio must be greater than zero")

        # Every id resolved through a COMPANY-SCOPED query (the class docstring's own
        # rule: no explicit company_id argument, `do_orm_execute` applies it) - a well-
        # formed UUID naming a product in another company reads exactly like one that
        # does not exist at all, which is the correct answer (never confirm a
        # cross-company id is real).
        wanted_ids = {companion_product_id, *host_product_ids}
        found_ids = {
            pid for (pid,) in self.db.query(Product.id).filter(Product.id.in_(wanted_ids)).all()
        }
        missing = wanted_ids - found_ids
        if missing:
            raise handle_not_found("Product", next(iter(missing)))

        self._reject_duplicate(companion_product_id, supplier_id)

        rule = ProductCompanionRule(
            companion_product_id=companion_product_id,
            supplier_id=supplier_id or None,
            ratio=ratio_dec,
            is_active=True,
            created_by=created_by,
        )
        self.db.add(rule)
        self.db.flush()
        for host_product_id in host_product_ids:
            self.db.add(
                ProductCompanionRuleHost(rule_id=rule.id, host_product_id=host_product_id)
            )
        self.db.flush()
        self.db.commit()
        rule = self._query().filter(ProductCompanionRule.id == rule.id).one()
        return _serialize(rule)

    def delete(self, rule_id: str) -> None:
        """Hard delete, per the CRUD standard (UAC A3). Hosts cascade; products do not."""
        rule = self.db.query(ProductCompanionRule).filter(
            ProductCompanionRule.id == rule_id
        ).first()
        if rule is None:
            raise handle_not_found("Rule", rule_id)
        self.db.delete(rule)
        self.db.commit()

    # ------------------------------------------------------------------- internals

    def _reject_duplicate(self, companion_product_id: str, supplier_id: Optional[str]) -> None:
        """UAC A4: the same companion + supplier scope (including two "any supplier"
        rules) is a 409 naming the existing rule, never a silent refusal."""
        supplier_predicate = (
            ProductCompanionRule.supplier_id == supplier_id
            if supplier_id
            else ProductCompanionRule.supplier_id.is_(None)
        )
        existing = (
            self._query()
            .filter(
                ProductCompanionRule.companion_product_id == companion_product_id,
                supplier_predicate,
            )
            .first()
        )
        if existing is None:
            return
        supplier_name = existing.supplier.supplier_name if existing.supplier else "any supplier"
        host_codes = " + ".join(
            host.host_product.product_code
            for host in existing.hosts
            if host.host_product is not None
        )
        companion_code = (
            existing.companion_product.product_code if existing.companion_product else ""
        )
        raise handle_conflict(
            f"{companion_code} already has a rule for {supplier_name} "
            f"(included with {host_codes})."
        )


def bundled_with_item_codes_map(
    db: Session, *, company_id: str, companion_item_codes: Iterable[str]
) -> Dict[str, List[str]]:
    """Every bundled companion's rule, resolved in TWO queries for a whole PAGE of rows
    rather than two PER bundled row (review round 1 item 10 - `_bundled_po_number` and
    `_serialize`/`serialize_rows` used to ask the database once per row for a fact that
    is the same for every row naming the same companion).

    Keyed by companion item code; the value is that companion's active rule's hosts, in
    rule order (UAC D10 - "Included with 2 items"). A companion with no active rule
    (deleted or deactivated since the row was derived, B16/B17) is simply absent from
    the map - `resolve_bundled_item_codes` below falls back to naming just the anchor
    for that case, exactly as the per-row version used to.
    """
    codes = {code for code in companion_item_codes if code}
    if not codes:
        return {}
    id_to_code = dict(
        db.query(Product.id, Product.product_code).filter(
            Product.company_id == company_id, Product.product_code.in_(codes)
        )
    )
    if not id_to_code:
        return {}
    rules = (
        db.query(ProductCompanionRule)
        .options(
            joinedload(ProductCompanionRule.hosts).joinedload(
                ProductCompanionRuleHost.host_product
            )
        )
        .filter(
            ProductCompanionRule.company_id == company_id,
            ProductCompanionRule.companion_product_id.in_(id_to_code.keys()),
            ProductCompanionRule.is_active.is_(True),
        )
        .all()
    )
    result: Dict[str, List[str]] = {}
    for rule in rules:
        companion_code = id_to_code.get(rule.companion_product_id)
        if not companion_code:
            continue
        host_codes = [
            host.host_product.product_code
            for host in sorted(rule.hosts, key=lambda h: h.seq)
            if host.host_product is not None
        ]
        if host_codes:
            result[companion_code] = host_codes
    return result


def resolve_bundled_item_codes(
    bundle_map: Dict[str, List[str]],
    *,
    companion_item_code: str,
    anchor_item_code: Optional[str],
) -> List[str]:
    """Pure lookup against a map `bundled_with_item_codes_map` already built for the
    whole page - no database access here at all (review round 1 item 10).

    Best-effort, same as the map builder's own docstring: an anchor whose rule is not
    in the map falls back to naming just the anchor's own code, so a reader never
    renders an empty "Included with" line.
    """
    if not anchor_item_code:
        return []
    codes = bundle_map.get(companion_item_code)
    if codes and codes[0] == anchor_item_code:
        return codes
    return [anchor_item_code]
