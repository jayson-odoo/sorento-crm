"""The product spec words of a report ask (lane REPORT-UNIFY, slice 1;
`documentation/plans/reports/PLAN-report-unify-27oct.md` section 1).

`resolve` turns the route's `key:value` terms into the ids of the products that hold them, through
`product_spec_search.membership_clause` (the clause spec search already filters with: the values of
one key ORed, different keys ANDed). A term that cannot narrow is returned under `not_applied`,
never guessed at. `fold_by_key` groups a product ranking by one key's value.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.models.product import Product
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry

NOT_STATED = "Not stated"

_NUMBER = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*([^\d\s].*)?$")
_YES, _NO = {"yes", "true"}, {"no", "false"}


def registry(db: Session) -> dict[str, ProductSpecRegistry]:
    return {row.spec_key: row for row in db.query(ProductSpecRegistry).all()}


def parse(raw: list[str]) -> list[tuple[str, str]]:
    """`key:value` terms; ValueError (the offending text) when one has no colon, key or value."""
    out = []
    for item in raw:
        key, sep, value = str(item or "").partition(":")
        if not sep or not key.strip() or not value.strip():
            raise ValueError(item)
        out.append((key.strip().lower(), value.strip()))
    return out


def value_text(row: ProductSpecRegistry, value: Any) -> str:
    """A stored or asked value as a person reads it: the registry's label where it has one."""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float, Decimal)):
        return f"{value:g}"
    from app.services.product_spec_registry import display_spec_value

    labels = {str(k).lower(): v for k, v in (row.value_labels or {}).items()}
    return str(labels.get(str(value).lower()) or display_spec_value(value))


def _typed(row: ProductSpecRegistry, value: str) -> tuple[Any, Optional[str]]:
    """`(value as the stored type, None)`, or `(None, reason)` when the term cannot narrow."""
    if row.data_type == "numeric":
        match = _NUMBER.match(value)
        if match is None:
            return None, "invalid_value"
        unit = (match.group(2) or "").strip()
        if unit and unit.lower() != (row.unit or "").lower():
            return None, "unit"
        return float(match.group(1)), None
    if row.data_type == "boolean":
        word = value.lower()
        return (True if word in _YES else False if word in _NO else None), (None if word in _YES | _NO else "invalid_value")
    return value, None


def resolve(
    db: Session, terms: list[tuple[str, str]], hidden: set[str], grants: set[str]
) -> tuple[Optional[list[str]], list[str], list[dict[str, str]]]:
    """`(product ids or None when no term applied, echo values, not_applied)`."""
    from app.services.product_spec_search import membership_clause

    rows = registry(db)
    membership: dict[str, list[Any]] = {}
    echo: list[str] = []
    not_applied: list[dict[str, str]] = []
    for key, value in terms:
        row = rows.get(key)
        # A key the contact may not see reads as one that does not exist: the reason must not confirm it is registered.
        reason = "unknown_spec" if row is None or key in hidden else None
        typed = None
        if reason is None:
            typed, reason = _typed(row, value)
        if reason is not None:
            not_applied.append({"filter": "spec", "value": f"{key}:{value}", "reason": reason})
            continue
        membership.setdefault(key, []).append(typed)
        echo.append(f"{row.label}: {value_text(row, typed)}")
    clause = membership_clause(membership)
    if clause is None:
        return None, [], not_applied
    with company_scope(db, None if grants is None else frozenset(grants)):
        ids = (
            db.query(Product.id)
            .join(ProductSpecifications, ProductSpecifications.product_id == Product.id)
            .filter(clause)
            .all()
        )
    return sorted({str(i) for (i,) in ids}), echo, not_applied


def fold_by_key(
    db: Session, key: str, ranked: list[tuple], ids_by_name: dict[str, list[str]]
) -> list[tuple]:
    """`ranked` rows `(product name, qty, amount, count)` regrouped by the value each product
    holds for `key` ("Not stated" for none); a product holding several values is named by all."""
    row = registry(db)[key]
    wanted = sorted({i for ids in ids_by_name.values() for i in ids})
    held: dict[str, str] = {}
    for product_id, values in (
        db.query(ProductSpecifications.product_id, ProductSpecifications.values)
        .filter(ProductSpecifications.product_id.in_(wanted))
        .all()
        if wanted
        else []
    ):
        raw = ((values or {}).get(key) or {}).get("value")
        if raw in (None, "", []):
            continue
        raws = raw if isinstance(raw, list) else [raw]
        held[str(product_id)] = ", ".join(value_text(row, r) for r in raws)
    folded: dict[str, list] = {}
    for name, qty, amount, count in ranked:
        label = next((held[i] for i in ids_by_name.get(name, []) if i in held), NOT_STATED)
        acc = folded.setdefault(label, [Decimal(0), Decimal(0), Decimal(0)])
        acc[0] += qty
        acc[1] += amount
        acc[2] += count
    return [(label, *acc) for label, acc in folded.items()]
