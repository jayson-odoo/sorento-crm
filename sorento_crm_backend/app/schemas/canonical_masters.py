"""Canonical shapes for master data pushed in by the ESB (Phase C).

**Canonical, not AutoCount.** Sorento never sees `DocKey`, `AccNo` or `ItemCode`
— the ESB translates before it gets here. That boundary is what keeps vendor
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


class CanonicalCreditTerm(_Canonical):
    """AutoCount credit term. ``code`` is the DisplayTerm -- the value suppliers
    and customers carry as ``payment_terms_code`` and resolve against here."""

    code: str = Field(..., min_length=1, max_length=100)
    terms: Optional[str] = Field(None, max_length=255)
    term_days: Optional[int] = Field(None, ge=0, le=3650)
    is_active: bool = True


class CanonicalTaxCode(_Canonical):
    """AutoCount tax code. Resolve-target for document-line TaxCode in later
    slices. ``supply_purchase`` is 'S' or 'P'; ``tax_rate`` is a percentage."""

    code: str = Field(..., min_length=1, max_length=100)
    supply_purchase: Optional[str] = Field(None, max_length=1)
    tax_rate: Optional[Decimal] = Field(None, ge=0)
    is_active: bool = True


class CanonicalSalesAgent(_Canonical):
    """AutoCount SalesAgent (code == name). NOT the Respond.io access agent."""

    code: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    is_active: bool = True


class CanonicalPaymentMethod(_Canonical):
    code: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    bank_account: Optional[str] = Field(None, max_length=100)
    journal_type: Optional[str] = Field(None, max_length=100)
    is_active: bool = True


class CanonicalTaxEntity(_Canonical):
    """AutoCount e-Invoice tax party. ``code`` is the surrogate TaxEntityID."""

    code: str = Field(..., min_length=1, max_length=100)
    name: Optional[str] = Field(None, max_length=255)
    tin: Optional[str] = Field(None, max_length=100)
    identity_no: Optional[str] = Field(None, max_length=100)
    tax_branch_id: Optional[str] = Field(None, max_length=100)
    tax_classification: Optional[int] = None
    gst_register_no: Optional[str] = Field(None, max_length=100)
    sst_register_no: Optional[str] = Field(None, max_length=100)
    tourism_tax_register_no: Optional[str] = Field(None, max_length=100)
    trade_name: Optional[str] = Field(None, max_length=255)
    business_activity_desc: Optional[str] = Field(None, max_length=255)
    msic_code: Optional[str] = Field(None, max_length=40)
    address: Optional[str] = Field(None, max_length=255)
    post_code: Optional[str] = Field(None, max_length=40)
    city: Optional[str] = Field(None, max_length=100)
    state_code: Optional[str] = Field(None, max_length=40)
    country_code: Optional[str] = Field(None, max_length=40)
    phone: Optional[str] = Field(None, max_length=100)
    email_address: Optional[str] = Field(None, max_length=255)
    is_active: bool = True


class CanonicalItemPackageLine(BaseModel):
    """One PackageDTL line. Addressed by product code, resolved to a real
    product at ingest -- an unresolvable code makes the whole package retryable
    (the product may simply not have synced yet)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    product_code: str = Field(..., min_length=1, max_length=100)
    uom: Optional[str] = Field(None, max_length=100)
    qty: Optional[Decimal] = Field(None, ge=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)


class CanonicalItemPackage(_Canonical):
    """AutoCount item package (header + PackageDTL). ``code`` is the PackageCode,
    which is also the idempotency key (no DocKey for packages)."""

    code: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    expiry_date: Optional[str] = Field(None, max_length=40)
    limited_qty: Optional[Decimal] = Field(None, ge=0)
    opening_qty: Optional[Decimal] = Field(None, ge=0)
    user_uom: Optional[str] = Field(None, max_length=100)
    bar_code: Optional[str] = Field(None, max_length=100)
    further_description: Optional[str] = None
    is_active: bool = True
    lines: list[CanonicalItemPackageLine] = Field(default_factory=list)


class CanonicalStockBalanceRow(BaseModel):
    """One stock-balance report row. NOT a _Canonical: a report has no
    source_ref/DocKey. Product/location are addressed by code and resolved
    best-effort; an unresolvable code is kept raw, never rejected."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    item_code: str = Field(..., min_length=1, max_length=100)
    location_code: Optional[str] = Field(None, max_length=100)
    uom: Optional[str] = Field(None, max_length=100)
    batch_no: Optional[str] = Field(None, max_length=100)
    # Signed: a report can show negative on-hand.
    balance: Optional[Decimal] = None
    smallest_bal_qty: Optional[Decimal] = None
    standard_cost: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None
    average_cost: Optional[Decimal] = None
    rate: Optional[Decimal] = None
    description: Optional[str] = Field(None, max_length=255)


class CanonicalQuotationLine(BaseModel):
    """One QTDTL line. product_code must resolve (quotation_lines.product_id NOT
    NULL / RESTRICT); a miss makes the WHOLE quotation retryable."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    product_code: str = Field(..., min_length=1, max_length=100)
    uom: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=100)
    qty: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    sub_total: Optional[Decimal] = None
    discount_amt: Optional[Decimal] = None
    tax_code: Optional[str] = Field(None, max_length=100)
    tax_rate: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    description: Optional[str] = None
    further_description: Optional[str] = None
    package_code: Optional[str] = Field(None, max_length=100)
    proj_no: Optional[str] = Field(None, max_length=100)
    dept_no: Optional[str] = Field(None, max_length=100)


class CanonicalQuotation(_Canonical):
    """AutoCount sales quotation (header + QTDTL) -> NEW quotations +
    quotation_lines. ``source_ref`` is the DocKey; stored quote_number =
    AC-{DocKey}."""

    debtor_code: Optional[str] = Field(None, max_length=100)
    debtor_name: Optional[str] = Field(None, max_length=255)
    doc_date: Optional[str] = Field(None, max_length=40)
    is_cancelled: bool = False
    attention: Optional[str] = Field(None, max_length=255)
    branch_code: Optional[str] = Field(None, max_length=100)
    deliver_addr1: Optional[str] = Field(None, max_length=255)
    deliver_addr2: Optional[str] = Field(None, max_length=255)
    deliver_addr3: Optional[str] = Field(None, max_length=255)
    deliver_addr4: Optional[str] = Field(None, max_length=255)
    terms: Optional[str] = Field(None, max_length=255)
    sales_agent: Optional[str] = Field(None, max_length=100)
    lines: list[CanonicalQuotationLine] = Field(default_factory=list)


class CanonicalSalesOrderLine(BaseModel):
    """One SODTL line. product_code must resolve (sales_order_lines.product_id
    NOT NULL / RESTRICT); a miss makes the whole SO retryable. Location resolves
    to warehouse_id best-effort (that FK is nullable on the SCM line)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    product_code: str = Field(..., min_length=1, max_length=100)
    location: Optional[str] = Field(None, max_length=100)
    uom: Optional[str] = Field(None, max_length=100)
    qty: Optional[Decimal] = None
    transfered_qty: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    discount_amt: Optional[Decimal] = None
    tax_code: Optional[str] = Field(None, max_length=100)
    tax_rate: Optional[Decimal] = None
    tax_amt: Optional[Decimal] = None
    sub_total: Optional[Decimal] = None
    delivery_date: Optional[str] = Field(None, max_length=40)


class CanonicalSalesOrder(_Canonical):
    """AutoCount sales order (header + SODTL) -> REUSE sales_orders +
    sales_order_lines. ``source_ref`` is the DocKey; so_number = AC-{DocKey};
    source_system='autocount'."""

    debtor_code: Optional[str] = Field(None, max_length=100)
    doc_date: Optional[str] = Field(None, max_length=40)
    lines: list[CanonicalSalesOrderLine] = Field(default_factory=list)


class CanonicalPurchaseOrderLine(BaseModel):
    """One PODTL line. product_code must resolve (purchase_order_lines.product_id
    NOT NULL / RESTRICT). Location -> warehouse_id best-effort (nullable)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    product_code: str = Field(..., min_length=1, max_length=100)
    location: Optional[str] = Field(None, max_length=100)
    qty: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    description: Optional[str] = Field(None, max_length=500)
    sub_total: Optional[Decimal] = None


class CanonicalPurchaseOrder(_Canonical):
    """AutoCount purchase order (header + PODTL) -> REUSE purchase_orders +
    purchase_order_lines. ``source_ref`` = DocKey; po_number = AC-{DocKey};
    source_system='autocount'. Cancelled maps to status='cancelled'."""

    creditor_code: Optional[str] = Field(None, max_length=100)
    doc_date: Optional[str] = Field(None, max_length=40)
    is_cancelled: bool = False
    lines: list[CanonicalPurchaseOrderLine] = Field(default_factory=list)


class CanonicalRequestQuotationLine(BaseModel):
    """One RQDTL line. product_code must resolve (request_quotation_lines.
    product_id NOT NULL / RESTRICT); a miss makes the whole RFQ retryable."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    product_code: str = Field(..., min_length=1, max_length=100)
    uom: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=100)
    qty: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    sub_total: Optional[Decimal] = None


class CanonicalRequestQuotation(_Canonical):
    """AutoCount request-for-quotation (header + RQDTL) -> NEW request_quotations
    + request_quotation_lines. ``source_ref`` is the DocKey; stored rq_number =
    AC-{DocKey}. Supplier-keyed (CreditorCode)."""

    creditor_code: Optional[str] = Field(None, max_length=100)
    creditor_name: Optional[str] = Field(None, max_length=255)
    doc_date: Optional[str] = Field(None, max_length=40)
    purchase_agent: Optional[str] = Field(None, max_length=100)
    lines: list[CanonicalRequestQuotationLine] = Field(default_factory=list)


class CanonicalDeliveryOrderLine(BaseModel):
    """One DODTL line. Both product and location must resolve — order_lines has
    product_id AND warehouse_id NOT NULL (RESTRICT). An unresolvable code makes
    the WHOLE delivery order retryable (the master may not have synced yet), so
    the DO is never half-written."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    product_code: str = Field(..., min_length=1, max_length=100)
    location_code: str = Field(..., min_length=1, max_length=100)
    qty: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    sub_total: Optional[Decimal] = None


class CanonicalDeliveryOrder(_Canonical):
    """AutoCount delivery order (header + DODTL) → REUSE orders + order_lines.
    ``source_ref`` is the DocKey. The stored order_number is ``AC-{DocKey}`` so
    an ingested DO never collides with a native one."""

    debtor_code: Optional[str] = Field(None, max_length=100)
    debtor_name: Optional[str] = Field(None, max_length=255)
    order_date: Optional[str] = Field(None, max_length=40)
    agent: Optional[str] = Field(None, max_length=100)
    is_cancelled: bool = False
    lines: list[CanonicalDeliveryOrderLine] = Field(default_factory=list)


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
