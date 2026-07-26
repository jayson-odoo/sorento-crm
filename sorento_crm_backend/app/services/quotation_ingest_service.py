"""Ingest AutoCount quotations (header + QTDTL lines) — Slice 6.

New parent+lines document mirror (does NOT fit ENTITY_SPECS). Keeps the same
contract as the flat masters / item packages / delivery orders: per-record
verdict, per-record SAVEPOINT isolation, adopt-by-code
(``quote_number = AC-{DocKey}``), retryable-on-missing-reference,
dry-run-writes-nothing. Idempotency + provenance via ``integration_references``
(entity_type ``quotations``, source_ref = DocKey).

Line resolution: every QTDTL line's ``product_code`` must resolve
(quotation_lines.product_id is NOT NULL / RESTRICT). An unresolvable code makes
the WHOLE quotation retryable -- the product may not have synced yet -- so the
quotation is never written with a dangling line. Lines are replaced wholesale on
update (delete children, re-insert): the canonical QTDTL is authoritative.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.quotation import Quotation
from app.schemas.canonical_masters import CanonicalQuotation
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

ENTITY_TYPE = "quotations"


def _parse_date(value) -> date | None:
    """Parse AutoCount date strings. Local parser (avoids the circular import
    from app.api.v1.external whose __init__ imports this service's router)."""
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


class QuotationIngestService:
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
            payload = CanonicalQuotation(**raw)
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
            logger.warning("quotation.record_failed source_ref=%s error=%s", payload.source_ref, exc)
            return RecordResult(source_ref=payload.source_ref, outcome=IngestOutcome.FAILED,
                                errors={"_": str(exc)})

    def _resolve_lines(self, payload: CanonicalQuotation) -> list[dict]:
        """Resolve each line's product_code -> product_id. A miss raises
        MissingReference (retryable) BEFORE any write."""
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
                "discount_amt": line.discount_amt,
                "tax_code": line.tax_code,
                "tax_rate": line.tax_rate,
                "tax": line.tax,
                "description": line.description,
                "further_description": line.further_description,
                "package_code": line.package_code,
                "proj_no": line.proj_no,
                "dept_no": line.dept_no,
            })
        return resolved

    def _header_columns(self, payload: CanonicalQuotation) -> dict:
        return {
            "quote_number": f"AC-{payload.source_ref}",
            "source_doc_no": payload.source_doc_no,
            "debtor_code": payload.debtor_code,
            "debtor_name": payload.debtor_name,
            "doc_date": _parse_date(payload.doc_date),
            "is_cancelled": bool(payload.is_cancelled),
            "attention": payload.attention,
            "branch_code": payload.branch_code,
            "deliver_addr1": payload.deliver_addr1,
            "deliver_addr2": payload.deliver_addr2,
            "deliver_addr3": payload.deliver_addr3,
            "deliver_addr4": payload.deliver_addr4,
            "terms": payload.terms,
            "sales_agent": payload.sales_agent,
        }

    def _apply(self, payload: CanonicalQuotation) -> tuple[IngestOutcome, str]:
        lines = self._resolve_lines(payload)
        cols = self._header_columns(payload)

        existing_id = self.refs.resolve(entity_type=ENTITY_TYPE, source_ref=payload.source_ref)
        if existing_id is None:
            adopted = self.db.execute(
                text("SELECT id FROM quotations WHERE quote_number = :n LIMIT 1"),
                {"n": cols["quote_number"]},
            ).first()
            if adopted is not None:
                if self.refs.origin_of(entity_type=ENTITY_TYPE, entity_id=str(adopted[0])) is not None:
                    raise ReferenceConflict(
                        f"quote_number={cols['quote_number']!r} is already linked to another source"
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

    def _insert_header(self, quotation_id: str, cols: dict) -> None:
        # ORM insert so server_default columns (is_cancelled, follow_up,
        # timestamps) fill in without spelling them out.
        self.db.add(Quotation(id=quotation_id, **cols))
        self.db.flush()

    def _update_header(self, quotation_id: str, cols: dict) -> None:
        # quote_number is the adopt key; never rewrite it on update.
        q = self.db.query(Quotation).filter(Quotation.id == quotation_id).one()
        for key, value in cols.items():
            if key == "quote_number":
                continue
            setattr(q, key, value)
        self.db.flush()

    def _replace_lines(self, quotation_id: str, lines: list[dict]) -> None:
        # Canonical QTDTL is authoritative; a merge would orphan a removed line.
        self.db.execute(text("DELETE FROM quotation_lines WHERE quotation_id = :q"),
                        {"q": quotation_id})
        for line in lines:
            names = ", ".join(["id", "quotation_id", *line])
            binds = ", ".join([":id", ":quotation_id", *(f":{c}" for c in line)])
            self.db.execute(
                text(f"INSERT INTO quotation_lines ({names}) VALUES ({binds})"),
                {"id": str(uuid.uuid4()), "quotation_id": quotation_id, **line},
            )

    def _link(self, quotation_id: str, payload: CanonicalQuotation) -> None:
        self.refs.link(
            entity_type=ENTITY_TYPE,
            entity_id=quotation_id,
            source_ref=payload.source_ref,
            source_doc_no=payload.source_doc_no,
            integration_id=self.integration_id,
        )
