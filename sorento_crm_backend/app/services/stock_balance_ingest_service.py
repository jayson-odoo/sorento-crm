"""Ingest AutoCount stock balance pushes (contract 2.5, Foundryx SR5).

PLAN: `documentation/plans/autocount/PLAN-ingest-stock-balances-2-5.md` D1-D11.
UAC:  `documentation/plans/autocount/ingest-stock-balances-2-5-acceptance-criteria.md`.

`stock_balances` is not a master, a document or a shipping order - it never
back-creates, never adopts, never touches `integration_references` at all
(D3: `source_ref` is an echo key only, never stored). Its identity is the
(product, warehouse) pair, resolved fresh on every push - a small enough shape
that it gets its own service rather than another branch inside
`MasterIngestService`, which the module docstring there says is already
carrying three different fused semantics.

**Same envelope, different resolution.** `ingest()` returns the exact same
`IngestResult`/`RecordResult` dataclasses `MasterIngestService` does, so the
wire shape at `/external/ingest/stock_balances` is byte-identical in kind to
every other entity on this surface - only the resolution ladder underneath is
new. `delete()` does the same with `deletion_service`'s `DeletionResult`/
`DeletionRecordResult`.

**Only `quantity_on_hand` is ever written.** `reserved`, `damaged`,
`reorder_point` and `zone_id` are set by the CRM side (manual counts, picks,
zoning) and AutoCount has no opinion on any of them - D4's upsert touches one
column, full stop, on both a create (the model's own defaults handle the
rest) and an update (every other column is left exactly as it was).

**A deletion zeroes, it never removes.** D7: AutoCount deleting a stock
balance means "this pair no longer holds any quantity", not "forget this
pair ever existed" - the row (and whatever ledger/audit history points at
it) stays, at zero.

**Warehouse resolution never raises.** Unlike a product miss (retryable -
the row may simply not have synced yet), an unresolved or inactive warehouse
is `updated` with a fixed warning and nothing written - the same shape
`MasterRefResolver` already gives warehouses on every other ingest surface,
reused here via `WARN_WAREHOUSE_UNRESOLVED`.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.inventory import Stock
from app.services.deletion_service import (
    DeletionOutcome,
    DeletionRecordResult,
    DeletionResult,
)
from app.services.master_ingest_service import (
    INTERNAL_ERROR_MESSAGE,
    IngestOutcome,
    IngestResult,
    RecordResult,
    _field_errors,
)
from app.services.master_ref_resolver import WARN_WAREHOUSE_UNRESOLVED

logger = logging.getLogger(__name__)

#: D1. The one entity this service ingests, folded into `SUPPORTED_ENTITIES`
#: (`app/api/v1/external/ingest.py`) the same way `SHIPPING_ORDER_ENTITIES` is.
STOCK_BALANCE_ENTITIES = {"stock_balances"}

#: D2. The one new warning contract 2.5 introduces. A match WAS found (unlike
#: `WARN_WAREHOUSE_UNRESOLVED`) - it simply is not a place stock can be
#: booked into, so nothing is written for it either.
WARN_WAREHOUSE_INACTIVE = "warehouse_inactive"


class _StockBalanceRecord(BaseModel):
    """D3. `extra="forbid"`: an unmapped key is a wiring bug on the ESB's
    side, not data to silently drop. `item_description`/`uom_code` are the
    two named exceptions - accepted and ignored, display fields Sorento
    already resolves the product/uom by code.

    `qty` is a strict, non-negative int: a bool, a float or a numeric string
    are all exactly the kind of upstream mapping slip this validation exists
    to catch (AC-SB-9) - `0` is a legitimate, and common, incoming value.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_ref: str = Field(..., min_length=1, max_length=255)
    item_code: str = Field(..., min_length=1, max_length=255)
    location_code: str = Field(..., min_length=1, max_length=255)
    qty: StrictInt = Field(..., ge=0)
    item_description: Optional[str] = None
    uom_code: Optional[str] = None


def _resolve_warehouse(db: Session, company_id: str, location_code: str):
    """(`id`, `is_active`) for the warehouse this pair names, trimmed +
    case-insensitive, scoped to `company_id` explicitly (never ambient
    session scope) - the same match `autocount_pull_service.classify_stock_rows`
    uses for the Pull side of this same table. `None` when nothing matches."""
    row = db.execute(
        text(
            "SELECT id, is_active FROM warehouses "
            "WHERE company_id = :cid AND upper(btrim(warehouse_code)) = upper(btrim(:code)) "
            "LIMIT 1"
        ),
        {"cid": company_id, "code": location_code},
    ).first()
    return row


def _resolve_product(db: Session, company_id: str, item_code: str) -> Optional[str]:
    """The product id this pair's `item_code` names, trimmed + case-insensitive,
    scoped to `company_id` explicitly. `None` when nothing matches (retryable -
    the master push may simply not have drained yet)."""
    row = db.execute(
        text(
            "SELECT id FROM products "
            "WHERE company_id = :cid AND upper(btrim(product_code)) = upper(btrim(:code)) "
            "LIMIT 1"
        ),
        {"cid": company_id, "code": item_code},
    ).first()
    return str(row[0]) if row else None


def _find_stock_row(db: Session, company_id: str, product_id: str, warehouse_id: str):
    return (
        db.query(Stock)
        .filter(
            Stock.company_id == company_id,
            Stock.product_id == product_id,
            Stock.warehouse_id == warehouse_id,
        )
        .first()
    )


class StockBalanceIngestService:
    """Same constructor shape as `MasterIngestService`/`DeletionService` -
    `integration_id` is accepted for parity with that call convention but
    unused: `stock_balances` never touches `integration_references` (D3)."""

    def __init__(
        self, db: Session, integration_id: Optional[str] = None, *, company_id: str
    ):
        self.db = db
        self.integration_id = integration_id
        # Required, not defaulted, for the same reason every other ingest
        # surface requires it (see `master_ingest_service`'s own docstring):
        # a default would be the incumbent company, and a push meant for the
        # other one would land there silently.
        self.company_id = company_id

    # ------------------------------------------------------------- ingest
    def ingest(
        self, entity_type: str, records: list[dict], *, dry_run: bool = False
    ) -> IngestResult:
        """D5/D6: one savepoint per record, input order, dry run resolves and
        applies exactly like a real run and is then rolled back - the same
        contract `MasterIngestService.ingest` documents at length.

        A dry run's own rollback is scoped to a SAVEPOINT wrapping this whole
        batch, taken via `begin_nested()` rather than a bare `self.db
        .rollback()`: this call is one write in a session a caller may
        already hold other not-yet-committed work on (a route sharing one
        request-scoped session, or - the same shape this surface's own tests
        rely on - a test fixture that seeds a row with `flush()` alone,
        never `commit()`, then calls a dry run and expects that seed to
        survive it). A session-level rollback would discard that too; a
        SAVEPOINT undoes only what THIS batch did.
        """
        result = IngestResult(dry_run=dry_run)
        batch_savepoint = self.db.begin_nested() if dry_run else None
        try:
            for raw in records:
                result.records.append(self._ingest_one(raw))
        finally:
            if batch_savepoint is not None:
                batch_savepoint.rollback()
        return result

    def _ingest_one(self, raw: dict) -> RecordResult:
        source_ref = raw.get("source_ref") if isinstance(raw, dict) else None
        try:
            payload = _StockBalanceRecord(**raw)
        except ValidationError as exc:
            return RecordResult(
                source_ref=source_ref,
                outcome=IngestOutcome.FAILED,
                errors=_field_errors(exc),
            )
        except TypeError:
            logger.warning(
                "stock_balance_ingest.record_malformed source_ref=%s", source_ref,
                exc_info=True,
            )
            return RecordResult(
                source_ref=source_ref,
                outcome=IngestOutcome.FAILED,
                errors={"_": INTERNAL_ERROR_MESSAGE},
            )

        # Each record commits or rolls back alone - without this a failed
        # flush poisons the session and every later record in the batch
        # fails too.
        savepoint = self.db.begin_nested()
        try:
            record = self._apply(payload)
            savepoint.commit()
            return record
        except Exception:  # noqa: BLE001 - one record's failure, not the batch's
            savepoint.rollback()
            logger.warning(
                "stock_balance_ingest.record_failed source_ref=%s", payload.source_ref,
                exc_info=True,
            )
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.FAILED,
                errors={"_": INTERNAL_ERROR_MESSAGE},
            )

    def _apply(self, payload: _StockBalanceRecord) -> RecordResult:
        # D4 step 2: location, before item - an unresolved/inactive warehouse
        # never even looks at the item code.
        warehouse = _resolve_warehouse(self.db, self.company_id, payload.location_code)
        if warehouse is None:
            # D6: an `updated` verdict always carries SOME diff shape on a
            # dry run - `{}` here, the same "nothing changed" answer an
            # unchanged upsert gives, since nothing was written either way.
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.UPDATED,
                entity_id=None,
                diff={},
                warnings=[WARN_WAREHOUSE_UNRESOLVED],
            )
        warehouse_id, warehouse_active = str(warehouse[0]), bool(warehouse[1])
        if not warehouse_active:
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.UPDATED,
                entity_id=None,
                diff={},
                warnings=[WARN_WAREHOUSE_INACTIVE],
            )

        # D4 step 3: item code, company-scoped, trimmed + case-insensitive.
        product_id = _resolve_product(self.db, self.company_id, payload.item_code)
        if product_id is None:
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.RETRYABLE,
                errors={"item_code": f"not found: {payload.item_code}"},
            )

        # D4 step 4: upsert. `quantity_on_hand` ONLY, never reserved/damaged/
        # reorder_point/zone_id.
        existing = _find_stock_row(self.db, self.company_id, product_id, warehouse_id)
        if existing is None:
            row = Stock(
                product_id=product_id,
                warehouse_id=warehouse_id,
                company_id=self.company_id,
                quantity_on_hand=payload.qty,
                updated_at=datetime.utcnow(),
            )
            self.db.add(row)
            self.db.flush()
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.CREATED,
                entity_id=str(row.id),
                diff=None,
            )

        current_qty = existing.quantity_on_hand
        diff: Optional[dict[str, dict[str, Any]]] = (
            {} if current_qty == payload.qty else {
                "qty": {"current": current_qty, "incoming": payload.qty}
            }
        )
        existing.quantity_on_hand = payload.qty
        existing.updated_at = datetime.utcnow()
        self.db.flush()
        return RecordResult(
            source_ref=payload.source_ref,
            outcome=IngestOutcome.UPDATED,
            entity_id=str(existing.id),
            diff=diff,
        )

    # ------------------------------------------------------------ deletions
    def delete(
        self, source_refs: list[str], pairs: dict, *, dry_run: bool = False
    ) -> DeletionResult:
        """D7. `pairs` is `{source_ref: {item_code, location_code}}` - unlike
        every other deletion entity there is no reference to resolve through;
        the pair IS the identity, exactly as on the ingest side.

        Same SAVEPOINT-scoped dry-run rollback as `ingest()` - see that
        docstring for why a bare `self.db.rollback()` is not used here.
        """
        result = DeletionResult(dry_run=dry_run)
        batch_savepoint = self.db.begin_nested() if dry_run else None
        try:
            for ref in source_refs:
                key = ref if isinstance(ref, str) else str(ref)
                result.records.append(self._delete_one(key, pairs.get(key) if isinstance(pairs, dict) else None))
        finally:
            if batch_savepoint is not None:
                batch_savepoint.rollback()
        return result

    def _delete_one(self, ref: str, pair: Any) -> DeletionRecordResult:
        if pair is None:
            return DeletionRecordResult(source_ref=ref, outcome=DeletionOutcome.NOT_FOUND)
        if not isinstance(pair, dict):
            return DeletionRecordResult(source_ref=ref, outcome=DeletionOutcome.FAILED)

        item_code = pair.get("item_code")
        location_code = pair.get("location_code")
        if (
            not isinstance(item_code, str)
            or not item_code.strip()
            or not isinstance(location_code, str)
            or not location_code.strip()
        ):
            return DeletionRecordResult(source_ref=ref, outcome=DeletionOutcome.FAILED)

        savepoint = self.db.begin_nested()
        try:
            warehouse = _resolve_warehouse(self.db, self.company_id, location_code)
            if warehouse is None:
                savepoint.commit()
                return DeletionRecordResult(source_ref=ref, outcome=DeletionOutcome.NOT_FOUND)
            warehouse_id, warehouse_active = str(warehouse[0]), bool(warehouse[1])
            if not warehouse_active:
                savepoint.commit()
                return DeletionRecordResult(
                    source_ref=ref,
                    outcome=DeletionOutcome.NOT_FOUND,
                    warnings=[WARN_WAREHOUSE_INACTIVE],
                )

            product_id = _resolve_product(self.db, self.company_id, item_code)
            if product_id is None:
                savepoint.commit()
                return DeletionRecordResult(source_ref=ref, outcome=DeletionOutcome.NOT_FOUND)

            existing = _find_stock_row(self.db, self.company_id, product_id, warehouse_id)
            if existing is None:
                savepoint.commit()
                return DeletionRecordResult(source_ref=ref, outcome=DeletionOutcome.NOT_FOUND)

            existing.quantity_on_hand = 0
            existing.updated_at = datetime.utcnow()
            self.db.flush()
            savepoint.commit()
            return DeletionRecordResult(
                source_ref=ref, outcome=DeletionOutcome.DELETED, entity_id=str(existing.id)
            )
        except Exception:  # noqa: BLE001 - one record's failure, not the batch's
            savepoint.rollback()
            logger.warning(
                "stock_balance_ingest.deletion_failed source_ref=%s", ref, exc_info=True
            )
            return DeletionRecordResult(
                source_ref=ref, outcome=DeletionOutcome.FAILED, errors={"_": INTERNAL_ERROR_MESSAGE}
            )

    # ------------------------------------------------------------- read-back
    def current_state(self, source_refs: list[str], pairs: dict) -> dict[str, Any]:
        """D8. `{records: [{source_ref, qty}], not_found: [...]}` for a batch
        of pairs - optional on the contract, implemented because the entity
        set on this surface drives the route regardless of whether any
        caller uses it yet."""
        records: list[dict[str, Any]] = []
        not_found: list[str] = []
        for ref in source_refs:
            key = ref if isinstance(ref, str) else str(ref)
            pair = pairs.get(key) if isinstance(pairs, dict) else None
            row = None
            if isinstance(pair, dict):
                item_code = pair.get("item_code")
                location_code = pair.get("location_code")
                if isinstance(item_code, str) and isinstance(location_code, str):
                    warehouse = _resolve_warehouse(self.db, self.company_id, location_code)
                    if warehouse is not None:
                        product_id = _resolve_product(self.db, self.company_id, item_code)
                        if product_id is not None:
                            row = _find_stock_row(
                                self.db, self.company_id, product_id, str(warehouse[0])
                            )
            if row is None:
                not_found.append(key)
            else:
                records.append({"source_ref": key, "qty": row.quantity_on_hand})
        return {"records": records, "not_found": not_found}
