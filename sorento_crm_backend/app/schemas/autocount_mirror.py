"""Response + annotation schemas for AutoCount read-only mirror entities.

Every mirror response carries ``source`` so the frontend gates read-only on one
uniform field (AC-G3). For new mirror tables (credit_terms, tax_codes, ...) only
ingest ever creates a row, so ``source`` is always "autocount"; the field still
ships for a uniform FE contract with the reused tables (orders/SO/PO) where it is
computed from provenance.

Annotation is the ONLY write the UI performs on a mirror: two Sorento-only
columns the ingest column-map never touches, so they survive re-sync (AC-G2).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict


class MirrorAnnotationUpdate(BaseModel):
    """PATCH body. Only these two columns may be written from the UI."""

    model_config = ConfigDict(extra="forbid")
    internal_note: Optional[str] = None
    follow_up: Optional[bool] = None


class _MirrorBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    is_active: bool
    internal_note: Optional[str] = None
    follow_up: bool = False
    source: Literal["autocount", "manual"] = "autocount"
    created_at: datetime
    updated_at: Optional[datetime] = None


class CreditTermResponse(_MirrorBase):
    display_term: str
    terms: Optional[str] = None
    term_days: Optional[int] = None


class TaxCodeResponse(_MirrorBase):
    tax_code: str
    supply_purchase: Optional[str] = None
    tax_rate: Optional[Decimal] = None


class SalesAgentResponse(_MirrorBase):
    sales_agent: str
    description: Optional[str] = None


class PaymentMethodResponse(_MirrorBase):
    payment_method: str
    description: Optional[str] = None
    bank_account: Optional[str] = None
    journal_type: Optional[str] = None


class ItemPackageLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    product_id: str
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    line_sequence: int
    uom: Optional[str] = None
    qty: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None


class ItemPackageResponse(_MirrorBase):
    package_code: str
    description: Optional[str] = None
    expiry_date: Optional[date] = None
    limited_qty: Optional[Decimal] = None
    opening_qty: Optional[Decimal] = None
    user_uom: Optional[str] = None
    bar_code: Optional[str] = None
    further_description: Optional[str] = None
    lines: List[ItemPackageLineResponse] = []


class QuotationLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    product_id: str
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    line_sequence: int
    uom: Optional[str] = None
    location: Optional[str] = None
    qty: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    sub_total: Optional[Decimal] = None
    discount_amt: Optional[Decimal] = None
    tax_code: Optional[str] = None
    tax_rate: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    description: Optional[str] = None
    further_description: Optional[str] = None
    package_code: Optional[str] = None
    proj_no: Optional[str] = None
    dept_no: Optional[str] = None


class RequestQuotationLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    product_id: str
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    line_sequence: int
    uom: Optional[str] = None
    location: Optional[str] = None
    qty: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    sub_total: Optional[Decimal] = None


class RequestQuotationResponse(BaseModel):
    """Supplier RFQ document mirror. Same annotation + provenance shape as the
    quotation mirror; supplier-keyed instead of debtor-keyed."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    rq_number: str
    source_doc_no: Optional[str] = None
    supplier_id: Optional[str] = None
    supplier_code: Optional[str] = None
    supplier_name: Optional[str] = None
    creditor_code: Optional[str] = None
    creditor_name: Optional[str] = None
    doc_date: Optional[date] = None
    purchase_agent: Optional[str] = None
    internal_note: Optional[str] = None
    follow_up: bool = False
    source: Literal["autocount", "manual"] = "autocount"
    created_at: datetime
    updated_at: Optional[datetime] = None
    lines: List[RequestQuotationLineResponse] = []


class QuotationResponse(BaseModel):
    """Quotation document mirror. NOT a _MirrorBase (that forces is_active — a
    quotation has is_cancelled instead). Same annotation + provenance shape."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    quote_number: str
    source_doc_no: Optional[str] = None
    debtor_code: Optional[str] = None
    debtor_name: Optional[str] = None
    doc_date: Optional[date] = None
    is_cancelled: bool = False
    attention: Optional[str] = None
    branch_code: Optional[str] = None
    deliver_addr1: Optional[str] = None
    deliver_addr2: Optional[str] = None
    deliver_addr3: Optional[str] = None
    deliver_addr4: Optional[str] = None
    terms: Optional[str] = None
    sales_agent: Optional[str] = None
    internal_note: Optional[str] = None
    follow_up: bool = False
    source: Literal["autocount", "manual"] = "autocount"
    created_at: datetime
    updated_at: Optional[datetime] = None
    lines: List[QuotationLineResponse] = []


class StockBalanceSnapshotRunResponse(BaseModel):
    """A stock-balance run header -- one per ingest. The 'run selector' lists
    these; the annotation lives here (rows are ephemeral)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    captured_at: datetime
    row_count: int
    source: str = "autocount"
    internal_note: Optional[str] = None
    follow_up: bool = False
    created_at: datetime


class StockBalanceSnapshotRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    item_code: str
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    location_code: Optional[str] = None
    warehouse_id: Optional[str] = None
    uom: Optional[str] = None
    batch_no: Optional[str] = None
    balance: Optional[Decimal] = None
    smallest_bal_qty: Optional[Decimal] = None
    standard_cost: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None
    average_cost: Optional[Decimal] = None
    rate: Optional[Decimal] = None
    description: Optional[str] = None


class StockBalanceSnapshotRunDetailResponse(StockBalanceSnapshotRunResponse):
    rows: List[StockBalanceSnapshotRowResponse] = []


class TaxEntityResponse(_MirrorBase):
    tax_entity_id: str
    name: Optional[str] = None
    tin: Optional[str] = None
    identity_no: Optional[str] = None
    tax_branch_id: Optional[str] = None
    tax_classification: Optional[int] = None
    gst_register_no: Optional[str] = None
    sst_register_no: Optional[str] = None
    tourism_tax_register_no: Optional[str] = None
    trade_name: Optional[str] = None
    business_activity_desc: Optional[str] = None
    msic_code: Optional[str] = None
    address: Optional[str] = None
    post_code: Optional[str] = None
    city: Optional[str] = None
    state_code: Optional[str] = None
    country_code: Optional[str] = None
    phone: Optional[str] = None
    email_address: Optional[str] = None
