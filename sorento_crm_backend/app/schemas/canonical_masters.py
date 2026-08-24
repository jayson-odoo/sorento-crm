"""Canonical shapes for master data pushed in by the ESB (Phase C).

**Canonical, not AutoCount.** Sorento never sees `DocKey`, `AccNo` or `ItemCode`
 -  the ESB translates before it gets here. That boundary is what keeps vendor
quirks (`"T"`/`"F"` booleans, `Dtlkey` vs `DtlKey` casing, per-customer UDF
arrays) out of Sorento entirely.

Every model forbids unknown fields. A field the ESB believed it sent and Sorento
silently dropped is the worst kind of mapping bug: it looks like data loss on
our side and survives to production because nothing complains. Rejecting is
noisy and immediate.

Related records are addressed by **code, never by local id**. The ESB has no
knowledge of Sorento's UUIDs, and a code that does not resolve yet is a
sequencing artefact the ingest reports as retryable rather than invalid.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _Canonical(BaseModel):
    # extra="forbid" is the point of this layer, not a default worth relaxing.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # AutoCount's stable DocKey. The idempotency key: without it a re-push
    # cannot be told from a new record and every sync duplicates.
    source_ref: str = Field(..., min_length=1, max_length=255)
    # Human-facing document/account number. Display only -- expected to change.
    source_doc_no: Optional[str] = Field(None, max_length=100)


class CanonicalProductCategory(_Canonical):
    """Products cannot be created without a category (products.category_id is
    NOT NULL), so this must sync before products or every product reports
    retryable."""

    code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: bool = True


class CanonicalUnitOfMeasure(_Canonical):
    """Likewise for products.base_uom_id."""

    code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    # Canonical divisibility, 0..4 (front-planning plan 6.4). Absent means 0: an
    # upstream master that has never expressed precision counts in whole units.
    decimal_places: int = Field(0, ge=0, le=4)
    description: Optional[str] = None
    is_active: bool = True


class CanonicalWarehouse(_Canonical):
    code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    location: Optional[str] = Field(None, max_length=255)
    is_active: bool = True


class CanonicalSupplier(_Canonical):
    code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    contact_name: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=100)
    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=40)
    country: Optional[str] = Field(None, max_length=100)
    payment_terms_days: Optional[int] = Field(None, ge=0, le=3650)
    # Resolved against the payment-terms master once it exists (Phase D). Until
    # then an unresolvable code is reported retryable, never persisted.
    payment_terms_code: Optional[str] = Field(None, max_length=100)
    is_active: bool = True


class CanonicalCustomer(_Canonical):
    code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=100)
    registration_number: Optional[str] = Field(None, max_length=100)
    tax_id: Optional[str] = Field(None, max_length=100)
    credit_limit: Optional[Decimal] = Field(None, ge=0)
    payment_terms_days: Optional[int] = Field(None, ge=0, le=3650)
    payment_terms_code: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    is_active: bool = True


class CanonicalProduct(_Canonical):
    code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    # products.category_id and base_uom_id are NOT NULL, so these are how a
    # product becomes creatable at all. Unresolvable -> retryable, because the
    # category may simply not have been synced yet.
    category_code: Optional[str] = Field(None, max_length=100)
    uom_code: Optional[str] = Field(None, max_length=100)
    brand_code: Optional[str] = Field(None, max_length=100)
    list_price: Optional[Decimal] = Field(None, ge=0)
    cost_price: Optional[Decimal] = Field(None, ge=0)
    is_active: bool = True
