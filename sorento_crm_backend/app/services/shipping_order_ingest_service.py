"""Ingest DOCUMENTS pushed in by the ESB: shipping orders (D3/D5/D11, S3).

A shipping order has no header table. It is a GROUP of `spo_allocations` rows
sharing one `spo_number` (migration 420), so this is the one entity on the
ingest surface with no single `entity_id` to name in a verdict, and no
`integration_references` row to identify it by either: a push finds its rows
by `source_doc_ref` (AutoCount's DocKey), falling back to `spo_number` alone
for a document's first sync - exactly the way `DocumentIngestService._header`
adopts a v1 document by its number, without the reference lookup a header
row would otherwise give it.

Shares the ref/code/name/back-create ladder (`MasterRefResolver`) with
`DocumentIngestService` rather than duplicating it - both subclass it.
Everything else here is peculiar to a header-less document:

**A line still owns its identity.** AutoCount's DtlKey (`source_ref`) is the
upsert key within the document, same as a sales/purchase-order line - a line
keeps its row, and therefore its GRN links and order-link claims, across
every re-push.

**xlsx-era rows are adopted, not replaced (D11).** The purchase-history import
wrote thousands of `spo_allocations` rows before AutoCount owned any of them,
with no `source_ref` at all. The upload's OWN dedup key is `(product_id,
upper(location_code))` (`outstanding_import_service._spo_line_plans`), so
adoption matches on that same pair rather than on `warehouse_id` - the book
routinely names a location this system holds no warehouse row for. Exact
first (that pair plus `warehouse_id`-or-None and outstanding, all agreeing),
then the pair alone when exactly one candidate remains, then position
(`spo_line_number` order) when nothing else discriminates - the same
three-pass shape `document_ingest_service._adopt_lines` uses, with the roles
of "coarse, durable" and "tight, secondary" key components swapped to match
what a shipping-order row actually carries.

**A leftover line closes, it never deletes.** Same reason as a document line
(A3): `scm.order_link_claim.spo_allocation_id` and a GRN's picking line point
at the row's id, and removing it would either cascade a real receipt away or
orphan a pairing already made. `line_status='closed'` takes it out of
`scm.on_order_v` while leaving whatever points at it intact.

**Status is validated, not stored.** The row has no header column for it -
only `line_status` (`open`/`closed`), derived from quantities the same way
`outstanding_import_service._write_spo_lines` derives it. `cancelled` is the
one exception: it forces every line closed regardless of what is still
outstanding, since a cancelled shipment covers no demand however much of it
had already arrived. Every other canonical word is accepted for its
vocabulary check alone and changes nothing about how a line's own status is
computed.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from pydantic import ValidationError
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.procurement import SPOAllocation, Supplier
from app.models.product import Product
from app.schemas.canonical_documents import CanonicalShippingOrder
from app.services.document_ingest_service import SOURCE_SYSTEM
from app.services.integration_reference_service import (
    IntegrationReferenceService,
    ReferenceConflict,
)
from app.services.master_ingest_service import (
    IngestOutcome,
    IngestResult,
    MissingReference,
    RecordResult,
    _field_errors,
)
from app.services.master_ref_resolver import MasterRefResolver
from app.services.scm.outstanding_import_service import DEFAULT_PO_CURRENCY

logger = logging.getLogger(__name__)

# The entity name this service answers for. Read by the route so the one
# ingest endpoint dispatches to this service alongside `MasterIngestService`
# and `DocumentIngestService`, and by `deletion_service` for the same reason.
SHIPPING_ORDERS_ENTITY = "shipping_orders"
SHIPPING_ORDER_ENTITIES = frozenset({SHIPPING_ORDERS_ENTITY})

LINE_OPEN = "open"
LINE_CLOSED = "closed"
RECEIPT_PENDING = "pending"
RECEIPT_FULLY_RECEIVED = "fully_received"

# Canonical vocabulary check only - the row carries no header status column to
# map onto, so nothing here is ever stored verbatim. `cancelled` is the one
# word that changes what gets WRITTEN (every line forced closed); the other
# four are accepted and otherwise inert - a line's own `line_status` always
# comes from its quantities, never from this word.
STATUS_WORDS = frozenset({"open", "partial", "fulfilled", "closed", "cancelled"})


def _document_status(rows: list[SPOAllocation]) -> Optional[str]:
    """Live-derived canonical status for a read-back (AC-V3-6).

    There is no header status to read, so the answer is computed off what the
    rows currently show - the same three-way ladder a document's OWN status
    starts from before cancellation enters it: nothing received is `open`,
    everything received is `fulfilled`, anything in between is `partial`.
    """
    if not rows:
        return None
    ordered = sum(int(r.allocated_quantity or 0) for r in rows)
    received = sum(int(r.quantity_received or 0) for r in rows)
    if ordered > 0 and received >= ordered:
        return "fulfilled"
    if received > 0:
        return "partial"
    return "open"


@dataclass(frozen=True)
class _Verdict:
    outcome: IngestOutcome
    warnings: list[str]
    line_counts: dict[str, int]


class ShippingOrderIngestService(MasterRefResolver):
    """Same constructor and ``ingest()``/``RecordResult`` contract as its siblings.

    Subclasses `MasterRefResolver` for the ref/code/name/back-create ladder,
    shared with `DocumentIngestService` rather than duplicated.
    """

    def __init__(
        self, db: Session, integration_id: Optional[str] = None, *, company_id: str
    ):
        super().__init__(db, integration_id, company_id=company_id)

    # --------------------------------------------------------------- the batch
    def ingest(
        self, entity_type: str, records: list[dict], *, dry_run: bool = False
    ) -> IngestResult:
        result = IngestResult(dry_run=dry_run)
        try:
            for raw in records:
                result.records.append(self._ingest_one(raw))
        finally:
            if dry_run:
                # In a finally, so an error mid-batch cannot leave a partially
                # applied preview in the session for whatever commits next.
                self.db.rollback()
        return result

    def _ingest_one(self, raw: dict) -> RecordResult:
        source_ref = raw.get("source_ref") if isinstance(raw, dict) else None

        try:
            payload = CanonicalShippingOrder(**raw)
        except ValidationError as exc:
            return RecordResult(
                source_ref=source_ref,
                outcome=IngestOutcome.FAILED,
                errors=_field_errors(exc),
            )
        except TypeError as exc:
            return RecordResult(
                source_ref=source_ref, outcome=IngestOutcome.FAILED, errors={"_": str(exc)}
            )

        status_word = (payload.status or "").strip().lower()
        if status_word not in STATUS_WORDS:
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.FAILED,
                errors={
                    "status": (
                        f"unknown status {payload.status!r}; expected one of: "
                        f"{', '.join(sorted(STATUS_WORDS))}"
                    )
                },
            )
        force_closed = status_word == "cancelled"

        # One document per savepoint. Without it a failed flush poisons the
        # session and every later record in the file fails too.
        savepoint = self.db.begin_nested()
        try:
            verdict = self._apply(payload, force_closed)
            savepoint.commit()
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=verdict.outcome,
                # No header row exists for a shipping order (D3) - the verdict
                # cannot name one.
                entity_id=None,
                warnings=verdict.warnings,
                lines=verdict.line_counts,
            )
        except MissingReference as exc:
            savepoint.rollback()
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.RETRYABLE,
                errors={exc.field_name: f"not found: {exc.code}"},
            )
        except ReferenceConflict as exc:
            savepoint.rollback()
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.FAILED,
                errors={exc.field_name: str(exc)},
            )
        except Exception as exc:  # noqa: BLE001 - one document's failure, not the file's
            savepoint.rollback()
            logger.warning(
                "ingest.document_failed entity=%s source_ref=%s error=%s",
                SHIPPING_ORDERS_ENTITY,
                payload.source_ref,
                exc,
            )
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.FAILED,
                errors={"_": str(exc)},
            )

    # ------------------------------------------------------------ one document
    def _apply(self, payload: CanonicalShippingOrder, force_closed: bool) -> _Verdict:
        # EVERYTHING is resolved before ANYTHING is written - same rule as
        # `DocumentIngestService._apply`, for the same reason: an unresolved
        # reference has to leave the database exactly as it found it.
        warnings: list[str] = []
        supplier_id = self._resolve_master(
            model=Supplier,
            ref_field="supplier_ref",
            ref=payload.supplier_ref,
            code_field="supplier_code",
            code=payload.supplier_code,
            name=payload.supplier_name,
            warnings=warnings,
        )
        currency = payload.currency or DEFAULT_PO_CURRENCY

        line_values = [
            self._line_values(payload, line, index, supplier_id, currency, warnings)
            for index, line in enumerate(payload.lines)
        ]

        rows = self._existing_rows(payload)
        outcome = IngestOutcome.UPDATED if rows else IngestOutcome.CREATED
        by_ref, pool, dup_ref = self._split_rows(rows)

        counts = {"adopted": 0, "created": 0, "updated": 0, "deleted": 0, "cancelled": 0}

        unmatched: list[dict[str, Any]] = []
        for values in line_values:
            row = by_ref.pop(values["source_ref"], None)
            if row is not None:
                self._write_row(row, values, force_closed)
                counts["updated"] += 1
            else:
                unmatched.append(values)

        if unmatched and pool:
            self._adopt_lines(unmatched, pool, counts, force_closed)

        next_number = max([r.spo_line_number or 0 for r in rows], default=0)
        for values in unmatched:
            next_number += 1
            row = SPOAllocation(
                id=str(uuid.uuid4()),
                company_id=self.company_id,
                spo_number=payload.spo_number,
                spo_line_number=next_number,
            )
            self.db.add(row)
            self._write_row(row, values, force_closed)
            counts["created"] += 1

        # A leftover row - the payload no longer names it - is ALWAYS closed,
        # never deleted (D3/D11), unlike a document's own line sweep. A
        # shipping order's ref-less pool routinely holds rows another push
        # will restate later, and a claim or a picking line can point at ANY
        # of them; explicit removal is the deletion endpoint's job
        # (`DeletionService._delete_shipping_order`), not a side effect of a
        # re-push that simply stopped naming a line this time.
        for row in [*by_ref.values(), *pool, *dup_ref]:
            row.line_status = LINE_CLOSED
            counts["cancelled"] += 1
        self.db.flush()
        return _Verdict(outcome=outcome, warnings=warnings, line_counts=counts)

    def _existing_rows(self, payload: CanonicalShippingOrder) -> list[SPOAllocation]:
        """This document's rows: by DocKey, or by DocNo when none carries one yet."""
        return (
            self.db.query(SPOAllocation)
            .filter(
                SPOAllocation.company_id == self.company_id,
                or_(
                    SPOAllocation.source_doc_ref == payload.source_ref,
                    and_(
                        SPOAllocation.spo_number == payload.spo_number,
                        SPOAllocation.source_doc_ref.is_(None),
                    ),
                ),
            )
            .all()
        )

    def _split_rows(
        self, rows: list[SPOAllocation]
    ) -> tuple[dict[str, SPOAllocation], list[SPOAllocation], list[SPOAllocation]]:
        by_ref: dict[str, SPOAllocation] = {}
        pool: list[SPOAllocation] = []
        # A second row sharing a ref another row already claims cannot happen
        # under the partial unique index, but the ladder below defends the
        # invariant rather than assuming the constraint always wins the race.
        dup_ref: list[SPOAllocation] = []
        for row in rows:
            if row.source_ref and row.source_ref not in by_ref:
                by_ref[row.source_ref] = row
            elif row.source_ref:
                dup_ref.append(row)
            else:
                pool.append(row)
        return by_ref, pool, dup_ref

    def _line_values(
        self,
        payload: CanonicalShippingOrder,
        line: Any,
        index: int,
        supplier_id: Optional[str],
        currency: str,
        warnings: list[str],
    ) -> dict[str, Any]:
        product_id = self._resolve_master(
            model=Product,
            ref_field=f"lines.{index}.product_ref",
            ref=line.product_ref,
            code_field=f"lines.{index}.product_code",
            code=line.product_code,
            name=line.product_name,
            warnings=warnings,
        )
        warehouse_id = self._resolve_master(
            model=Warehouse,
            ref_field=f"lines.{index}.warehouse_ref",
            ref=line.warehouse_ref,
            code_field=f"lines.{index}.warehouse_code",
            code=line.warehouse_code,
            name=None,
            warnings=warnings,
        )
        location_code = self._location_code(warehouse_id, line.warehouse_code)

        ordered = line.qty_ordered or Decimal("0")
        received = line.qty_received or Decimal("0")
        outstanding = ordered - received

        return {
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "location_code": location_code,
            "allocated_quantity": int(ordered),
            "quantity_received": int(received),
            "unit_cost": line.unit_cost,
            # A line's own date, when sent, is more specific than the
            # document's - falling back to it keeps every row dated even when
            # only the header states one.
            "expected_date": line.expected_date or payload.expected_date,
            "receipt_status": RECEIPT_PENDING if outstanding > 0 else RECEIPT_FULLY_RECEIVED,
            "line_status": LINE_OPEN if outstanding > 0 else LINE_CLOSED,
            "source_system": SOURCE_SYSTEM,
            "source_ref": line.source_ref,
            "source_doc_ref": payload.source_ref,
            "supplier_id": supplier_id,
            "issue_date": payload.issue_date,
            "currency": currency,
            # AutoCount's Seq (D11), position only - popped before persistence
            # by `_write_row`. No column exists for it on this table either.
            "line_number": getattr(line, "line_number", None),
        }

    def _location_code(
        self, warehouse_id: Optional[str], sent_code: Optional[str]
    ) -> Optional[str]:
        """The sent `warehouse_code`, or the resolved warehouse's own code.

        Adoption (D11) matches ref-less xlsx-era rows on this column - if a
        resolved-by-ref line wrote nothing here, its own resolved warehouse
        would never match the code the book already holds.
        """
        if sent_code:
            return sent_code
        if not warehouse_id:
            return None
        return (
            self.db.query(Warehouse.warehouse_code)
            .filter(Warehouse.id == warehouse_id)
            .scalar()
        )

    def _write_row(
        self, row: SPOAllocation, values: dict[str, Any], force_closed: bool
    ) -> None:
        values = dict(values)
        values.pop("line_number", None)
        for column, value in values.items():
            setattr(row, column, value)
        if force_closed:
            # `cancelled` (D3/D9): every line closes regardless of what is
            # still outstanding - a cancelled shipment covers no demand
            # however much of it had already arrived.
            row.line_status = LINE_CLOSED

    def _adopt_lines(
        self,
        unmatched: list[dict[str, Any]],
        pool: list[SPOAllocation],
        counts: dict[str, int],
        force_closed: bool,
    ) -> None:
        """D11: claim ref-less POOL rows for ref-less UNMATCHED incoming lines.

        Three ordered passes, mirroring `document_ingest_service._adopt_lines`
        with the durable/secondary roles swapped: `(product_id,
        upper(location_code))` is the pair that survives into pass 2 (the
        upload's own dedup key - `outstanding_import_service._spo_line_plans`),
        `warehouse_id`-or-None is the secondary component that only pass 1
        requires, since a legacy row routinely carries a location this system
        holds no warehouse row for.

        1. exact `(product_id, location, warehouse_id-or-None, outstanding)`
           key, ties among rows/lines sharing one key broken by position;
        2. `(product_id, location)` alone, only where exactly one pool row
           remains for it;
        3. position alone (incoming `line_number` order against the rows' own
           `spo_line_number` order), only where the remaining counts agree.
        """
        all_have_line_number = all(v.get("line_number") is not None for v in unmatched)

        def _position(idx: int, values: dict[str, Any]):
            return values["line_number"] if all_have_line_number else idx

        def _row_position(row: SPOAllocation):
            return (
                row.spo_line_number if row.spo_line_number is not None else 10**9,
                str(row.id),
            )

        def _location(code: Optional[str]) -> Optional[str]:
            return (code or "").strip().upper() or None

        def _row_key(row: SPOAllocation):
            outstanding = int(row.allocated_quantity or 0) - int(row.quantity_received or 0)
            return (
                str(row.product_id) if row.product_id else None,
                _location(row.location_code),
                str(row.warehouse_id) if row.warehouse_id else None,
                outstanding,
            )

        def _line_key(values: dict[str, Any]):
            outstanding = values["allocated_quantity"] - values["quantity_received"]
            return (
                str(values.get("product_id")) if values.get("product_id") else None,
                _location(values.get("location_code")),
                str(values.get("warehouse_id")) if values.get("warehouse_id") else None,
                outstanding,
            )

        def _coarse_row_key(row: SPOAllocation):
            return (
                str(row.product_id) if row.product_id else None,
                _location(row.location_code),
            )

        def _coarse_line_key(values: dict[str, Any]):
            return (
                str(values.get("product_id")) if values.get("product_id") else None,
                _location(values.get("location_code")),
            )

        claimed_lines: set[int] = set()
        claimed_rows: set[int] = set()

        def _claim(idx: int, values: dict[str, Any], row: SPOAllocation) -> None:
            self._write_row(row, values, force_closed)
            counts["adopted"] += 1
            claimed_lines.add(idx)
            claimed_rows.add(id(row))

        # ---- pass 1: exact (product, location, warehouse, outstanding) key ----
        pool_by_key: dict[tuple, list] = {}
        for row in pool:
            pool_by_key.setdefault(_row_key(row), []).append(row)
        for rows in pool_by_key.values():
            rows.sort(key=_row_position)

        lines_by_key: dict[tuple, list] = {}
        for idx, values in enumerate(unmatched):
            lines_by_key.setdefault(_line_key(values), []).append(idx)
        for indices in lines_by_key.values():
            indices.sort(key=lambda i: _position(i, unmatched[i]))

        for key, indices in lines_by_key.items():
            rows = pool_by_key.get(key, [])
            for idx, row in zip(indices, rows):
                _claim(idx, unmatched[idx], row)

        # ---- pass 2: (product, location) alone, exactly one row remaining ----
        remaining_indices = sorted(
            (i for i in range(len(unmatched)) if i not in claimed_lines),
            key=lambda i: _position(i, unmatched[i]),
        )
        coarse_pool: dict[tuple, list] = {}
        for row in pool:
            if id(row) in claimed_rows:
                continue
            coarse_pool.setdefault(_coarse_row_key(row), []).append(row)

        for idx in remaining_indices:
            values = unmatched[idx]
            key = _coarse_line_key(values)
            rows = coarse_pool.get(key)
            if rows and len(rows) == 1:
                row = rows[0]
                _claim(idx, values, row)
                coarse_pool[key] = []

        # ---- pass 3: position alone, only when the remaining counts agree ----
        remaining_indices = [i for i in range(len(unmatched)) if i not in claimed_lines]
        remaining_pool = [r for r in pool if id(r) not in claimed_rows]
        if remaining_indices and len(remaining_indices) == len(remaining_pool):
            remaining_indices.sort(key=lambda i: _position(i, unmatched[i]))
            remaining_pool.sort(key=_row_position)
            for idx, row in zip(remaining_indices, remaining_pool):
                _claim(idx, unmatched[idx], row)

        for idx in sorted(claimed_lines, reverse=True):
            del unmatched[idx]
        pool[:] = [r for r in pool if id(r) not in claimed_rows]


class ShippingOrderReadService:
    """Current shipping-order state for a batch of refs, in the ESB's vocabulary.

    Same contract as `DocumentReadService.current_state` - keyed by
    `source_doc_ref` rather than by `integration_references` (D3), since a
    shipping order has no single entity id to resolve one through.
    """

    def __init__(self, db: Session, *, company_id: str):
        self.db = db
        self.company_id = company_id
        self.refs = IntegrationReferenceService(db)

    def current_state(self, entity_type: str, source_refs: list[str]) -> dict[str, Any]:
        found: list[dict[str, Any]] = []
        not_found: list[str] = []

        for source_ref in source_refs:
            rows = (
                self.db.query(SPOAllocation)
                .filter(
                    SPOAllocation.company_id == self.company_id,
                    SPOAllocation.source_doc_ref == source_ref,
                )
                .order_by(SPOAllocation.spo_line_number)
                .all()
            )
            if not rows:
                not_found.append(source_ref)
                continue
            found.append(self._record(source_ref, rows))

        return {"records": found, "not_found": not_found}

    def _record(self, source_ref: str, rows: list[SPOAllocation]) -> dict[str, Any]:
        first = rows[0]
        return {
            "source_ref": source_ref,
            # No header row exists for a shipping order (D3).
            "entity_id": None,
            "spo_number": first.spo_number,
            "supplier_ref": self._ref_of(Supplier, first.supplier_id),
            "issue_date": first.issue_date,
            "expected_date": first.expected_date,
            "currency": first.currency,
            "status": _document_status(rows),
            "lines": [self._line(row) for row in rows],
        }

    def _line(self, row: SPOAllocation) -> dict[str, Any]:
        return {
            "entity_id": str(row.id),
            "source_ref": row.source_ref,
            "product_ref": self._ref_of(Product, row.product_id),
            "warehouse_ref": self._ref_of(Warehouse, row.warehouse_id),
            "qty_ordered": row.allocated_quantity,
            "qty_received": row.quantity_received,
            "unit_cost": row.unit_cost,
        }

    def _ref_of(self, model: type, entity_id: Optional[str]) -> Optional[str]:
        if not entity_id:
            return None
        origin = self.refs.origin_of(
            entity_type=model.__tablename__, entity_id=str(entity_id)
        )
        return str(origin.source_ref) if origin is not None else None
