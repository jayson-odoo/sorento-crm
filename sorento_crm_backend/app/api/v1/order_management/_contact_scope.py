"""One helper the order routes share to keep a customer-scoped contact on its own
customers (PLAN-chatbot-customer-scope-29sep.md D5).

The chatbot lane and engine already keep a scoped contact off other customers
(`engine._customer_scope_gate`, `fetch.entity_ids_transformer`); this is the defence
behind the MCP, for a caller that skips them (a direct MCP or n8n call sending
`contact_id` + `space_id`).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.services.error_handler import AppException

NOT_PERMITTED_MESSAGE = "You can only see orders for your own account."


def require_contact_identity_pair(contact_id: Optional[str], space_id: Optional[str]) -> None:
    """`contact_id` and `space_id` are both-or-neither (the sales report's rule): one
    without the other is never silently read as "no contact at all"."""
    if bool(contact_id) != bool(space_id):
        raise AppException(
            422,
            "contact_id and space_id must both be given, or neither",
            detail="contact_id, space_id",
            code="contact_identity_required",
        )


def enforce_customer_scope(
    db: Session,
    *,
    contact_id: Optional[str],
    space_id: Optional[str],
    customer_ids: Optional[list[str]],
    customer_query: Optional[str],
) -> Optional[list[str]]:
    """The customer ids a scoped contact's request is forced to, or None when the request
    is not scoped (no contact identity, staff, or a contact nobody linked): the caller then
    runs exactly as before.

    A scoped contact (`contact_customer_scope.enforced`: linked and no active office
    access type) may name only its own customers: any id outside its links is 403
    `customer_not_permitted`; a `customer_query` is matched inside its links only, and one
    matching none gets the same 403 as another customer's name, so the answer never says
    whether a name exists in the book. Returns the requested ids, else the query's
    matches, else the links.
    """
    # Stripped like `_resolve_api_key_scope` does: a padded id resolves the company scope
    # there, so it must resolve the contact here too or the scope fails open.
    contact_id = (contact_id or "").strip() or None
    space_id = (space_id or "").strip() or None
    require_contact_identity_pair(contact_id, space_id)
    if not (contact_id and space_id):
        return None
    from app.services import contact_customer_scope as scope_mod
    from app.services.field_access import resolve_contact_with_null_workspace_fallback

    resolved = resolve_contact_with_null_workspace_fallback(db, contact_id=contact_id, space_id=space_id)
    if not resolved:
        return None
    scope = scope_mod.contact_customer_scope(db, str(resolved))
    if not scope.enforced:
        return None
    not_permitted = AppException(403, NOT_PERMITTED_MESSAGE, code="customer_not_permitted")
    own = scope.customer_ids
    requested = [str(c) for c in (customer_ids or [])]
    if any(c not in own for c in requested):
        raise not_permitted
    query = " ".join((customer_query or "").split())
    matched: Optional[list[str]] = None
    if query:
        matched = scope.match_words([query])
        if not matched:
            raise not_permitted
    return requested or matched or own
