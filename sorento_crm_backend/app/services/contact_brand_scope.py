"""Which brands a WhatsApp contact may see: the one reader of `respond_contacts.brand_ids`.

NULL or an empty array means every brand (unscoped, the answer is `None`). A non-empty list
is a strict allow-list: a product whose brand is not in it, or has no brand at all, is out
of scope (CONTACT-BRAND-SCOPE Q1). Core code: it never imports the chatbot package
(tests/chatbot/test_import_boundary.py).

`contact_id` is the INTERNAL `respond_contacts.id`; a Respond.io id resolves through
`field_access.resolve_contact_with_null_workspace_fallback` first (as
`contact_customer_scope.py` does).

PLAN-contact-brand-scope-4oct.md, slice 1.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.base import _BRAND_SCOPE_KEY


def contact_brand_scope(db: Session, contact_id: str) -> Optional[frozenset[str]]:
    """The contact's accessible brand ids, or None when it is unscoped."""
    from app.models.access import RespondContact
    from app.models.base import company_scope
    from app.services.field_access import resolve_contact_with_null_workspace_fallback

    if not contact_id:
        return None
    key = str(contact_id)
    # Company scope OFF for the read: a NULL-workspace contact's row can be hidden under an
    # API-key request's scope, and a hidden row must not read as "unscoped" by accident.
    with company_scope(db, None):
        resolved = resolve_contact_with_null_workspace_fallback(db, contact_id=key) or key
        row = db.query(RespondContact.brand_ids).filter(RespondContact.id == str(resolved)).first()
    ids = row[0] if row else None
    if not ids:
        return None
    return frozenset(str(i) for i in ids)


def brand_predicate(scope: frozenset[str], brand_col):
    """`brand_col IN scope`; a NULL brand never matches (Q1)."""
    return brand_col.in_(sorted(scope))


@contextmanager
def _brand_scope_off(db: Session):
    """Run a lookup that must SEE out-of-scope products (the output guard asks which ones are)."""
    had = _BRAND_SCOPE_KEY in db.info
    prev = db.info.pop(_BRAND_SCOPE_KEY, None)
    try:
        yield
    finally:
        if had:
            db.info[_BRAND_SCOPE_KEY] = prev


def out_of_scope_product_codes(db: Session, scope: frozenset[str], codes: Iterable[str]) -> set[str]:
    """The codes whose product brand is NULL or outside `scope`; unknown codes are left alone."""
    from app.models.product import Product

    wanted = {str(c) for c in codes if c}
    if not wanted:
        return set()
    with _brand_scope_off(db):
        rows = db.query(Product.product_code, Product.brand_id).filter(Product.product_code.in_(wanted)).all()
    return {code for code, brand_id in rows if brand_id is None or str(brand_id) not in scope}


def out_of_scope_product_ids(db: Session, scope: frozenset[str], ids: Iterable[str]) -> set[str]:
    """As `out_of_scope_product_codes`, for product uuids (a stale pick or follow-up)."""
    from app.models.product import Product

    wanted = {str(i) for i in ids if i}
    if not wanted:
        return set()
    with _brand_scope_off(db):
        rows = db.query(Product.id, Product.brand_id).filter(Product.id.in_(wanted)).all()
    return {str(pid) for pid, brand_id in rows if brand_id is None or str(brand_id) not in scope}
