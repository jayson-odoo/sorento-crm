"""Match container status rows to shipments and write them.

Three rules do the work, and each one is a deliberate departure from something
that already exists in this codebase:

**Match across EVERY status.** ``procurement_service`` matches a packing list only
among not-fully-received shipments, because a container carries exactly one open
shipment at a time. That rule is right for a packing list and wrong here: 318 of
the 407 rows in the workbook sit on the archived ``Arrived`` tab, so reusing it
would create a duplicate shipment for every container that already completed.
This importer therefore has its OWN matcher (A3).

**A blank cell never clears (A5).** The parser only carries non-empty cells, so
"absent" and "blank" collapse into the same thing here and neither can overwrite a
value somebody has since filled in. A re-upload of last week's sheet is safe.

**Nothing is written when nothing changed (A4).** A no-op assignment would still
bump ``updated_at`` and emit an audit row, so a daily re-upload would look like 407
edits every morning. Values are compared before assignment.

Remarks become ``activity_events`` rows, not columns and not ``internal_notes`` -
those are private to their author, which would hide them from everyone else (B4).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.activities import ActivityEvent
from app.models.procurement import InboundShipment
from app.services.container_status_import import (
    ContainerStatusParseError,
    ParsedRow,
    ParsedWorkbook,
    normalize_container,
    parse_container_status_workbook,
)

logger = logging.getLogger(__name__)

#: Shipment columns this importer is allowed to write. Anything the parser
#: produces that is not listed here is ignored rather than set blindly.
WRITABLE_FIELDS: tuple[str, ...] = (
    "loc",
    "liner_code",
    "china_forwarder",
    "malaysia_forwarder",
    "consignee",
    "free_days_available",
    "stacked",
    "loading_date",
    "etc_date",
    "etd_date",
    "eta_date",
    "eta_delay_date",
    "inspection_date",
    "approval_date",
    "gatepass_date",
    "delivery_warehouse",
    "warehouse_arrival_date",
    "informed_collection_date",
    "collection_date",
    "ata_date",
    "ori_doc_received_date",
    "k1_submission_date",
    "yard_arrival_date",
    "coa_permit_no",
    "source_sheet",
)

_ACTIVITY_ENTITY_TYPE = "inbound_shipment"
_REMARK_TEMPLATE = "container_status_remark"

# The sheet has no shipment date column, but `inbound_shipments.shipment_date` is
# NOT NULL. Fall back through the dates the sheet DOES carry, earliest-known first,
# so a created row lands on something meaningful rather than on today.
_SHIPMENT_DATE_FALLBACKS = ("etd_date", "etc_date", "loading_date", "eta_date")


def _container_key_sql(column):
    """SQL twin of :func:`normalize_container`, using only UPPER/REPLACE."""
    expr = column
    for ch in (" ", "-", "/", ".", "_"):
        expr = func.replace(expr, ch, "")
    return func.upper(expr)


class ContainerStatusImportService:
    """Dry-run and apply for the container status workbook."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ dry run

    def validate(self, file_data: bytes) -> dict[str, Any]:
        """What would happen, without writing anything.

        The summary keys are fixed by the frontend's shared upload dialog, which
        renders exactly ``total_rows`` / ``would_create`` / ``would_update`` /
        ``error_count`` and silently drops anything else.
        """
        try:
            parsed = parse_container_status_workbook(file_data)
        except ContainerStatusParseError as exc:
            return {
                "valid": False,
                "errors": [str(exc)],
                "warnings": [],
                "summary": {
                    "total_rows": 0,
                    "would_update": 0,
                    "would_create": 0,
                    "error_count": 1,
                },
            }

        existing = self._existing_by_key([r.container_key for r in parsed.rows])
        would_update = sum(1 for r in parsed.rows if r.container_key in existing)
        errors = self._errors_from(parsed)

        return {
            "valid": not errors,
            "errors": errors,
            "warnings": list(parsed.warnings),
            "summary": {
                "total_rows": len(parsed.rows),
                "would_update": would_update,
                "would_create": len(parsed.rows) - would_update,
                "error_count": len(errors),
            },
        }

    def _errors_from(self, parsed: ParsedWorkbook) -> list[str]:
        """Rejected rows and in-run collisions, each locatable in the sheet."""
        errors = list(parsed.errors)
        for rejected in parsed.rejected:
            errors.append(
                f"{rejected.sheet} row {rejected.excel_row}: {rejected.reason}"
            )
        for collision in parsed.collisions:
            where = ", ".join(
                f"{o.sheet} row {o.excel_row}" for o in collision.occurrences
            )
            errors.append(
                f"Container {collision.container_key} appears "
                f"{len(collision.occurrences)} times in this file ({where}). "
                "Resolve it in the sheet - the importer will not pick a winner."
            )
        return errors

    # -------------------------------------------------------------------- apply

    def apply(
        self,
        parsed: ParsedWorkbook,
        *,
        user_id: Optional[str],
        outcome: Any = None,
    ) -> dict[str, Any]:
        """Write the parsed rows. Caller owns the commit.

        ``outcome`` is an optional :class:`~app.services.import_outcome.ImportOutcome`
        so Import Job Details can say what happened to every row.
        """
        counts = {"created": 0, "updated": 0, "unchanged": 0, "rejected": 0}
        existing = self._existing_by_key([r.container_key for r in parsed.rows])

        for row in parsed.rows:
            shipment = existing.get(row.container_key)
            if shipment is None:
                shipment = self._create(row, user_id=user_id)
                existing[row.container_key] = shipment
                counts["created"] += 1
                if outcome is not None:
                    outcome.success(
                        row=row.excel_row,
                        code="container_status_created",
                        message=(
                            f"Created container {row.container} "
                            f"from {row.sheet} row {row.excel_row}."
                        ),
                    )
            else:
                changed = self._apply_values(shipment, row)
                if changed:
                    counts["updated"] += 1
                    if outcome is not None:
                        outcome.updated(
                            row=row.excel_row,
                            code="container_status_updated",
                            message=(
                                f"Updated container {row.container}: "
                                + ", ".join(sorted(changed))
                            ),
                        )
                else:
                    counts["unchanged"] += 1
                    if outcome is not None:
                        outcome.unchanged(
                            row=row.excel_row,
                            code="container_status_unchanged",
                            message=f"Container {row.container} already matches the sheet.",
                        )

            self._record_remarks(shipment, row, user_id=user_id)

        for rejected in parsed.rejected:
            counts["rejected"] += 1
            if outcome is not None:
                outcome.fail(
                    row=rejected.excel_row,
                    code="container_status_invalid_container",
                    message=f"{rejected.sheet} row {rejected.excel_row}: {rejected.reason}",
                )

        self.db.flush()
        return counts

    # ---------------------------------------------------------------- internals

    def _existing_by_key(self, keys: list[str]) -> dict[str, InboundShipment]:
        """Normalized container key -> shipment, across EVERY status (A3).

        One query, chunked, rather than a lookup per row: 407 rows would otherwise
        be 407 round trips.
        """
        wanted = {k for k in keys if k}
        if not wanted:
            return {}

        found: dict[str, InboundShipment] = {}
        key_column = _container_key_sql(InboundShipment.shipping_container_number)
        chunk_size = 500
        ordered = sorted(wanted)
        for start in range(0, len(ordered), chunk_size):
            chunk = ordered[start : start + chunk_size]
            rows = (
                self.db.query(InboundShipment)
                .filter(
                    InboundShipment.shipping_container_number.isnot(None),
                    key_column.in_(chunk),
                )
                # Deterministic winner when a container somehow already has two
                # shipments: the oldest row is the one history hangs off.
                .order_by(InboundShipment.created_at.asc())
                .all()
            )
            for shipment in rows:
                key = normalize_container(shipment.shipping_container_number)
                found.setdefault(key, shipment)
        return found

    def _create(self, row: ParsedRow, *, user_id: Optional[str]) -> InboundShipment:
        shipment = InboundShipment(
            id=str(uuid.uuid4()),
            shipping_container_number=row.container,
            shipment_date=self._shipment_date_for(row),
            shipment_status="in_transit",
            created_by=user_id,
        )
        # `supplier_id` stays NULL: the sheet does not name a supplier, and
        # inventing one would attribute the container to the wrong party.
        for name in WRITABLE_FIELDS:
            if name in row.values:
                setattr(shipment, name, row.values[name])
        self.db.add(shipment)
        self.db.flush()
        return shipment

    def _shipment_date_for(self, row: ParsedRow) -> date:
        for name in _SHIPMENT_DATE_FALLBACKS:
            value = row.values.get(name)
            if isinstance(value, date):
                return value
        # Nothing dated on the row at all. Use today rather than fail the insert;
        # the real dates arrive with the next upload.
        return datetime.utcnow().date()

    def _apply_values(self, shipment: InboundShipment, row: ParsedRow) -> list[str]:
        """Assign only what actually differs. Returns the field names changed.

        Comparing first is what keeps a re-upload a no-op: a same-value assignment
        would still fire `onupdate` on `updated_at` and write an audit row, so a
        daily upload would read as 407 edits every morning (A4).
        """
        changed: list[str] = []
        for name in WRITABLE_FIELDS:
            if name not in row.values:
                # Absent from the sheet. Never a clear (A5).
                continue
            new_value = row.values[name]
            if getattr(shipment, name) == new_value:
                continue
            setattr(shipment, name, new_value)
            changed.append(name)
        return changed

    def _record_remarks(
        self, shipment: InboundShipment, row: ParsedRow, *, user_id: Optional[str]
    ) -> None:
        """Remarks join the shared activity feed, once each (B4).

        Deduplicated on body text per shipment, because the same remark is
        re-uploaded every day the sheet is maintained and an append-per-import
        would grow the feed without adding information.
        """
        if not row.remarks:
            return

        existing_bodies = {
            body
            for (body,) in self.db.query(ActivityEvent.body_text)
            .filter(
                ActivityEvent.entity_type == _ACTIVITY_ENTITY_TYPE,
                ActivityEvent.entity_id == shipment.id,
                ActivityEvent.system_template == _REMARK_TEMPLATE,
            )
            .all()
        }

        for remark in row.remarks:
            if remark in existing_bodies:
                continue
            self.db.add(
                ActivityEvent(
                    id=str(uuid.uuid4()),
                    entity_type=_ACTIVITY_ENTITY_TYPE,
                    entity_id=shipment.id,
                    kind="user_update",
                    body_text=remark,
                    system_template=_REMARK_TEMPLATE,
                    system_payload={
                        "source_sheet": row.sheet,
                        "excel_row": row.excel_row,
                    },
                    actor_id=user_id,
                )
            )
            existing_bodies.add(remark)
