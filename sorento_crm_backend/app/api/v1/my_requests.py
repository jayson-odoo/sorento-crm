"""My Requests from the CRM: a salesperson's own forms, written by the portal's own code.

Plan: documentation/plans/portal/PLAN-portal-p4-requests-28oct.md (Architecture item 4).

``/api/v1/my-requests`` carries the SAME routes, bodies and responses as the portal
(``register_submission_routes`` in ``app/api/v1/public/portal.py``, one body per route for both
surfaces). Only the caller differs: a CRM session instead of a portal token. ``my_requests_token``
turns the session into a transient, never-persisted ``PortalToken`` of the user's linked contact
and that contact's workspace space, so every ownership rule, draft / submit / revise rule,
notification and SLA tracker is the portal's. The audit actor is the session user, stamped by
``get_current_user`` (the target user and the admin under impersonation).

Who may call it (fails closed, before the portal code runs):

- the form is one of ``own_scope.REQUEST_KINDS`` (anything else 404);
- the user holds that form's ``view_own`` and not its ``view``: staff keep the staff create, and
  admin / superadmin are refused by role. A route with no form (the requestor picker, an
  attachment by id) needs that for at least one of the four;
- the user has a linked contact with a workspace (403 / the contact-impersonation answers);
- a create also needs the form's ``.add``.

Sample requests, new product applications and opportunities (S4, S5, S6) have their own portal
routers (``register_sample_request_routes``, ``register_new_product_application_routes``,
``register_sales_opportunity_routes``), mounted here on their own routers ahead of the generic
routes, which would otherwise answer their literal paths. Same gates, the kind fixed per router
(``own_scope.MODULE_REQUEST_KINDS``); the write slugs differ (``_WRITE_SLUGS``): a sample request
and an application are created with ``.create``, an opportunity with ``.add`` and changed with
``.edit``. An application's files ride the generic attachment routes (``_ATTACHMENT_KINDS``), as
on the portal.
"""
from __future__ import annotations

import dataclasses
import uuid
from typing import Iterable, Optional

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.v1.public.portal import register_submission_routes
from app.api.v1.public.portal_new_product_application import register_new_product_application_routes
from app.api.v1.public.portal_sales_opportunity import register_sales_opportunity_routes
from app.api.v1.public.portal_sample_request import register_sample_request_routes
from app.api.v1.user_management.contact_impersonation import _resolve_contact_and_space
from app.database import get_db
from app.dependencies import get_current_user
from app.models.portal import PortalToken
from app.services import own_scope
from app.services.error_handler import AppException
from app.services.user_service import UserPermissionService

PREFIX = "/api/v1/my-requests"
_CREATE = ("POST", "/submissions/{kind}")
_UPLOAD = ("POST", "/attachments")
#: The generic attachment routes, and the own-router kinds whose files they carry (S5).
_ATTACHMENT_ROUTES = frozenset(
    {
        ("GET", "/attachments"),
        _UPLOAD,
        ("GET", "/attachments/{attachment_id}/download"),
        ("DELETE", "/attachments/{link_id}"),
    }
)
_ATTACHMENT_KINDS = ("new_product_application",)

#: Names the per-user portal rate-limit bucket (the comment route keys it on ``token.id``).
_TOKEN_NAMESPACE = uuid.UUID("6f1d3c2a-4b7e-4f0a-9a51-2c8e5d0b7a13")

#: The write slug a route of the own-router kinds needs besides the kind's view_own.
_WRITE_SLUGS = {
    ("POST", "/submissions/sample_request"): "projects.sample_requests.create",
    ("POST", "/submissions/new_product_application"): "procurement.new_product_applications.create",
    ("POST", "/sales-opportunities"): "sales.opportunities.add",
    ("PATCH", "/sales-opportunities/{opportunity_id}"): "sales.opportunities.edit",
}

router = APIRouter()
sample_request_router = APIRouter()
new_product_application_router = APIRouter()
sales_opportunity_router = APIRouter()


def _add_slug(kind: str) -> str:
    """``procurement.stock_inquiries.view`` -> ``procurement.stock_inquiries.add``."""
    return own_scope.REQUEST_KINDS[kind][0].rsplit(".", 1)[0] + ".add"


def _route(request: Request) -> tuple[str, str]:
    """(method, path under the prefix) of the matched route."""
    found = request.scope.get("route")
    path_format = getattr(found, "path_format", "") or ""
    return request.method, path_format[len(PREFIX):] if path_format.startswith(PREFIX) else path_format


def _refused(message: str) -> AppException:
    return AppException(status_code=status.HTTP_403_FORBIDDEN, message=message, code="FORBIDDEN")


async def _kind_of(request: Request, route: tuple[str, str]) -> Optional[str]:
    """The form a call is about: the path, the attachment list's query, the upload's form."""
    kind = request.path_params.get("kind") or request.query_params.get("kind")
    if not kind and route == _UPLOAD:
        kind = (await request.form()).get("kind")
    return str(kind).strip().lower() if kind else None


def _token_for(
    request: Request,
    db: Session,
    current_user: dict,
    kinds: Iterable[str],
    write_slug: Optional[str],
) -> PortalToken:
    """The gates every my-requests route shares (module docstring), then the caller as a portal
    token of their own contact. ``kinds``: any one of them held as ``"own"`` opens the route."""
    user_id = str(current_user["id"])
    service = UserPermissionService(db)
    if service.get_user_role_slugs(user_id) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        raise _refused("Staff create requests from the staff pages.")
    perms = service.get_user_permission_slugs(user_id)
    if not any(own_scope.request_access(perms, k) == "own" for k in kinds):
        raise _refused("Not available with your access.")
    contact_id = own_scope.me(db, user_id).contact_id
    if not contact_id:
        raise _refused("Your account is not linked to a WhatsApp contact.")
    if write_slug and write_slug not in perms:
        raise _refused("You cannot create this form." if request.method == "POST" else "You cannot change this form.")

    contact, space_id = _resolve_contact_and_space(db, contact_id)
    _act_through(request, db, str(contact.id))
    # Transient: never added to the session. The reused routes read contact_id and space_id;
    # the comment route keys its per-token rate limit on id, so it is stable per user.
    return PortalToken(
        id=str(uuid.uuid5(_TOKEN_NAMESPACE, user_id)),
        contact_id=str(contact.id),
        space_id=space_id,
        is_impersonation=False,
    )


def _act_through(request: Request, db: Session, contact_id: str) -> None:
    """Name the contact on the session's audit actor, user and impersonating admin kept.

    Under impersonation the stamped actor carries no contact, and a reused route that re-stamps a
    portal contact when the actor's contact is not the token's (the opportunity router's
    ``_require_agents``) would otherwise drop the user and the admin from the audit row."""
    from app.audit_context import get_actor, stamp_actor

    actor = get_actor(db)
    if actor is not None and actor.contact_id != contact_id:
        stamp_actor(dataclasses.replace(actor, contact_id=contact_id), db=db, request=request)


async def my_requests_token(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortalToken:
    """The CRM caller as a portal token of their own contact, or 403 / 404 (module docstring)."""
    route = _route(request)
    kind = await _kind_of(request, route)
    known = tuple(own_scope.REQUEST_KINDS)
    if route in _ATTACHMENT_ROUTES:
        known += _ATTACHMENT_KINDS
    if kind is not None and kind not in known:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="This form is not available here.",
            code="NOT_FOUND",
        )
    kinds = (kind,) if kind else known
    write_slug = _add_slug(kind) if route == _CREATE and kind else None
    return _token_for(request, db, current_user, kinds, write_slug)


def _kind_token(kind: str):
    """The token dependency of a kind served by its own portal router (S4, S6)."""

    async def token(
        request: Request,
        current_user: dict = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> PortalToken:
        return _token_for(request, db, current_user, (kind,), _WRITE_SLUGS.get(_route(request)))

    token.__name__ = f"my_requests_{kind}_token"
    return token


register_sample_request_routes(sample_request_router, _kind_token("sample_request"))
register_new_product_application_routes(
    new_product_application_router, _kind_token("new_product_application")
)
register_sales_opportunity_routes(sales_opportunity_router, _kind_token("sales_opportunity"))
register_submission_routes(router, my_requests_token)
