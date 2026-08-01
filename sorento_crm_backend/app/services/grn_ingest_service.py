"""Ingest AutoCount GRNs (goods-received notes) — S17-1c.

A GRN is a header + lines document that REUSES ``picking_headers`` +
``picking_lines`` (``picking_type='goods_received'``). It keeps the EXACT verdict
contract the masters + delivery-order ingest already ship: per-record verdict,
per-record SAVEPOINT isolation, adopt-by-``source_ref``, retryable-on-missing-
reference, dry-run-writes-nothing. This is a near-verbatim clone of
``delivery_order_ingest_service`` adapted to the picking tables.

Identity is ``source_ref`` ONLY (the stable AutoCount ``{db}:{AutoKey}``), tracked
in ``integration_references`` (entity_type ``picking_headers`` — a REAL table name,
since the existence check interpolates it). ``picking_number`` is display + mutable
and is NEVER an adopt key: a re-sync may carry a renamed doc no.

Line resolution: ``product_code`` is the hard requirement (picking_lines.product_id
is NOT NULL / RESTRICT) — a miss makes the WHOLE GRN retryable. ``location`` resolves
to a warehouse (miss also retryable — the master may not have synced). ``supplier_code``
and ``uom`` are captured-if-resolvable: a miss keeps the code / leaves the id NULL,
never a 400. Lines are replaced wholesale on update (the canonical GRN is authoritative).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.procurement import PickingHeader
from app.schemas.external.procurement import GRNRequest
from app.services.integration_reference_service import (
    IntegrationReferenceService,
    ReferenceConflict,
)
from app.services.master_ingest_service import (
    IngestOutcome,
    IngestResult,
    MissingReference,
    RecordResult,
)

logger = logging.getLogger(__name__)

# integration_references interpolates entity_type as a REAL table name in its
# existence check, so this is the reused table ("picking_headers"), not a logical
# "goods_received_note" (which would query a non-existent table and abort the txn).
ENTITY_TYPE = "picking_headers"

# Header columns compared to build the dry-run diff on an adopt-overwrite.
_DIFF_COLUMNS = ("picking_number", "picking_date", "notes", "supplier_code", "supplier_id")


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


class GrnIngestService:
    def __init__(self, db: Session, integration_id: Optional[str] = None):
        self.db = db
        self.integration_id = integration_id
        self.refs = IntegrationReferenceService(db)

    def ingest(self, payload: GRNRequest, *, dry_run: bool = False) -> IngestResult:
        """Ingest ONE GRN (FoundryX sends chunk size 1). Returns a one-record
        verdict envelope; on dry_run the whole transaction is rolled back."""
        result = IngestResult(dry_run=dry_run)
        try:
            result.records.append(self._ingest_one(payload, dry_run=dry_run))
        finally:
            if dry_run:
                self.db.rollback()
        return result

    def _ingest_one(self, payload: GRNRequest, *, dry_run: bool) -> RecordResult:
        source_ref = payload.goods_receive_notes.source_ref
        savepoint = self.db.begin_nested()
        try:
            outcome, entity_id, diff = self._apply(payload, dry_run=dry_run)
            savepoint.commit()
            return RecordResult(source_ref=source_ref, outcome=outcome,
                                entity_id=entity_id, diff=diff)
        except MissingReference as exc:
            savepoint.rollback()
            return RecordResult(source_ref=source_ref, outcome=IngestOutcome.RETRYABLE,
                                errors={exc.field_name: f"not found: {exc.code}"})
        except ReferenceConflict as exc:
            savepoint.rollback()
            return RecordResult(source_ref=source_ref, outcome=IngestOutcome.FAILED,
                                errors={"source_ref": str(exc)})
        except Exception as exc:  # noqa: BLE001 - one record's failure, not the batch's
            savepoint.rollback()
            logger.warning("grn.record_failed source_ref=%s error=%s", source_ref, exc)
            return RecordResult(source_ref=source_ref, outcome=IngestOutcome.FAILED,
                                errors={"_": str(exc)})

    # --- resolution -------------------------------------------------------

    def _resolve_lines(self, payload: GRNRequest) -> list[dict]:
        """Resolve every line's product_code (hard) + location (warehouse) + uom.
        A missing product/warehouse raises MissingReference (retryable) BEFORE any
        write, so the GRN is never half-applied. uom is best-effort (nullable)."""
        resolved = []
        for line in payload.grn_lines:
            prod = self.db.execute(
                text("SELECT id FROM products WHERE product_code = :c LIMIT 1"),
                {"c": line.product_code},
            ).first()
            if prod is None:
                raise MissingReference("product_code", line.product_code)

            warehouse_id = None
            loc = (line.location or "").strip()
            if loc:
                wh = self.db.execute(
                    text(
                        "SELECT id FROM warehouses "
                        "WHERE warehouse_code = :c OR warehouse_name = :c LIMIT 1"
                    ),
                    {"c": loc},
                ).first()
                if wh is None:
                    raise MissingReference("location", loc)
                warehouse_id = str(wh[0])

            uom_id = None
            uom_code = (getattr(line, "uom", None) or "").strip()
            if uom_code:
                u = self.db.execute(
                    text("SELECT id FROM units_of_measure WHERE uom_code = :c LIMIT 1"),
                    {"c": uom_code},
                ).first()
                uom_id = str(u[0]) if u is not None else None  # best-effort

            qty = line.quantity if line.quantity is not None else Decimal("0")
            resolved.append({
                "product_id": str(prod[0]),
                "quantity_expected": qty,
                "quantity_picked": qty,
                "uom_id": uom_id,
                "source_warehouse_id": warehouse_id,
                "destination_warehouse_id": warehouse_id,
            })
        return resolved

    def _resolve_supplier_id(self, supplier_code: Optional[str]) -> Optional[str]:
        """Best-effort supplier_code -> suppliers.id. A miss keeps the code with
        supplier_id NULL — supplier is captured-if-resolvable, not a hard req."""
        code = (supplier_code or "").strip()
        if not code:
            return None
        row = self.db.execute(
            text("SELECT id FROM suppliers WHERE supplier_code = :c LIMIT 1"),
            {"c": code},
        ).first()
        return str(row[0]) if row is not None else None

    def _header_columns(self, payload: GRNRequest) -> dict:
        header = payload.goods_receive_notes
        return {
            "picking_number": header.picking_number,
            "picking_type": "goods_received",
            "picking_date": _parse_date(header.picking_date) or date.today(),
            "notes": header.notes,
            "supplier_code": (header.supplier_code or "").strip() or None,
            "supplier_id": self._resolve_supplier_id(header.supplier_code),
        }

    # --- apply ------------------------------------------------------------

    def _apply(self, payload: GRNRequest, *, dry_run: bool):
        # Resolve lines first: a missing product/warehouse aborts the whole GRN as
        # retryable before we touch any row.
        lines = self._resolve_lines(payload)
        cols = self._header_columns(payload)
        source_ref = payload.goods_receive_notes.source_ref

        existing_id = self.refs.resolve(entity_type=ENTITY_TYPE, source_ref=source_ref)

        if existing_id is not None:
            diff = self._diff(existing_id, cols) if dry_run else None
            self._update_header(existing_id, cols)
            self._replace_lines(existing_id, lines)
            self._link(existing_id, cols, source_ref)
            return IngestOutcome.UPDATED, existing_id, diff

        new_id = str(uuid.uuid4())
        self._insert_header(new_id, cols)
        self._replace_lines(new_id, lines)
        self._link(new_id, cols, source_ref)
        return IngestOutcome.CREATED, new_id, None

    def _diff(self, header_id: str, cols: dict) -> dict:
        header = self.db.query(PickingHeader).filter(PickingHeader.id == header_id).one()
        out: dict = {}
        for key in _DIFF_COLUMNS:
            current = getattr(header, key)
            incoming = cols.get(key)
            if str(current) != str(incoming):
                out[key] = {"current": _jsonable(current), "incoming": _jsonable(incoming)}
        return out

    def _insert_header(self, header_id: str, cols: dict) -> None:
        # ORM (not raw INSERT) so CompanyScopedMixin auto-stamps company_id and the
        # inspection_status/picking_status defaults apply.
        self.db.add(PickingHeader(id=header_id, **cols))
        self.db.flush()

    def _update_header(self, header_id: str, cols: dict) -> None:
        header = self.db.query(PickingHeader).filter(PickingHeader.id == header_id).one()
        for key, value in cols.items():
            setattr(header, key, value)
        self.db.flush()

    def _replace_lines(self, header_id: str, lines: list[dict]) -> None:
        # Canonical GRN is authoritative; a merge would orphan a removed line.
        # picking_lines is company-scoped: a raw INSERT bypasses the ORM auto-stamp,
        # so carry the header's company_id onto each line or the fail-closed SELECT
        # filter hides them. quantity_discrepancy is generated — never inserted.
        company_id = self.db.execute(
            text("SELECT company_id FROM picking_headers WHERE id = :h"), {"h": header_id}
        ).scalar()
        self.db.execute(
            text("DELETE FROM picking_lines WHERE picking_header_id = :h"), {"h": header_id}
        )
        for line in lines:
            self.db.execute(
                text(
                    "INSERT INTO picking_lines "
                    "(id, picking_header_id, company_id, product_id, quantity_expected, "
                    " quantity_picked, uom_id, source_warehouse_id, destination_warehouse_id, "
                    " picked_condition, synced_to_excel) "
                    "VALUES (:id, :picking_header_id, :company_id, :product_id, :quantity_expected, "
                    " :quantity_picked, :uom_id, :source_warehouse_id, :destination_warehouse_id, "
                    " 'good', false)"
                ),
                {"id": str(uuid.uuid4()), "picking_header_id": header_id,
                 "company_id": company_id, **line},
            )

    def _link(self, header_id: str, cols: dict, source_ref: str) -> None:
        self.refs.link(
            entity_type=ENTITY_TYPE,
            entity_id=header_id,
            source_ref=source_ref,
            source_doc_no=cols.get("picking_number"),
            integration_id=self.integration_id,
        )


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
