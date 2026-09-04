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
# `MasterRefResolver` is the ref/code/name/back-create ladder (D1/D2/D10),
# shared with `ShippingOrderIngestService` (S3) - lifted out in S3 rather than
# duplicated, see that module's docstring.
from app.services.master_ref_resolver import WARN_UNCLASSIFIED_DEMAND, MasterRefResolver
from app.services.master_ingest_service import (
    IngestOutcome,
    IngestResult,
    MissingReference,
    RecordResult,
    UnsupportedIngestEntity,
    _field_errors,
    _value_changed,
)
from app.services.scm import order_link_service, plan_exception_service
from app.services.scm.customer_label import normalize_debtor_code
from app.services.scm.demand_class import classify_document
# `DEFAULT_PO_CURRENCY` is the upload's own rule (D1's CNY fill) - imported
# rather than restated so the two channels that read a purchase book from
# AutoCount cannot drift.
from app.services.scm.outstanding_import_service import DEFAULT_PO_CURRENCY
# D5: an `SPO-` numbered document belongs under `shipping_orders`, never
# `purchase_orders` - the same family test the PO listing importer uses.
from app.services.scm.po_listing_reader import FAMILY_SPO, doc_family

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
    # D6a (S5): a `partial` sales order is stored `open`, not `partially_delivered`.
    # `qty_delivered` already carries the partial fact per line, and `open` is the
    # one word `scm.committed_v` and every other SCM reader already admits as
    # committed demand - mapping `partial` onto it needs zero view changes, where
    # widening every one of those readers to also admit `partially_delivered`
    # would (plan D6, option (a) over (b)). This makes the map NOT injective:
    # `partial` and `open` both stored as `open`. `_canonical_status` below
    # therefore reads back `open` for either - see its own docstring.
    "partial": "open",
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

# The rest of the verdict-warning vocabulary (D9) - `customer_created`,
# `supplier_created`, `agent_created`, `warehouse_unresolved`,
# `customer_unresolved` - lives on `master_ref_resolver` next to the ladder
# that emits them (S3). `WARN_UNCLASSIFIED_DEMAND` is imported above since
# `_classify_sales_order` below is the only thing that raises it.


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

    D6a (S5) makes `SALES_ORDER_STATUS_MAP` NOT injective: `open` and `partial`
    both store `open`. The FIRST canonical word whose mapping matches wins - dict
    order is declaration order, and `open` is declared before `partial` - so a
    stored `open` row always reads back `open` (AC-V5-3), never `partial`, which
    is correct: once written, nothing on the row still says which canonical word
    produced it, and `open` is the more general of the two.
    """
    if stored is None:
        return None
    for canonical, mapped in spec.status_map.items():
        if mapped == stored:
            return canonical
    return stored


class _UnknownStatus(ValueError):
    """A status word outside the canonical vocabulary. Failed, never stored."""


class DocumentIngestService(MasterRefResolver):
    """Same constructor and same ``ingest()`` contract as ``MasterIngestService``.

    Deliberately interchangeable: the route picks one or the other on the entity
    name and calls the same method, so there is one ingest endpoint rather than
    two that can drift on batch caps, verdicts or the dry-run rollback.

    Subclasses `MasterRefResolver` for the ref/code/name/back-create ladder
    (`_resolve_master` and its helpers) - shared with `ShippingOrderIngestService`
    rather than duplicated (S3).
    """

    def __init__(
        self, db: Session, integration_id: Optional[str] = None, *, company_id: str
    ):
        # Required, for the reason the master ingest states: a default would be
        # the incumbent company, and a push meant for the other one would land
        # there silently.
        super().__init__(db, integration_id, company_id=company_id)
        self._dry_run = False
        # D7/S5 (plan section 2.6): what the ROUTE's post-write hooks need, read
        # off this instance after `ingest()` returns rather than threaded through
        # `IngestResult` - plain attributes, no new classes, and `MasterIngestService`
        # (which the route also constructs for masters) needs none of them.
        # Populated only by a record that actually WROTE (the last lines of `_apply`,
        # after everything else in it has already succeeded) - a savepoint rollback
        # is a Python-level no-op here since execution never reaches that point.
        self.touched_product_ids: set[str] = set()
        self.so_numbers: set[str] = set()
        self.written_header_ids: set[str] = set()
        # (product_id, supplier_id, po_number) triples, purchase_orders only -
        # what `supersede_crm_raised_pos` (the extracted shared function) wants.
        self.po_supersede_triples: set[tuple[str, str, str]] = set()
        # sales_orders only: the BEFORE half of the route's plan-exception hook
        # (AC-V5-1), keyed by product id. Captured per record, the first time
        # THIS BATCH touches a product and before anything is written for it
        # (`_capture_plan_exception_before`) - the same "read the old position
        # while it is still the one in the database" rule
        # `outstanding_import_service.apply` follows for its own
        # `before_positions`, generalised across a multi-record batch by never
        # overwriting a product already captured.
        self.plan_exception_before: dict[str, Any] = {}

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

        # D5: an `SPO-` numbered document pushed as a purchase order is refused
        # outright, before any savepoint work - it is a shipping order wearing
        # the wrong entity name, and adopting it here would create a phantom
        # purchase order `spo_allocations` can never link back to.
        if spec.entity_type == "purchase_orders" and doc_family(payload.po_number) == FAMILY_SPO:
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.FAILED,
                errors={"po_number": "shipping order; push under shipping_orders"},
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
        # The header is resolved (not yet written into) BEFORE `_header_values`, unlike
        # every other value here: D4's fill-only `order_type` and never-downgraded
        # `demand_class` both have to read what the row ALREADY holds, which does not
        # exist to read until `_header` has found-or-created it. For a CREATE, `header`
        # is deliberately not in the session yet (see `_header`'s comment) - added just
        # below, once `header_values` is complete and about to be written, so no query
        # the ref/demand ladders run in between can autoflush a half-built row and fail
        # on its own not-null constraints.
        header, outcome = self._header(spec, payload)
        header_values = self._header_values(spec, payload, status, warnings, header)
        line_values = [
            self._line_values(spec, line, index, status, warnings)
            for index, line in enumerate(payload.lines)
        ]
        # D7/S5: the BEFORE snapshot, taken here because this is the last point
        # before ANY write for this record - `header` is not yet `db.add()`-ed
        # (a CREATE) and `_sync_lines` has not run - and it must be per-product
        # rather than per-record, since a busy batch names the same product on
        # more than one line.
        if spec.entity_type == "sales_orders":
            self._capture_plan_exception_before(line_values)

        # Only an update overwrites anything, and only a dry run needs to say so.
        diff = (
            self._diff(header, header_values)
            if outcome is IngestOutcome.UPDATED
            else None
        )
        self.db.add(header)
        for column, value in header_values.items():
            setattr(header, column, value)
        self.db.flush()

        line_counts = self._sync_lines(spec, header, line_values)
        if spec.entity_type == "purchase_orders":
            self._write_order_link_claims(header, payload)
        self.refs.link(
            entity_type=spec.entity_type,
            entity_id=str(header.id),
            source_ref=payload.source_ref,
            source_doc_no=payload.source_doc_no,
            integration_id=self.integration_id,
        )
        # D7/S5: recorded LAST - everything above has already succeeded by here,
        # so a record whose ladder or status word failed earlier never reaches
        # this line and never pollutes the batch-level state the route's hooks
        # read after `ingest()` returns.
        self._record_hook_state(spec, header, payload, header_values, line_values)
        return outcome, str(header.id), diff, warnings, line_counts

    def _capture_plan_exception_before(self, line_values: list[dict[str, Any]]) -> None:
        """The BEFORE half of AC-V5-1, one snapshot per product, first-touch-wins.

        Best-effort like the upload's own equivalent: a defect here must cost
        the route's plan-exception hook (which simply has less to compare
        against), never this record - a document ingest is not the operation
        this diff is FOR.
        """
        new_ids = [
            str(values["product_id"])
            for values in line_values
            if values.get("product_id")
            and str(values["product_id"]) not in self.plan_exception_before
        ]
        if not new_ids:
            return
        try:
            self.plan_exception_before.update(
                plan_exception_service.snapshot(self.db, new_ids)
            )
        except Exception:  # noqa: BLE001 - best-effort, see docstring
            logger.warning(
                "ingest.plan_exception_before_snapshot_failed product_ids=%s",
                new_ids,
                exc_info=True,
            )

    def _record_hook_state(
        self,
        spec: DocumentSpec,
        header: Any,
        payload: Any,
        header_values: dict[str, Any],
        line_values: list[dict[str, Any]],
    ) -> None:
        """What the route's post-write hooks (D7) need, gathered per record."""
        self.written_header_ids.add(str(header.id))
        for values in line_values:
            product_id = values.get("product_id")
            if product_id:
                self.touched_product_ids.add(str(product_id))

        if spec.entity_type == "sales_orders":
            self.so_numbers.add(payload.so_number)
        elif spec.entity_type == "purchase_orders":
            supplier_id = header_values.get("supplier_id")
            if supplier_id:
                for values in line_values:
                    product_id = values.get("product_id")
                    if product_id:
                        self.po_supersede_triples.add(
                            (str(product_id), str(supplier_id), payload.po_number)
                        )

    def _write_order_link_claims(self, header: Any, payload: Any) -> None:
        """V4 (plan section 2.5): a PO line dedicating its purchase against
        sales orders the ESB already knows the numbers of.

        Runs AFTER the lines are flushed, so every line named has a real id
        to claim against. Inside the SAME record savepoint as everything
        else in `_apply` - a dry run rolls this back with the rest of the
        record, never a special case of its own (AC-V4-4).
        """
        wanted = [
            (line.source_ref, [n for n in (line.from_so_numbers or []) if n])
            for line in payload.lines
            if getattr(line, "from_so_numbers", None)
        ]
        if not wanted:
            return

        refs = [source_ref for source_ref, _ in wanted]
        rows = (
            self.db.query(PurchaseOrderLine)
            .filter(
                PurchaseOrderLine.purchase_order_id == str(header.id),
                PurchaseOrderLine.source_ref.in_(refs),
            )
            .all()
        )
        rows_by_ref = {row.source_ref: row for row in rows}
        product_ids = {row.product_id for row in rows if row.product_id}
        codes = (
            dict(
                self.db.query(Product.id, Product.product_code)
                .filter(Product.id.in_(product_ids))
                .all()
            )
            if product_ids
            else {}
        )

        seen: set[tuple[str, str, Optional[str]]] = set()
        so_numbers: set[str] = set()
        for source_ref, numbers in wanted:
            row = rows_by_ref.get(source_ref)
            if row is None:
                continue
            item_code = codes.get(row.product_id)
            for number in numbers:
                key = (number, payload.po_number, item_code)
                if key in seen:
                    continue
                seen.add(key)
                order_link_service.claim_book_pairing(
                    self.db,
                    company_id=self.company_id,
                    so_number=number,
                    po_number=payload.po_number,
                    item_code=item_code,
                    source=order_link_service.SOURCE_AUTOCOUNT,
                    po_line_id=str(row.id),
                )
                so_numbers.add(number)

        if so_numbers:
            self.db.flush()
            order_link_service.resolve(self.db, so_numbers=so_numbers)

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
        # NOT `db.add()`-ed here on purpose. `_header_values` (D4) reads this
        # object's stored columns before the caller ever writes into it -
        # harmless for an UPDATE (`_load` returns an already-persisted row),
        # but a CREATE's row would otherwise sit in the session as a pending
        # INSERT with every NOT NULL column still empty. Any query anywhere
        # between here and the setattr loop - the ref/code ladder's lookups, a
        # back-create's own explicit flush - would autoflush that half-built
        # row and fail on its own constraints. `_apply` adds it once
        # `header_values` is complete and about to be written.
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
        self,
        spec: DocumentSpec,
        payload: Any,
        status: str,
        warnings: list[str],
        header: Any,
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
        # v2 demand classification (D4, sales_orders only). `order_type` only
        # exists on `CanonicalSalesOrder`, so this is a no-op for a PO - the
        # same shape-driven guard the currency fill above uses.
        if hasattr(payload, "order_type"):
            self._classify_sales_order(payload, values, warnings, header, customer_code)
        # Adoption takes ownership: from here on the row is AutoCount's, and the
        # next push has to find it by reference rather than by number again.
        values["source_system"] = SOURCE_SYSTEM
        values["source_ref"] = payload.source_ref
        if spec.doc_no_column:
            values[spec.doc_no_column] = getattr(payload, spec.number_field)
        return values

    def _classify_sales_order(
        self,
        payload: Any,
        values: dict[str, Any],
        warnings: list[str],
        header: Any,
        customer_code: Optional[str],
    ) -> None:
        """D4 (plan section 1/2.3): fill-only `order_type`, never-downgraded `demand_class`.

        A stored `demand_class` is a settled fact - possibly set by CS by hand,
        possibly by an order_type this same ladder decided on an earlier push -
        and this ingest never overwrites or blanks it, whatever a fresh run of
        the ladder would say today (AC-V2-6). Only when NOTHING is stored yet
        does `classify_document` run at all.
        """
        stored_order_type = getattr(header, "order_type", None)
        stated_order_type = payload.order_type
        if not stored_order_type and stated_order_type:
            values["order_type"] = stated_order_type

        if getattr(header, "demand_class", None):
            return

        agent_id = values.get("sales_agent_id")
        agent_demand_class = (
            self.db.query(SalesAgent.demand_class).filter(SalesAgent.id == agent_id).scalar()
            if agent_id
            else None
        )
        debtor_code = customer_code or getattr(header, "debtor_code", None)
        customer_id = values.get("customer_id")
        if not debtor_code and customer_id:
            # No code was SENT and none is stored yet, but the ref resolved to a
            # real customer - its own code is the debtor code this document
            # names, just not spelled out in this particular payload.
            debtor_code = (
                self.db.query(Customer.customer_code)
                .filter(Customer.id == customer_id)
                .scalar()
            )

        cls = classify_document(
            self.db,
            stored_order_type=stored_order_type,
            stated_order_type=stated_order_type,
            agent_demand_class=agent_demand_class,
            debtor_code=debtor_code,
            company_id=self.company_id,
        )
        if cls is not None:
            values["demand_class"] = cls
        else:
            warnings.append(WARN_UNCLASSIFIED_DEMAND)

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
        # `order_type` (D4) is read-only here on purpose - NOT added to
        # `header_fields`, which `_header_values` also uses to build the write
        # side, where it would restate the payload's value unconditionally and
        # break the fill-only rule (AC-V2-1). `PurchaseOrder` has no such
        # column, hence the guard rather than a per-entity literal.
        if hasattr(header, "order_type"):
            record["order_type"] = header.order_type
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
