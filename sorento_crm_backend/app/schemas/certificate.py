"""Certificate register schemas.

The response carries DERIVED validity (``validity_state`` / ``is_expired`` /
``days_until_expiry``) computed from the current revision at read time. None of
it is stored, and none of it may be sent in on a create or update - a client
that could write ``validity_state`` would be writing a fact that goes stale.
"""
from datetime import date, datetime
from typing import Any, ClassVar, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.certificate import (
    CERTIFICATE_SOURCE_MANUAL,
    CERTIFICATE_SOURCES,
    CERTIFICATE_STATUS_ACTIVE,
    CERTIFICATE_STATUSES,
)


def _blank_to_none(v: Any) -> Any:
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


class CertificateBase(BaseModel):
    scheme: str = Field(min_length=1, max_length=60)
    certificate_number: str = Field(min_length=1, max_length=120)
    certifying_body: Optional[str] = Field(default=None, max_length=120)
    issuer: Optional[str] = Field(default=None, max_length=200)
    title: Optional[str] = None
    attachment_type_id: Optional[str] = None

    @field_validator("certifying_body", "issuer", "title", "attachment_type_id", mode="before")
    @classmethod
    def _empty_string_is_null(cls, v):
        return _blank_to_none(v)


class CertificateCreate(CertificateBase):
    """Manual create. The optional revision fields file revision 1 in the same
    call, so a staff member who has the PDF in hand never has to make a second
    request to record when it expires."""

    status: str = CERTIFICATE_STATUS_ACTIVE
    attachment_id: Optional[str] = None
    issued_at: Optional[date] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    product_ids: Optional[List[str]] = None
    source: str = CERTIFICATE_SOURCE_MANUAL

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        if v not in CERTIFICATE_STATUSES:
            raise ValueError(f"status must be one of {', '.join(CERTIFICATE_STATUSES)}")
        return v

    @field_validator("source")
    @classmethod
    def _known_source(cls, v: str) -> str:
        if v not in CERTIFICATE_SOURCES:
            raise ValueError(f"source must be one of {', '.join(CERTIFICATE_SOURCES)}")
        return v


class CertificateUpdate(BaseModel):
    """Identity + lifecycle only. Dates live on a revision, coverage on
    ``certificate_products`` - neither is editable through here."""

    scheme: Optional[str] = Field(default=None, min_length=1, max_length=60)
    certificate_number: Optional[str] = Field(default=None, min_length=1, max_length=120)
    certifying_body: Optional[str] = Field(default=None, max_length=120)
    issuer: Optional[str] = Field(default=None, max_length=200)
    title: Optional[str] = None
    attachment_type_id: Optional[str] = None
    status: Optional[str] = None

    @field_validator("certifying_body", "issuer", "title", "attachment_type_id", mode="before")
    @classmethod
    def _empty_string_is_null(cls, v):
        return _blank_to_none(v)

    @field_validator("status")
    @classmethod
    def _known_status(cls, v):
        if v is not None and v not in CERTIFICATE_STATUSES:
            raise ValueError(f"status must be one of {', '.join(CERTIFICATE_STATUSES)}")
        return v


class CertificateEditRequest(CertificateUpdate):
    """PUT body: everything ``CertificateUpdate`` takes, plus the three dates.

    The dates are NOT certificate columns - they belong to the current revision,
    and the route applies them there. Only the keys the caller actually sent are
    forwarded: ``update_revision`` nulls any date it is handed as omitted, so a
    partial edit that touched the issuer would otherwise silently wipe the
    expiry.
    """

    issued_at: Optional[date] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None

    REVISION_FIELDS: ClassVar[tuple[str, ...]] = ("issued_at", "valid_from", "valid_until")

    def revision_fields_set(self) -> set[str]:
        return {f for f in self.REVISION_FIELDS if f in self.model_fields_set}


class CertificateProductAddRequest(BaseModel):
    """Body for ``POST /certificates/{id}/products``. Coverage added by a human
    is always ``manual`` - the source split is what stops an inferred link being
    presented as confirmed."""

    product_id: str


class BulkDeleteCertificatesRequest(BaseModel):
    """Body for ``DELETE /certificates/bulk``: { ids: string[] }."""

    ids: List[str]


class CertificateRef(BaseModel):
    """A certificate reduced to what can be rendered: never a bare id."""

    id: str
    scheme: str
    certificate_number: str


class CertificateReminderResponse(BaseModel):
    """One expiry reminder that actually went out for this certificate."""

    id: str
    days_before: Optional[int] = None
    sent_at: Optional[datetime] = None
    recipient_count: int = 0


class CertificateRevisionResponse(BaseModel):
    """One issue in the timeline. ``attachment_is_deleted`` is what lets the FE
    render a "file removed" node instead of dropping the revision."""

    id: str
    certificate_id: str
    revision_no: int
    attachment_id: Optional[str] = None
    attachment_filename: Optional[str] = None
    attachment_is_deleted: bool = False
    access_levels: Optional[List[str]] = None
    issued_at: Optional[date] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    is_current: bool = False
    source: str
    needs_review: bool = False
    review_reasons: List[dict] = []
    unmatched_products: List[str] = []
    extracted_json: Optional[dict] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class CertificateProductResponse(BaseModel):
    """One coverage row. Product code and name are resolved so no UUID reaches
    the UI."""

    id: str
    certificate_id: str
    product_id: str
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    source: str
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class CertificateResponse(BaseModel):
    id: str
    scheme: str
    certificate_number: str
    certifying_body: Optional[str] = None
    issuer: Optional[str] = None
    title: Optional[str] = None
    status: str
    attachment_type_id: Optional[str] = None
    attachment_type_name: Optional[str] = None
    possible_duplicate_of_certificate_id: Optional[str] = None
    possible_duplicate_of_label: Optional[str] = None
    expiry_notified_at: Optional[datetime] = None
    expiry_notify_batch_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None

    # --- from the CURRENT revision only ---
    current_revision_id: Optional[str] = None
    revision_no: Optional[int] = None
    issued_at: Optional[date] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    needs_review: bool = False
    review_reasons: List[dict] = []
    unmatched_products: List[str] = []

    # --- DERIVED at read time, never stored ---
    validity_state: str
    is_expired: bool = False
    days_until_expiry: Optional[int] = None
    covered_product_count: int = 0

    # --- signed on demand, CURRENT revision only (MCP-7 / MCP-8) ---
    # Populated when the caller asks for ``resolve_signed_urls``. Both stay null
    # when the current revision has no file or its attachment was trashed, so a
    # consumer is handed the live document or nothing, never a broken URL. A
    # superseded revision is never signed here.
    preview_url: Optional[str] = None
    download_url: Optional[str] = None

    # --- optionally expanded (detail page) ---
    revisions: Optional[List[CertificateRevisionResponse]] = None
    covered_products: Optional[List[CertificateProductResponse]] = None
    # Detail-page aliases and expansions. ``products`` mirrors
    # ``covered_products``; ``possible_duplicate_of`` resolves the pointer so the
    # UI renders "may be a renewal of PPS 04424FC" rather than an id.
    products: Optional[List[CertificateProductResponse]] = None
    current_revision: Optional[CertificateRevisionResponse] = None
    possible_duplicate_of: Optional[CertificateRef] = None
    reminders: Optional[List[CertificateReminderResponse]] = None

    class Config:
        from_attributes = True
