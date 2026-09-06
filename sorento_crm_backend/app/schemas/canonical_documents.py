"""Canonical shapes for the DOCUMENTS the ESB pushes: sales and purchase orders.

The masters' rules all hold here (`canonical_masters`): canonical rather than
AutoCount, `extra="forbid"`, related records addressed by reference rather than
by a Sorento id. Three things are different, and each is a property of a
document rather than of a master:

**A document owns its lines.** They arrive nested, not as a second entity, so
one push is one atomic statement about the whole order. Splitting them would let
a header land without its lines - an order for nothing, which the netting reads
as fully covered demand.

**Its line key is the line's own.** `source_ref` on a line is AutoCount's
`DtlKey`, not a position: a line deleted upstream must not silently renumber the
ones after it onto each other's allocations. Two lines carrying the same key in
one record is therefore a validation failure rather than a last-one-wins, since
picking one would drop a quantity somebody ordered.

**Its status is a vocabulary.** Five canonical words - `open`, `partial`,
`fulfilled`, `closed`, `cancelled` - map onto two different Sorento vocabularies
(sales orders and purchase orders do not share theirs). The mapping lives in
`document_ingest_service`; what is fixed here is that `status` is required. A
document with no state is not a document anyone can plan against.

Money and quantity are `Decimal`, never float: these figures are summed into
what a customer is charged.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.canonical_masters import _Canonical

#: Each entry of `from_so_numbers` (V4) - length-capped like every other
#: document number on this surface, never a full row on its own.
_SoNumber = Annotated[str, Field(max_length=100)]


class _CanonicalLine(BaseModel):
    """Shared line rules. Not `_Canonical`: a line has no `source_doc_no`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # AutoCount's DtlKey. The upsert key within the document, which is what lets
    # a line keep its Sorento id - and therefore its allocations - across syncs.
    source_ref: str = Field(..., min_length=1, max_length=255)
    # Integration reference of the product, never a code: a code is unique per
    # company only, while the ref already names one row. Optional ONLY in the
    # sense that `product_code` may stand in for it (v2, D1) - the validator
    # below still requires one of the two, because `product_id` is NOT NULL on
    # both line tables and a line without either is not a line that can exist.
    product_ref: Optional[str] = Field(None, max_length=255)
    # v2 code/name fallback (D1). Products are never back-created - a code the
    # catalogue does not hold stays retryable, the same as an unresolved ref -
    # so `product_name` is accepted and never used: a typo must never become a
    # SKU. `warehouse_code` follows the same ref-then-code ladder as the ref,
    # but an unresolved SENT code lands NULL with a warning rather than
    # retryable (D10) - a warehouse is optional, a product is not.
    product_code: Optional[str] = Field(None, max_length=100)
    product_name: Optional[str] = Field(None, max_length=255)
    warehouse_ref: Optional[str] = Field(None, max_length=255)
    warehouse_code: Optional[str] = Field(None, max_length=100)
    qty_ordered: Decimal = Field(..., ge=0)
    discount: Optional[Decimal] = None
    line_total: Optional[Decimal] = None
    uom: Optional[str] = Field(None, max_length=100)
    # AutoCount's Seq (D11). Position only, for telling apart ref-less rows
    # that share the same (product, warehouse, outstanding) key at cutover -
    # never persisted, no column exists for it on either line table.
    line_number: Optional[int] = Field(None, ge=0)

    @model_validator(mode="after")
    def _product_ref_or_code(self):
        if not self.product_ref and not self.product_code:
            raise ValueError("product_ref or product_code is required")
        return self


class CanonicalSalesOrderLine(_CanonicalLine):
    qty_delivered: Optional[Decimal] = Field(Decimal("0"), ge=0)
    unit_price: Optional[Decimal] = None
    # PER LINE, not per header: one order routinely carries several dates and the
    # coverage timeline has no time axis without them (ADR-0011).
    required_date: Optional[date] = None


class CanonicalPurchaseOrderLine(_CanonicalLine):
    qty_received: Optional[Decimal] = Field(Decimal("0"), ge=0)
    unit_cost: Optional[Decimal] = None
    currency: Optional[str] = Field(None, max_length=3)
    expected_date: Optional[date] = None
    # V4 (plan section 2.5): the sales orders the ESB already knows this
    # purchase line is FOR. `str_strip_whitespace` (the model config above)
    # already strips each entry; blank ones are dropped here rather than
    # rejected - an ESB that sends `["SO-A", ""]` names one real number, not
    # a bad one. Absent or `[]` both mean "nothing to claim" (schema pin,
    # AC-V4 tests) - never a trigger of its own.
    from_so_numbers: Optional[list[_SoNumber]] = Field(None, max_length=50)

    @field_validator("from_so_numbers")
    @classmethod
    def _drop_blank_so_numbers(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        return [v for v in value if v] if value is not None else None


class _CanonicalDocument(_Canonical):
    # Canonical, mapped per document type in `document_ingest_service`. Required:
    # a document whose state nobody stated cannot be told from an open one, and
    # that difference is the whole of demand planning.
    status: str = Field(..., min_length=1, max_length=50)
    # Declared here so the validator below can read it, and re-declared with the
    # concrete line type by each subclass - which is what actually parses. `Any`
    # rather than `list[_CanonicalLine]` only because a mutable field's type is
    # invariant, so a narrowing subclass would be an override error for a
    # relationship that is correct.
    # `max_length` (SEC5): a cap on the CARDINALITY of the list, not on any one
    # line's own size - an unbounded array is the DOS surface a length limit
    # elsewhere on the line does not close.
    lines: list[Any] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def _line_refs_are_unique(self):
        """One DtlKey, one line.

        Two lines sharing a key cannot both be upserted onto it. Last-one-wins
        would drop a quantity the customer ordered, and it would do so silently
        on every sync - so the record is refused and quarantined instead.
        """
        seen: set[str] = set()
        duplicates: set[str] = set()
        for line in self.lines:
            if line.source_ref in seen:
                duplicates.add(line.source_ref)
            seen.add(line.source_ref)
        if duplicates:
            raise ValueError(f"duplicate line source_ref: {', '.join(sorted(duplicates))}")
        return self


class CanonicalSalesOrder(_CanonicalDocument):
    """`source_ref` is AutoCount's DocKey; `so_number` its DocNo.

    Both are needed and they are not interchangeable: the DocKey is stable and
    is what makes a re-push idempotent, while the DocNo is what the extract
    importer already wrote into `so_number` and is therefore the only thing a
    FIRST sync can adopt an existing row by.
    """

    # D20 (S2): optional here - absent, `document_ingest_service` derives it
    # via `document_rules.derive_document_status`. `CanonicalShippingOrder`
    # gets the same override for the same reason (D20 for SPO, S3) - see its
    # own comment below.
    status: Optional[str] = Field(None, min_length=1, max_length=50)
    so_number: str = Field(..., min_length=1, max_length=100)
    customer_ref: Optional[str] = Field(None, max_length=255)
    # v2 code/name fallback (D1/D2). `customer_code` is written to
    # `sales_orders.debtor_code` whenever sent, ref or no ref (D9); a customer
    # is back-created only when BOTH are present (D2) - the unique index is on
    # the pair, and a code-only row would collide with a later named one.
    # `max_length=50` (SEC4): matches `customers.customer_code`'s own
    # `String(50)` column - a longer value can only ever fail at INSERT.
    customer_code: Optional[str] = Field(None, max_length=50)
    customer_name: Optional[str] = Field(None, max_length=255)
    # D16/D8 (S2): used ONLY when back-creating a customer off (customer_code,
    # customer_name) - never applied to an existing row (that is what the
    # customers master push's own market_segment_code/region are for).
    customer_segment: Optional[str] = Field(None, max_length=50)
    customer_region: Optional[str] = Field(None, max_length=80)
    sales_agent_ref: Optional[str] = Field(None, max_length=255)
    agent_code: Optional[str] = Field(None, max_length=100)
    # v2 demand classification (D4). FILL-only: written to `sales_orders.order_type`
    # only when the header holds none yet, the same rule `customer_code` follows for
    # `debtor_code`. `demand_class` itself stays an unaccepted key (AC-V2-7) - it is
    # DERIVED from this ladder, never stated directly, so a payload naming it outright
    # would let a document claim a priority nothing here actually earned.
    order_type: Optional[str] = Field(None, max_length=50)
    doc_date: Optional[date] = None
    requested_delivery_date: Optional[date] = None
    internal_note: Optional[str] = None
    lines: list[CanonicalSalesOrderLine] = Field(default_factory=list, max_length=2000)


class CanonicalPurchaseOrder(_CanonicalDocument):
    # D20 (S2): same override as CanonicalSalesOrder.status - see its comment.
    status: Optional[str] = Field(None, min_length=1, max_length=50)
    po_number: str = Field(..., min_length=1, max_length=100)
    supplier_ref: Optional[str] = Field(None, max_length=255)
    # v2 code/name fallback (D1). `agent_code` is accepted for symmetry with
    # the sales-order shape but IGNORED here: a purchase order has no agent FK,
    # and there is nowhere on `purchase_orders` for it to land.
    # `max_length=50` (SEC4): matches `suppliers.supplier_code`'s own
    # `String(50)` column.
    supplier_code: Optional[str] = Field(None, max_length=50)
    supplier_name: Optional[str] = Field(None, max_length=255)
    agent_code: Optional[str] = Field(None, max_length=100)
    issue_date: Optional[date] = None
    expected_date: Optional[date] = None
    currency: Optional[str] = Field(None, max_length=3)
    # D6 (S3, AC-P3-7): AutoCount's `UDF_ShipOrder`. A purchase order the
    # payload flags this way is refused the same as an `SPO-` numbered one
    # (`document_ingest_service`'s D5 refusal) - a document number alone
    # misses a differently-numbered shipping order AutoCount still marks as
    # one.
    is_shipping_order: Optional[bool] = None
    lines: list[CanonicalPurchaseOrderLine] = Field(default_factory=list, max_length=2000)


class CanonicalShippingOrderLine(_CanonicalLine):
    """A shipping-order line - one `spo_allocations` row (D3, S3)."""

    qty_received: Optional[Decimal] = Field(Decimal("0"), ge=0)
    unit_cost: Optional[Decimal] = None
    expected_date: Optional[date] = None
    # V4, same rule as `CanonicalPurchaseOrderLine.from_so_numbers` - a
    # shipping-order line dedicates against a sales order exactly as a
    # purchase-order line does (`resolve()` decides which purchase table by
    # `spo_number`'s own family, not by which entity pushed the claim).
    from_so_numbers: Optional[list[_SoNumber]] = Field(None, max_length=50)

    @field_validator("from_so_numbers")
    @classmethod
    def _drop_blank_so_numbers(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        return [v for v in value if v] if value is not None else None


class CanonicalShippingOrder(_CanonicalDocument):
    """`source_ref` is AutoCount's DocKey; `spo_number` its DocNo.

    Unlike a sales or purchase order, this shape addresses no header table -
    `spo_number` and `spo_line_number` together ARE the identity of the rows
    it writes (D3). `from_so_numbers` (V4) lives on the LINE, the same as a
    purchase-order line's - see `CanonicalShippingOrderLine`.
    """

    # D20 (S3): optional, same override and same reason as
    # `CanonicalSalesOrder.status` - absent, `ShippingOrderIngestService`
    # derives it via `document_rules.derive_document_status` over the
    # pushed lines' own ordered/received quantities (all received = closed,
    # else open) - there is no header row to read an EXISTING status off,
    # unlike the SO/PO case, so derivation never sees anything but `None`.
    status: Optional[str] = Field(None, min_length=1, max_length=50)
    # `max_length=50` (review nit): matches `spo_allocations.spo_number`'s own
    # `String(50)` column - `sales_orders.so_number`/`purchase_orders.po_number`
    # are `String(100)`, which is why only THIS number is narrower.
    spo_number: str = Field(..., min_length=1, max_length=50)
    supplier_ref: Optional[str] = Field(None, max_length=255)
    # `max_length=50` (SEC4): matches `suppliers.supplier_code`'s own
    # `String(50)` column.
    supplier_code: Optional[str] = Field(None, max_length=50)
    supplier_name: Optional[str] = Field(None, max_length=255)
    # Accepted for symmetry with the other two documents but IGNORED here -
    # same reason as `CanonicalPurchaseOrder.agent_code`.
    agent_code: Optional[str] = Field(None, max_length=100)
    issue_date: Optional[date] = None
    expected_date: Optional[date] = None
    # D6 (S3): AutoCount's `PO.Ref` - cleaned through the shared
    # `shipping_order_rules.extract_container_number` before it lands on
    # every allocation of this document.
    container_number: Optional[str] = Field(None, max_length=100)
    currency: Optional[str] = Field(None, max_length=3)
    lines: list[CanonicalShippingOrderLine] = Field(default_factory=list, max_length=2000)
