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
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.v1.public.portal import register_submission_routes
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

#: Names the per-user portal rate-limit bucket (the comment route keys it on ``token.id``).
_TOKEN_NAMESPACE = uuid.UUID("6f1d3c2a-4b7e-4f0a-9a51-2c8e5d0b7a13")

router = APIRouter()


def _add_slug(kind: str) -> str:
    """``procurement.stock_inquiries.view`` -> ``procurement.stock_inquiries.add``."""
    return own_scope.REQUEST_KINDS[kind][0].rsplit(".", 1)[0] + ".add"


def _refused(message: str) -> AppException:
    return AppException(status_code=status.HTTP_403_FORBIDDEN, message=message, code="FORBIDDEN")


async def _kind_of(request: Request, route: tuple[str, str]) -> Optional[str]:
    """The form a call is about: the path, the attachment list's query, the upload's form."""
    kind = request.path_params.get("kind") or request.query_params.get("kind")
    if not kind and route == _UPLOAD:
        kind = (await request.form()).get("kind")
    return str(kind).strip().lower() if kind else None


async def my_requests_token(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortalToken:
    """The CRM caller as a portal token of their own contact, or 403 / 404 (module docstring)."""
    found = request.scope.get("route")
    path_format = getattr(found, "path_format", "") or ""
    route = (request.method, path_format[len(PREFIX):] if path_format.startswith(PREFIX) else path_format)
    kind = await _kind_of(request, route)
    if kind is not None and kind not in own_scope.REQUEST_KINDS:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="This form is not available here.",
            code="NOT_FOUND",
        )

    user_id = str(current_user["id"])
    service = UserPermissionService(db)
    if service.get_user_role_slugs(user_id) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        raise _refused("Staff create requests from the staff pages.")
    perms = service.get_user_permission_slugs(user_id)
    kinds = (kind,) if kind else tuple(own_scope.REQUEST_KINDS)
    if not any(own_scope.request_access(perms, k) == "own" for k in kinds):
        raise _refused("Not available with your access.")
    contact_id = own_scope.me(db, user_id).contact_id
    if not contact_id:
        raise _refused("Your account is not linked to a WhatsApp contact.")
    if route == _CREATE and kind and _add_slug(kind) not in perms:
        raise _refused("You cannot create this form.")

    contact, space_id = _resolve_contact_and_space(db, contact_id)
    # Transient: never added to the session. The reused routes read contact_id and space_id;
    # the comment route keys its per-token rate limit on id, so it is stable per user.
    return PortalToken(
        id=str(uuid.uuid5(_TOKEN_NAMESPACE, user_id)),
        contact_id=str(contact.id),
        space_id=space_id,
        is_impersonation=False,
    )


register_submission_routes(router, my_requests_token)
