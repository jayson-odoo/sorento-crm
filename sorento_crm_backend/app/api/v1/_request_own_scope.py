"""The request-form "only theirs" guard (PORTAL-P4-REQUESTS, plan Architecture item 3).

One router-level dependency per staff router of the four request forms (Stock Inquiry,
Complaint, Purchase Request / Sponsorship Form), the shape of the project-sales guard
(``app/api/v1/projects/_own_scope.py``). A user is LIMITED in a form when they hold its
``view_own`` and not its ``view`` (``own_scope.REQUEST_KINDS``); admin and superadmin never are.
For a user limited in no kind of the router the guard does nothing.

For a limited user it fails closed:

- the list (``_READS`` role ``list``) is open; the route narrows it with ``RequestScope``, which
  it receives by depending on this same guard (FastAPI caches it per request);
- a row read (role ``row``: detail, revisions) answers 404 unless the row is theirs
  (``own_scope.request_in_scope``: their contact submitted it);
- every other route answers 403, so a route added later is closed to them until it is
  classified here.

Purchase requests and sponsorship forms share a router, so the kind is decided per row (its
``request_type``) and, for the list, by the ``request_type`` filter. A row of a kind the user
holds ``view`` for is left alone. A route without a row id (create, bulk delete, attachment
unlink, the customer lookup, by-number) has no kind, so it is refused to a user limited in either.

``tests/test_portal_p4_request_scope.py`` enumerates every route of the three routers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.services import own_scope
from app.services.error_handler import AppException, handle_not_found
from app.utils.multi_value import multi_values

_PREFIX = {
    "stock_inquiry": "/api/v1/procurement/stock-inquiries",
    "purchase_request": "/api/v1/procurement/purchase-requests",
    "complaint": "/api/v1/complaints-management/complaints",
}

#: The kinds each router serves.
_KINDS = {
    "stock_inquiry": ("stock_inquiry",),
    "purchase_request": ("purchase_request", "sponsorship_form"),
    "complaint": ("complaint",),
}

#: The row id's path param name per router.
_ROW_ID = {"stock_inquiry": "inquiry_id", "purchase_request": "request_id", "complaint": "complaint_id"}

#: (method, path under the router) a limited user may reach, and how.
_READS: Dict[str, Dict[Tuple[str, str], str]] = {
    "stock_inquiry": {
        ("GET", ""): "list",
        ("GET", "/{inquiry_id}"): "row",
        ("GET", "/{inquiry_id}/revisions"): "row",
    },
    "purchase_request": {
        ("GET", ""): "list",
        ("GET", "/{request_id}"): "row",
        ("GET", "/{request_id}/revisions"): "row",
    },
    "complaint": {
        ("GET", ""): "list",
        ("GET", "/{complaint_id}"): "row",
    },
}


@dataclass(frozen=True)
class RequestScope:
    """What a limited user's list may show: per kind ``"all"``, ``"own"`` or None (nothing)."""

    access: Dict[str, Optional[str]]
    contact_id: Optional[str]

    def list_filter(
        self, requested: Optional[Iterable[str]] = None
    ) -> Optional[Tuple[List[str], Optional[str]]]:
        """``(kinds, contact_id)`` for the list query, or None when it shows nothing.

        ``requested`` is the list's kind filter (the purchase-request router's ``request_type``);
        unknown values are ignored as the service ignores them. ``contact_id`` is None only when
        every visible kind is ``"all"``. A user holding ``view`` for one kind and only
        ``view_own`` for the other gets their own rows of both unless the filter names the
        first kind alone.
        """
        wanted = [k for k in (multi_values(requested) or []) if k in self.access]
        visible = [k for k in (wanted or list(self.access)) if self.access[k]]
        if not visible:
            return None
        if all(self.access[k] == "all" for k in visible):
            return visible, None
        if not self.contact_id:
            return None
        return visible, self.contact_id


def empty_page(page: int, limit: int) -> dict:
    """The list answer when a limited user can see nothing."""
    return {"data": [], "pagination": {"total": 0, "page": page, "limit": limit}, "empty": True}


def _refused() -> AppException:
    return AppException(
        status_code=403,
        message="Not available with access to your own records only.",
        code="FORBIDDEN",
    )


def _purchase_request_kind(db: Session, row_id: str) -> Optional[str]:
    import uuid

    from app.models.procurement import PurchaseRequestHeader

    try:
        uuid.UUID(row_id)
    except ValueError:
        return None
    return (
        db.query(PurchaseRequestHeader.request_type)
        .filter(PurchaseRequestHeader.id == row_id)
        .scalar()
    )


def check(
    db: Session, user_id: str, router: str, method: str, path_format: str, path_params: dict
) -> Optional[RequestScope]:
    """Raise unless a limited user may reach this route with this id. Returns the list scope
    for a limited user, None for everyone the rule leaves alone."""
    from app.services.user_service import UserPermissionService

    service = UserPermissionService(db)
    # Said by role, not left to "admin holds every slug": that holds only while each `view`
    # row exists in user_permissions.
    if service.get_user_role_slugs(user_id) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        return None
    perms = service.get_user_permission_slugs(user_id)
    access = {kind: own_scope.request_access(perms, kind) for kind in _KINDS[router]}
    if "own" not in access.values():
        return None
    m = own_scope.me(db, user_id)
    scope = RequestScope(access=access, contact_id=m.contact_id)
    prefix = _PREFIX[router]
    path = path_format[len(prefix):] if path_format.startswith(prefix) else path_format
    role = _READS[router].get((method, path.rstrip("/")))
    if role == "list":
        return scope
    row_id = str(path_params.get(_ROW_ID[router]) or "")
    if "all" in access.values() and row_id:
        # Purchase-request router only: staff for this row's kind, so the rule steps aside.
        if access.get(_purchase_request_kind(db, row_id) or "") == "all":
            return None
    if role == "row":
        if any(
            level == "own" and own_scope.request_in_scope(db, kind, row_id, m)
            for kind, level in access.items()
        ):
            return scope
        raise handle_not_found("Record", row_id)
    raise _refused()


def _guard(router: str):
    async def guard(
        request: Request,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_user_or_api_key),
    ) -> Optional[RequestScope]:
        route = request.scope.get("route")
        path_format = getattr(route, "path_format", None) or request.url.path
        return check(
            db,
            str(current_user.get("id") or ""),
            router,
            request.method,
            path_format,
            request.path_params,
        )

    guard.__name__ = f"{router}_own_scope_guard"
    return guard


#: One instance per router: mounted on the router in its package ``__init__`` and depended on
#: by the list route, so FastAPI runs it once per request.
stock_inquiry_own_scope = _guard("stock_inquiry")
purchase_request_own_scope = _guard("purchase_request")
complaint_own_scope = _guard("complaint")
