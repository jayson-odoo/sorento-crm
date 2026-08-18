"""Per-(company, brand) recipient scopes for the product-discontinued notice.

A scope is one row of ``user_product_discontinued_scopes``: ``company_id`` NULL
means every company (and forces ``brand_id`` NULL), ``brand_id`` NULL means every
brand in that company. The channel toggles on ``users`` stay HOW a recipient is
notified; these rows decide WHAT they hear about, and zero rows means silence.

Two jobs live here and nowhere else, so the read and the write can never disagree
about what a scope means:

- ``serialize_scopes`` - the saved scopes resolved to company / brand NAMES, which
  is what the user API returns (no UUID ever reaches the UI).
- ``replace_scopes`` - replace-all for one user, with the validation the semantics
  imply: a named brand must belong to the named company, an all-companies scope
  cannot name a brand, and duplicates collapse.

Brands are ``CompanyScopedMixin``, so both paths read them with the company scope
explicitly cleared: an admin edits (and a detail page renders) scopes for
companies they are not currently switched into, and the scoped read would return
nothing for those - a saved brand would silently render as blank.

Decision log: documentation/plans/PLAN-product-discontinued-brand-scope.md
"""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.models.company import Company
from app.models.product import Brand
from app.models.user import UserProductDiscontinuedScope
from app.services.error_handler import handle_unprocessable


def _brands_by_id(db: Session, brand_ids: Iterable[Optional[str]]) -> dict:
    ids = [b for b in brand_ids if b]
    if not ids:
        return {}
    with company_scope(db, None):
        rows = db.query(Brand).filter(Brand.id.in_(ids)).all()
    return {str(b.id): b for b in rows}


def _companies_by_id(db: Session, company_ids: Iterable[Optional[str]]) -> dict:
    ids = [c for c in company_ids if c]
    if not ids:
        return {}
    rows = db.query(Company).filter(Company.id.in_(ids)).all()
    return {str(c.id): c for c in rows}


def list_scopes(db: Session, user_id: str) -> list[UserProductDiscontinuedScope]:
    return (
        db.query(UserProductDiscontinuedScope)
        .filter(UserProductDiscontinuedScope.user_id == user_id)
        .all()
    )


def serialize_scopes(db: Session, user_id: str) -> list[dict]:
    """The user's saved scopes, resolved to names and ordered for display.

    All-companies first, then by company name, then all-brands before named
    brands, then by brand name - the same order the editor lists its rows in, so
    the read view and the edit view cannot disagree (View/Edit parity).
    """
    rows = list_scopes(db, user_id)
    if not rows:
        return []

    pairs = [
        (
            str(row.id),
            str(row.company_id) if row.company_id is not None else None,
            str(row.brand_id) if row.brand_id is not None else None,
        )
        for row in rows
    ]
    companies = _companies_by_id(db, [c for _, c, _ in pairs])
    brands = _brands_by_id(db, [b for _, _, b in pairs])

    out = []
    for scope_id, company_id, brand_id in pairs:
        company = companies.get(company_id) if company_id else None
        brand = brands.get(brand_id) if brand_id else None
        out.append(
            {
                "id": scope_id,
                "company_id": company_id,
                "company_name": company.name if company is not None else None,
                "brand_id": brand_id,
                "brand_code": brand.brand_code if brand is not None else None,
                "brand_name": brand.brand_name if brand is not None else None,
            }
        )

    out.sort(
        key=lambda s: (
            s["company_id"] is not None,
            (s["company_name"] or "").lower(),
            s["brand_id"] is not None,
            (s["brand_name"] or "").lower(),
        )
    )
    return out


_COMPANY_GONE = "That company no longer exists. Refresh and pick it again."
_BRAND_GONE = "That brand no longer exists. Refresh and pick it again."


def _field(item, name: str) -> Optional[str]:
    """One field of a scope item, whether it arrived as a schema or a plain dict.

    ``UserUpdate.model_dump()`` turns the nested schemas into dicts, so the update
    path hands us dicts while a direct caller hands us schemas.
    """
    value = item.get(name) if isinstance(item, dict) else getattr(item, name, None)
    return (str(value).strip() or None) if value else None


def _uuid_field(item, name: str, on_malformed: str) -> Optional[str]:
    """One id field, normalised to canonical (lowercase, hyphenated) UUID text.

    The dedupe below compares strings, but the unique index compares uuid VALUES:
    the same company sent once uppercase and once lowercase would survive dedupe
    as two entries and then collide at flush, which reads to the user as a save
    that failed for no reason. Normalising here is also where a malformed id is
    caught, before it reaches a uuid column and aborts the transaction.
    """
    raw = _field(item, name)
    if raw is None:
        return None
    try:
        return str(uuid.UUID(raw))
    except (ValueError, AttributeError, TypeError):
        raise handle_unprocessable(on_malformed)


def replace_scopes(db: Session, user_id: str, items) -> None:
    """Replace this user's scopes with ``items`` (replace-all semantics).

    Does NOT commit - the caller's update commits once, so a rejected scope list
    cannot leave a half-applied profile update behind.
    """
    pairs: list[tuple[Optional[str], Optional[str]]] = []
    seen: set[tuple[Optional[str], Optional[str]]] = set()

    for item in items or []:
        company_id = _uuid_field(item, "company_id", _COMPANY_GONE)
        brand_id = _uuid_field(item, "brand_id", _BRAND_GONE)
        # All companies can only ever mean all brands: there is no brand that
        # exists in every company, so a brand here would be unsatisfiable.
        if company_id is None:
            brand_id = None
        key = (company_id, brand_id)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(key)

    companies = _companies_by_id(db, [c for c, _ in pairs])
    brands = _brands_by_id(db, [b for _, b in pairs])

    for company_id, brand_id in pairs:
        if company_id is not None and company_id not in companies:
            raise handle_unprocessable(_COMPANY_GONE)
        if brand_id is None:
            continue
        brand = brands.get(brand_id)
        if brand is None:
            raise handle_unprocessable(_BRAND_GONE)
        if str(getattr(brand, "company_id", "") or "") != company_id:
            raise handle_unprocessable(
                f"Brand '{brand.brand_name}' does not belong to "
                f"{companies[company_id].name}."
            )

    db.query(UserProductDiscontinuedScope).filter(
        UserProductDiscontinuedScope.user_id == user_id
    ).delete(synchronize_session=False)

    for company_id, brand_id in pairs:
        db.add(
            UserProductDiscontinuedScope(
                id=str(uuid.uuid4()),
                user_id=user_id,
                company_id=company_id,
                brand_id=brand_id,
            )
        )
