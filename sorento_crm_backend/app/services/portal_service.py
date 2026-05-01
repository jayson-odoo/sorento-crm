"""User submission portal service.

Owns:
- Portal token issuance and validation (7 day TTL, contact-scoped, revocable).
- OTP request / verification via Respond.io once a token expires.
- List, create, update, submit and attachment helpers across the four supported
  submission types (complaint, stock_inquiry, purchase_request, sponsorship_form).

Editing rules:
- A submission is editable from the portal when ``portal_draft_at IS NOT NULL``
  or when ``status == 'rejected'``.
- Saving as draft sets ``portal_draft_at`` and does not trigger team notifications.
- Submitting clears ``portal_draft_at`` and triggers the existing per-type
  notification flow (same one used by the legacy external-create endpoints).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.access import RespondContact
from app.models.complaints import Complaint
from app.models.portal import PortalOtpCode, PortalToken
from app.models.procurement import (
    PurchaseRequestHeader,
    PurchaseRequestLine,
    StockInquiry,
)
from app.models.resources import AttachmentType
from app.services.error_handler import (
    handle_not_found,
    handle_validation_error,
)
from app.services.integration_service import RespondClient

logger = logging.getLogger(__name__)


PORTAL_TOKEN_TTL = timedelta(days=7)
OTP_TTL = timedelta(minutes=10)
OTP_REQUEST_COOLDOWN = timedelta(seconds=60)
OTP_MAX_ATTEMPTS = 5
SUPPORTED_TYPES = ("complaint", "stock_inquiry", "purchase_request", "sponsorship_form")
PORTAL_ATTACHMENT_TYPE_CODE = "portal_submission"


def _utcnow() -> datetime:
    return datetime.utcnow()


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


class PortalAuthError(Exception):
    """Raised when a portal token is missing, expired, or revoked."""


class PortalService:
    def __init__(self, db: Session):
        self.db = db

    # ---------- Token lifecycle ----------

    def mint_token(self, contact_id: str, space_id: str) -> PortalToken:
        contact_id = (contact_id or "").strip()
        space_id = (space_id or "").strip()
        if not contact_id or not space_id:
            raise handle_validation_error("contact_id and space_id are required.")
        # Confirm contact exists in respond_contacts.
        contact = self.db.query(RespondContact).filter(RespondContact.id == contact_id).first()
        if not contact:
            raise handle_not_found("Contact", contact_id)
        token = PortalToken(
            token=secrets.token_urlsafe(48),
            contact_id=contact_id,
            space_id=space_id,
            expires_at=_utcnow() + PORTAL_TOKEN_TTL,
        )
        self.db.add(token)
        self.db.commit()
        self.db.refresh(token)
        return token

    def get_or_mint_token(self, contact_id: str, space_id: str) -> tuple[PortalToken, bool]:
        """Return latest live token for (contact_id, space_id) or mint a new one.

        Returns (token, reused). A token is "live" if revoked_at is null and expires_at > now.
        """
        contact_id = (contact_id or "").strip()
        space_id = (space_id or "").strip()
        if not contact_id or not space_id:
            raise handle_validation_error("contact_id and space_id are required.")
        live = (
            self.db.query(PortalToken)
            .filter(
                PortalToken.contact_id == contact_id,
                PortalToken.space_id == space_id,
                PortalToken.revoked_at.is_(None),
                PortalToken.expires_at > _utcnow(),
            )
            .order_by(PortalToken.expires_at.desc())
            .first()
        )
        if live is not None:
            return live, True
        return self.mint_token(contact_id, space_id), False

    def _build_send_message_text(
        self, contact: RespondContact, portal_url: str, expires_at
    ) -> str:
        name = (contact.name or getattr(contact, "first_name", None) or "").strip()
        greeting = f"Hi {name}," if name else "Hi,"
        expires_human = expires_at.strftime("%b %d, %Y")
        return (
            f"{greeting} here is your secure portal link:\n"
            f"{portal_url}\n\n"
            f"The link expires on {expires_human}. Reply if you need help."
        )

    def send_link_via_respond_io(
        self,
        contact_id: str,
        space_id: str,
        base_url: Optional[str] = None,
    ) -> dict:
        """Mint or reuse a portal token and deliver it via Respond.io chat.

        Raises httpx.HTTPStatusError on upstream failure (caller maps to 502).
        """
        contact = (
            self.db.query(RespondContact)
            .filter(RespondContact.id == contact_id)
            .first()
        )
        if contact is None:
            raise handle_not_found("Contact", contact_id)
        respond_io_id = (contact.respond_io_id or "").strip()
        if not respond_io_id:
            raise handle_validation_error(
                "Contact has no Respond.io identifier; cannot send link."
            )
        token, reused = self.get_or_mint_token(contact_id, space_id)
        portal_url = self.build_portal_url(token.token, base_url)
        text = self._build_send_message_text(contact, portal_url, token.expires_at)
        RespondClient().send_message(respond_io_id, text)
        return {
            "token": token.token,
            "expires_at": token.expires_at.isoformat(),
            "portal_url": portal_url,
            "reused": reused,
            "sent": True,
        }

    def resolve_token(self, token_value: str) -> PortalToken:
        if not token_value or not token_value.strip():
            raise PortalAuthError("Missing portal token.")
        row = (
            self.db.query(PortalToken)
            .filter(PortalToken.token == token_value.strip())
            .first()
        )
        if row is None:
            raise PortalAuthError("Invalid portal token.")
        if row.revoked_at is not None:
            raise PortalAuthError("Portal token revoked.")
        if row.expires_at <= _utcnow():
            raise PortalAuthError("Portal token expired. Verify with OTP to continue.")
        return row

    def build_portal_url(self, token: str, base_url_override: Optional[str] = None) -> str:
        base = (base_url_override or "").strip().rstrip("/")
        if not base:
            base = (getattr(settings, "frontend_base_url", None) or "").strip().rstrip("/")
        path = f"/portal?token={token}"
        return f"{base}{path}" if base else path

    # ---------- OTP flow ----------

    def request_otp(self, contact_id: str, space_id: str) -> dict:
        """Generate a fresh OTP code and dispatch via Respond.io. Returns delivery hint."""
        contact_id = (contact_id or "").strip()
        space_id = (space_id or "").strip()
        if not contact_id or not space_id:
            raise handle_validation_error("contact_id and space_id are required.")
        contact = self.db.query(RespondContact).filter(RespondContact.id == contact_id).first()
        if contact is None:
            raise handle_not_found("Contact", contact_id)

        # Rate-limit: at most one outstanding OTP per contact within cooldown.
        recent = (
            self.db.query(PortalOtpCode)
            .filter(PortalOtpCode.contact_id == contact_id)
            .order_by(PortalOtpCode.created_at.desc())
            .first()
        )
        if recent is not None and (_utcnow() - recent.created_at) < OTP_REQUEST_COOLDOWN:
            raise handle_validation_error("Please wait before requesting another verification code.")

        code = f"{secrets.randbelow(1_000_000):06d}"
        otp = PortalOtpCode(
            contact_id=contact_id,
            space_id=space_id,
            code_hash=_hash_otp(code),
            expires_at=_utcnow() + OTP_TTL,
        )
        self.db.add(otp)
        self.db.commit()
        self.db.refresh(otp)

        # Dispatch via Respond.io. Prefer respond_io_id; fall back to contact_id.
        identifier = (contact.respond_io_id or "").strip() or contact_id
        try:
            from app.services.integration_service import RespondClient

            client = RespondClient()
            client.send_message(
                identifier,
                f"Your Sorento portal verification code is {code}. It expires in 10 minutes.",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to dispatch portal OTP for contact %s: %s", contact_id, e)
            raise handle_validation_error(
                "Could not send the verification code right now. Please try again shortly."
            ) from e
        masked_phone = self._mask_phone(contact.phone_number)
        return {"sent_to": masked_phone, "expires_at": otp.expires_at.isoformat()}

    def verify_otp(self, contact_id: str, space_id: str, code: str) -> PortalToken:
        contact_id = (contact_id or "").strip()
        space_id = (space_id or "").strip()
        code = (code or "").strip()
        if not contact_id or not space_id or not code:
            raise handle_validation_error("contact_id, space_id and code are required.")

        otp = (
            self.db.query(PortalOtpCode)
            .filter(
                PortalOtpCode.contact_id == contact_id,
                PortalOtpCode.consumed_at.is_(None),
            )
            .order_by(PortalOtpCode.created_at.desc())
            .first()
        )
        if otp is None:
            raise handle_validation_error("No verification code outstanding. Request a new one.")
        if otp.expires_at <= _utcnow():
            raise handle_validation_error("Verification code expired. Request a new one.")
        if otp.attempts >= OTP_MAX_ATTEMPTS:
            raise handle_validation_error("Too many attempts. Request a new verification code.")

        if not hmac.compare_digest(otp.code_hash, _hash_otp(code)):
            otp.attempts += 1
            self.db.commit()
            raise handle_validation_error("Incorrect verification code.")

        otp.consumed_at = _utcnow()
        self.db.commit()
        return self.mint_token(contact_id, space_id)

    @staticmethod
    def _mask_phone(phone: Optional[str]) -> Optional[str]:
        if not phone:
            return None
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) <= 4:
            return phone
        return f"••••••{digits[-4:]}"

    # ---------- Identity ----------

    def get_contact(self, token: PortalToken) -> RespondContact:
        contact = (
            self.db.query(RespondContact)
            .filter(RespondContact.id == token.contact_id)
            .first()
        )
        if contact is None:
            raise handle_not_found("Contact", token.contact_id)
        return contact

    # ---------- List submissions ----------

    def list_submissions(self, token: PortalToken, kind: str) -> list[dict]:
        kind = (kind or "").strip().lower()
        if kind not in SUPPORTED_TYPES:
            raise handle_validation_error(f"Unsupported submission type: {kind!r}.")
        if kind == "complaint":
            rows = (
                self.db.query(Complaint)
                .filter(
                    Complaint.contact_id == token.contact_id,
                    Complaint.space_id == token.space_id,
                )
                .order_by(Complaint.created_at.desc())
                .all()
            )
            return [self._serialize_complaint_summary(r) for r in rows]
        if kind == "stock_inquiry":
            rows = (
                self.db.query(StockInquiry)
                .filter(
                    StockInquiry.contact_id == token.contact_id,
                    StockInquiry.space_id == token.space_id,
                )
                .order_by(StockInquiry.created_at.desc())
                .all()
            )
            return [self._serialize_stock_inquiry_summary(r) for r in rows]
        # purchase_request / sponsorship_form
        rows = (
            self.db.query(PurchaseRequestHeader)
            .filter(
                PurchaseRequestHeader.contact_id == token.contact_id,
                PurchaseRequestHeader.space_id == token.space_id,
                PurchaseRequestHeader.request_type == kind,
            )
            .order_by(PurchaseRequestHeader.created_at.desc())
            .all()
        )
        return [self._serialize_request_summary(r) for r in rows]

    # ---------- Detail ----------

    def get_submission(self, token: PortalToken, kind: str, submission_id: str) -> dict:
        kind = kind.strip().lower()
        if kind == "complaint":
            row = (
                self.db.query(Complaint)
                .filter(
                    Complaint.id == submission_id,
                    Complaint.contact_id == token.contact_id,
                    Complaint.space_id == token.space_id,
                )
                .first()
            )
            if row is None:
                raise handle_not_found("Complaint", submission_id)
            return self._serialize_complaint_detail(row)
        if kind == "stock_inquiry":
            row = (
                self.db.query(StockInquiry)
                .filter(
                    StockInquiry.id == submission_id,
                    StockInquiry.contact_id == token.contact_id,
                    StockInquiry.space_id == token.space_id,
                )
                .first()
            )
            if row is None:
                raise handle_not_found("Stock Inquiry", submission_id)
            return self._serialize_stock_inquiry_detail(row)
        if kind in ("purchase_request", "sponsorship_form"):
            row = (
                self.db.query(PurchaseRequestHeader)
                .options(joinedload(PurchaseRequestHeader.lines))
                .filter(
                    PurchaseRequestHeader.id == submission_id,
                    PurchaseRequestHeader.contact_id == token.contact_id,
                    PurchaseRequestHeader.space_id == token.space_id,
                    PurchaseRequestHeader.request_type == kind,
                )
                .first()
            )
            if row is None:
                raise handle_not_found("Purchase Request", submission_id)
            return self._serialize_request_detail(row)
        raise handle_validation_error(f"Unsupported submission type: {kind!r}.")

    # ---------- Mutations ----------

    def create_or_update_draft(
        self,
        token: PortalToken,
        kind: str,
        payload: dict,
        submission_id: Optional[str] = None,
    ) -> dict:
        kind = kind.strip().lower()
        if submission_id is None:
            row = self._instantiate(kind, token, payload)
            row.portal_draft_at = _utcnow()
            self.db.add(row)
            self.db.flush()
            self._replace_request_lines_if_needed(kind, row, payload)
            self.db.commit()
            self.db.refresh(row)
        else:
            row = self._fetch_for_edit(kind, token, submission_id)
            self._apply_payload(kind, row, payload)
            row.portal_draft_at = _utcnow()
            self._replace_request_lines_if_needed(kind, row, payload)
            self.db.commit()
            self.db.refresh(row)
        return self.get_submission(token, kind, str(row.id))

    def submit_draft(
        self,
        token: PortalToken,
        kind: str,
        submission_id: str,
        payload: Optional[dict] = None,
    ) -> dict:
        kind = kind.strip().lower()
        row = self._fetch_for_edit(kind, token, submission_id)
        if payload:
            self._apply_payload(kind, row, payload)
            self._replace_request_lines_if_needed(kind, row, payload)

        # Status transition + notification.
        previous_status = row.status
        row.portal_draft_at = None
        if kind == "complaint":
            if previous_status not in ("draft", "rejected"):
                raise handle_validation_error(
                    f"Cannot submit complaint with status {previous_status!r}."
                )
            row.status = "new"
        elif kind == "stock_inquiry":
            if previous_status not in ("draft", "rejected"):
                raise handle_validation_error(
                    f"Cannot submit stock inquiry with status {previous_status!r}."
                )
            row.status = "new"
            row.rejection_reason = None
            row.rejected_at = None
            row.rejected_by = None
            row.rejected_from = None
        else:  # purchase_request / sponsorship_form
            if previous_status not in ("draft", "rejected"):
                raise handle_validation_error(
                    f"Cannot submit {kind} with status {previous_status!r}."
                )
            # Keep status='draft' to align with legacy external-create flow.
        self.db.commit()
        self.db.refresh(row)

        # Notifications — failures must not block the user-facing submit.
        try:
            self._post_submit_notify(kind, row)
        except Exception as e:  # noqa: BLE001
            logger.warning("Post-submit notify failed for %s %s: %s", kind, row.id, e)

        return self.get_submission(token, kind, str(row.id))

    def _instantiate(self, kind: str, token: PortalToken, payload: dict) -> Any:
        if kind == "complaint":
            row = Complaint(
                contact_id=token.contact_id,
                space_id=token.space_id,
                status="draft",
            )
            self._apply_payload(kind, row, payload)
            return row
        if kind == "stock_inquiry":
            row = StockInquiry(
                contact_id=token.contact_id,
                space_id=token.space_id,
                status="draft",
            )
            self._apply_payload(kind, row, payload)
            return row
        if kind in ("purchase_request", "sponsorship_form"):
            row = PurchaseRequestHeader(
                contact_id=token.contact_id,
                space_id=token.space_id,
                request_type=kind,
                status="draft",
                source="portal",
            )
            self._apply_payload(kind, row, payload)
            return row
        raise handle_validation_error(f"Unsupported submission type: {kind!r}.")

    def _fetch_for_edit(self, kind: str, token: PortalToken, submission_id: str) -> Any:
        if kind == "complaint":
            row = (
                self.db.query(Complaint)
                .filter(
                    Complaint.id == submission_id,
                    Complaint.contact_id == token.contact_id,
                    Complaint.space_id == token.space_id,
                )
                .first()
            )
            if row is None:
                raise handle_not_found("Complaint", submission_id)
        elif kind == "stock_inquiry":
            row = (
                self.db.query(StockInquiry)
                .filter(
                    StockInquiry.id == submission_id,
                    StockInquiry.contact_id == token.contact_id,
                    StockInquiry.space_id == token.space_id,
                )
                .first()
            )
            if row is None:
                raise handle_not_found("Stock Inquiry", submission_id)
        elif kind in ("purchase_request", "sponsorship_form"):
            row = (
                self.db.query(PurchaseRequestHeader)
                .options(joinedload(PurchaseRequestHeader.lines))
                .filter(
                    PurchaseRequestHeader.id == submission_id,
                    PurchaseRequestHeader.contact_id == token.contact_id,
                    PurchaseRequestHeader.space_id == token.space_id,
                    PurchaseRequestHeader.request_type == kind,
                )
                .first()
            )
            if row is None:
                raise handle_not_found("Purchase Request", submission_id)
        else:
            raise handle_validation_error(f"Unsupported submission type: {kind!r}.")
        if not (row.portal_draft_at or row.status == "rejected"):
            raise handle_validation_error("This submission is not editable.")
        return row

    def _apply_payload(self, kind: str, row: Any, payload: dict) -> None:
        editable = self._editable_fields(kind)
        for field in editable:
            if field in payload:
                value = payload.get(field)
                if value == "":
                    value = None
                if field in self._date_fields(kind):
                    value = self._coerce_date(value)
                if field in self._decimal_fields(kind):
                    value = self._coerce_decimal(value)
                setattr(row, field, value)

    def _replace_request_lines_if_needed(self, kind: str, row: Any, payload: dict) -> None:
        if kind not in ("purchase_request", "sponsorship_form"):
            return
        if "products" not in payload:
            return
        products = payload.get("products") or []
        # Drop existing lines for this row (cascade on delete via relationship).
        self.db.query(PurchaseRequestLine).filter(
            PurchaseRequestLine.purchase_request_id == row.id
        ).delete(synchronize_session=False)
        for index, line_data in enumerate(products):
            if not isinstance(line_data, dict):
                continue
            self.db.add(
                PurchaseRequestLine(
                    purchase_request_id=row.id,
                    item_code=line_data.get("item_code"),
                    quantity=self._coerce_decimal(line_data.get("quantity")),
                    unit_price=self._coerce_decimal(line_data.get("unit_price")),
                    total=self._coerce_decimal(line_data.get("total")),
                    remark=line_data.get("remark"),
                    sort_order=index,
                )
            )

    def _editable_fields(self, kind: str) -> tuple[str, ...]:
        if kind == "complaint":
            return (
                "delivery_order_number",
                "complaint_date",
                "customer_type",
                "customer_type_others",
                "within_warranty",
                "product_type",
                "defects_discovered",
                "complaint_type",
                "defect_description",
                "product_code",
                "salesperson",
                "customer_name",
                "contact_person",
                "contact_number",
                "customer_address",
                "project_title",
            )
        if kind == "stock_inquiry":
            return (
                "salesperson",
                "product_code",
                "item_description",
                "project_customer",
                "project_name",
                "quantity",
                "delivery_date",
                "remark",
                "additional_remark",
            )
        return (
            "request_date",
            "customer_name",
            "project_title",
            "purpose",
            "delivery_address",
            "total_project_value",
            "total_project_value_text",
            "sponsor_subject",
            "expected_delivery_date",
            "expected_po_date",
            "requested_by",
            "external_reference",
        )

    @staticmethod
    def _date_fields(kind: str) -> tuple[str, ...]:
        if kind == "complaint":
            return ("complaint_date",)
        if kind in ("purchase_request", "sponsorship_form"):
            return ("request_date", "expected_delivery_date", "expected_po_date")
        return ()

    @staticmethod
    def _decimal_fields(kind: str) -> tuple[str, ...]:
        if kind in ("purchase_request", "sponsorship_form"):
            return ("total_project_value",)
        return ()

    @staticmethod
    def _coerce_date(value: Any) -> Optional[date]:
        if value is None or value == "":
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            try:
                return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
        return None

    @staticmethod
    def _coerce_decimal(value: Any) -> Optional[Decimal]:
        if value is None or value == "":
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    # ---------- Notifications ----------

    def _post_submit_notify(self, kind: str, row: Any) -> None:
        if kind == "complaint":
            from app.services.complaints_service import ComplaintService

            service = ComplaintService(self.db)
            try:
                service.notify_team_complaint_external_created(complaint_id=str(row.id))
            except Exception as e:  # noqa: BLE001
                logger.warning("Complaint submit notify failed: %s", e)
            try:
                service.get_or_create_view_token(str(row.id))
                self.db.commit()
            except Exception:  # noqa: BLE001
                pass
        elif kind == "stock_inquiry":
            from app.services.procurement_service import StockInquiryService

            service = StockInquiryService(self.db)
            try:
                service.get_or_create_view_token(str(row.id))
                self.db.commit()
            except Exception:  # noqa: BLE001
                pass
            try:
                service._notify_team_stock_inquiry(  # noqa: SLF001
                    inquiry_id=str(row.id),
                    agent_code="lead_time_enquiries",
                    team_assignment_code="project_sales",
                    title="New Stock Inquiry created",
                    intro_plain=(
                        "Dear Project Sales Team,\n\nA new stock inquiry has been "
                        "submitted via the user portal and requires your review."
                    ),
                    intro_html=(
                        "Dear Project Sales Team,<br /><br />A new stock inquiry has been "
                        "submitted via the user portal and requires your review."
                    ),
                    event_type="portal_submitted",
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("Stock inquiry submit notify failed: %s", e)
        else:  # purchase_request / sponsorship_form
            from app.services.procurement_service import PurchaseRequestService

            service = PurchaseRequestService(self.db)
            try:
                service.get_or_create_view_token(str(row.id))
                self.db.commit()
            except Exception:  # noqa: BLE001
                pass
            try:
                service._notify_team_on_external_pr_created(  # noqa: SLF001
                    header_id=str(row.id),
                    request_type=row.request_type,
                    request_number=row.request_number or "N/A",
                    project_title=row.project_title or "N/A",
                    base_url_override=None,
                    integration_action="created",
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("Purchase request submit notify failed: %s", e)

    # ---------- Attachment policy ----------

    def get_portal_attachment_type(self) -> AttachmentType:
        row = (
            self.db.query(AttachmentType)
            .filter(AttachmentType.code == PORTAL_ATTACHMENT_TYPE_CODE)
            .first()
        )
        if row is None:
            raise handle_validation_error(
                "Portal submission attachment type is not configured."
            )
        return row

    # ---------- Serializers ----------

    def _serialize_complaint_summary(self, row: Complaint) -> dict:
        return {
            "id": str(row.id),
            "kind": "complaint",
            "title": (row.defect_description or "Complaint")[:100],
            "reference": row.delivery_order_number,
            "status": row.status,
            "is_editable": bool(row.portal_draft_at) or row.status == "rejected",
            "is_draft": row.portal_draft_at is not None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def _serialize_complaint_detail(self, row: Complaint) -> dict:
        base = self._serialize_complaint_summary(row)
        base.update(
            {
                "delivery_order_number": row.delivery_order_number,
                "complaint_date": row.complaint_date.isoformat() if row.complaint_date else None,
                "customer_type": row.customer_type,
                "customer_type_others": row.customer_type_others,
                "within_warranty": row.within_warranty,
                "product_type": row.product_type,
                "defects_discovered": row.defects_discovered,
                "complaint_type": row.complaint_type,
                "defect_description": row.defect_description,
                "product_code": row.product_code,
                "salesperson": row.salesperson,
                "customer_name": row.customer_name,
                "contact_person": row.contact_person,
                "contact_number": row.contact_number,
                "customer_address": row.customer_address,
                "project_title": row.project_title,
            }
        )
        return base

    def _serialize_stock_inquiry_summary(self, row: StockInquiry) -> dict:
        return {
            "id": str(row.id),
            "kind": "stock_inquiry",
            "title": (row.product_code or "Stock Inquiry"),
            "reference": row.inquiry_number,
            "status": row.status,
            "rejection_reason": row.rejection_reason,
            "is_editable": bool(row.portal_draft_at) or row.status == "rejected",
            "is_draft": row.portal_draft_at is not None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def _serialize_stock_inquiry_detail(self, row: StockInquiry) -> dict:
        base = self._serialize_stock_inquiry_summary(row)
        base.update(
            {
                "salesperson": row.salesperson,
                "product_code": row.product_code,
                "item_description": row.item_description,
                "project_customer": row.project_customer,
                "project_name": row.project_name,
                "quantity": row.quantity,
                "delivery_date": row.delivery_date,
                "remark": row.remark,
                "additional_remark": row.additional_remark,
            }
        )
        return base

    def _serialize_request_summary(self, row: PurchaseRequestHeader) -> dict:
        return {
            "id": str(row.id),
            "kind": row.request_type,
            "title": row.project_title or row.sponsor_subject or "Request",
            "reference": row.request_number,
            "status": row.status,
            "approval_status": row.approval_status,
            "is_editable": bool(row.portal_draft_at) or row.status == "rejected",
            "is_draft": row.portal_draft_at is not None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def _serialize_request_detail(self, row: PurchaseRequestHeader) -> dict:
        base = self._serialize_request_summary(row)
        base.update(
            {
                "request_type": row.request_type,
                "request_date": row.request_date.isoformat() if row.request_date else None,
                "customer_name": row.customer_name,
                "project_title": row.project_title,
                "purpose": row.purpose,
                "delivery_address": row.delivery_address,
                "total_project_value": str(row.total_project_value) if row.total_project_value is not None else None,
                "total_project_value_text": row.total_project_value_text,
                "sponsor_subject": row.sponsor_subject,
                "expected_delivery_date": row.expected_delivery_date.isoformat() if row.expected_delivery_date else None,
                "expected_po_date": row.expected_po_date.isoformat() if row.expected_po_date else None,
                "requested_by": row.requested_by,
                "external_reference": row.external_reference,
                "products": [
                    {
                        "id": str(line.id),
                        "item_code": line.item_code,
                        "quantity": str(line.quantity) if line.quantity is not None else None,
                        "unit_price": str(line.unit_price) if line.unit_price is not None else None,
                        "total": str(line.total) if line.total is not None else None,
                        "remark": line.remark,
                    }
                    for line in sorted(row.lines or [], key=lambda l: l.sort_order or 0)
                ],
            }
        )
        return base
