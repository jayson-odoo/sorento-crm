"""Portal sample request endpoints (SR-CORE).

Mounted at ``/api/v1/public/portal`` BEFORE the generic portal router (D49): the generic
``/submissions/{kind}`` handlers would otherwise answer these literal paths. Opt-in per
contact like price tag requests (`GRANTABLE_PORTAL_FORM_TYPES`), so every route calls
``_assert_visible`` first, and every record loads by ``(id, contact_id)``: someone else's
id is a 404, never a 403 (no existence leak).

All rules are in ``sample_request_service``; this module resolves the contact and company.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.v1.public.portal import get_portal_token
from app.api.v1.public.portal_price_tag import _resolve_company
from app.database import get_db
from app.models.base import company_scope
from app.models.portal import PortalToken
from app.models.user import User
from app.schemas.sample_request import SampleRequestWrite
from app.services import sample_request_service as svc
from app.services.error_handler import AppException
from app.services.portal_form_visibility_service import resolve_visible_form_types
from app.services.portal_service import PortalService
from app.services.uuid_path_param import validate_uuid_path
from app.utils.http import content_disposition

router = APIRouter(tags=["public-portal-sample-request"])

_FORM_TYPE = "sample_request"


def _assert_visible(db: Session, contact_id: str) -> None:
    if _FORM_TYPE not in resolve_visible_form_types(db, contact_id):
        raise AppException(
            status_code=403,
            message="Sample requests are not available for your account.",
            code="FORM_TYPE_NOT_VISIBLE",
        )


def _actor(token: PortalToken) -> svc.Actor:
    return svc.Actor(contact_id=str(token.contact_id))


def _linked_user_id(db: Session, contact_id: str) -> Optional[str]:
    """The CRM user whose linked contact this is (`users.respond_contact_id`), or None."""
    return db.query(User.id).filter(User.respond_contact_id == str(contact_id)).scalar()


def _assert_own_quoted_project(db: Session, token: PortalToken, project_id: Optional[str]) -> None:
    """A contact linked to a CRM user who may see only their own projects reads and records the
    quotation of their own projects only (SAMPLE-FROM-QUOTE, SFQ-10): the same rule the staff
    pre-fill route applies, which the company-wide portal project rule alone does not."""
    from app.services import own_scope

    user_id = _linked_user_id(db, token.contact_id)
    if not (project_id and user_id):
        return
    if own_scope.user_is_limited(
        db, user_id, own_scope.PROJECTS_VIEW, own_scope.PROJECTS_VIEW_OWN
    ) and not own_scope.project_in_scope(db, own_scope.me(db, user_id), str(project_id)):
        raise AppException(
            status_code=422,
            message="Pick one of your own projects.",
            code="SAMPLE_REQUEST_PROJECT_NOT_ALLOWED",
            details={"field": "project_id"},
        )


def _own(db: Session, token: PortalToken, request_id: str):
    return svc.get_for(
        db,
        validate_uuid_path(request_id, resource="Sample request"),
        contact_id=str(token.contact_id),
    )


# ---------- The contact's sample request routes, shared with the CRM ----------


def register_sample_request_routes(router: APIRouter, token_dependency: Callable[..., Any]) -> None:
    """Register the sample request routes on ``router``, the caller resolved by ``token_dependency``.

    ONE body per route for two surfaces (PORTAL-P4-REQUESTS S4), the shape of
    ``portal.register_submission_routes``: the portal mounts them below with ``get_portal_token``;
    ``app/api/v1/my_requests.py`` mounts them on ``/api/v1/my-requests`` with a transient portal
    token built from a CRM session, so a salesperson writes their own sample requests through
    exactly the code a portal contact does.
    """

    @router.get("/sample-request/products")
    def portal_search_products(
        q: str = Query(""),
        token: PortalToken = Depends(token_dependency),
        db: Session = Depends(get_db),
    ):
        _assert_visible(db, token.contact_id)
        with company_scope(db, frozenset({_resolve_company(db, token)})):
            return svc.search_products(db, q)


    @router.get("/sample-request/quotation-prefill")
    def portal_quotation_prefill(
        project_id: str = Query(...),
        document_id: Optional[str] = Query(None),
        token: PortalToken = Depends(token_dependency),
        db: Session = Depends(get_db),
    ):
        """The rows a new request on one of the contact's own projects starts with (SFQ-11)."""
        from app.services.sponsorship_link_service import contact_company_ids

        _assert_visible(db, token.contact_id)
        contact = PortalService(db).get_contact(token)
        svc.assert_portal_project_allowed(db, contact=contact, project_id=project_id)
        _assert_own_quoted_project(db, token, project_id)
        with company_scope(db, frozenset(contact_company_ids(db, contact=contact))):
            return svc.quotation_prefill(db, project_id, document_id)

    @router.get("/sample-request/customers")
    def portal_search_customers(
        q: str = Query(""),
        token: PortalToken = Depends(token_dependency),
        db: Session = Depends(get_db),
    ):
        _assert_visible(db, token.contact_id)
        # The same one company submit checks the pick in, so listed and accepted cannot drift.
        with company_scope(db, frozenset({_resolve_company(db, token)})):
            return svc.portal_customers(db, str(token.contact_id), q)


    @router.get("/submissions/sample_request")
    def portal_list(
        q: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=200),
        token: PortalToken = Depends(token_dependency),
        db: Session = Depends(get_db),
    ):
        _assert_visible(db, token.contact_id)
        with company_scope(db, frozenset({_resolve_company(db, token)})):
            return svc.list_for(
                db,
                actor=_actor(token),
                contact_id=str(token.contact_id),
                q=q,
                page=page,
                limit=limit,
            )


    @router.post("/submissions/sample_request", status_code=201)
    def portal_create(
        payload: SampleRequestWrite,
        token: PortalToken = Depends(token_dependency),
        db: Session = Depends(get_db),
    ):
        _assert_visible(db, token.contact_id)
        company_id = _resolve_company(db, token)
        try:
            with company_scope(db, frozenset({company_id})):
                data = payload.model_dump(exclude_unset=True)
                svc.assert_portal_project_allowed(
                    db, contact=PortalService(db).get_contact(token), project_id=data.get("project_id")
                )
                svc.assert_portal_customer_allowed(
                    db, contact_id=token.contact_id, customer_id=data.get("customer_id")
                )
                if data.get("quotation_document_id"):
                    _assert_own_quoted_project(db, token, data.get("project_id"))
                req = svc.create_draft(
                    db,
                    salesperson_id=_linked_user_id(db, token.contact_id),
                    data=data,
                    source="portal",
                    contact_id=str(token.contact_id),
                    space_id=token.space_id,
                )
                db.commit()
                db.refresh(req)
                return svc.serialize_detail(db, req)
        except Exception:
            db.rollback()
            raise


    @router.get("/submissions/sample_request/{request_id}")
    def portal_get(
        request_id: str,
        token: PortalToken = Depends(token_dependency),
        db: Session = Depends(get_db),
    ):
        _assert_visible(db, token.contact_id)
        with company_scope(db, frozenset({_resolve_company(db, token)})):
            return svc.serialize_detail(db, _own(db, token, request_id))


    @router.put("/submissions/sample_request/{request_id}")
    def portal_update(
        request_id: str,
        payload: SampleRequestWrite,
        token: PortalToken = Depends(token_dependency),
        db: Session = Depends(get_db),
    ):
        _assert_visible(db, token.contact_id)
        company_id = _resolve_company(db, token)
        try:
            with company_scope(db, frozenset({company_id})):
                req = _own(db, token, request_id)
                data = payload.model_dump(exclude_unset=True)
                if data.get("project_id"):
                    svc.assert_portal_project_allowed(
                        db, contact=PortalService(db).get_contact(token), project_id=data["project_id"]
                    )
                if data.get("quotation_document_id"):
                    _assert_own_quoted_project(db, token, data.get("project_id") or req.project_id)
                # Only a CHANGED debtor is re-checked: a draft whose debtor later left the
                # agent's book must still be saveable with the customer it already has.
                if data.get("customer_id") != req.customer_id:
                    svc.assert_portal_customer_allowed(
                        db, contact_id=token.contact_id, customer_id=data.get("customer_id")
                    )
                svc.update_draft(db, req, actor=_actor(token), data=data)
                db.commit()
                db.refresh(req)
                return svc.serialize_detail(db, req)
        except Exception:
            db.rollback()
            raise


    @router.post("/submissions/sample_request/{request_id}/submit")
    def portal_submit(
        request_id: str,
        token: PortalToken = Depends(token_dependency),
        db: Session = Depends(get_db),
    ):
        _assert_visible(db, token.contact_id)
        company_id = _resolve_company(db, token)
        try:
            with company_scope(db, frozenset({company_id})):
                req = _own(db, token, request_id)
                svc.submit(db, req, actor=_actor(token))
                db.commit()
                db.refresh(req)
                return svc.serialize_detail(db, req)
        except Exception:
            db.rollback()
            raise


    @router.post("/submissions/sample_request/{request_id}/cancel")
    def portal_cancel(
        request_id: str,
        token: PortalToken = Depends(token_dependency),
        db: Session = Depends(get_db),
    ):
        """Only while Draft or Submitted; once the coordinator is on it, staff cancel."""
        _assert_visible(db, token.contact_id)
        company_id = _resolve_company(db, token)
        try:
            with company_scope(db, frozenset({company_id})):
                req = _own(db, token, request_id)
                frm = svc.status_key(db, req)
                if frm not in (svc.DRAFT, svc.SUBMITTED):
                    raise svc.illegal_move(frm, svc.CANCELLED)
                svc.move(db, req, actor=_actor(token), to=svc.CANCELLED)
                db.commit()
                db.refresh(req)
                return svc.serialize_detail(db, req)
        except Exception:
            db.rollback()
            raise


    @router.get("/submissions/sample_request/{request_id}/pdf")
    def portal_pdf(
        request_id: str,
        token: PortalToken = Depends(token_dependency),
        db: Session = Depends(get_db),
    ):
        _assert_visible(db, token.contact_id)
        with company_scope(db, frozenset({_resolve_company(db, token)})):
            req = _own(db, token, request_id)
            return Response(
                content=svc.render_pdf(db, req),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": content_disposition(f"{req.request_no}.pdf", inline=True)
                },
            )


register_sample_request_routes(router, get_portal_token)
