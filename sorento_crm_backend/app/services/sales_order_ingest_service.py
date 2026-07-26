"""Ingest AutoCount sales orders (header + SODTL) — Slice 8.

REUSE the existing SCM ``sales_orders`` + ``sales_order_lines``. These tables
already carry ``source_system`` / ``source_ref``, so provenance + idempotency use
those columns directly (WHERE source_system='autocount' AND source_ref=DocKey) --
no integration_references side table. so_number = AC-{DocKey}. The AutoCount rows
are read-only in the SCM UI (mutations 403 when source_system='autocount').

Same contract as the other ingesters: per-record verdict, per-record SAVEPOINT
isolation, retryable-on-missing-reference, dry-run-writes-nothing. A line whose
product has not synced makes the whole SO retryable (never half-written); lines
are replaced wholesale on update.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.order import SalesOrder
from app.schemas.canonical_masters import CanonicalSalesOrder
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


class SalesOrderIngestService:
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
            payload = CanonicalSalesOrder(**raw)
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
            logger.warning("sales_order.record_failed source_ref=%s error=%s", payload.source_ref, exc)
            return RecordResult(source_ref=payload.source_ref, outcome=IngestOutcome.FAILED,
                                errors={"_": str(exc)})

    def _resolve_lines(self, payload: CanonicalSalesOrder) -> list[dict]:
        resolved = []
        for i, line in enumerate(payload.lines, start=1):
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
                "qty_delivered": line.transfered_qty if line.transfered_qty is not None else 0,
                "line_status": "open",
                "source_system": SOURCE_SYSTEM,
                "source_ref": payload.source_ref,
                "unit_price": line.unit_price,
                "discount_amt": line.discount_amt,
                "tax_rate": line.tax_rate,
                "tax_amt": line.tax_amt,
                "sub_total": line.sub_total,
                "delivery_date": _parse_date(line.delivery_date),
                "uom": line.uom,
                "tax_code": line.tax_code,
            })
        return resolved

    def _resolve_customer_id(self, payload: CanonicalSalesOrder) -> Optional[str]:
        if not payload.debtor_code:
            return None
        row = self.db.execute(
            text("SELECT id FROM customers WHERE customer_code = :c LIMIT 1"),
            {"c": payload.debtor_code},
        ).first()
        return str(row[0]) if row is not None else None

    def _apply(self, payload: CanonicalSalesOrder) -> tuple[IngestOutcome, str]:
        lines = self._resolve_lines(payload)
        so_number = f"AC-{payload.source_ref}"
        header = {
            "customer_id": self._resolve_customer_id(payload),
            "order_date": _parse_date(payload.doc_date),
            "source_system": SOURCE_SYSTEM,
            "source_ref": payload.source_ref,
            "source_doc_no": payload.source_doc_no,
        }

        existing = self.db.execute(
            text(
                "SELECT id FROM sales_orders "
                "WHERE (source_system = :ss AND source_ref = :sr) OR so_number = :n LIMIT 1"
            ),
            {"ss": SOURCE_SYSTEM, "sr": payload.source_ref, "n": so_number},
        ).first()

        if existing is not None:
            so_id = str(existing[0])
            so = self.db.query(SalesOrder).filter(SalesOrder.id == so_id).one()
            for k, v in header.items():
                setattr(so, k, v)
            self.db.flush()
            self._replace_lines(so_id, lines)
            return IngestOutcome.UPDATED, so_id

        so_id = str(uuid.uuid4())
        self.db.add(SalesOrder(id=so_id, so_number=so_number, **header))
        self.db.flush()
        self._replace_lines(so_id, lines)
        return IngestOutcome.CREATED, so_id

    def _replace_lines(self, so_id: str, lines: list[dict]) -> None:
        self.db.execute(text("DELETE FROM sales_order_lines WHERE sales_order_id = :s"), {"s": so_id})
        for line in lines:
            names = ", ".join(["id", "sales_order_id", *line])
            binds = ", ".join([":id", ":sales_order_id", *(f":{c}" for c in line)])
            self.db.execute(
                text(f"INSERT INTO sales_order_lines ({names}) VALUES ({binds})"),
                {"id": str(uuid.uuid4()), "sales_order_id": so_id, **line},
            )
