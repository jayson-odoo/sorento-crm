"""The ``product`` fact source for the shared rule engine (AC-F3).

A collection's `conditions_json` is evaluated by ``app/rule_engine`` - the SAME
evaluator the promo-expiry automation uses. This module only tells that engine
which product fields a rule may speak about; it does not evaluate anything.

That constraint is the point. A bespoke product filter would be a second
evaluator with its own operator semantics, its own null handling and its own
bugs, and the two would drift the first time either was touched. Registering
facts here means a Designer's collection rule and an automation rule behave
identically, and the RuleBuilder UI already knows how to render both.

Facts are a WHITELIST, never a model reflection: exposing every column would put
`cost_price` in front of anyone who can build a collection.
"""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.rule_engine.registry import (
    FactDef,
    infer_facts,
    register_fact_source,
    resolve_facts,
)

SOURCE = "product"


def _category_name(product: Any, db: Session) -> Any:
    category = getattr(product, "category", None)
    return getattr(category, "category_name", None) if category else None


def _brand_name(product: Any, db: Session) -> Any:
    brand = getattr(product, "brand", None)
    return getattr(brand, "brand_name", None) if brand else None


def _access_levels(product: Any, db: Session) -> List[str]:
    levels = getattr(product, "access_levels", None)
    return list(levels) if isinstance(levels, list) else []


def _category_options(db: Session, current_user: Any) -> List[Dict[str, str]]:
    from app.models.product import ProductCategory

    rows = (
        db.query(ProductCategory.category_name)
        .order_by(ProductCategory.category_name)
        .all()
    )
    return [{"value": name, "label": name} for (name,) in rows if name]


def _brand_options(db: Session, current_user: Any) -> List[Dict[str, str]]:
    from app.models.product import Brand

    rows = db.query(Brand.brand_name).order_by(Brand.brand_name).all()
    return [{"value": name, "label": name} for (name,) in rows if name]


def register_product_facts() -> None:
    """Idempotent - ``register_fact_source`` overwrites by name."""
    from app.models.product import Product

    register_fact_source(
        SOURCE,
        "Product",
        [
            # Resolved to NAMES rather than ids: a rule is authored and read by
            # people, and a UUID in a condition is unreadable and unmaintainable.
            FactDef(
                key="product.category",
                label="Category",
                type="enum",
                resolver=_category_name,
                options=_category_options,
            ),
            FactDef(
                key="product.brand",
                label="Brand",
                type="enum",
                resolver=_brand_name,
                options=_brand_options,
            ),
            FactDef(
                key="product.accessLevels",
                label="Access levels",
                type="list",
                resolver=_access_levels,
            ),
            *infer_facts(
                Product,
                [
                    "product_code",
                    "product_name",
                    "item_type",
                    "list_price",
                    "currency",
                    "warranty_months",
                    "is_active",
                    "is_discontinued",
                ],
                prefix="product",
                overrides={
                    "product_code": {"label": "Product code"},
                    "product_name": {"label": "Product name"},
                    "item_type": {"label": "Item type"},
                    "list_price": {"label": "List price"},
                    "warranty_months": {"label": "Warranty (months)"},
                    "is_active": {"label": "Active"},
                    "is_discontinued": {"label": "Discontinued"},
                },
            ),
        ],
    )


def product_facts(product: Any, db: Session, only_keys: Any = None) -> Dict[str, Any]:
    """Materialise the registered facts for one product, ready for
    ``rule_engine.evaluate``.

    Goes through the registry's own ``resolve_facts`` rather than reading the
    resolvers directly: that is where a raising resolver becomes None instead of
    a 500, so a stale rule referring to a since-changed field degrades rather
    than taking the page down with it.
    """
    register_product_facts()
    return resolve_facts(db, {SOURCE: product}, only_keys=only_keys)
