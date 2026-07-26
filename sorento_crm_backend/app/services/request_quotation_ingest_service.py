"""Ingest AutoCount request-for-quotations (header + RQDTL lines) — Slice 7.

New parent+lines document mirror (supplier RFQ). Same contract as the flat
masters / item packages / quotations: per-record verdict, per-record SAVEPOINT
isolation, adopt-by-code (``rq_number = AC-{DocKey}``),
retryable-on-missing-reference, dry-run-writes-nothing. Idempotency + provenance
via ``integration_references`` (entity_type ``request_quotations``,
source_ref = DocKey).

Line resolution: every RQDTL line's ``product_code`` must resolve
(request_quotation_lines.product_id NOT NULL / RESTRICT). An unresolvable code
makes the WHOLE RFQ retryable. The header's supplier is resolved best-effort
(CreditorCode -> suppliers; the FK is nullable, so a miss keeps the raw code).
Lines are replaced wholesale on update.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.request_quotation import RequestQuotation
from app.schemas.canonical_masters import CanonicalRequestQuotation
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

ENTITY_TYPE = "request_quotations"


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


class RequestQuotationIngestService:
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
            payload = CanonicalRequestQuotation(**raw)
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
            logger.warning("request_quotation.record_failed source_ref=%s error=%s", payload.source_ref, exc)
            return RecordResult(source_ref=payload.source_ref, outcome=IngestOutcome.FAILED,
                                errors={"_": str(exc)})

    def _resolve_lines(self, payload: CanonicalRequestQuotation) -> list[dict]:
        resolved = []
        for i, line in enumerate(payload.lines, start=1):
            row = self.db.execute(
                text("SELECT id FROM products WHERE product_code = :c LIMIT 1"),
                {"c": line.product_code},
            ).first()
            if row is None:
                raise MissingReference("product_code", line.product_code)
            resolved.append({
                "line_sequence": i,
                "product_id": str(row[0]),
                "uom": line.uom,
                "location": line.location,
                "qty": line.qty,
                "unit_price": line.unit_price,
                "sub_total": line.sub_total,
            })
        return resolved

    def _resolve_supplier_id(self, payload: CanonicalRequestQuotation) -> Optional[str]:
        if not payload.creditor_code:
            return None
        row = self.db.execute(
            text("SELECT id FROM suppliers WHERE supplier_code = :c LIMIT 1"),
            {"c": payload.creditor_code},
        ).first()
        return str(row[0]) if row is not None else None

    def _header_columns(self, payload: CanonicalRequestQuotation) -> dict:
        return {
            "rq_number": f"AC-{payload.source_ref}",
            "source_doc_no": payload.source_doc_no,
            "supplier_id": self._resolve_supplier_id(payload),
            "creditor_code": payload.creditor_code,
            "creditor_name": payload.creditor_name,
            "doc_date": _parse_date(payload.doc_date),
            "purchase_agent": payload.purchase_agent,
        }

    def _apply(self, payload: CanonicalRequestQuotation) -> tuple[IngestOutcome, str]:
        lines = self._resolve_lines(payload)
        cols = self._header_columns(payload)

        existing_id = self.refs.resolve(entity_type=ENTITY_TYPE, source_ref=payload.source_ref)
        if existing_id is None:
            adopted = self.db.execute(
                text("SELECT id FROM request_quotations WHERE rq_number = :n LIMIT 1"),
                {"n": cols["rq_number"]},
            ).first()
            if adopted is not None:
                if self.refs.origin_of(entity_type=ENTITY_TYPE, entity_id=str(adopted[0])) is not None:
                    raise ReferenceConflict(
                        f"rq_number={cols['rq_number']!r} is already linked to another source"
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

    def _insert_header(self, rq_id: str, cols: dict) -> None:
        self.db.add(RequestQuotation(id=rq_id, **cols))
        self.db.flush()

    def _update_header(self, rq_id: str, cols: dict) -> None:
        rq = self.db.query(RequestQuotation).filter(RequestQuotation.id == rq_id).one()
        for key, value in cols.items():
            if key == "rq_number":
                continue
            setattr(rq, key, value)
        self.db.flush()

    def _replace_lines(self, rq_id: str, lines: list[dict]) -> None:
        self.db.execute(
            text("DELETE FROM request_quotation_lines WHERE request_quotation_id = :q"),
            {"q": rq_id},
        )
        for line in lines:
            names = ", ".join(["id", "request_quotation_id", *line])
            binds = ", ".join([":id", ":request_quotation_id", *(f":{c}" for c in line)])
            self.db.execute(
                text(f"INSERT INTO request_quotation_lines ({names}) VALUES ({binds})"),
                {"id": str(uuid.uuid4()), "request_quotation_id": rq_id, **line},
            )

    def _link(self, rq_id: str, payload: CanonicalRequestQuotation) -> None:
        self.refs.link(
            entity_type=ENTITY_TYPE,
            entity_id=rq_id,
            source_ref=payload.source_ref,
            source_doc_no=payload.source_doc_no,
            integration_id=self.integration_id,
        )
