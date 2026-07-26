"""Ingest AutoCount delivery orders (header + DODTL lines) — Slice 5.

REUSE the existing ``orders`` + ``order_lines`` tables rather than a new mirror:
a DO is a delivery order, and Sorento already has that entity. The ingested row
carries ``sync_source='autocount'`` (read-only in the UI, mutations 403 in
``OrderService``); native rows stay ``'manual'``. Idempotency + provenance are
tracked in the ``integration_references`` side table (entity_type
``delivery_orders``, source_ref = DocKey), never on the row itself.

Same contract as the flat masters and item packages: per-record verdict,
per-record SAVEPOINT isolation, adopt-by-code (``order_number = AC-{DocKey}``),
retryable-on-missing-reference, dry-run-writes-nothing.

Line resolution: every DODTL line's ``product_code`` AND ``location_code`` must
resolve (order_lines.product_id + warehouse_id are NOT NULL / RESTRICT). An
unresolvable code makes the WHOLE order retryable — the master may not have
synced yet — so the order is never written with a dangling line. Lines are
replaced wholesale on update (delete children, re-insert): the canonical DODTL
is authoritative for the order's contents.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.order import Order
from app.schemas.canonical_masters import CanonicalDeliveryOrder
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
from datetime import date, datetime

logger = logging.getLogger(__name__)

# The integration_references side table interpolates entity_type as a REAL table
# name in its existence check, so this must be the reused table ("orders"), not a
# logical "delivery_orders" (which would query a non-existent table and abort the
# transaction). source_ref = DocKey keeps DO rows distinct from any other orders
# linkage.
ENTITY_TYPE = "orders"


def _parse_date(value) -> date | None:
    """Parse AutoCount date strings. Local parser to avoid importing from
    app.api.v1.external (circular: that package __init__ imports this router)."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[: len(fmt) + 4], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


class DeliveryOrderIngestService:
    def __init__(self, db: Session, integration_id: Optional[str] = None):
        self.db = db
        self.integration_id = integration_id
        self.refs = IntegrationReferenceService(db)

    def ingest(self, records: list[dict], *, dry_run: bool = False) -> IngestResult:
        result = IngestResult(dry_run=dry_run)
        try:
            for raw in records:
                result.records.append(self._ingest_one(raw))
        finally:
            if dry_run:
                self.db.rollback()
        return result

    def _ingest_one(self, raw: dict) -> RecordResult:
        source_ref = raw.get("source_ref") if isinstance(raw, dict) else None
        try:
            payload = CanonicalDeliveryOrder(**raw)
        except ValidationError as exc:
            return RecordResult(source_ref=source_ref, outcome=IngestOutcome.FAILED,
                                errors=_field_errors(exc))
        except TypeError as exc:
            return RecordResult(source_ref=source_ref, outcome=IngestOutcome.FAILED,
                                errors={"_": str(exc)})

        savepoint = self.db.begin_nested()
        try:
            outcome, entity_id = self._apply(payload)
            savepoint.commit()
            return RecordResult(source_ref=payload.source_ref, outcome=outcome, entity_id=entity_id)
        except MissingReference as exc:
            savepoint.rollback()
            return RecordResult(source_ref=payload.source_ref, outcome=IngestOutcome.RETRYABLE,
                                errors={exc.field_name: f"not found: {exc.code}"})
        except ReferenceConflict as exc:
            savepoint.rollback()
            return RecordResult(source_ref=payload.source_ref, outcome=IngestOutcome.FAILED,
                                errors={"source_ref": str(exc)})
        except Exception as exc:  # noqa: BLE001 - one record's failure, not the batch's
            savepoint.rollback()
            logger.warning("delivery_order.record_failed source_ref=%s error=%s", payload.source_ref, exc)
            return RecordResult(source_ref=payload.source_ref, outcome=IngestOutcome.FAILED,
                                errors={"_": str(exc)})

    def _resolve_lines(self, payload: CanonicalDeliveryOrder) -> list[dict]:
        """Resolve every line's product_code -> product_id and location_code ->
        warehouse_id. A miss raises MissingReference (retryable) BEFORE any write,
        so the order is never partially applied. Location resolves by warehouse
        code OR name."""
        resolved = []
        for i, line in enumerate(payload.lines, start=1):
            prod = self.db.execute(
                text("SELECT id FROM products WHERE product_code = :c LIMIT 1"),
                {"c": line.product_code},
            ).first()
            if prod is None:
                raise MissingReference("product_code", line.product_code)
            wh = self.db.execute(
                text(
                    "SELECT id FROM warehouses "
                    "WHERE warehouse_code = :c OR warehouse_name = :c LIMIT 1"
                ),
                {"c": line.location_code},
            ).first()
            if wh is None:
                raise MissingReference("location_code", line.location_code)
            resolved.append({
                "line_sequence": i,
                "product_id": str(prod[0]),
                "warehouse_id": str(wh[0]),
                "quantity": line.qty if line.qty is not None else Decimal("0"),
                "unit_price": line.unit_price,
                "discount": line.discount,
                "tax": line.tax,
                "total": line.sub_total,
            })
        return resolved

    def _resolve_customer_id(self, payload: CanonicalDeliveryOrder) -> Optional[str]:
        """Best-effort DebtorCode -> customers.id. The FK is SET NULL / nullable,
        so a miss is fine — debtor_code/name are still stored for display."""
        if not payload.debtor_code:
            return None
        row = self.db.execute(
            text("SELECT id FROM customers WHERE customer_code = :c LIMIT 1"),
            {"c": payload.debtor_code},
        ).first()
        return str(row[0]) if row is not None else None

    def _header_columns(self, payload: CanonicalDeliveryOrder) -> dict:
        return {
            "order_number": f"AC-{payload.source_ref}",
            "order_date": _parse_date(payload.order_date),
            "customer_id": self._resolve_customer_id(payload),
            "debtor_code": payload.debtor_code,
            "debtor_name": payload.debtor_name,
            "agent": payload.agent,
            "is_cancelled": bool(payload.is_cancelled),
            "sync_source": "autocount",
        }

    def _apply(self, payload: CanonicalDeliveryOrder) -> tuple[IngestOutcome, str]:
        # Resolve lines first: a missing product/warehouse aborts the whole order
        # as retryable before we touch any row.
        lines = self._resolve_lines(payload)
        cols = self._header_columns(payload)

        existing_id = self.refs.resolve(entity_type=ENTITY_TYPE, source_ref=payload.source_ref)
        if existing_id is None:
            adopted = self.db.execute(
                text("SELECT id FROM orders WHERE order_number = :n LIMIT 1"),
                {"n": cols["order_number"]},
            ).first()
            if adopted is not None:
                if self.refs.origin_of(entity_type=ENTITY_TYPE, entity_id=str(adopted[0])) is not None:
                    raise ReferenceConflict(
                        f"order_number={cols['order_number']!r} is already linked to another source"
                    )
                existing_id = str(adopted[0])

        if existing_id is not None:
            self._update_header(existing_id, cols)
            self._replace_lines(existing_id, lines)
            self._link(existing_id, payload)
            return IngestOutcome.UPDATED, existing_id

        new_id = str(uuid.uuid4())
        self._insert_header(new_id, cols)
        self._replace_lines(new_id, lines)
        self._link(new_id, payload)
        return IngestOutcome.CREATED, new_id

    def _insert_header(self, order_id: str, cols: dict) -> None:
        # Use the ORM (not raw INSERT) so orders' many client-side NOT NULL
        # defaults (kpi_warning, *_amount, synced_to_excel, ...) are applied --
        # a raw INSERT omitting them violates the NOT NULL constraints.
        self.db.add(Order(id=order_id, **cols))
        self.db.flush()

    def _update_header(self, order_id: str, cols: dict) -> None:
        # order_number is the adopt key; never rewrite it on update.
        order = self.db.query(Order).filter(Order.id == order_id).one()
        for key, value in cols.items():
            if key == "order_number":
                continue
            setattr(order, key, value)
        self.db.flush()

    def _replace_lines(self, order_id: str, lines: list[dict]) -> None:
        # Canonical DODTL is authoritative; a merge would orphan a removed line.
        self.db.execute(text("DELETE FROM order_lines WHERE order_id = :o"), {"o": order_id})
        for line in lines:
            self.db.execute(
                text(
                    "INSERT INTO order_lines "
                    "(id, order_id, line_sequence, product_id, warehouse_id, "
                    " quantity, unit_price, discount, tax, total) "
                    "VALUES (:id, :order_id, :line_sequence, :product_id, :warehouse_id, "
                    " :quantity, :unit_price, :discount, :tax, :total)"
                ),
                {"id": str(uuid.uuid4()), "order_id": order_id, **line},
            )

    def _link(self, order_id: str, payload: CanonicalDeliveryOrder) -> None:
        self.refs.link(
            entity_type=ENTITY_TYPE,
            entity_id=order_id,
            source_ref=payload.source_ref,
            source_doc_no=payload.source_doc_no,
            integration_id=self.integration_id,
        )
