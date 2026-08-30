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
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.canonical_masters import _Canonical


class _CanonicalLine(BaseModel):
    """Shared line rules. Not `_Canonical`: a line has no `source_doc_no`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # AutoCount's DtlKey. The upsert key within the document, which is what lets
    # a line keep its Sorento id - and therefore its allocations - across syncs.
    source_ref: str = Field(..., min_length=1, max_length=255)
    # Integration reference of the product, never a code: a code is unique per
    # company only, while the ref already names one row. REQUIRED, because
    # `product_id` is NOT NULL on both line tables - a line without it is not a
    # line that can exist.
    product_ref: str = Field(..., min_length=1, max_length=255)
    warehouse_ref: Optional[str] = Field(None, max_length=255)
    qty_ordered: Decimal = Field(..., ge=0)
    discount: Optional[Decimal] = None
    line_total: Optional[Decimal] = None
    uom: Optional[str] = Field(None, max_length=100)


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
    lines: list[Any] = Field(default_factory=list)

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

    so_number: str = Field(..., min_length=1, max_length=100)
    customer_ref: Optional[str] = Field(None, max_length=255)
    sales_agent_ref: Optional[str] = Field(None, max_length=255)
    doc_date: Optional[date] = None
    requested_delivery_date: Optional[date] = None
    internal_note: Optional[str] = None
    lines: list[CanonicalSalesOrderLine] = Field(default_factory=list)


class CanonicalPurchaseOrder(_CanonicalDocument):
    po_number: str = Field(..., min_length=1, max_length=100)
    supplier_ref: Optional[str] = Field(None, max_length=255)
    issue_date: Optional[date] = None
    expected_date: Optional[date] = None
    currency: Optional[str] = Field(None, max_length=3)
    lines: list[CanonicalPurchaseOrderLine] = Field(default_factory=list)
