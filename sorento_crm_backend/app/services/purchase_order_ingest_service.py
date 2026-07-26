"""Ingest AutoCount purchase orders (header + PODTL) — Slice 8.

REUSE the existing SCM ``purchase_orders`` + ``purchase_order_lines``. Provenance
+ idempotency via the existing ``source_system`` / ``source_ref`` columns
(WHERE source_system='autocount' AND source_ref=DocKey). po_number = AC-{DocKey}.
Cancelled -> status='cancelled'. AutoCount rows are read-only in the SCM UI.

Same contract as the other ingesters. A line whose product has not synced makes
the whole PO retryable; lines replaced wholesale on update.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.procurement import PurchaseOrder
from app.schemas.canonical_masters import CanonicalPurchaseOrder
from app.services.master_ingest_service import (
    IngestOutcome,
    IngestResult,
    MissingReference,
    RecordResult,
    _field_errors,
)
from datetime import date, datetime

logger = logging.getLogger(__name__)

SOURCE_SYSTEM = "autocount"


def _parse_date(value) -> date | None:
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


class PurchaseOrderIngestService:
    def __init__(self, db: Session, integration_id: Optional[str] = None):
        self.db = db
        self.integration_id = integration_id

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
            payload = CanonicalPurchaseOrder(**raw)
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
        except Exception as exc:  # noqa: BLE001
            savepoint.rollback()
            logger.warning("purchase_order.record_failed source_ref=%s error=%s", payload.source_ref, exc)
            return RecordResult(source_ref=payload.source_ref, outcome=IngestOutcome.FAILED,
                                errors={"_": str(exc)})

    def _resolve_lines(self, payload: CanonicalPurchaseOrder) -> list[dict]:
        resolved = []
        for line in payload.lines:
            prod = self.db.execute(
                text("SELECT id FROM products WHERE product_code = :c LIMIT 1"),
                {"c": line.product_code},
            ).first()
            if prod is None:
                raise MissingReference("product_code", line.product_code)
            wh_id = None
            if line.location:
                wh = self.db.execute(
                    text("SELECT id FROM warehouses WHERE warehouse_code = :c OR warehouse_name = :c LIMIT 1"),
                    {"c": line.location},
                ).first()
                wh_id = str(wh[0]) if wh is not None else None
            resolved.append({
                "product_id": str(prod[0]),
                "warehouse_id": wh_id,
                "qty_ordered": line.qty if line.qty is not None else 0,
                "qty_received": 0,
                "unit_cost": line.unit_price,
                "line_status": "open",
                "source_system": SOURCE_SYSTEM,
                "source_ref": payload.source_ref,
                "description": line.description,
                "sub_total": line.sub_total,
            })
        return resolved

    def _resolve_supplier_id(self, payload: CanonicalPurchaseOrder) -> Optional[str]:
        if not payload.creditor_code:
            return None
        row = self.db.execute(
            text("SELECT id FROM suppliers WHERE supplier_code = :c LIMIT 1"),
            {"c": payload.creditor_code},
        ).first()
        return str(row[0]) if row is not None else None

    def _apply(self, payload: CanonicalPurchaseOrder) -> tuple[IngestOutcome, str]:
        lines = self._resolve_lines(payload)
        po_number = f"AC-{payload.source_ref}"
        header = {
            "supplier_id": self._resolve_supplier_id(payload),
            "issue_date": _parse_date(payload.doc_date),
            "status": "cancelled" if payload.is_cancelled else "active",
            "source_system": SOURCE_SYSTEM,
            "source_ref": payload.source_ref,
            "source_doc_no": payload.source_doc_no,
        }

        existing = self.db.execute(
            text(
                "SELECT id FROM purchase_orders "
                "WHERE (source_system = :ss AND source_ref = :sr) OR po_number = :n LIMIT 1"
            ),
            {"ss": SOURCE_SYSTEM, "sr": payload.source_ref, "n": po_number},
        ).first()

        if existing is not None:
            po_id = str(existing[0])
            po = self.db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).one()
            for k, v in header.items():
                setattr(po, k, v)
            self.db.flush()
            self._replace_lines(po_id, lines)
            return IngestOutcome.UPDATED, po_id

        po_id = str(uuid.uuid4())
        self.db.add(PurchaseOrder(id=po_id, po_number=po_number, **header))
        self.db.flush()
        self._replace_lines(po_id, lines)
        return IngestOutcome.CREATED, po_id

    def _replace_lines(self, po_id: str, lines: list[dict]) -> None:
        # purchase_order_lines is company-scoped: carry the header's company_id
        # onto each raw-inserted line or the fail-closed SELECT filter hides them.
        company_id = self.db.execute(
            text("SELECT company_id FROM purchase_orders WHERE id = :p"), {"p": po_id}
        ).scalar()
        self.db.execute(text("DELETE FROM purchase_order_lines WHERE purchase_order_id = :p"), {"p": po_id})
        for line in lines:
            row = {"purchase_order_id": po_id, "company_id": company_id, **line}
            names = ", ".join(["id", *row])
            binds = ", ".join([":id", *(f":{c}" for c in row)])
            self.db.execute(
                text(f"INSERT INTO purchase_order_lines ({names}) VALUES ({binds})"),
                {"id": str(uuid.uuid4()), **row},
            )
