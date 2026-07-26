"""Ingest AutoCount item packages (header + PackageDTL lines) — Slice 3.

Item packages do not fit ENTITY_SPECS (that layer maps ONE canonical shape to a
flat table). A package is a header plus lines that must be resolved to products,
so it gets a bespoke adopter here -- but it keeps the SAME contract the ESB
already consumes for flat masters: per-record verdict, per-record SAVEPOINT
isolation, adopt-by-code, retryable-on-missing-reference, dry-run-writes-nothing.

Line resolution: every line's ``product_code`` must resolve to a real product.
An unresolvable code makes the WHOLE package retryable (not failed) -- the
product may simply not have synced yet, exactly like a flat product whose
category has not landed. The package is not half-written with a dangling line.

On update the lines are replaced wholesale (delete children, re-insert): the
canonical PackageDTL is the source of truth for the package's contents, and a
merge would leave a removed line orphaned in Sorento.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.canonical_masters import CanonicalItemPackage
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

ENTITY_TYPE = "item_packages"


def _parse_date(value) -> date | None:
    """Parse AutoCount's date strings ("YYYY/MM/DD" masters, ISO docs). A local
    parser to avoid importing from app.api.v1.external (circular: that package's
    __init__ imports this service's router)."""
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


class ItemPackageIngestService:
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
            payload = CanonicalItemPackage(**raw)
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
            logger.warning("item_package.record_failed source_ref=%s error=%s", payload.source_ref, exc)
            return RecordResult(source_ref=payload.source_ref, outcome=IngestOutcome.FAILED,
                                errors={"_": str(exc)})

    def _resolve_lines(self, payload: CanonicalItemPackage) -> list[dict]:
        """Resolve every line's product_code -> product_id. A miss raises
        MissingReference (retryable) BEFORE any write, so the package is never
        partially applied."""
        resolved = []
        for i, line in enumerate(payload.lines, start=1):
            row = self.db.execute(
                text("SELECT id FROM products WHERE product_code = :c LIMIT 1"),
                {"c": line.product_code},
            ).first()
            if row is None:
                raise MissingReference("product_code", line.product_code)
            resolved.append({
                "product_id": str(row[0]),
                "line_sequence": i,
                "uom": line.uom,
                "qty": line.qty,
                "unit_price": line.unit_price,
            })
        return resolved

    def _header_columns(self, payload: CanonicalItemPackage) -> dict:
        return {
            "package_code": payload.code,
            "description": payload.description,
            "expiry_date": _parse_date(payload.expiry_date),
            "limited_qty": payload.limited_qty,
            "opening_qty": payload.opening_qty,
            "user_uom": payload.user_uom,
            "bar_code": payload.bar_code,
            "further_description": payload.further_description,
            "is_active": payload.is_active,
        }

    def _apply(self, payload: CanonicalItemPackage) -> tuple[IngestOutcome, str]:
        # Resolve lines first: a missing product must abort the whole package as
        # retryable before we touch any row.
        lines = self._resolve_lines(payload)
        cols = self._header_columns(payload)

        existing_id = self.refs.resolve(entity_type=ENTITY_TYPE, source_ref=payload.source_ref)
        if existing_id is None:
            adopted = self.db.execute(
                text("SELECT id FROM item_packages WHERE package_code = :c LIMIT 1"),
                {"c": payload.code},
            ).first()
            if adopted is not None:
                if self.refs.origin_of(entity_type=ENTITY_TYPE, entity_id=str(adopted[0])) is not None:
                    raise ReferenceConflict(
                        f"package_code={payload.code!r} is already linked to another source"
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

    def _insert_header(self, package_id: str, cols: dict) -> None:
        names = ", ".join(["id", *cols])
        binds = ", ".join([":id", *(f":{c}" for c in cols)])
        self.db.execute(text(f"INSERT INTO item_packages ({names}) VALUES ({binds})"),
                        {"id": package_id, **cols})

    def _update_header(self, package_id: str, cols: dict) -> None:
        assignments = ", ".join(f"{c} = :{c}" for c in cols)
        self.db.execute(text(f"UPDATE item_packages SET {assignments} WHERE id = :id"),
                        {"id": package_id, **cols})

    def _replace_lines(self, package_id: str, lines: list[dict]) -> None:
        # The canonical PackageDTL is authoritative for contents; a merge would
        # orphan a removed line. Delete-then-insert keeps Sorento in step.
        self.db.execute(text("DELETE FROM item_package_lines WHERE item_package_id = :p"),
                        {"p": package_id})
        for line in lines:
            self.db.execute(
                text(
                    "INSERT INTO item_package_lines "
                    "(id, item_package_id, product_id, line_sequence, uom, qty, unit_price) "
                    "VALUES (:id, :p, :product_id, :line_sequence, :uom, :qty, :unit_price)"
                ),
                {"id": str(uuid.uuid4()), "p": package_id, **line},
            )

    def _link(self, package_id: str, payload: CanonicalItemPackage) -> None:
        self.refs.link(
            entity_type=ENTITY_TYPE,
            entity_id=package_id,
            source_ref=payload.source_ref,
            source_doc_no=payload.source_doc_no,
            integration_id=self.integration_id,
        )
