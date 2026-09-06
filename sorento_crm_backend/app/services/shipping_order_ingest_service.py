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
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.base import company_scope
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
    INTERNAL_ERROR_MESSAGE,
    IngestOutcome,
    IngestResult,
    MissingReference,
    RecordResult,
    _field_errors,
    integrity_conflict_errors,
)
from app.services.master_ref_resolver import MasterRefResolver, dedupe_warnings
from app.services.rules import shipping_order_rules
from app.services.rules.document_rules import derive_document_status
from app.services.scm import order_link_service
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

# D6/D7 (S3) verdict warnings - same fixed vocabulary convention as
# `master_ref_resolver`'s `WARN_*` constants.
WARN_CONTAINER_UNRESOLVED = "container_unresolved"
WARN_RECEIVED_LOCKED = "received_locked"


def _round_qty(value: Optional[Decimal]) -> int:
    """A canonical line quantity as a whole number, half-up (S3 review fix).

    `allocated_quantity`/`quantity_received` are INTEGER columns; the ESB's
    own figures are `Decimal` and occasionally fractional (a pack count, a
    weight-based line). `int(round(x))` is the exact technique
    `outstanding_import_service._spo_quantities` already uses for the same
    two columns, reused here rather than restated so the two channels that
    write this table cannot round differently.
    """
    return int(round(float(value or 0)))


def _document_status(rows: list[SPOAllocation]) -> Optional[str]:
    """Live-derived canonical status for a read-back (AC-V3-6).

    There is no header status to read, so the answer is computed off what the
    rows currently show. `closed` first (S5 review fix): every row closed -
    the whole-document shape a `cancelled` push (or a fully-superseded
    document) leaves behind - must read back `closed`, never re-derived as
    `open`/`fulfilled` from quantities that are no longer the reason the
    lines are closed. Short of that, the same three-way ladder a document's
    OWN status starts from before cancellation enters it: nothing received
    is `open`, everything received is `fulfilled`, anything in between is
    `partial`.
    """
    if not rows:
        return None
    if all(r.line_status == LINE_CLOSED for r in rows):
        return "closed"
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

    def __init__(self, db: Session, integration_id: Optional[str], *, company_id: str):
        super().__init__(db, integration_id, company_id=company_id)
        # D7 (S3): SPO numbers this batch touched, read by the route's
        # post-write forward-match hook (`app.api.v1.external.ingest
        # ._run_document_hooks`) after commit - same role
        # `DocumentIngestService.so_numbers` plays for its own hook.
        self.spo_numbers_touched: set[str] = set()

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
        # Security review (blocker 2): the forward-match batch-end sweep used
        # to run HERE, before the route's own `db.commit()`.
        # `forward_match_grn_lines_for_spo` commits on success and rolls back
        # on failure, so one exception mid-batch discarded every not-yet-
        # committed record of the batch while the route still answered 200
        # with entity ids. It now runs from the route's post-commit hook slot
        # (`app.api.v1.external.ingest._run_document_hooks`, dispatched off
        # `self.spo_numbers_touched`) instead, the same slot the SO/PO hooks
        # use - this service only RECORDS which SPO numbers were touched.
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
            logger.warning(
                "ingest.document_malformed entity=%s source_ref=%s",
                SHIPPING_ORDERS_ENTITY,
                source_ref,
                exc_info=True,
            )
            return RecordResult(
                source_ref=source_ref,
                outcome=IngestOutcome.FAILED,
                errors={"_": INTERNAL_ERROR_MESSAGE},
            )

        if payload.status is None:
            # D20 (S3, AC-P3-6): absent derives via the same shared function
            # the SO/PO side uses - all allocations received = closed, else
            # open. There is no header row to read an EXISTING status off
            # (D3), so `existing` is always `None` here; `cancelled` is
            # therefore never derived, only ever explicitly sent.
            line_dicts = [
                {"qty_ordered": line.qty_ordered, "qty_received": line.qty_received}
                for line in payload.lines
            ]
            status_word = derive_document_status(line_dicts, None)
        else:
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
        except IntegrityError as exc:
            # Fix round 4, BUG B: a unique-constraint race (two companies, or a
            # concurrent push of the same number) - named by constraint, never
            # by `str(exc)`'s full SQL statement.
            savepoint.rollback()
            logger.warning(
                "ingest.integrity_conflict entity=%s source_ref=%s",
                SHIPPING_ORDERS_ENTITY,
                payload.source_ref,
                exc_info=True,
            )
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.FAILED,
                errors=integrity_conflict_errors(exc),
            )
        except Exception:  # noqa: BLE001 - one document's failure, not the file's
            savepoint.rollback()
            # SEC3: never echo a non-domain exception's own message - it
            # routinely quotes SQL, a table/column name or a raw UUID.
            logger.warning(
                "ingest.document_failed entity=%s source_ref=%s",
                SHIPPING_ORDERS_ENTITY,
                payload.source_ref,
                exc_info=True,
            )
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.FAILED,
                errors={"_": INTERNAL_ERROR_MESSAGE},
            )

    # ------------------------------------------------------------ one document
    def _apply(self, payload: CanonicalShippingOrder, force_closed: bool) -> _Verdict:
        """Pins `company_scope` for the WHOLE record (security review advisory
        a / S9), same reason and same shape as `MasterIngestService._apply`:
        the ladder resolves references and the adoption pass runs ordinary
        ORM queries against company-scoped tables, and without this those
        queries are filtered by whatever the ambient session scope happens to
        be - which the `X-API-Key` principal's `None`/all-companies scope
        never narrows on its own.
        """
        with company_scope(self.db, frozenset({self.company_id})):
            return self._apply_scoped(payload, force_closed)

    def _apply_scoped(self, payload: CanonicalShippingOrder, force_closed: bool) -> _Verdict:
        # S2 review fix: refused before anything else - a conflicting OPEN
        # claim on this spo_number is a fact about the DOCUMENT, not about
        # any one reference on it, so it is checked before the ladder runs.
        self._guard_spo_number_conflict(payload)

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
        # D6 (S3): cleaned ONCE per document - every line of it stores the
        # same container, so there is no reason to re-clean per line.
        container_number = (
            shipping_order_rules.extract_container_number(payload.container_number)
            if payload.container_number
            else None
        )

        line_values = [
            self._line_values(payload, line, index, supplier_id, currency, warnings)
            for index, line in enumerate(payload.lines)
        ]

        rows = self._existing_rows(payload)
        outcome = IngestOutcome.UPDATED if rows else IngestOutcome.CREATED
        by_ref, pool, already_closed = self._split_rows(rows)

        counts = {"adopted": 0, "created": 0, "updated": 0, "deleted": 0, "cancelled": 0}

        unmatched: list[dict[str, Any]] = []
        for values in line_values:
            row = by_ref.pop(values["source_ref"], None)
            if row is not None:
                # D7 (S3): a received quantity is a fact of what physically
                # arrived, and an ESB push cannot pull it out from under a
                # GRN that already drew against it - the line is left
                # exactly as it was, and the record still lands (rest of the
                # document unaffected).
                guard = shipping_order_rules.received_guard(
                    row, values["allocated_quantity"], values["quantity_received"]
                )
                if guard == shipping_order_rules.GUARD_RECEIVED_LOCKED:
                    warnings.append(WARN_RECEIVED_LOCKED)
                    continue
                self._write_row(
                    row, values, force_closed,
                    container_number=container_number, warnings=warnings,
                )
                counts["updated"] += 1
            else:
                unmatched.append(values)

        if unmatched and pool:
            self._adopt_lines(
                unmatched, pool, counts, force_closed,
                container_number=container_number, warnings=warnings,
            )

        # S1 review fix: the NEXT number is the highest across every row this
        # `spo_number` has EVER carried, not just the rows THIS DocKey's own
        # query matched (`rows`, above, deliberately excludes another
        # DocKey's rows). A delete-and-recreate under a fresh DocKey - the
        # old one's rows now all closed, so S2's guard let this push through
        # - must not reuse a line number the retired DocKey already claimed.
        next_number = self._max_line_number(payload)
        for values in unmatched:
            next_number += 1
            row = SPOAllocation(
                id=str(uuid.uuid4()),
                company_id=self.company_id,
                spo_number=payload.spo_number,
                spo_line_number=next_number,
            )
            self.db.add(row)
            self._write_row(
                row, values, force_closed,
                container_number=container_number, warnings=warnings,
            )
            counts["created"] += 1

        # A leftover row - the payload no longer names it - is ALWAYS closed,
        # never deleted (D3/D11), unlike a document's own line sweep. A
        # shipping order's ref-less pool routinely holds rows another push
        # will restate later, and a claim or a picking line can point at ANY
        # of them; explicit removal is the deletion endpoint's job
        # (`DeletionService._delete_shipping_order`), not a side effect of a
        # re-push that simply stopped naming a line this time. `already_closed`
        # (S4) rows fall through here unchanged - they were excluded only
        # from adoption CANDIDACY, not from this sweep.
        for row in [*by_ref.values(), *pool, *already_closed]:
            row.line_status = LINE_CLOSED
            counts["cancelled"] += 1
        self.db.flush()
        self._write_order_link_claims(payload)
        self.spo_numbers_touched.add(payload.spo_number)
        return _Verdict(outcome=outcome, warnings=dedupe_warnings(warnings), line_counts=counts)

    def _write_order_link_claims(self, payload: CanonicalShippingOrder) -> None:
        """V4 (plan section 2.5), the shipping-order side of
        `DocumentIngestService._write_order_link_claims` - see that
        docstring for the shared rule. Runs after every row is flushed, so
        it queries by `source_doc_ref` rather than holding onto row objects
        built mid-`_apply` (some are new, some adopted, some merely updated).
        The claim-writing loop itself is `order_link_service
        .write_claims_for_lines` (S7 dedup), shared with
        `DocumentIngestService`'s own line claims.
        """
        wanted = [
            (line.source_ref, [n for n in (line.from_so_numbers or []) if n])
            for line in payload.lines
            if getattr(line, "from_so_numbers", None)
        ]
        if not wanted:
            return

        refs = [source_ref for source_ref, _ in wanted]
        rows = (
            self.db.query(SPOAllocation)
            .filter(
                SPOAllocation.company_id == self.company_id,
                SPOAllocation.source_doc_ref == payload.source_ref,
                SPOAllocation.source_ref.in_(refs),
            )
            .all()
        )
        order_link_service.write_claims_for_lines(
            self.db,
            company_id=self.company_id,
            document_number=payload.spo_number,
            rows=rows,
            wanted=wanted,
            id_attr="spo_allocation_id",
        )

    def _guard_spo_number_conflict(self, payload: CanonicalShippingOrder) -> None:
        """S2 review fix: refuse a push whose `spo_number` still has OPEN rows
        under a DIFFERENT DocKey - mirrors `DocumentIngestService._header`'s
        "two AutoCount documents claiming one Sorento order" guard for a
        document adopted by number. Rows that are all CLOSED under an old
        DocKey do NOT block - that is the delete-and-recreate path, where a
        fresh DocKey continues a number a since-retired DocKey used - they
        only count toward `_max_line_number` below.
        """
        conflict = (
            self.db.query(SPOAllocation.id)
            .filter(
                SPOAllocation.company_id == self.company_id,
                SPOAllocation.spo_number == payload.spo_number,
                SPOAllocation.line_status == LINE_OPEN,
                SPOAllocation.source_doc_ref.isnot(None),
                SPOAllocation.source_doc_ref != payload.source_ref,
            )
            .first()
        )
        if conflict is not None:
            raise ReferenceConflict(
                f"spo_number {payload.spo_number!r} is already linked to another source",
                field_name="spo_number",
            )

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

    def _max_line_number(self, payload: CanonicalShippingOrder) -> int:
        """S1 review fix: the highest `spo_line_number` across EVERY row this
        `spo_number` has ever carried in this company - not just the rows
        `_existing_rows` matched for THIS DocKey, which deliberately excludes
        another DocKey's rows even when S2's guard has let them stay (all
        closed, under a retired DocKey).
        """
        return (
            self.db.query(func.max(SPOAllocation.spo_line_number))
            .filter(
                SPOAllocation.company_id == self.company_id,
                SPOAllocation.spo_number == payload.spo_number,
            )
            .scalar()
            or 0
        )

    def _split_rows(
        self, rows: list[SPOAllocation]
    ) -> tuple[dict[str, SPOAllocation], list[SPOAllocation], list[SPOAllocation]]:
        """`(by_ref, pool, already_closed)`.

        A second row sharing one `source_ref` cannot happen - the partial
        unique index on `(company_id, source_ref)` forbids it - so there is
        no third "duplicate ref" bucket to defend against here.

        `already_closed` (S4 review fix): a ref-less row this system already
        closed - by an earlier absence, or the deletion endpoint - is not a
        live xlsx-era adoption candidate any more; matching a NEW DtlKey onto
        it would resurrect demand that was correctly retired. It still flows
        into `_apply`'s final leftover sweep unchanged.
        """
        by_ref: dict[str, SPOAllocation] = {}
        pool: list[SPOAllocation] = []
        already_closed: list[SPOAllocation] = []
        for row in rows:
            if row.source_ref:
                by_ref[row.source_ref] = row
            elif row.line_status == LINE_CLOSED:
                already_closed.append(row)
            else:
                pool.append(row)
        return by_ref, pool, already_closed

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

        # S3 review fix: round, half-up, exactly the way
        # `outstanding_import_service._spo_quantities` does for the same two
        # INTEGER columns - `int(Decimal("10.6"))` truncates to 10, silently
        # dropping outstanding demand a book that states a fractional pack
        # count actually named. Outstanding is computed off the ROUNDED
        # whole numbers, same as `_spo_quantities`'s own caller does.
        ordered = _round_qty(line.qty_ordered)
        received = _round_qty(line.qty_received)
        outstanding = ordered - received

        return {
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "location_code": location_code,
            "allocated_quantity": ordered,
            "quantity_received": received,
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
        self,
        row: SPOAllocation,
        values: dict[str, Any],
        force_closed: bool,
        *,
        container_number: Optional[str] = None,
        warnings: Optional[list[str]] = None,
    ) -> None:
        values = dict(values)
        values.pop("line_number", None)
        if "quantity_received" in values:
            # Security review (blocker 1), belt-and-suspenders on EVERY caller
            # of this method: `quantity_received` can never regress below what
            # the row already shows, even if some future path calls this
            # without first running `received_guard` - the guard call sites
            # (by-ref update, adoption) already refuse the whole write on a
            # regression, so this is normally a no-op, but a brand new row's
            # stored value is always 0/None and `max()` is a no-op there too.
            stored_received = int(getattr(row, "quantity_received", 0) or 0)
            values["quantity_received"] = max(stored_received, int(values["quantity_received"] or 0))
        for column, value in values.items():
            setattr(row, column, value)
        if force_closed:
            # `cancelled` (D3/D9): every line closes regardless of what is
            # still outstanding - a cancelled shipment covers no demand
            # however much of it had already arrived.
            row.line_status = LINE_CLOSED
        # D6 (S3): every allocation of the pushed document stores the cleaned
        # container - `None` when the payload named none, so an absent
        # header field never clears one a previous push (or the xlsx import)
        # already set here.
        if container_number:
            linked = shipping_order_rules.link_allocation_to_shipment(
                self.db, row, container_number, company_id=self.company_id
            )
            if not linked and warnings is not None:
                warnings.append(WARN_CONTAINER_UNRESOLVED)

    def _adopt_lines(
        self,
        unmatched: list[dict[str, Any]],
        pool: list[SPOAllocation],
        counts: dict[str, int],
        force_closed: bool,
        *,
        container_number: Optional[str] = None,
        warnings: Optional[list[str]] = None,
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

        def _claim(idx: int, values: dict[str, Any], row: SPOAllocation) -> bool:
            # Security review (blocker 1): the adoption path used to call
            # `_write_row` with no guard at all - a legacy xlsx-era row with a
            # real receipt on it could be adopted by an incoming line whose
            # `qty_ordered`/`qty_received` shrink below what was already
            # received, exactly the exposure `received_guard` already closed
            # on the by-ref update path. Guarded here the same way: on a
            # trip, this pairing is refused - the row is left completely
            # unchanged, and both the row and the incoming line remain
            # available to the next pass (or fall through to their normal
            # unmatched/leftover handling) rather than being claimed.
            guard = shipping_order_rules.received_guard(
                row, values["allocated_quantity"], values["quantity_received"]
            )
            if guard == shipping_order_rules.GUARD_RECEIVED_LOCKED:
                if warnings is not None:
                    warnings.append(WARN_RECEIVED_LOCKED)
                return False
            self._write_row(
                row, values, force_closed,
                container_number=container_number, warnings=warnings,
            )
            counts["adopted"] += 1
            claimed_lines.add(idx)
            claimed_rows.add(id(row))
            return True

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
