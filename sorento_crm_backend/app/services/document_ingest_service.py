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

**Unless something else points at that line.** `scm.loading_plan_line.po_line_id`
is `ON DELETE CASCADE`, so removing a purchase-order line takes loading-plan rows
with it; `stock_transfers.so_line_id` and four more are `SET NULL` and would be
silently orphaned - a transfer that has already physically moved stock, detached
from the order it moved it for. The first sync of an ADOPTED document is where
this bites hardest: every pre-existing line is ref-less, so all of them are
replaced at once. So a line that is going away is asked the same question the
deletion endpoint asks (`app/services/dependent_probe.py`), and one that anything
references is `cancelled` in place instead - out of the demand, still there for
whatever points at it.

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

The ORM is used for every read and every write here, deliberately, where the
master ingest uses raw SQL. Both `sales_orders` and `sales_order_lines` (and
their purchase-order twins) exist a SECOND time in the `projects` schema, and
unqualified raw SQL resolves those names through `search_path`. The ORM models
say which table they mean - which is also why a reference declares the MODEL it
resolves into rather than a table name, and the entity name is read back off that
model. The company anchor is still stamped by hand on top of the auto-stamp,
because a document must never depend on ambient session state for the one thing
that partitions it.

Ingest emits no lifecycle events, for the same reason the master ingest does
not: a record arriving FROM AutoCount must never trigger a write back to it.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product
from app.models.sales_agent import SalesAgent
from app.schemas.canonical_documents import CanonicalPurchaseOrder, CanonicalSalesOrder
from app.services.dependent_probe import is_referenced
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
    _value_changed,
)
from app.services.scm import customer_back_create, sales_agent_service
from app.services.scm.customer_label import normalize_debtor_code
# `_clean_supplier_name` and `DEFAULT_PO_CURRENCY` are the upload's own rules
# (D9's "cleaned name" match, D1's CNY fill) - imported rather than restated so
# the two channels that read a purchase book from AutoCount cannot drift on
# either.
from app.services.scm.outstanding_import_service import (
    DEFAULT_PO_CURRENCY,
    _clean_supplier_name,
)
from app.services.scm.supplier_back_create import back_create_supplier, supplier_slug

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

# Fixed verdict-warning vocabulary (D9). Module constants rather than literals
# at each call site, for the same reason the status maps are: this IS the
# cross-repo contract, and the ESB's log renders these strings verbatim.
WARN_CUSTOMER_CREATED = "customer_created"
WARN_CUSTOMER_UNRESOLVED = "customer_unresolved"
WARN_SUPPLIER_CREATED = "supplier_created"
WARN_AGENT_CREATED = "agent_created"
WARN_WAREHOUSE_UNRESOLVED = "warehouse_unresolved"
#: Reserved for S2 (`classify_document`); not yet emitted.
WARN_UNCLASSIFIED_DEMAND = "unclassified_demand"

# The exact-match code column per master the ref/code ladder resolves through.
# `sales_agents` is absent on purpose: it is shared (no company scope) and
# matched through `sales_agent_service`, which owns its own normalisation.
_CODE_COLUMNS: dict[type, Any] = {
    Customer: Customer.customer_code,
    Supplier: Supplier.supplier_code,
    Product: Product.product_code,
    Warehouse: Warehouse.warehouse_code,
}


@dataclass(frozen=True)
class DocumentSpec:
    """How one canonical document maps onto a header table and its line table."""

    schema: type[BaseModel]
    header_model: type
    line_model: type
    # The business number, which is what a FIRST sync adopts an existing row by.
    # ONE name: the payload field and the column are spelled the same on both
    # documents (`so_number`, `po_number`), and two fields holding one string
    # could be given two values that no test would notice.
    number_field: str
    status_map: dict[str, str]
    # Only sales_orders carries `source_doc_no`; purchase_orders has no such
    # column, and writing one would be an AttributeError per record.
    doc_no_column: Optional[str]
    # (column, ref field, master MODEL, code field or None, name field or None)
    # for the header's FKs and the line's. The model is what the ref resolves
    # through - its `__tablename__` is the entity type - and it is also how the
    # resolved row's company is read, which is a table the ORM names rather
    # than one `search_path` chooses. `code field`/`name field` name the v2
    # fallback siblings on the SAME payload object (D1) - `None` where a model
    # has no such field (`sales_agent_ref` has no name step; `product`/
    # `warehouse` have no name step either).
    header_refs: tuple[tuple[str, str, type, Optional[str], Optional[str]], ...]
    line_refs: tuple[tuple[str, str, type, Optional[str], Optional[str]], ...]
    # (column, payload field) for the plain values.
    header_fields: tuple[tuple[str, str], ...]
    line_fields: tuple[tuple[str, str], ...]
    # The line's delivered/received quantity, which decides `line_status`.
    line_delivered_field: str
    # The FK from a line back to its header.
    line_fk: str

    @property
    def entity_type(self) -> str:
        """The name this document is ingested, read and deleted under.

        Read off the model rather than restated: the key in `DOCUMENT_SPECS`, the
        entity type in `integration_references` and the table name are one
        string, and a spec that could disagree with its own model about which
        would be a mismatch nothing reports.
        """
        return self.header_model.__tablename__


DOCUMENT_SPECS: dict[str, DocumentSpec] = {
    "sales_orders": DocumentSpec(
        schema=CanonicalSalesOrder,
        header_model=SalesOrder,
        line_model=SalesOrderLine,
        number_field="so_number",
        status_map=SALES_ORDER_STATUS_MAP,
        doc_no_column="source_doc_no",
        header_refs=(
            ("customer_id", "customer_ref", Customer, "customer_code", "customer_name"),
            ("sales_agent_id", "sales_agent_ref", SalesAgent, "agent_code", None),
        ),
        line_refs=(
            ("product_id", "product_ref", Product, "product_code", None),
            ("warehouse_id", "warehouse_ref", Warehouse, "warehouse_code", None),
        ),
        # `demand_class`, `demand_origin`, `priority` and
        # `order_type` are absent on purpose, the same way the agent master's
        # annotations are: they are set by the importers and by CS, AutoCount
        # holds no opinion about any of them, and a weekly re-sync that restated
        # them from a payload which never carried them would blank the captain's
        # classification. Absent from the written set, they cannot be touched.
        # `debtor_code` is the one exception (v2, D9): it is written from
        # `customer_code` in `_header_values`, not through this generic list,
        # because it fires on the payload field being SENT rather than on a
        # fixed column mapping.
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
        schema=CanonicalPurchaseOrder,
        header_model=PurchaseOrder,
        line_model=PurchaseOrderLine,
        number_field="po_number",
        status_map=PURCHASE_ORDER_STATUS_MAP,
        doc_no_column=None,
        header_refs=(
            ("supplier_id", "supplier_ref", Supplier, "supplier_code", "supplier_name"),
        ),
        line_refs=(
            ("product_id", "product_ref", Product, "product_code", None),
            ("warehouse_id", "warehouse_ref", Warehouse, "warehouse_code", None),
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
            outcome, entity_id, diff, warnings, line_counts = self._apply(spec, payload)
            savepoint.commit()
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=outcome,
                entity_id=entity_id,
                diff=diff,
                warnings=warnings,
                lines=line_counts,
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
                errors={exc.field_name: str(exc)},
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
    ) -> tuple[
        IngestOutcome, str, Optional[dict[str, dict[str, Any]]], list[str], dict[str, int]
    ]:
        # EVERYTHING is resolved before ANYTHING is written. An unresolved
        # reference has to leave the database exactly as it found it, and a
        # header inserted before the line that fails would only be taken back by
        # the savepoint - which is a guarantee about this transaction, not about
        # the order the work happens in.
        #
        # Shared across the header and every line: a back-create triggered by
        # line 3 belongs on the SAME record verdict as one triggered by the
        # header, not a per-line list nothing reads (D9).
        warnings: list[str] = []
        status = self._status(spec, payload.status)
        header_values = self._header_values(spec, payload, status, warnings)
        line_values = [
            self._line_values(spec, line, index, status, warnings)
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

        line_counts = self._sync_lines(spec, header, line_values)
        self.refs.link(
            entity_type=spec.entity_type,
            entity_id=str(header.id),
            source_ref=payload.source_ref,
            source_doc_no=payload.source_doc_no,
            integration_id=self.integration_id,
        )
        return outcome, str(header.id), diff, warnings, line_counts

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
                spec.header_model,
                existing_id,
                f"source_ref {payload.source_ref!r}",
            )
            return self._load(spec, existing_id), IngestOutcome.UPDATED

        # Within the company, and through the model: `so_number` is unique per
        # company only (migration 305), and the same name in the `projects`
        # schema is a different table that raw SQL would let `search_path`
        # choose between.
        adopted = (
            self.db.query(spec.header_model.id)
            .filter(
                getattr(spec.header_model, spec.number_field)
                == getattr(payload, spec.number_field),
                spec.header_model.company_id == self.company_id,
            )
            .scalar()
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
                    f"{spec.number_field}="
                    f"{getattr(payload, spec.number_field)!r} "
                    "is already linked to another source"
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

    def _header_values(
        self, spec: DocumentSpec, payload: Any, status: str, warnings: list[str]
    ) -> dict[str, Any]:
        values: dict[str, Any] = {
            column: getattr(payload, field) for column, field in spec.header_fields
        }
        values["status"] = status
        for column, ref_field, model, code_field, name_field in spec.header_refs:
            values[column] = self._resolve_master(
                model=model,
                ref_field=ref_field,
                ref=getattr(payload, ref_field),
                code_field=code_field,
                code=getattr(payload, code_field) if code_field else None,
                name=getattr(payload, name_field) if name_field else None,
                warnings=warnings,
            )
        # `debtor_code` (v2, D9): written from `customer_code` whenever it is
        # SENT, independent of whether the customer itself resolved - an
        # order whose debtor Sorento does not (yet) hold still carries the
        # code it was pushed with. Absent on `CanonicalPurchaseOrder`, so the
        # attribute simply is not there and this is a no-op for a PO.
        customer_code = getattr(payload, "customer_code", None)
        if customer_code:
            values["debtor_code"] = normalize_debtor_code(customer_code)
        # PO currency default (D1): only a spec that carries a `currency`
        # header column reaches this, which today is `purchase_orders` alone -
        # so the fill is shape-driven rather than a hardcoded entity check.
        if "currency" in values and not values["currency"]:
            values["currency"] = DEFAULT_PO_CURRENCY
        # Adoption takes ownership: from here on the row is AutoCount's, and the
        # next push has to find it by reference rather than by number again.
        values["source_system"] = SOURCE_SYSTEM
        values["source_ref"] = payload.source_ref
        if spec.doc_no_column:
            values[spec.doc_no_column] = getattr(payload, spec.number_field)
        return values

    def _line_values(
        self, spec: DocumentSpec, line: Any, index: int, status: str, warnings: list[str]
    ) -> dict[str, Any]:
        values: dict[str, Any] = {
            column: getattr(line, field) for column, field in spec.line_fields
        }
        for column, ref_field, model, code_field, name_field in spec.line_refs:
            values[column] = self._resolve_master(
                model=model,
                ref_field=f"lines.{index}.{ref_field}",
                ref=getattr(line, ref_field),
                code_field=f"lines.{index}.{code_field}" if code_field else None,
                code=getattr(line, code_field) if code_field else None,
                name=getattr(line, name_field) if name_field else None,
                warnings=warnings,
            )
        # Same shape-driven PO currency fill as the header, for the per-line
        # `currency` column purchase-order lines alone carry.
        if "currency" in values and not values["currency"]:
            values["currency"] = DEFAULT_PO_CURRENCY
        # NOT NULL on both line tables, and an absent figure means none delivered.
        for column in ("qty_ordered", spec.line_delivered_field):
            if values.get(column) is None:
                values[column] = 0
        values["line_status"] = _line_status(
            status, values["qty_ordered"], values[spec.line_delivered_field]
        )
        values["source_system"] = SOURCE_SYSTEM
        values["source_ref"] = line.source_ref
        # AutoCount's Seq (D11), position only - popped before persistence by
        # every setattr site in `_sync_lines`/`_adopt_lines`. No column exists
        # for it on either line table.
        values["line_number"] = getattr(line, "line_number", None)
        return values

    def _resolve_ref(
        self, field: str, source_ref: Optional[str], model: type
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
        entity_id = self.refs.resolve(
            entity_type=model.__tablename__, source_ref=source_ref
        )
        if entity_id is None:
            raise MissingReference(field, source_ref)
        self._require_same_company(
            model, entity_id, f"{field} {source_ref!r}", field_name=field
        )
        return entity_id

    def _require_same_company(
        self, model: type, entity_id: str, subject: str, *, field_name: str = "source_ref"
    ) -> None:
        """Refuse a reference that resolves into another company.

        `integration_references` is global, so a ref finds its row whatever
        company the request anchored to. Binding this document to it - or
        updating it - would be a cross-company write wearing the clothes of an
        ordinary re-sync. Shared masters (`sales_agents`) carry no company at all
        and are visible from either anchor, so they are exempt.

        `field_name` (AC-V1-8) is the verdict-error key the conflict is filed
        under: the document's own `source_ref` for the header's own adoption
        check (the default, unchanged), or the specific master field (e.g.
        `"customer_ref"`) when this guards a v2 ladder resolution - so the ESB
        sees WHICH reference conflicted, not just that the record failed.
        """
        if not _is_company_scoped(model.__tablename__):
            return
        mine = (
            self.db.query(model.id)
            .filter(model.id == str(entity_id), model.company_id == self.company_id)
            .first()
        )
        if mine is None:
            raise ReferenceConflict(
                f"{subject} is linked to a record in another company",
                field_name=field_name,
            )

    # -------------------------------------------------------- v2 resolution
    def _resolve_master(
        self,
        *,
        model: type,
        ref_field: str,
        ref: Optional[str],
        code_field: Optional[str],
        code: Optional[str],
        name: Optional[str],
        warnings: list[str],
    ) -> Optional[str]:
        """Ref, then code, then (supplier only) name, then back-create (D1/D2/D10).

        A SENT ref that does not resolve is `MissingReference` on its own -
        unchanged from v1 - but ONLY when there is nothing else to try: the
        moment `code` or `name` is also present, an unresolved ref falls
        through to them rather than failing the whole record, because sending
        MORE identifying information must never make a push worse off than
        sending the ref alone (AC-V1-3, AC-V1-5). `warehouse` is the one
        exception end to end (D10): it never raises, a miss is always a NULL
        FK plus a warning, ref or code alike.
        """
        ref = (ref or "").strip() or None
        code = (code or "").strip() or None
        name = (name or "").strip() or None

        if ref:
            try:
                return self._resolve_ref(ref_field, ref, model)
            except MissingReference:
                if model is Warehouse:
                    warnings.append(WARN_WAREHOUSE_UNRESOLVED)
                    return None
                if not code and not name:
                    raise

        entity_id = self._resolve_by_fallback(model, code, name, warnings)
        if entity_id is not None:
            if ref:
                # The ref did not resolve above, but the row it names now
                # exists (or was just found by code/name) - register it so
                # the NEXT push is a step-1 ref match (D1).
                self.refs.link(
                    entity_type=model.__tablename__,
                    entity_id=entity_id,
                    source_ref=ref,
                    integration_id=self.integration_id,
                )
            return entity_id

        if model is Warehouse:
            warnings.append(WARN_WAREHOUSE_UNRESOLVED)
            return None
        if model is Product:
            raise MissingReference(code_field if code else ref_field, code or ref)
        if model is Customer:
            if code:
                warnings.append(WARN_CUSTOMER_UNRESOLVED)
                return None
            if ref:
                raise MissingReference(ref_field, ref)
            return None
        if ref:
            # Supplier / sales agent: nothing was sent to fall back on, so this
            # is exactly the v1 shape - a sent ref that never resolved.
            raise MissingReference(ref_field, ref)
        return None

    def _resolve_by_fallback(
        self, model: type, code: Optional[str], name: Optional[str], warnings: list[str]
    ) -> Optional[str]:
        """Code, then (supplier only) name, then back-create. Never touches ref."""
        if model in (Product, Warehouse):
            return self._resolve_by_code(model, code) if code else None

        if model is SalesAgent:
            if not code:
                return None
            agent = sales_agent_service.resolve(self.db, code)
            if agent is None:
                agent = sales_agent_service.resolve_or_create(self.db, code)
                if agent is not None:
                    warnings.append(WARN_AGENT_CREATED)
            return str(agent.id) if agent is not None else None

        if model is Supplier:
            entity_id = self._resolve_by_code(model, code) if code else None
            if entity_id is None and name:
                entity_id = self._resolve_supplier_by_name(name)
            if entity_id is not None:
                return entity_id
            if code or name:
                supplier = back_create_supplier(
                    self.db,
                    code=code or supplier_slug(self.db, name),
                    name=name or code,
                )
                if supplier is not None:
                    warnings.append(WARN_SUPPLIER_CREATED)
                    return str(supplier.id)
            return None

        if model is Customer:
            entity_id = self._resolve_by_code(model, code) if code else None
            if entity_id is not None:
                return entity_id
            # D2: only when BOTH are sent - the unique index is on the pair,
            # and a code-only row would collide with a later named one.
            if code and name:
                customer = customer_back_create.get_or_create(self.db, code=code, name=name)
                if customer is not None:
                    warnings.append(WARN_CUSTOMER_CREATED)
                    return str(customer.id)
            return None

        return None

    def _resolve_by_code(self, model: type, code: str) -> Optional[str]:
        """Exact match on the model's code column, case/whitespace-insensitive.

        `order_by(id.desc())` rather than an unqualified `.scalar()`: a code is
        unique per company for every model here EXCEPT `customers` (D2 - one
        debtor code routinely carries more than one legal name), and a query
        that raises on more than one row would turn that into a 500 instead of
        a deterministic pick.
        """
        column = _CODE_COLUMNS[model]
        query = (
            self.db.query(model.id)
            .filter(func.upper(func.btrim(column)) == code.upper())
            .order_by(model.id.desc())
        )
        if _is_company_scoped(model.__tablename__):
            query = query.filter(model.company_id == self.company_id)
        row = query.first()
        return str(row[0]) if row else None

    def _resolve_supplier_by_name(self, name: str) -> Optional[str]:
        """The upload's own name-fallback rule: cleaned name, order by id desc.

        `supplier_name` carries no uniqueness constraint, so more than one row
        can share one - ordered so the pick is deterministic rather than
        whatever order Postgres happens to return (`outstanding_import_service
        ._resolve_parties_by_name`, which this mirrors).
        """
        cleaned = _clean_supplier_name(name)
        if not cleaned:
            return None
        row = (
            self.db.query(Supplier.id)
            .filter(func.upper(Supplier.supplier_name) == cleaned.upper())
            .filter(Supplier.company_id == self.company_id)
            .order_by(Supplier.id.desc())
            .first()
        )
        return str(row[0]) if row else None

    def _sync_lines(
        self, spec: DocumentSpec, header: Any, line_values: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Make the header's lines equal to the payload's, by the line's own ref.

        Five outcomes per line, counted for the verdict (D11, AC-V7-5):
        `updated` (matched by its own existing `source_ref`), `adopted` (an
        xlsx-era ref-less row claimed by `_adopt_lines`'s three-step match),
        `created` (neither matched, so a fresh row), `deleted` (an unmatched
        leftover row nothing points at) and `cancelled` (an unmatched leftover
        row something still points at).

        A line whose `source_ref` is NULL was written by the extract importer
        before AutoCount owned this document, and leaving it counted would
        count the same physical line twice - but deleting one a loading plan or
        a stock transfer points at either destroys that row (CASCADE) or
        orphans it (SET NULL). Cancelled satisfies both: the demand is gone,
        the row a dependent needs is still there. Adoption (D11) exists so
        that row is not manufactured fresh in the first place: the SAME
        physical line, matched by what it actually is rather than replaced,
        keeps every allocation, claim and GRN link that already hangs off it.
        """
        existing = (
            self.db.query(spec.line_model)
            .filter(getattr(spec.line_model, spec.line_fk) == str(header.id))
            .all()
        )
        by_ref: dict[str, Any] = {}
        pool: list[Any] = []
        # A second row sharing a ref another row already claims (should never
        # happen, but the original code guarded it) - a leftover like any
        # other, never a D11 adoption candidate since it already has A ref.
        dup_ref: list[Any] = []
        for row in existing:
            if row.source_ref and row.source_ref not in by_ref:
                by_ref[row.source_ref] = row
            elif row.source_ref:
                dup_ref.append(row)
            else:
                pool.append(row)

        counts = {"adopted": 0, "created": 0, "updated": 0, "deleted": 0, "cancelled": 0}

        unmatched: list[dict[str, Any]] = []
        for values in line_values:
            row = by_ref.pop(values["source_ref"], None)
            if row is not None:
                values.pop("line_number", None)
                for column, value in values.items():
                    setattr(row, column, value)
                counts["updated"] += 1
            else:
                unmatched.append(values)

        if unmatched and pool:
            self._adopt_lines(spec, unmatched, pool, counts)

        for values in unmatched:
            row = spec.line_model(
                id=str(uuid.uuid4()),
                company_id=self.company_id,
                **{spec.line_fk: str(header.id)},
            )
            self.db.add(row)
            values.pop("line_number", None)
            for column, value in values.items():
                setattr(row, column, value)
            counts["created"] += 1

        line_table = spec.line_model.__tablename__
        for row in [*by_ref.values(), *pool, *dup_ref]:
            if is_referenced(self.db, line_table, row.id):
                # Quantities and prices are left exactly as they were: this row
                # is now evidence of what a transfer moved or a plan was built
                # from, and rewriting it would falsify that record.
                row.line_status = CANCELLED
                counts["cancelled"] += 1
            else:
                self.db.delete(row)
                counts["deleted"] += 1
        self.db.flush()
        return counts

    def _adopt_lines(
        self,
        spec: DocumentSpec,
        unmatched: list[dict[str, Any]],
        pool: list[Any],
        counts: dict[str, int],
    ) -> None:
        """D11: claim ref-less POOL rows for ref-less UNMATCHED incoming lines.

        Three ordered passes over what the PREVIOUS pass left unclaimed:

        1. exact `(product_id, warehouse_id-or-None, outstanding)` key, ties
           among rows/lines sharing one key broken by position;
        2. `(product_id, warehouse_id-or-None)` alone, only where exactly one
           pool row remains for it;
        3. position alone (incoming `line_number` order against the rows' own
           `created_at, id` order), only where the remaining counts agree.

        `outstanding` is `qty_ordered - qty_delivered|qty_received`, never
        `qty_ordered` alone - the upload writes `qty_ordered = outstanding` on
        an open xlsx-era line and `fulfilled + outstanding` on update, so
        `qty_ordered` on such a row is not AutoCount's Qty; outstanding is the
        one figure both sides agree on. Mutates `unmatched` and `pool` in
        place, removing whatever it claims - what is left in `unmatched` is a
        genuinely new line, what is left in `pool` is a genuinely stale row
        for the caller's existing delete-or-cancel step.
        """
        delivered_field = spec.line_delivered_field
        all_have_line_number = all(v.get("line_number") is not None for v in unmatched)

        def _position(idx: int, values: dict[str, Any]):
            return values["line_number"] if all_have_line_number else idx

        def _row_created(row: Any):
            return row.created_at or datetime.min

        def _row_key(row: Any):
            ordered = getattr(row, "qty_ordered", None) or Decimal("0")
            delivered = getattr(row, delivered_field, None) or Decimal("0")
            outstanding = (ordered - delivered).quantize(Decimal("0.0001"))
            return (
                str(row.product_id) if row.product_id else None,
                str(row.warehouse_id) if row.warehouse_id else None,
                outstanding,
            )

        def _line_key(values: dict[str, Any]):
            ordered = values.get("qty_ordered") or Decimal("0")
            delivered = values.get(delivered_field) or Decimal("0")
            outstanding = (ordered - delivered).quantize(Decimal("0.0001"))
            product_id = values.get("product_id")
            warehouse_id = values.get("warehouse_id")
            return (
                str(product_id) if product_id else None,
                str(warehouse_id) if warehouse_id else None,
                outstanding,
            )

        claimed_lines: set[int] = set()
        claimed_rows: set[int] = set()

        def _claim(idx: int, values: dict[str, Any], row: Any) -> None:
            values.pop("line_number", None)
            for column, value in values.items():
                setattr(row, column, value)
            counts["adopted"] += 1
            claimed_lines.add(idx)
            claimed_rows.add(id(row))

        # ---- pass 1: exact (product, warehouse, outstanding) key ----
        pool_by_key: dict[tuple, list] = {}
        for row in pool:
            pool_by_key.setdefault(_row_key(row), []).append(row)
        for rows in pool_by_key.values():
            rows.sort(key=lambda r: (_row_created(r), str(r.id)))

        lines_by_key: dict[tuple, list] = {}
        for idx, values in enumerate(unmatched):
            lines_by_key.setdefault(_line_key(values), []).append(idx)
        for indices in lines_by_key.values():
            indices.sort(key=lambda i: _position(i, unmatched[i]))

        for key, indices in lines_by_key.items():
            rows = pool_by_key.get(key, [])
            for idx, row in zip(indices, rows):
                _claim(idx, unmatched[idx], row)

        # ---- pass 2: (product, warehouse) alone, exactly one row remaining ----
        remaining_indices = sorted(
            (i for i in range(len(unmatched)) if i not in claimed_lines),
            key=lambda i: _position(i, unmatched[i]),
        )
        pw_pool: dict[tuple, list] = {}
        for row in pool:
            if id(row) in claimed_rows:
                continue
            pw_pool.setdefault(
                (
                    str(row.product_id) if row.product_id else None,
                    str(row.warehouse_id) if row.warehouse_id else None,
                ),
                [],
            ).append(row)

        for idx in remaining_indices:
            values = unmatched[idx]
            pw_key = (
                str(values.get("product_id")) if values.get("product_id") else None,
                str(values.get("warehouse_id")) if values.get("warehouse_id") else None,
            )
            rows = pw_pool.get(pw_key)
            if rows and len(rows) == 1:
                row = rows[0]
                _claim(idx, values, row)
                pw_pool[pw_key] = []

        # ---- pass 3: position alone, only when the remaining counts agree ----
        remaining_indices = [i for i in range(len(unmatched)) if i not in claimed_lines]
        remaining_pool = [r for r in pool if id(r) not in claimed_rows]
        if remaining_indices and len(remaining_indices) == len(remaining_pool):
            remaining_indices.sort(key=lambda i: _position(i, unmatched[i]))
            remaining_pool.sort(key=lambda r: (_row_created(r), str(r.id)))
            for idx, row in zip(remaining_indices, remaining_pool):
                _claim(idx, unmatched[idx], row)

        for idx in sorted(claimed_lines, reverse=True):
            del unmatched[idx]
        pool[:] = [r for r in pool if id(r) not in claimed_rows]

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
        # The route 404s an unknown entity (`_entity`) and dispatches to this
        # class only for `DOCUMENT_ENTITIES`, so a missing spec here would mean
        # the two lists had come apart, not that a caller asked for something odd.
        spec = DOCUMENT_SPECS[entity_type]

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
        for column, field, model, _code_field, _name_field in spec.header_refs:
            record[field] = self._ref_of(model, getattr(header, column))
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
        for column, field, model, _code_field, _name_field in spec.line_refs:
            record[field] = self._ref_of(model, getattr(line, column))
        for column, field in spec.line_fields:
            record[field] = getattr(line, column)
        return record

    def _ref_of(self, model: type, entity_id: Optional[str]) -> Optional[str]:
        if not entity_id:
            return None
        origin = self.refs.origin_of(
            entity_type=model.__tablename__, entity_id=str(entity_id)
        )
        return str(origin.source_ref) if origin is not None else None
