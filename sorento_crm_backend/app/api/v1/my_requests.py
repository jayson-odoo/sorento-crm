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
- a create also needs the form's ``.add``;
- the form's own module is on (``_KIND_MODULES``, as the staff routers are mounted): a call
  naming no form needs one of the forms it could reach.

An upload is gated on its multipart ``kind``, the one it writes to; a query ``kind`` naming
another form answers 422.

Sample requests, new product applications and opportunities (S4, S5, S6) have their own portal
routers (``register_sample_request_routes``, ``register_new_product_application_routes``,
``register_sales_opportunity_routes``), mounted here on their own routers ahead of the generic
routes, which would otherwise answer their literal paths. Same gates, the kind fixed per router
(``own_scope.MODULE_REQUEST_KINDS``); the write slugs differ (``_WRITE_SLUGS``): a sample request
and an application are created with ``.create``, an opportunity with ``.add`` and changed with
``.edit``. An application's files ride the generic attachment routes (``_ATTACHMENT_KINDS``), as
on the portal.

Price tag requests (S7) are the same: their own portal router (``register_price_tag_routes``),
created with ``dealer_kit.price_tag_requests.create``. Their files ride the generic attachment
routes and their revise the generic revision routes (``_REVISION_ROUTES``), as on the portal.

The CRM pages never call the two deletes directly (D7, crew answer a85478781): "Delete draft"
parks ``my_request.delete`` and removing an own upload parks ``my_request_attachment.unlink``
(``app/services/record_actions.py``). Both run the portal delete through ``delete_request`` /
``unlink_attachment`` below, under the same gates, for the user who parked them.
"""
from __future__ import annotations

import dataclasses
import uuid
from contextlib import contextmanager
from typing import Iterable, Iterator, Optional

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.v1.public.portal import (
    deletable_submission_draft,
    delete_submission_draft,
    register_submission_routes,
    removable_attachment_link,
    remove_attachment_link,
)
from app.api.v1.public.portal_new_product_application import register_new_product_application_routes
from app.api.v1.public.portal_price_tag import (
    deletable_price_tag_draft,
    delete_price_tag_draft,
    register_price_tag_routes,
)
from app.api.v1.public.portal_sales_opportunity import register_sales_opportunity_routes
from app.api.v1.public.portal_sample_request import register_sample_request_routes
from app.api.v1.user_management.contact_impersonation import _resolve_contact_and_space
from app.database import get_db
from app.dependencies import get_actor_user_id, get_current_user
from app.models.portal import PortalToken
from app.modules.runtime.guards import module_blocked
from app.services import own_scope
from app.services.error_handler import AppException
from app.services.user_service import UserPermissionService
from app.services.uuid_path_param import validate_uuid_path

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
_ATTACHMENT_KINDS = ("new_product_application", "price_tag_request")
#: The generic revision routes, and the own-router kinds whose revisions they carry (S7).
_REVISION_ROUTES = frozenset(
    {
        ("GET", "/submissions/{kind}/{submission_id}/revisions"),
        ("POST", "/submissions/{kind}/{submission_id}/revise"),
        ("PUT", "/submissions/{kind}/{submission_id}/revision-draft"),
        ("DELETE", "/submissions/{kind}/{submission_id}/revision-draft"),
        ("GET", "/submissions/{kind}/{submission_id}/neighbours"),
    }
)
_REVISION_KINDS = ("price_tag_request",)

#: The module each form's staff router is mounted under (``app/api/v1/__init__.py``). A form is
#: served here only while its own module is on, as its staff pages are.
_KIND_MODULES = {
    "stock_inquiry": "procurement",
    "complaint": "complaints",
    "purchase_request": "procurement",
    "sponsorship_form": "procurement",
    "new_product_application": "procurement",
    "price_tag_request": "dealer_kit",
    "sample_request": "projects",
    "sales_opportunity": "sales",
}

#: Names the per-user portal rate-limit bucket (the comment route keys it on ``token.id``).
_TOKEN_NAMESPACE = uuid.UUID("6f1d3c2a-4b7e-4f0a-9a51-2c8e5d0b7a13")

#: The write slug a route of the own-router kinds needs besides the kind's view_own.
_WRITE_SLUGS = {
    ("POST", "/submissions/sample_request"): "projects.sample_requests.create",
    ("POST", "/submissions/new_product_application"): "procurement.new_product_applications.create",
    ("POST", "/sales-opportunities"): "sales.opportunities.add",
    ("PATCH", "/sales-opportunities/{opportunity_id}"): "sales.opportunities.edit",
    ("POST", "/submissions/price_tag_request"): "dealer_kit.price_tag_requests.create",
}

router = APIRouter()
sample_request_router = APIRouter()
new_product_application_router = APIRouter()
sales_opportunity_router = APIRouter()
price_tag_router = APIRouter()


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


def _not_here() -> AppException:
    return AppException(
        status_code=status.HTTP_404_NOT_FOUND,
        message="This form is not available here.",
        code="NOT_FOUND",
    )


def _norm(kind) -> Optional[str]:
    return str(kind).strip().lower() if kind else None


async def _kind_of(request: Request, route: tuple[str, str]) -> Optional[str]:
    """The form a call is about: the path, the attachment list's query, the upload's form.

    An upload writes to its FORM ``kind`` (``portal_upload_attachment``), so that is the one
    gated; a query ``kind`` naming another form is refused, never gated in its place."""
    if route == _UPLOAD:
        kind = _norm((await request.form()).get("kind"))
        asked = _norm(request.query_params.get("kind"))
        if asked and asked != kind:
            raise AppException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                message="The upload names two different forms.",
                code="VALIDATION_ERROR",
            )
        return kind
    return _norm(request.path_params.get("kind") or request.query_params.get("kind"))


def portal_token_for(
    db: Session,
    user_id: str,
    kinds: Iterable[str],
    write_slug: Optional[str] = None,
    write_refusal: str = "You cannot change this form.",
) -> PortalToken:
    """The gates every my-requests call shares (module docstring), then ``user_id`` as a portal
    token of their own contact. ``kinds``: any one of them held as ``"own"``, its module on,
    opens the call. The routes reach it through ``_token_for``; the deferred deletes call it
    directly, since they commit after the request with only the user id."""
    service = UserPermissionService(db)
    if service.get_user_role_slugs(user_id) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        raise _refused("Staff create requests from the staff pages.")
    kinds = tuple(kinds)
    if not kinds or any(k not in _KIND_MODULES for k in kinds):
        raise _not_here()
    modules = {_KIND_MODULES[k] for k in kinds}
    blocked = {m for m in modules if module_blocked(db, user_id, m)}
    kinds = tuple(k for k in kinds if _KIND_MODULES[k] not in blocked)
    if not kinds:
        raise _refused(f"Module not enabled: {', '.join(sorted(blocked))}")
    perms = service.get_user_permission_slugs(user_id)
    if not any(own_scope.request_access(perms, k) == "own" for k in kinds):
        raise _refused("Not available with your access.")
    contact_id = own_scope.me(db, user_id).contact_id
    if not contact_id:
        raise _refused("Your account is not linked to a WhatsApp contact.")
    if write_slug and write_slug not in perms:
        raise _refused(write_refusal)

    contact, space_id = _resolve_contact_and_space(db, contact_id)
    # Transient: never added to the session. The reused routes read contact_id and space_id;
    # the comment route keys its per-token rate limit on id, so it is stable per user.
    return PortalToken(
        id=str(uuid.uuid5(_TOKEN_NAMESPACE, user_id)),
        contact_id=str(contact.id),
        space_id=space_id,
        is_impersonation=False,
    )


def _token_for(
    request: Request,
    db: Session,
    current_user: dict,
    kinds: Iterable[str],
    write_slug: Optional[str],
) -> PortalToken:
    """``portal_token_for`` for the caller of a route, the contact named on the audit actor."""
    token = portal_token_for(
        db,
        str(current_user["id"]),
        kinds,
        write_slug,
        "You cannot create this form." if request.method == "POST" else "You cannot change this form.",
    )
    _act_through(request, db, str(token.contact_id))
    if getattr(request.state, "impersonation_session_id", None):
        # An admin viewing as the salesperson: a comment records them, as a portal
        # impersonation does (``portal._comment_acting_user_id``). An attribute, not a column.
        setattr(token, "impersonating_admin_id", get_actor_user_id(request, current_user))
    return token


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
    if route in _REVISION_ROUTES:
        known += _REVISION_KINDS
    if kind is not None and kind not in known:
        raise _not_here()
    kinds = (kind,) if kind else known
    write_slug = _add_slug(kind) if route == _CREATE and kind else None
    return _token_for(request, db, current_user, kinds, write_slug)


def _kind_token(kind: str):
    """The token dependency of a kind served by its own portal router (S4, S5, S6, S7)."""

    async def token(
        request: Request,
        current_user: dict = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> PortalToken:
        return _token_for(request, db, current_user, (kind,), _WRITE_SLUGS.get(_route(request)))

    token.__name__ = f"my_requests_{kind}_token"
    return token


# ------------------------------------------------------------------ deferred deletes (D7)

#: The forms ``my_request.delete`` deletes a draft of. Sample requests and new product
#: applications park their own (``sample_request.delete``, ``new_product_application.delete``).
DELETE_KINDS = (*own_scope.REQUEST_KINDS, "price_tag_request")
#: The forms whose files ``my_request_attachment.unlink`` removes: the attachment routes' own.
UNLINK_KINDS = (*own_scope.REQUEST_KINDS, *_ATTACHMENT_KINDS)


@contextmanager
def _acting_as(
    db: Session, user_id: str, token: PortalToken, real_user_id: Optional[str]
) -> Iterator[None]:
    """The parked delete commits after its request, from a sweep or someone's poll: the audit
    actor is the user who parked it, their contact named, as ``_act_through`` names it, and the
    admin who parked it while viewing as them (``real_user_id``, stored at park time) kept as the
    real user, as ``get_current_user`` stamps an impersonated request."""
    from app.audit_context import AuditActor, actor_scope

    real = real_user_id or user_id
    actor = AuditActor(
        actor_type="user",
        user_id=user_id,
        real_user_id=real,
        auth_method="impersonation" if real != user_id else None,
        contact_id=str(token.contact_id),
    )
    with actor_scope(actor, db=db):
        yield


def delete_request(
    db: Session,
    user_id: str,
    kind: str,
    request_id: str,
    *,
    check_only: bool = False,
    real_user_id: Optional[str] = None,
) -> None:
    """``my_request.delete``: the portal's own draft delete, as ``user_id``, behind the same gates
    as ``DELETE /my-requests/submissions/{kind}/{id}``. ``check_only`` (park time) runs every
    refusal and deletes nothing; the commit runs them again, as the state may have moved."""
    token = portal_token_for(db, user_id, (kind,))
    if kind not in DELETE_KINDS:
        raise _not_here()
    request_id = validate_uuid_path(request_id, resource="Request")
    if check_only:
        if kind == "price_tag_request":
            deletable_price_tag_draft(db, token, request_id)
        else:
            deletable_submission_draft(db, token, kind, request_id)
        return
    with _acting_as(db, user_id, token, real_user_id):
        if kind == "price_tag_request":
            delete_price_tag_draft(db, token, request_id)
        else:
            delete_submission_draft(db, token, kind, request_id)


def unlink_attachment(
    db: Session,
    user_id: str,
    link_id: str,
    *,
    check_only: bool = False,
    real_user_id: Optional[str] = None,
) -> None:
    """``my_request_attachment.unlink``: the portal's own ``DELETE /attachments/{link_id}``, as
    ``user_id``, behind that my-requests route's gates. A staff upload stays locked."""
    token = portal_token_for(db, user_id, UNLINK_KINDS)
    link_id = validate_uuid_path(link_id, resource="Attachment")
    if check_only:
        removable_attachment_link(db, token, link_id)
        return
    with _acting_as(db, user_id, token, real_user_id):
        remove_attachment_link(db, token, link_id)


register_sample_request_routes(sample_request_router, _kind_token("sample_request"))
register_new_product_application_routes(
    new_product_application_router, _kind_token("new_product_application")
)
register_sales_opportunity_routes(sales_opportunity_router, _kind_token("sales_opportunity"))
register_price_tag_routes(price_tag_router, _kind_token("price_tag_request"))
register_submission_routes(router, my_requests_token)
