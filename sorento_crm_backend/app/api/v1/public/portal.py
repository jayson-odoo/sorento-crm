"""Public user submission portal endpoints (no CRM login).

Auth: 7-day portal token. Token travels in either:
- ``X-Portal-Token`` header
- ``token`` query parameter

When a token expires the contact requests an OTP via ``POST /request-otp`` and
exchanges the code for a fresh token via ``POST /verify-otp``.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entity_attachment import EntityAttachmentLink
from app.models.portal import PortalToken
from app.models.resources import Attachment, AttachmentType
from app.services.entity_attachment_service import EntityAttachmentService
from app.services.error_handler import AppException, handle_validation_error
from app.services.portal_service import (
    PORTAL_ATTACHMENT_TYPE_CODE,
    PortalAuthError,
    PortalService,
    SUPPORTED_TYPES,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_portal_token(
    db: Session,
    header_token: Optional[str],
    query_token: Optional[str],
) -> PortalToken:
    raw = (header_token or query_token or "").strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Portal token is required.",
        )
    try:
        return PortalService(db).resolve_token(raw)
    except PortalAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)
        ) from e


def get_portal_token(
    x_portal_token: Annotated[Optional[str], Header(alias="X-Portal-Token")] = None,
    token: Annotated[Optional[str], Query()] = None,
    db: Session = Depends(get_db),
) -> PortalToken:
    resolved = _resolve_portal_token(db, x_portal_token, token)
    # Attribute any audited write in this request to the acting contact (WS2a),
    # so portal submissions read as the contact's name instead of "System".
    # Stash on the SHARED db.info (not a contextvar): FastAPI runs this sync
    # dependency in a different threadpool thread than the path op + flush, so a
    # contextvar set here wouldn't be visible at flush time. db.info lives on the
    # Session object (same instance via Depends(get_db)) and survives the thread hop.
    if resolved.contact_id:
        db.info["actor_contact_id"] = str(resolved.contact_id)
    from app.audit_context import set_actor_contact_id
    set_actor_contact_id(str(resolved.contact_id) if resolved.contact_id else None)
    return resolved


# ---------- OTP ----------


class OtpRequestPayload(BaseModel):
    contact_id: str
    space_id: str


class OtpVerifyPayload(BaseModel):
    contact_id: str
    space_id: str
    code: str = Field(..., min_length=4, max_length=10)


class OtpResponse(BaseModel):
    sent_to: Optional[str]
    expires_at: str


class TokenResponse(BaseModel):
    token: str
    expires_at: str


@router.post("/request-otp", response_model=OtpResponse)
def portal_request_otp(payload: OtpRequestPayload, request: Request, db: Session = Depends(get_db)):
    # Per-IP global limit on this unauthenticated endpoint - the per-contact
    # cooldown/cap in PortalService can't stop an attacker fanning out across many
    # contact_ids to enumerate or to DOS the Respond.io send queue. Fail-open.
    from app.config import settings as app_settings
    from app.services import rate_limit

    ip = request.client.host if request.client else None
    gate = rate_limit.hit(
        "portal_otp", ip,
        limit=app_settings.rate_limit_portal_otp_max,
        window_seconds=app_settings.rate_limit_portal_otp_window_seconds,
    )
    if not gate.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again shortly.",
            headers={"Retry-After": str(gate.retry_after_seconds or app_settings.rate_limit_portal_otp_window_seconds)},
        )
    return PortalService(db).request_otp(payload.contact_id, payload.space_id)


@router.post("/verify-otp", response_model=TokenResponse)
def portal_verify_otp(payload: OtpVerifyPayload, db: Session = Depends(get_db)):
    token = PortalService(db).verify_otp(payload.contact_id, payload.space_id, payload.code)
    return TokenResponse(token=token.token, expires_at=token.expires_at.isoformat())


class PortalTokenInfoResponse(BaseModel):
    contact_id: str
    space_id: str
    expires_at: str
    expired: bool
    revoked: bool
    portal_slug: Optional[str] = None
    name: Optional[str] = None
    masked_phone: Optional[str] = None
    whatsapp_number: Optional[str] = None


@router.get("/token-info", response_model=PortalTokenInfoResponse)
def portal_token_info(token: str, db: Session = Depends(get_db)):
    """Return basic info for any token row in ``portal_tokens``, even when the
    token is expired or revoked. Lets the verify page recover the
    ``contact_id`` / ``space_id`` pair without granting access.
    """
    from app.models.access import RespondContact
    from app.services.portal_service import _utcnow

    row = (
        db.query(PortalToken)
        .filter(PortalToken.token == (token or "").strip())
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found.")
    service = PortalService(db)
    contact = (
        db.query(RespondContact)
        .filter(RespondContact.id == row.contact_id)
        .first()
    )
    hint = service.identity_hint(contact) if contact else {}
    return PortalTokenInfoResponse(
        contact_id=row.contact_id,
        space_id=row.space_id,
        expires_at=row.expires_at.isoformat(),
        expired=row.expires_at <= _utcnow(),
        revoked=row.revoked_at is not None,
        portal_slug=contact.portal_slug if contact else None,
        name=hint.get("name"),
        masked_phone=hint.get("masked_phone"),
        whatsapp_number=hint.get("whatsapp_number"),
    )


class PortalSlugInfoResponse(BaseModel):
    contact_id: str
    space_id: str
    name: Optional[str] = None
    masked_phone: Optional[str]
    whatsapp_number: Optional[str]


@router.get("/slug-info/{slug}", response_model=PortalSlugInfoResponse)
def portal_slug_info(slug: str = Path(..., min_length=4, max_length=32), db: Session = Depends(get_db)):
    """Identity hint behind the stable URL /portal/c/{slug}.

    Public by design: the slug is bookmarkable/shareable. Knowing it grants
    nothing beyond the ability to trigger an OTP that goes to the contact's
    own WhatsApp (cooldown + daily cap enforced in request_otp). 404 carries
    no detail — never confirm revoked-vs-missing.
    """
    return PortalSlugInfoResponse(**PortalService(db).slug_info(slug))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def portal_logout(
    x_portal_token: Annotated[Optional[str], Header(alias="X-Portal-Token")] = None,
    db: Session = Depends(get_db),
):
    """Server-side logout: revoke the presented token. Idempotent, and accepts
    expired/unverified tokens too — clearing client storage alone would leave
    a copied token valid until natural expiry.
    """
    raw = (x_portal_token or "").strip()
    if raw:
        PortalService(db).revoke_token(raw)
    return None


# ---------- Contact ----------


class PortalImpersonationInfo(BaseModel):
    session_id: str
    admin_user_id: str
    admin_name: Optional[str]
    admin_email: Optional[str]
    started_at: str


def _google_maps_api_key(db: Session) -> Optional[str]:
    """Best-effort. No key is a portal without a map, never a portal that fails to load."""
    try:
        from app.models.user import SystemSetting

        row = db.query(SystemSetting).first()
        return (getattr(row, "google_maps_api_key", "") or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


class PortalMeResponse(BaseModel):
    contact_id: str
    space_id: str
    name: Optional[str]
    phone_number: Optional[str]
    expires_at: str
    portal_slug: Optional[str] = None
    whatsapp_number: Optional[str] = None
    impersonation: Optional[PortalImpersonationInfo] = None
    # The Maps BROWSER key, so the lodge journey can draw a map the consumer drags a pin
    # on. Public by design - it reaches the page either way - and restricted by HTTP
    # referrer in Google Cloud. Null means no map and typed fields only, which is the
    # honest degradation: the pin never blocks (AC-M38).
    google_maps_api_key: Optional[str] = None


@router.get("/me", response_model=PortalMeResponse)
def portal_me(
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    service = PortalService(db)
    contact = service.get_contact(token)
    # Lazily mint the stable slug so even legacy tokens surface a
    # bookmarkable URL on first /me. Impersonation sessions stay slug-less on
    # the FE (legacy tree), but the slug itself is harmless to mint.
    portal_slug = service.get_or_create_slug(contact)

    # Surface admin-impersonation context so the portal can show a banner.
    from app.models.impersonation import ContactImpersonationSession
    from app.models.user import User

    impersonation_info: Optional[PortalImpersonationInfo] = None
    session_row = (
        db.query(ContactImpersonationSession)
        .filter(
            ContactImpersonationSession.portal_token_id == token.id,
            ContactImpersonationSession.ended_at.is_(None),
        )
        .first()
    )
    if session_row is not None:
        admin = (
            db.query(User)
            .filter(User.id == session_row.admin_user_id)
            .first()
        )
        impersonation_info = PortalImpersonationInfo(
            session_id=session_row.id,
            admin_user_id=session_row.admin_user_id,
            admin_name=admin.name if admin else None,
            admin_email=admin.email if admin else None,
            started_at=session_row.started_at.isoformat(),
        )

    return PortalMeResponse(
        contact_id=token.contact_id,
        space_id=token.space_id,
        name=contact.name or " ".join(filter(None, [contact.first_name, contact.last_name])).strip() or None,
        phone_number=contact.phone_number,
        expires_at=token.expires_at.isoformat(),
        portal_slug=portal_slug,
        whatsapp_number=service.whatsapp_number_for_contact(contact),
        impersonation=impersonation_info,
        google_maps_api_key=_google_maps_api_key(db),
    )


@router.post("/impersonation/stop")
def portal_impersonation_stop(
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """End the impersonation session and revoke the token from inside the portal.

    Authenticated via portal token, so the admin can exit impersonation
    directly from the portal banner without needing to switch back to the CRM
    tab first.
    """
    from app.models.impersonation import ContactImpersonationSession
    from app.services.audit_service import log_audit
    from datetime import datetime as _dt

    session_row = (
        db.query(ContactImpersonationSession)
        .filter(
            ContactImpersonationSession.portal_token_id == token.id,
            ContactImpersonationSession.ended_at.is_(None),
        )
        .first()
    )
    if session_row is None:
        # Token still gets revoked so a closed-tab token can't be reused.
        if token.revoked_at is None:
            token.revoked_at = _dt.utcnow()
            db.commit()
        return {"ended": False}

    now = _dt.utcnow()
    session_row.ended_at = now
    if token.revoked_at is None:
        token.revoked_at = now
    db.flush()
    log_audit(
        db,
        entity_type="contact_impersonation_session",
        entity_id=session_row.id,
        action="UPDATE",
        user_id=session_row.admin_user_id,
        description="contact_impersonation_end_via_portal",
        new_values={
            "admin_user_id": session_row.admin_user_id,
            "target_contact_id": session_row.target_contact_id,
            "ended_at": now.isoformat(),
        },
    )
    db.commit()
    return {"ended": True, "session_id": session_row.id}


# ---------- The door: there isn't one (AC-B4, AC-B5, AC-B5a) ----------


class PortalJourneyResponse(BaseModel):
    """What track this contact is on, and (if any) the Dealer they report for.

    Carries no identifiers on purpose. The portal is a frontend, so a uuid may not
    appear in it, and this response is the one shape that covers the dealer case as
    well as the consumer case - a customer_id leaked here is a raw uuid rendered on
    a consumer's phone.
    """

    journey: str
    dealer_name: Optional[str] = None


class PortalOrderLookupPayload(BaseModel):
    order_number: str = Field(..., min_length=1, max_length=100)

    @field_validator("order_number")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            # A blank string is not a lookup, it is a scan of the orders table.
            raise ValueError("order_number must not be blank.")
        return cleaned


class PortalOrderLookupResponse(PortalJourneyResponse):
    matched: bool


@router.get("/journey", response_model=PortalJourneyResponse)
def portal_journey(
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """Which journey this phone number is on. No question is ever asked (AC-B4).

    Dealer staff are known from their `customer_id` binding and Sorento staff from
    `user_id`; anything else is a Consumer by elimination. Kind is derived on every
    call rather than stored, so a binding configured five minutes ago takes effect
    on the next landing with no backfill.
    """
    from app.services import party_service

    contact = PortalService(db).get_contact(token)
    return PortalJourneyResponse(
        journey=party_service.derive_contact_kind(contact),
        dealer_name=party_service.dealer_display_name(db, contact),
    )


@router.post("/journey/order-lookup", response_model=PortalOrderLookupResponse)
def portal_journey_order_lookup(
    payload: PortalOrderLookupPayload,
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """Repair a missing dealer binding from a quoted Sorento order number (AC-B5a).

    An unbound dealer contact would otherwise be mis-routed to the Consumer journey
    and asked for a receipt they do not hold. Quoting an order number resolves the
    Dealer, writes the binding, and switches them to the dealer track - silently,
    with no question asked, which also fixes contacts nobody remembered to configure.

    **An unmatched number is a 200 with `matched: false`, never a 4xx.** A Consumer
    holding a dealer's own receipt quotes formats that do not exist in `orders`, and
    blocking them here would wall off exactly the people this was not aimed at.
    """
    from app.services import party_service

    contact = PortalService(db).get_contact(token)
    outcome = party_service.self_heal_dealer_binding(db, contact, payload.order_number)
    return PortalOrderLookupResponse(
        matched=outcome["matched"],
        journey=party_service.derive_contact_kind(contact),
        dealer_name=party_service.dealer_display_name(db, contact),
    )


# ---------- Lookups (gated by portal token) ----------


class ProductLookupItem(BaseModel):
    product_code: str
    product_name: Optional[str] = None
    category_id: Optional[str] = None
    category_code: Optional[str] = None
    category_name: Optional[str] = None


@router.get("/lookups/products", response_model=list[ProductLookupItem])
def lookup_products(
    q: str = Query("", description="Substring match on code or name"),
    limit: int = Query(20, ge=1, le=50),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    from app.models.product import Product, ProductCategory
    query = (
        db.query(Product, ProductCategory)
        .outerjoin(ProductCategory, Product.category_id == ProductCategory.id)
        .filter(Product.is_active.is_(True))
    )
    qs = (q or "").strip()
    if qs:
        like = f"%{qs}%"
        query = query.filter((Product.product_code.ilike(like)) | (Product.product_name.ilike(like)))
    rows = query.order_by(Product.product_code).limit(limit).all()
    return [
        ProductLookupItem(
            product_code=p.product_code,
            product_name=p.product_name,
            category_id=str(p.category_id) if p.category_id else None,
            category_code=c.category_code if c else None,
            category_name=c.category_name if c else None,
        )
        for (p, c) in rows
    ]


class DebtorLookupItem(BaseModel):
    debtor_name: str


@router.get("/lookups/debtors", response_model=list[DebtorLookupItem])
def lookup_debtors(
    q: str = Query(""),
    limit: int = Query(20, ge=1, le=50),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    from app.models.order import Order
    qs = (q or "").strip()
    query = db.query(Order.debtor_name).filter(Order.debtor_name.isnot(None))
    if qs:
        query = query.filter(Order.debtor_name.ilike(f"%{qs}%"))
    rows = query.distinct().order_by(Order.debtor_name).limit(limit).all()
    return [DebtorLookupItem(debtor_name=r[0]) for r in rows if r[0]]


class DOProductLine(BaseModel):
    product_code: str
    product_name: Optional[str] = None
    quantity: Optional[float] = None


class DOLookupItem(BaseModel):
    order_number: str
    debtor_name: Optional[str] = None
    customer_name: Optional[str] = None
    products: list[str] = []
    product_lines: list[DOProductLine] = []
    order_date: Optional[str] = None


@router.get("/lookups/delivery-orders", response_model=list[DOLookupItem])
def lookup_delivery_orders(
    q: str = Query(""),
    limit: int = Query(20, ge=1, le=50),
    start_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD) lower bound on order_date"),
    end_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD) upper bound on order_date"),
    product_code: Optional[str] = Query(None, description="Filter to DOs containing this product code (substring)"),
    debtor_name: Optional[str] = Query(None, description="Filter to DOs whose debtor or customer name matches (substring)"),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    from datetime import date as _date, datetime
    from sqlalchemy import or_
    from app.models.order import Customer, Order, OrderLine
    from app.models.product import Product

    qs = (q or "").strip()
    base = db.query(Order).outerjoin(Customer, Order.customer_id == Customer.id)
    if qs:
        like = f"%{qs}%"
        product_subq = (
            db.query(OrderLine.order_id)
            .join(Product, OrderLine.product_id == Product.id)
            .filter(Product.product_code.ilike(like))
        )
        base = base.filter(
            or_(
                Order.order_number.ilike(like),
                Order.debtor_name.ilike(like),
                Customer.customer_name.ilike(like),
                Order.id.in_(product_subq),
            )
        )
    if start_date:
        try:
            base = base.filter(Order.order_date >= datetime.fromisoformat(start_date))
        except ValueError:
            raise handle_validation_error(f"Invalid start_date: {start_date!r}")
    if end_date:
        try:
            # inclusive upper bound: end of that day
            end_dt = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59)
            base = base.filter(Order.order_date <= end_dt)
        except ValueError:
            raise handle_validation_error(f"Invalid end_date: {end_date!r}")
    if product_code and product_code.strip():
        like_p = f"%{product_code.strip()}%"
        product_subq = (
            db.query(OrderLine.order_id)
            .join(Product, OrderLine.product_id == Product.id)
            .filter(Product.product_code.ilike(like_p))
        )
        base = base.filter(Order.id.in_(product_subq))
    if debtor_name and debtor_name.strip():
        like_d = f"%{debtor_name.strip()}%"
        base = base.filter(
            or_(
                Order.debtor_name.ilike(like_d),
                Customer.customer_name.ilike(like_d),
            )
        )
    rows = base.order_by(Order.order_date.desc().nullslast(), Order.order_number.desc()).limit(limit).all()
    out: list[DOLookupItem] = []
    for o in rows:
        customer_name = o.customer.customer_name if getattr(o, "customer", None) else None
        products: list[str] = []
        product_lines: list[DOProductLine] = []
        try:
            from app.models.order import OrderLine as _OrderLine
            from app.models.product import Product as _Product

            lines = (
                db.query(_Product.product_code, _Product.product_name, _OrderLine.quantity)
                .join(_OrderLine, _OrderLine.product_id == _Product.id)
                .filter(_OrderLine.order_id == o.id)
                .order_by(_OrderLine.line_sequence.asc())
                .limit(200)
                .all()
            )
            for code, name, qty in lines:
                if not code:
                    continue
                products.append(code)
                product_lines.append(
                    DOProductLine(
                        product_code=code,
                        product_name=name,
                        quantity=float(qty) if qty is not None else None,
                    )
                )
        except Exception:
            pass
        od = o.order_date
        if od is None:
            order_date_iso = None
        elif isinstance(od, datetime):
            order_date_iso = od.date().isoformat()
        elif isinstance(od, _date):
            order_date_iso = od.isoformat()
        else:
            order_date_iso = str(od)
        out.append(
            DOLookupItem(
                order_number=o.order_number,
                debtor_name=o.debtor_name,
                customer_name=customer_name,
                products=products,
                product_lines=product_lines,
                order_date=order_date_iso,
            )
        )
    return out


_PORTAL_LOOKUP_SET_WHITELIST = {
    "complaints_within_warranty",
    "complaints_complaint_type",
    "complaints_customer_type",
    "complaints_defects_discovered",
    "procurement_sponsor_subject",
    "procurement_sales_type",
}


class LookupSetOption(BaseModel):
    value: str
    label: str


class LookupSetResponse(BaseModel):
    options: list[LookupSetOption]
    # Binding default option the portal pre-selects on a NEW form (from
    # lookup_bindings.default_value); mirrors the system LookupBoundField.
    default_value: Optional[str] = None


@router.get("/lookups/sets/{set_key}", response_model=LookupSetResponse)
def lookup_set_options(
    set_key: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    if set_key not in _PORTAL_LOOKUP_SET_WHITELIST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Lookup set not allowed for portal: {set_key}",
        )
    from app.models.lookup import LookupBinding, LookupOption, LookupSet

    s = db.query(LookupSet).filter(LookupSet.set_key == set_key).first()
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lookup set not found")
    opts = (
        db.query(LookupOption)
        .filter(LookupOption.set_id == s.id, LookupOption.is_active.is_(True))
        .order_by(LookupOption.sort_order)
        .all()
    )
    binding = db.query(LookupBinding).filter(LookupBinding.set_id == s.id).first()
    return LookupSetResponse(
        options=[LookupSetOption(value=o.value, label=o.label) for o in opts],
        default_value=getattr(binding, "default_value", None) if binding else None,
    )


class RequestorOption(BaseModel):
    id: str
    name: str


class RequestorOptionsResponse(BaseModel):
    items: list[RequestorOption]
    has_more: bool


@router.get("/requestor-options", response_model=RequestorOptionsResponse)
def portal_requestor_options(
    q: Optional[str] = Query(None, description="Case-insensitive substring match on name"),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """Names-only eligible set for the "Requested by" / "Salesperson" picker
    (PLAN-requested-by-contact-routing.md D3/D5/D6). Always includes the
    token's own contact even when unsegmented, so nobody is ever blocked from
    submitting on their own behalf."""
    return PortalService(db).list_requestor_options(token, q=q)


# ---------- Submissions ----------


class SubmissionPayload(BaseModel):
    fields: dict
    products: Optional[list[dict]] = None  # purchase_request / sponsorship_form


def _flatten_payload(payload: SubmissionPayload) -> dict:
    body = dict(payload.fields or {})
    if payload.products is not None:
        body["products"] = payload.products
    return body


def _check_kind(kind: str) -> str:
    k = (kind or "").strip().lower()
    if k not in SUPPORTED_TYPES:
        raise handle_validation_error(f"Unsupported submission type: {kind!r}.")
    return k


@router.get("/submissions")
def portal_list_submissions(
    type: str = Query(...),
    q: Optional[str] = Query(None, description="Free-text search across all fields"),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    return {
        "items": PortalService(db).list_submissions(token, _check_kind(type), q=q),
    }


@router.get("/submissions/{kind}/{submission_id}")
def portal_get_submission(
    kind: str = Path(...),
    submission_id: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    detail = PortalService(db).get_submission(token, _check_kind(kind), submission_id)
    detail["attachments"] = _list_attachments_for(db, _entity_type_for(kind), submission_id)
    return detail


class SubmissionNeighboursResponse(BaseModel):
    prev_id: Optional[str] = None
    next_id: Optional[str] = None
    position: int
    total: int


@router.get(
    "/submissions/{kind}/{submission_id}/neighbours",
    response_model=SubmissionNeighboursResponse,
)
def portal_submission_neighbours(
    kind: str = Path(...),
    submission_id: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """Prev/next over the contact's OWN submissions of the same kind (UAC G1/G2)."""
    return PortalService(db).get_neighbours(token, _check_kind(kind), submission_id)


@router.post("/submissions/{kind}")
def portal_create_draft(
    payload: SubmissionPayload,
    kind: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    return PortalService(db).create_or_update_draft(
        token, _check_kind(kind), _flatten_payload(payload)
    )


@router.put("/submissions/{kind}/{submission_id}")
def portal_update_draft(
    payload: SubmissionPayload,
    kind: str = Path(...),
    submission_id: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    return PortalService(db).create_or_update_draft(
        token, _check_kind(kind), _flatten_payload(payload), submission_id
    )


@router.delete("/submissions/{kind}/{submission_id}", status_code=204)
def portal_delete_draft(
    kind: str = Path(...),
    submission_id: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    PortalService(db).delete_draft(token, _check_kind(kind), submission_id)
    return None


@router.post("/submissions/{kind}/{submission_id}/submit")
def portal_submit(
    kind: str = Path(...),
    submission_id: str = Path(...),
    payload: Optional[SubmissionPayload] = Body(default=None),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    body = _flatten_payload(payload) if payload else None
    return PortalService(db).submit_draft(
        token, _check_kind(kind), submission_id, body
    )


# ---------- Workflow form submissions (F2b) ----------
#
# Here rather than under app/api/v1/workflow_forms/, which carries the JWT dependency:
# a contact holds a portal token and no login, so those routes could never be reached
# from the portal - and an unreachable surface is what invites a second token scheme.
# Separate paths from /submissions/{kind} above, which is the four bespoke forms and is
# keyed by a fixed SUPPORTED_TYPES enum; a workflow form is keyed by definition id.


class WorkflowSubmissionPayload(BaseModel):
    """A contact's answers, and the rows they filed under the form's repeaters.

    ``header_data`` is validated against the frozen published schema server-side, which
    drops unknown keys - so nothing here can reach a column. That is what stops a
    payload naming ``respond_inbox_url`` from blanking or redirecting the admin's chat
    link.
    """

    header_data: dict = Field(default_factory=dict)
    # None, not []: on an update an omitted `lines` must leave the existing rows alone,
    # where an empty list means "delete them all". Defaulting to [] would make every
    # header-only edit silently wipe the repeater rows the contact filed.
    lines: Optional[list[dict]] = None
    # What this form is ABOUT (the order a warranty claim is filed from, say). Optional,
    # and only ever set at creation: it is provenance, not an editable answer.
    source_entity_type: Optional[str] = None
    source_entity_id: Optional[str] = None


def _workflow_portal(db: Session):
    from app.services.workflow_submission_portal import (
        WorkflowSubmissionPortalService,
    )

    return WorkflowSubmissionPortalService(db)


@router.get("/workflow-forms")
def portal_list_workflow_forms(
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """The forms THIS contact may file: portal-open, published, and matching their kind."""
    return {"items": _workflow_portal(db).list_definitions(token)}


@router.get("/workflow-forms/{definition_id}")
def portal_get_workflow_form(
    definition_id: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """The published document to render, behind the same gate as the create."""
    return _workflow_portal(db).get_definition_schema(token, definition_id)


@router.get("/workflow-submissions")
def portal_list_workflow_submissions(
    definition_id: Optional[str] = Query(None),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    return {"items": _workflow_portal(db).list_submissions(token, definition_id)}


@router.get("/workflow-submissions/{submission_id}")
def portal_get_workflow_submission(
    submission_id: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    return _workflow_portal(db).get_submission(token, submission_id)


@router.post("/workflow-forms/{definition_id}/submissions", status_code=201)
def portal_create_workflow_submission(
    payload: WorkflowSubmissionPayload,
    definition_id: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    service = _workflow_portal(db)
    submission = service.create_submission(
        token,
        definition_id,
        payload.header_data,
        payload.lines,
        source_entity_type=payload.source_entity_type,
        source_entity_id=payload.source_entity_id,
    )
    return service.get_submission(token, str(submission.id))


@router.put("/workflow-submissions/{submission_id}")
def portal_update_workflow_submission(
    payload: WorkflowSubmissionPayload,
    submission_id: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    service = _workflow_portal(db)
    submission = service.update_submission(
        token, submission_id, payload.header_data, payload.lines
    )
    return service.get_submission(token, str(submission.id))


# ---------- Attachments ----------


def _entity_type_for(kind: str) -> str:
    """Sponsorship form shares the purchase_request entity_type for attachments."""
    return "purchase_request" if kind == "sponsorship_form" else kind


def _ext(filename: Optional[str], content_type: Optional[str]) -> str:
    if filename and "." in filename:
        return filename.rsplit(".", 1)[-1].lower().strip()
    if content_type and "/" in content_type:
        return content_type.split("/", 1)[1].split(";", 1)[0].strip().lower()
    return ""


def _check_quota(
    db: Session,
    attachment_type: AttachmentType,
    entity_type: str,
    entity_id: str,
    incoming_size: int,
    incoming_ext: str,
) -> None:
    allowed_exts = {
        e.strip().lower().lstrip(".")
        for e in (attachment_type.allowed_extensions or "").split(",")
        if e.strip()
    }
    if allowed_exts and incoming_ext not in allowed_exts:
        raise handle_validation_error(
            f"Unsupported file type. Allowed: {', '.join(sorted(allowed_exts))}."
        )
    max_bytes = (attachment_type.max_file_size_mb or 0) * 1024 * 1024
    if max_bytes and incoming_size > max_bytes:
        raise handle_validation_error(
            f"File exceeds {attachment_type.max_file_size_mb} MB limit."
        )
    if attachment_type.max_count_per_entity is not None:
        existing = (
            db.query(EntityAttachmentLink)
            .filter(
                EntityAttachmentLink.entity_type == entity_type,
                EntityAttachmentLink.entity_id == entity_id,
            )
            .count()
        )
        if existing >= attachment_type.max_count_per_entity:
            raise handle_validation_error(
                f"Attachment limit reached ({attachment_type.max_count_per_entity})."
            )


def _safe_presigned_url(
    file_path: Optional[str],
    provider: Optional[str] = None,
) -> Optional[str]:
    """Sign portal attachment URLs against the row's provider (s3 or r2)."""
    if not file_path:
        return None
    try:
        from app.services.storage_router import resolve_signed_url

        return resolve_signed_url(file_path, provider=provider)
    except Exception as e:  # noqa: BLE001
        logger.warning("Portal presigned URL failed for %s: %s", file_path, e)
        return None


def _list_attachments_for(db: Session, entity_type: str, entity_id: str) -> list[dict]:
    rows = (
        db.query(EntityAttachmentLink, Attachment)
        .join(Attachment, Attachment.id == EntityAttachmentLink.attachment_id)
        .filter(
            EntityAttachmentLink.entity_type == entity_type,
            EntityAttachmentLink.entity_id == entity_id,
        )
        .order_by(EntityAttachmentLink.sort_order.asc().nulls_last(), EntityAttachmentLink.created_at.asc())
        .all()
    )

    # Batch-resolve uploader names in two queries rather than one per row - a
    # submission can carry up to the type's per-record cap (10-20) attachments.
    from app.models.access import RespondContact
    from app.models.user import User

    contact_ids = {att.uploaded_by_contact_id for _, att in rows if att.uploaded_by_contact_id}
    user_ids = {att.uploaded_by for _, att in rows if att.uploaded_by}
    contacts_by_id: dict[str, RespondContact] = {}
    if contact_ids:
        contacts_by_id = {
            c.id: c
            for c in db.query(RespondContact).filter(RespondContact.id.in_(contact_ids)).all()
        }
    users_by_id: dict[str, User] = {}
    if user_ids:
        users_by_id = {
            u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()
        }

    out: list[dict] = []
    for link, att in rows:
        uploader_kind = att.uploader_kind
        uploaded_by_name = "Unknown"
        uploaded_by_role = "unknown"
        if uploader_kind == "contact" and att.uploaded_by_contact_id:
            contact = contacts_by_id.get(att.uploaded_by_contact_id)
            name = (
                (
                    (contact.name or "").strip()
                    or " ".join(
                        p for p in [(contact.first_name or "").strip(), (contact.last_name or "").strip()] if p
                    ).strip()
                    or (contact.phone_number or "").strip()
                )
                if contact is not None
                else ""
            )
            if name:
                uploaded_by_name = name
                uploaded_by_role = "contact"
        elif uploader_kind == "user" and att.uploaded_by:
            user = users_by_id.get(att.uploaded_by)
            name = ((user.name or "").strip() or (user.email or "").strip()) if user is not None else ""
            if name:
                uploaded_by_name = name
                uploaded_by_role = "staff"
        out.append(
            {
                "link_id": str(link.id),
                "attachment_id": str(att.id),
                "filename": att.original_filename,
                "size": att.file_size_bytes,
                "url": _safe_presigned_url(att.file_path, getattr(att, "storage_provider", None)) or att.file_path,
                "content_type": att.mime_type if hasattr(att, "mime_type") else None,
                "uploaded_at": att.uploaded_at.isoformat() if att.uploaded_at else None,
                "uploader_kind": uploader_kind,
                "uploaded_by_name": uploaded_by_name,
                "uploaded_by_role": uploaded_by_role,
                # A staff (`user`) upload has no unlink control in the portal
                # server-enforced in portal_delete_attachment, this just matches
                # the FE's gating so it never renders a control that would 403.
                "can_unlink": uploader_kind != "user",
            }
        )
    return out


@router.get("/attachments")
def portal_list_attachments(
    kind: str = Query(...),
    submission_id: str = Query(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    k = _check_kind(kind)
    # Ensures the contact owns this submission.
    PortalService(db).get_submission(token, k, submission_id)
    return {"items": _list_attachments_for(db, _entity_type_for(k), submission_id)}


@router.post("/attachments")
async def portal_upload_attachment(
    kind: Annotated[str, Form()],
    submission_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File(...)],
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    portal = PortalService(db)
    k = _check_kind(kind)
    portal.get_submission(token, k, submission_id)  # ownership check
    attachment_type = portal.get_portal_attachment_type()

    contents = await file.read()
    incoming_size = len(contents)
    extension = _ext(file.filename, file.content_type)
    _check_quota(
        db,
        attachment_type,
        _entity_type_for(k),
        submission_id,
        incoming_size,
        extension,
    )

    safe_ext = f".{extension}" if extension else ""
    s3_key = f"portal/{token.contact_id}/{uuid.uuid4()}{safe_ext}"
    from app.services.storage_router import default_provider, get_backend

    portal_provider = default_provider()
    portal_backend = get_backend(portal_provider)
    try:
        portal_backend.upload_file(
            contents, s3_key, content_type=file.content_type
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Portal attachment upload failed (provider=%s): %s", portal_provider, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="File upload failed. Please try again.",
        ) from e

    # Grid thumbnail (images only) - portal uploads are device bytes in our own
    # bucket, so the same small-variant path applies. Best-effort; never blocks.
    from app.services.image_thumbnailer import store_thumbnail

    portal_thumbnail = store_thumbnail(
        portal_backend, portal_provider, s3_key, contents, file.content_type
    )

    service = EntityAttachmentService(db)
    link = service.create_attachment_and_link(
        entity_type=_entity_type_for(k),
        entity_id=submission_id,
        file_url=s3_key,
        file_name=file.filename or os.path.basename(s3_key),
        file_size_bytes=incoming_size,
        attachment_type_code=PORTAL_ATTACHMENT_TYPE_CODE,
        created_by=None,
        thumbnail_path=portal_thumbnail,
        storage_provider=portal_provider,
    )
    # Uploader attribution (UAC B1): create_attachment_and_link has no fields
    # for this, so stamp the freshly created row directly, in the same
    # transaction as the link, before commit.
    attachment = db.query(Attachment).filter(Attachment.id == link.attachment_id).first()
    if attachment is not None:
        attachment.uploader_kind = "contact"
        attachment.uploaded_by_contact_id = token.contact_id
    db.commit()
    db.refresh(link)
    if attachment is not None:
        db.refresh(attachment)
    file_path = attachment.file_path if attachment else s3_key
    return {
        "link_id": str(link.id),
        "attachment_id": str(link.attachment_id),
        "filename": attachment.original_filename if attachment else file.filename,
        "size": incoming_size,
        "url": _safe_presigned_url(file_path) or file_path,
        "content_type": (attachment.mime_type if attachment else file.content_type) or None,
    }


@router.delete("/attachments/{link_id}")
def portal_delete_attachment(
    link_id: str = Path(...),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    link = (
        db.query(EntityAttachmentLink)
        .filter(EntityAttachmentLink.id == link_id)
        .first()
    )
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")

    portal = PortalService(db)
    raw_kind = link.entity_type
    # sponsorship_form attachments live under entity_type=purchase_request; verify ownership against either type.
    if raw_kind == "purchase_request":
        owns = False
        for k in ("purchase_request", "sponsorship_form"):
            try:
                portal.get_submission(token, k, link.entity_id)
                owns = True
                break
            except HTTPException:
                continue
        if not owns:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")
    else:
        portal.get_submission(token, raw_kind, link.entity_id)

    # UAC F2 (hard blocker): a staff-uploaded attachment cannot be unlinked from
    # the portal, even by a contact who owns the submission. FE gating alone is
    # not a control on a token surface - enforce it server-side here too.
    attachment = db.query(Attachment).filter(Attachment.id == link.attachment_id).first()
    if attachment is not None and attachment.uploader_kind == "user":
        raise AppException(
            status_code=status.HTTP_403_FORBIDDEN,
            message="This file was added by our team and cannot be removed here.",
            code="STAFF_UPLOAD_LOCKED",
        )

    EntityAttachmentService(db).delete_link(link_id)
    db.commit()
    return {"deleted": True}
