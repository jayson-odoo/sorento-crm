"""Ingest DOCUMENTS pushed in by the ESB: sales orders and purchase orders (A3).

The three semantics `master_ingest_service` carries are the same here and are
imported from it rather than restated - per-record SAVEPOINT isolation,
retryable-is-not-failed, adoption over duplication, and a dry run that is a real
run taken back. What follows is only what a document adds.

**The document owns its lines.** A push is one authoritative statement about the
whole order, so a line the payload no longer carries has been deleted upstream
and goes with it - including a line an earlier extract import created with no
`source_ref` at all. Keeping those would double the demand on the first
AutoCount sync: the same physical line would count once under the ref-less row
and once under the pushed one.

**A line keeps its id.** The upsert is by the line's own `source_ref`
(AutoCount's DtlKey), not by position and not by wholesale replacement. Stock
allocations, transfers and plan decisions point at a line id; replacing every
line on every sync - which is what the stale `sorento_crm-autocount` branch did -
would break those links weekly for lines nobody touched.

**Every reference is resolved before anything is written.** A document points at
five masters, and one that has not synced yet is a sequencing artefact rather
than bad data (AC-AC-16), so the record is `retryable` and NOTHING lands. A
header written without its lines is worse than no header: it reads as an order
for nothing, which the netting treats as fully covered demand.

**Status is a vocabulary, not a string.** Five canonical words map onto two
different Sorento vocabularies, and an unmapped word is `failed` rather than
stored - `status` is what decides whether a row is still open demand, so a value
nothing can classify would quietly leave the order out of every plan.

The ORM is used for the writes here, deliberately, where the master ingest uses
raw SQL. Both `sales_orders` and `sales_order_lines` (and their purchase-order
twins) exist a SECOND time in the `projects` schema, and unqualified raw SQL
resolves those names through `search_path`. The ORM models say which table they
mean; the company anchor is still stamped by hand on top of the auto-stamp,
because a document must never depend on ambient session state for the one thing
that partitions it.

Ingest emits no lifecycle events, for the same reason the master ingest does
not: a record arriving FROM AutoCount must never trigger a write back to it.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.schemas.canonical_documents import CanonicalPurchaseOrder, CanonicalSalesOrder
from app.services.integration_reference_service import (
    IntegrationReferenceService,
    ReferenceConflict,
)
from app.services.master_ingest_service import (
    IngestOutcome,
    IngestResult,
    MissingReference,
    RecordResult,
    UnsupportedIngestEntity,
    _field_errors,
    _is_company_scoped,
    _lookup_id,
    _value_changed,
)

logger = logging.getLogger(__name__)

SOURCE_SYSTEM = "autocount"

# Canonical status -> stored status. Two vocabularies, because sales orders and
# purchase orders never shared one: an order that has been shipped in full is
# `fulfilled` on the sales side and `received` on the buying side, and a purchase
# order that is merely live is `active` where a sales order is `open`.
#
# Module constants rather than literals in the spec, because these ARE the
# cross-repo contract: the shared service's sink codes against exactly these five
# words, and section 7.2 of the plan records them.
SALES_ORDER_STATUS_MAP = {
    "open": "open",
    "partial": "partially_delivered",
    "fulfilled": "fulfilled",
    "closed": "closed",
    "cancelled": "cancelled",
}
PURCHASE_ORDER_STATUS_MAP = {
    "open": "active",
    "partial": "partial",
    "fulfilled": "received",
    "closed": "closed",
    "cancelled": "cancelled",
}

CANCELLED = "cancelled"


@dataclass(frozen=True)
class DocumentSpec:
    """How one canonical document maps onto a header table and its line table."""

    entity_type: str
    schema: type[BaseModel]
    header_model: type
    line_model: type
    # The business number, which is what a FIRST sync adopts an existing row by.
    number_column: str
    number_field: str
    status_map: dict[str, str]
    # Only sales_orders carries `source_doc_no`; purchase_orders has no such
    # column, and writing one would be an AttributeError per record.
    doc_no_column: Optional[str]
    # (column, payload field, master entity_type) for the header's FKs and the
    # line's. The master entity_type is what the ref resolves through, and it is
    # also what decides whether the resolved row has to be in the anchor company.
    header_refs: tuple[tuple[str, str, str], ...]
    line_refs: tuple[tuple[str, str, str], ...]
    # (column, payload field) for the plain values.
    header_fields: tuple[tuple[str, str], ...]
    line_fields: tuple[tuple[str, str], ...]
    # The line's delivered/received quantity, which decides `line_status`.
    line_delivered_field: str
    # The FK from a line back to its header.
    line_fk: str


DOCUMENT_SPECS: dict[str, DocumentSpec] = {
    "sales_orders": DocumentSpec(
        entity_type="sales_orders",
        schema=CanonicalSalesOrder,
        header_model=SalesOrder,
        line_model=SalesOrderLine,
        number_column="so_number",
        number_field="so_number",
        status_map=SALES_ORDER_STATUS_MAP,
        doc_no_column="source_doc_no",
        header_refs=(
            ("customer_id", "customer_ref", "customers"),
            ("sales_agent_id", "sales_agent_ref", "sales_agents"),
        ),
        line_refs=(
            ("product_id", "product_ref", "products"),
            ("warehouse_id", "warehouse_ref", "warehouses"),
        ),
        # `debtor_code`, `demand_class`, `demand_origin`, `priority` and
        # `order_type` are absent on purpose, the same way the agent master's
        # annotations are: they are set by the importers and by CS, AutoCount
        # holds no opinion about any of them, and a weekly re-sync that restated
        # them from a payload which never carried them would blank the captain's
        # classification. Absent from the written set, they cannot be touched.
        header_fields=(
            ("so_number", "so_number"),
            ("order_date", "doc_date"),
            ("requested_delivery_date", "requested_delivery_date"),
            ("internal_note", "internal_note"),
        ),
        line_fields=(
            ("qty_ordered", "qty_ordered"),
            ("qty_delivered", "qty_delivered"),
            ("unit_price", "unit_price"),
            ("discount", "discount"),
            ("line_total", "line_total"),
            ("uom", "uom"),
            ("required_date", "required_date"),
        ),
        line_delivered_field="qty_delivered",
        line_fk="sales_order_id",
    ),
    "purchase_orders": DocumentSpec(
        entity_type="purchase_orders",
        schema=CanonicalPurchaseOrder,
        header_model=PurchaseOrder,
        line_model=PurchaseOrderLine,
        number_column="po_number",
        number_field="po_number",
        status_map=PURCHASE_ORDER_STATUS_MAP,
        doc_no_column=None,
        header_refs=(("supplier_id", "supplier_ref", "suppliers"),),
        line_refs=(
            ("product_id", "product_ref", "products"),
            ("warehouse_id", "warehouse_ref", "warehouses"),
        ),
        header_fields=(
            ("po_number", "po_number"),
            ("issue_date", "issue_date"),
            ("expected_date", "expected_date"),
            ("currency", "currency"),
        ),
        line_fields=(
            ("qty_ordered", "qty_ordered"),
            ("qty_received", "qty_received"),
            ("unit_cost", "unit_cost"),
            ("discount", "discount"),
            ("line_total", "line_total"),
            ("uom", "uom"),
            ("currency", "currency"),
            ("expected_date", "expected_date"),
        ),
        # `moq_snapshot` and `order_multiple_snapshot` are what Sorento's planner
        # believed when it raised the line, not what AutoCount knows now.
        line_delivered_field="qty_received",
        line_fk="purchase_order_id",
    ),
}

# The entity names this service answers for. Read by the route so ONE endpoint
# dispatches between masters and documents rather than a second router existing.
DOCUMENT_ENTITIES = frozenset(DOCUMENT_SPECS)


def _canonical_status(spec: DocumentSpec, stored: Optional[str]) -> Optional[str]:
    """The canonical word for a stored status, or the stored one if it has none.

    A locally raised purchase order sits in `draft`, and `draft` is not part of
    the contract vocabulary. Inventing a canonical word for it would tell the ESB
    the document is in a state it is not; handing back what is actually stored
    lets it see a value it does not own and leave the row alone.
    """
    if stored is None:
        return None
    for canonical, mapped in spec.status_map.items():
        if mapped == stored:
            return canonical
    return stored


class _UnknownStatus(ValueError):
    """A status word outside the canonical vocabulary. Failed, never stored."""


class DocumentIngestService:
    """Same constructor and same ``ingest()`` contract as ``MasterIngestService``.

    Deliberately interchangeable: the route picks one or the other on the entity
    name and calls the same method, so there is one ingest endpoint rather than
    two that can drift on batch caps, verdicts or the dry-run rollback.
    """

    def __init__(
        self, db: Session, integration_id: Optional[str] = None, *, company_id: str
    ):
        self.db = db
        self.integration_id = integration_id
        # Required, for the reason the master ingest states: a default would be
        # the incumbent company, and a push meant for the other one would land
        # there silently.
        self.company_id = company_id
        self.refs = IntegrationReferenceService(db)
        self._dry_run = False

    # --------------------------------------------------------------- the batch
    def ingest(
        self, entity_type: str, records: list[dict], *, dry_run: bool = False
    ) -> IngestResult:
        spec = DOCUMENT_SPECS.get(entity_type)
        if spec is None:
            raise UnsupportedIngestEntity(
                f"Unsupported ingest entity {entity_type!r}. "
                f"Expected one of: {', '.join(sorted(DOCUMENT_SPECS))}"
            )

        result = IngestResult(dry_run=dry_run)
        self._dry_run = dry_run
        try:
            for raw in records:
                result.records.append(self._ingest_one(spec, raw))
        finally:
            self._dry_run = False
            if dry_run:
                # In a finally, so an error mid-batch cannot leave a partially
                # applied preview in the session for whatever commits next.
                self.db.rollback()
        return result

    def _ingest_one(self, spec: DocumentSpec, raw: dict) -> RecordResult:
        source_ref = raw.get("source_ref") if isinstance(raw, dict) else None

        try:
            # `Any`, because the parsed shape is whichever canonical model the
            # spec names and every field read below is declared on that one, not
            # on BaseModel.
            payload: Any = spec.schema(**raw)
        except ValidationError as exc:
            return RecordResult(
                source_ref=source_ref,
                outcome=IngestOutcome.FAILED,
                errors=_field_errors(exc),
            )
        except TypeError as exc:
            return RecordResult(
                source_ref=source_ref, outcome=IngestOutcome.FAILED, errors={"_": str(exc)}
            )

        # One document per savepoint. Without it a failed flush poisons the
        # session and every later record in the file fails too.
        savepoint = self.db.begin_nested()
        try:
            outcome, entity_id, diff = self._apply(spec, payload)
            savepoint.commit()
            return RecordResult(
                source_ref=payload.source_ref, outcome=outcome, entity_id=entity_id, diff=diff
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
                errors={"source_ref": str(exc)},
            )
        except _UnknownStatus as exc:
            savepoint.rollback()
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.FAILED,
                errors={"status": str(exc)},
            )
        except Exception as exc:  # noqa: BLE001 - one document's failure, not the file's
            savepoint.rollback()
            logger.warning(
                "ingest.document_failed entity=%s source_ref=%s error=%s",
                spec.entity_type,
                payload.source_ref,
                exc,
            )
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.FAILED,
                errors={"_": str(exc)},
            )

    # ------------------------------------------------------------ one document
    def _apply(
        self, spec: DocumentSpec, payload: Any
    ) -> tuple[IngestOutcome, str, Optional[dict[str, dict[str, Any]]]]:
        # EVERYTHING is resolved before ANYTHING is written. An unresolved
        # reference has to leave the database exactly as it found it, and a
        # header inserted before the line that fails would only be taken back by
        # the savepoint - which is a guarantee about this transaction, not about
        # the order the work happens in.
        status = self._status(spec, payload.status)
        header_values = self._header_values(spec, payload, status)
        line_values = [
            self._line_values(spec, line, index, status)
            for index, line in enumerate(payload.lines)
        ]

        header, outcome = self._header(spec, payload)
        # Only an update overwrites anything, and only a dry run needs to say so.
        diff = (
            self._diff(header, header_values)
            if outcome is IngestOutcome.UPDATED
            else None
        )
        for column, value in header_values.items():
            setattr(header, column, value)
        self.db.flush()

        self._sync_lines(spec, header, line_values)
        self.refs.link(
            entity_type=spec.entity_type,
            entity_id=str(header.id),
            source_ref=payload.source_ref,
            source_doc_no=payload.source_doc_no,
            integration_id=self.integration_id,
        )
        return outcome, str(header.id), diff

    def _status(self, spec: DocumentSpec, canonical: str) -> str:
        """The stored status for a canonical word.

        Lower-cased first: AutoCount's exports are not consistent about case, and
        `Partial` naming a different state from `partial` would be a distinction
        nobody upstream intended.
        """
        mapped = spec.status_map.get((canonical or "").strip().lower())
        if mapped is None:
            raise _UnknownStatus(
                f"unknown status {canonical!r}; expected one of: "
                f"{', '.join(sorted(spec.status_map))}"
            )
        return mapped

    def _header(self, spec: DocumentSpec, payload: Any) -> tuple[Any, IngestOutcome]:
        """The row this document addresses: by reference, then by number, then new."""
        existing_id = self.refs.resolve(
            entity_type=spec.entity_type, source_ref=payload.source_ref
        )
        if existing_id is not None:
            self._require_same_company(
                spec.entity_type,
                existing_id,
                f"source_ref {payload.source_ref!r}",
            )
            return self._load(spec, existing_id), IngestOutcome.UPDATED

        number = getattr(payload, spec.number_field)
        adopted = _lookup_id(
            self.db, spec.entity_type, spec.number_column, number, self.company_id
        )
        if adopted is not None:
            if (
                self.refs.origin_of(entity_type=spec.entity_type, entity_id=adopted)
                is not None
            ):
                # Two AutoCount documents claiming one Sorento order is a
                # conflict a human settles; retargeting silently would move
                # somebody else's demand.
                raise ReferenceConflict(
                    f"{spec.number_column}={number!r} is already linked to another source"
                )
            return self._load(spec, adopted), IngestOutcome.UPDATED

        header = spec.header_model(id=str(uuid.uuid4()), company_id=self.company_id)
        self.db.add(header)
        return header, IngestOutcome.CREATED

    def _load(self, spec: DocumentSpec, entity_id: str):
        header = self.db.get(spec.header_model, str(entity_id))
        if header is None:
            # The reference resolved and the company check passed, so the row is
            # there; only a scope filter could hide it, and that would be a bug
            # worth naming rather than a silent create.
            raise ReferenceConflict(
                f"{spec.entity_type} {entity_id!r} resolved but is not readable in this company"
            )
        return header

    def _header_values(self, spec: DocumentSpec, payload: Any, status: str) -> dict[str, Any]:
        values: dict[str, Any] = {
            column: getattr(payload, field) for column, field in spec.header_fields
        }
        values["status"] = status
        for column, field, entity_type in spec.header_refs:
            values[column] = self._resolve_ref(field, getattr(payload, field), entity_type)
        # Adoption takes ownership: from here on the row is AutoCount's, and the
        # next push has to find it by reference rather than by number again.
        values["source_system"] = SOURCE_SYSTEM
        values["source_ref"] = payload.source_ref
        if spec.doc_no_column:
            values[spec.doc_no_column] = getattr(payload, spec.number_field)
        return values

    def _line_values(
        self, spec: DocumentSpec, line: Any, index: int, status: str
    ) -> dict[str, Any]:
        values: dict[str, Any] = {
            column: getattr(line, field) for column, field in spec.line_fields
        }
        for column, field, entity_type in spec.line_refs:
            values[column] = self._resolve_ref(
                f"lines.{index}.{field}", getattr(line, field), entity_type
            )
        # NOT NULL on both line tables, and an absent figure means none delivered.
        for column in ("qty_ordered", spec.line_delivered_field):
            if values.get(column) is None:
                values[column] = 0
        values["line_status"] = _line_status(
            status, values["qty_ordered"], values[spec.line_delivered_field]
        )
        values["source_system"] = SOURCE_SYSTEM
        values["source_ref"] = line.source_ref
        return values

    def _resolve_ref(
        self, field: str, source_ref: Optional[str], entity_type: str
    ) -> Optional[str]:
        """The local id an integration reference names, inside the anchor company.

        Absent is not the same as unknown. An optional ref nobody sent leaves the
        FK NULL - an order whose debtor Sorento does not hold is still an order.
        A ref that WAS sent and does not resolve is a sequencing artefact: the
        master push has not drained yet, so the whole document is retryable
        rather than written with the attribution silently dropped.
        """
        if source_ref is None or source_ref == "":
            return None
        entity_id = self.refs.resolve(entity_type=entity_type, source_ref=source_ref)
        if entity_id is None:
            raise MissingReference(field, source_ref)
        self._require_same_company(entity_type, entity_id, f"{field} {source_ref!r}")
        return entity_id

    def _require_same_company(self, entity_type: str, entity_id: str, subject: str) -> None:
        """Refuse a reference that resolves into another company.

        `integration_references` is global, so a ref finds its row whatever
        company the request anchored to. Binding this document to it - or
        updating it - would be a cross-company write wearing the clothes of an
        ordinary re-sync. Shared masters (`sales_agents`) carry no company at all
        and are visible from either anchor, so they are exempt.
        """
        if not _is_company_scoped(entity_type):
            return
        owner = self.db.execute(
            text(f"SELECT company_id FROM {entity_type} WHERE id = :id"),
            {"id": str(entity_id)},
        ).scalar()
        if str(owner) != str(self.company_id):
            raise ReferenceConflict(f"{subject} is linked to a record in another company")

    def _sync_lines(
        self, spec: DocumentSpec, header: Any, line_values: list[dict[str, Any]]
    ) -> None:
        """Make the header's lines equal to the payload's, by the line's own ref.

        Three outcomes per existing row: matched (updated in place, same id),
        unmatched (deleted), or absent from the database (inserted). The delete
        arm is the one that needs saying out loud: a line whose `source_ref` is
        NULL was written by the extract importer before AutoCount owned this
        document, and leaving it would count the same physical line twice.
        """
        existing = (
            self.db.query(spec.line_model)
            .filter(getattr(spec.line_model, spec.line_fk) == str(header.id))
            .all()
        )
        by_ref: dict[str, Any] = {}
        stale = []
        for row in existing:
            if row.source_ref and row.source_ref not in by_ref:
                by_ref[row.source_ref] = row
            else:
                stale.append(row)

        for values in line_values:
            row = by_ref.pop(values["source_ref"], None)
            if row is None:
                row = spec.line_model(
                    id=str(uuid.uuid4()),
                    company_id=self.company_id,
                    **{spec.line_fk: str(header.id)},
                )
                self.db.add(row)
            for column, value in values.items():
                setattr(row, column, value)

        for row in [*by_ref.values(), *stale]:
            self.db.delete(row)
        self.db.flush()

    def _diff(self, header: Any, values: dict[str, Any]) -> Optional[dict[str, dict[str, Any]]]:
        """Header values this document would replace, dry run only.

        Lines are not diffed: an operator reviewing a sync is asking what the
        header would lose, and a per-line before/after over a 200-line order is a
        wall of text that buries the one change that matters. The header is where
        the hand-entered values are.
        """
        if not self._dry_run:
            return None
        current = {column: getattr(header, column, None) for column in values}
        return {
            column: {"current": current[column], "incoming": incoming}
            for column, incoming in values.items()
            if _value_changed(current[column], incoming)
        }


def _line_status(header_status: str, qty_ordered: Any, qty_delivered: Any) -> str:
    """`cancelled`, `fulfilled` or `open`, in that order of precedence.

    Cancellation wins over completeness: a cancelled order's fully delivered line
    is still cancelled, and reading it as `fulfilled` would leave it counted as
    supply that arrived.
    """
    if header_status == CANCELLED:
        return CANCELLED
    ordered = qty_ordered or 0
    delivered = qty_delivered or 0
    if ordered > 0 and delivered >= ordered:
        return "fulfilled"
    return "open"


class DocumentReadService:
    """Current document state for a batch of refs, in the ESB's vocabulary.

    Same contract as ``MasterReadService.current_state`` - and the same reason
    for it: the ESB stages changes for human approval and renders a before/after,
    which is not a diff anyone can review unless both sides speak one language.
    So the answer carries `doc_date`, not `order_date`; the canonical status
    word, not the stored one; and the customer's integration REFERENCE, not a
    Sorento UUID the ESB has never seen.

    A master that carries no reference reads back as `null` rather than as an
    invented ref: the customer may have been created in Sorento by hand, and
    handing back something unresolvable would make the next approved sync push a
    link that does not exist.
    """

    def __init__(self, db: Session, *, company_id: str):
        self.db = db
        self.company_id = company_id
        self.refs = IntegrationReferenceService(db)

    def current_state(self, entity_type: str, source_refs: list[str]) -> dict[str, Any]:
        spec = DOCUMENT_SPECS.get(entity_type)
        if spec is None:
            return {"records": [], "not_found": list(source_refs)}

        found: list[dict[str, Any]] = []
        not_found: list[str] = []

        for source_ref in source_refs:
            entity_id = self.refs.resolve(entity_type=entity_type, source_ref=source_ref)
            header = None
            if entity_id is not None:
                header = (
                    self.db.query(spec.header_model)
                    .filter(
                        spec.header_model.id == str(entity_id),
                        # Part of the lookup, not a check after it: another
                        # company's row must read exactly like a row that is not
                        # there, or the caller has two answers to act on.
                        spec.header_model.company_id == self.company_id,
                    )
                    .first()
                )
            if header is None:
                not_found.append(source_ref)
                continue
            found.append(self._record(spec, source_ref, header))

        return {"records": found, "not_found": not_found}

    def _record(self, spec: DocumentSpec, source_ref: str, header: Any) -> dict[str, Any]:
        record: dict[str, Any] = {"source_ref": source_ref, "entity_id": str(header.id)}
        for column, field in spec.header_fields:
            record[field] = getattr(header, column)
        record["status"] = _canonical_status(spec, header.status)
        for column, field, entity_type in spec.header_refs:
            record[field] = self._ref_of(entity_type, getattr(header, column))
        record["lines"] = [
            self._line(spec, line) for line in self._lines(spec, header)
        ]
        return record

    def _lines(self, spec: DocumentSpec, header: Any) -> list[Any]:
        # Insertion order with the id as tie breaker: lines written in one
        # transaction share `created_at` (one now() per transaction), and without
        # the tie breaker Postgres returns them in whatever order it likes.
        return (
            self.db.query(spec.line_model)
            .filter(getattr(spec.line_model, spec.line_fk) == str(header.id))
            .order_by(spec.line_model.created_at, spec.line_model.id)
            .all()
        )

    def _line(self, spec: DocumentSpec, line: Any) -> dict[str, Any]:
        record: dict[str, Any] = {
            "source_ref": line.source_ref,
            "entity_id": str(line.id),
        }
        for column, field, entity_type in spec.line_refs:
            record[field] = self._ref_of(entity_type, getattr(line, column))
        for column, field in spec.line_fields:
            record[field] = getattr(line, column)
        return record

    def _ref_of(self, entity_type: str, entity_id: Optional[str]) -> Optional[str]:
        if not entity_id:
            return None
        origin = self.refs.origin_of(entity_type=entity_type, entity_id=str(entity_id))
        return str(origin.source_ref) if origin is not None else None
