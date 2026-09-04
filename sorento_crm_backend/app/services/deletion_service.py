"""Delete records the ESB says are gone upstream, or take them out of use (A4).

AutoCount deletes a master or a document and tells us its source refs. What we
do with that is not a `DELETE`, and the reason is in the foreign keys.

**A dependent is asked about, never discovered by failing.** Half the FKs
pointing at these tables are `ON DELETE SET NULL` - `sales_orders.customer_id`
is one. A bare `DELETE` of a customer with a hundred orders therefore SUCCEEDS,
and leaves a hundred orders belonging to nobody: the data is not gone, it is
silently detached, and the sync reports it removed the record cleanly. So the
catalogue is asked who points at the row first (`app/services/dependent_probe.py`,
which the document ingest asks the same question of before removing a line), and
anything pointing means the row stays.

**Staying means going out of use, not staying as it was.** A master with
dependents is deactivated; a document with dependents is `cancelled`, since a
document has no `is_active` and cancellation is what takes its demand out of
every plan. The integration reference stays linked either way - the row is still
AutoCount's, and a later re-push must find it rather than create a second one.

**A product is discontinued, not deactivated.** `is_active` is not the lever
there: placeholder products that exist only for order bookkeeping have to stay
active because orders reference them (`app/models/product.py`), so
`is_discontinued` is the flag that means retired.

Per-record SAVEPOINT isolation and the dry-run-is-a-real-run-taken-back rule are
the ingest's, imported rather than restated: a batch is not a transaction, and a
preview that writes is the one outcome this endpoint must never produce.
"""
from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import Customer
from app.models.procurement import SPOAllocation, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.sales_agent import SalesAgent
from app.services.dependent_probe import is_referenced, referrers_of, relation_name
from app.services.document_ingest_service import CANCELLED, DOCUMENT_SPECS
from app.services.integration_reference_service import IntegrationReferenceService
from app.services.master_ingest_service import (
    UnsupportedIngestEntity,
    _is_company_scoped,
)
from app.services.shipping_order_ingest_service import (
    LINE_CLOSED,
    SHIPPING_ORDERS_ENTITY,
)

logger = logging.getLogger(__name__)


class DeletionOutcome(str, enum.Enum):
    DELETED = "deleted"
    DEACTIVATED = "deactivated"
    NOT_FOUND = "not_found"
    FAILED = "failed"


@dataclass
class DeletionRecordResult:
    source_ref: Optional[str]
    outcome: DeletionOutcome
    entity_id: Optional[str] = None
    # field -> reason, so the ESB can quarantine per record without parsing prose.
    errors: dict[str, str] = field(default_factory=dict)


@dataclass
class DeletionResult:
    """Same envelope shape as ``IngestResult``, with the deletion's verdicts."""

    records: list[DeletionRecordResult] = field(default_factory=list)
    dry_run: bool = False

    def _count(self, outcome: DeletionOutcome) -> int:
        return sum(1 for r in self.records if r.outcome is outcome)

    def as_dict(self) -> dict[str, Any]:
        return {
            # Echoed so a caller can never mistake a preview for a completed run.
            "dry_run": self.dry_run,
            "summary": {
                "total": len(self.records),
                "deleted": self._count(DeletionOutcome.DELETED),
                "deactivated": self._count(DeletionOutcome.DEACTIVATED),
                "not_found": self._count(DeletionOutcome.NOT_FOUND),
                "failed": self._count(DeletionOutcome.FAILED),
            },
            "records": [
                {
                    "source_ref": r.source_ref,
                    "outcome": r.outcome.value,
                    "entity_id": r.entity_id,
                    **({"errors": r.errors} if r.errors else {}),
                }
                for r in self.records
            ],
        }


# The model behind each entity name. The delete goes through the ORM rather than
# raw SQL for one reason: a document's lines have to go with their header, and
# the cascade that does that is declared on the relationship. The document half
# is taken from `DOCUMENT_SPECS` so the two cannot list different classes; the
# master half is written out, and a master reachable on the ingest but missing
# here is refused as an unknown deletion entity rather than silently ignored.
ENTITY_MODELS: dict[str, type] = {
    "product_categories": ProductCategory,
    "units_of_measure": UnitOfMeasure,
    "warehouses": Warehouse,
    "suppliers": Supplier,
    "customers": Customer,
    "products": Product,
    "sales_agents": SalesAgent,
    **{name: spec.header_model for name, spec in DOCUMENT_SPECS.items()},
}

# What "out of use" means per master. `products` is the odd one and deliberately
# so: an is_active=false product would disappear from screens that orders still
# point at, and the placeholder rows the order bookkeeping needs must stay active
# (app/models/product.py). Documents are not here - they carry no is_active at
# all, and their retirement is `status='cancelled'` (see `_deactivate`).
MASTER_DEACTIVATION: dict[str, tuple[str, Any]] = {
    "product_categories": ("is_active", False),
    "units_of_measure": ("is_active", False),
    "warehouses": ("is_active", False),
    "suppliers": ("is_active", False),
    "customers": ("is_active", False),
    "products": ("is_discontinued", True),
    "sales_agents": ("is_active", False),
}


class DeletionService:
    """Same constructor as ``MasterIngestService`` / ``DocumentIngestService``."""

    def __init__(
        self, db: Session, integration_id: Optional[str] = None, *, company_id: str
    ):
        self.db = db
        self.integration_id = integration_id
        # Required, for the reason the ingest states: a default would be the
        # incumbent company, and a deletion meant for the other one would remove
        # a row this caller never named.
        self.company_id = company_id
        self.refs = IntegrationReferenceService(db)

    def delete(
        self, entity_type: str, source_refs: list[str], *, dry_run: bool = False
    ) -> DeletionResult:
        """Apply a batch of deletions, one verdict per reference.

        With ``dry_run`` every record takes exactly the same path - the same
        probe, the same delete, the same fallback - and the transaction is then
        rolled back. Simulating it instead would produce a preview that can
        disagree with the run it predicts, which is worse than no preview.
        """
        # Shipping orders (D3, S3) resolve to MANY rows by `source_doc_ref`,
        # never to one `entity_id` via `IntegrationReferenceService` - a
        # wholly separate path, sharing only the batch loop and the dry-run
        # rollback below. `ENTITY_MODELS` / `_has_dependents` / `_hard_delete`
        # / `_deactivate` stay untouched; this entity never reaches them.
        if entity_type == SHIPPING_ORDERS_ENTITY:
            result = DeletionResult(dry_run=dry_run)
            try:
                for source_ref in source_refs:
                    result.records.append(self._delete_shipping_order(source_ref))
            finally:
                if dry_run:
                    self.db.rollback()
            return result

        if entity_type not in ENTITY_MODELS:
            raise UnsupportedIngestEntity(
                f"Unsupported deletion entity {entity_type!r}. "
                f"Expected one of: {', '.join(sorted(ENTITY_MODELS))}, "
                f"{SHIPPING_ORDERS_ENTITY}"
            )

        result = DeletionResult(dry_run=dry_run)
        try:
            for source_ref in source_refs:
                result.records.append(self._delete_one(entity_type, source_ref))
        finally:
            if dry_run:
                # In a finally, so an unexpected error mid-batch cannot leave a
                # partially applied preview in the session for whatever commits
                # next.
                self.db.rollback()
        return result

    # ------------------------------------------------------ shipping orders
    def _delete_shipping_order(self, source_ref: Any) -> DeletionRecordResult:
        """Every row this document's DocKey names, closed or removed in place.

        No `entity_id` to resolve through (D3) - the rows are found directly by
        `source_doc_ref`, scoped to the anchor company the same way every other
        deletion is. A row something still references (a GRN pick, an
        order-link claim) is closed rather than removed, exactly as
        `ShippingOrderIngestService` closes a leftover line on a re-push - the
        verdict is `deactivated` if ANY row in the group was referenced, `deleted`
        only when none were.
        """
        ref = source_ref if isinstance(source_ref, str) else str(source_ref)

        savepoint = self.db.begin_nested()
        try:
            rows = (
                self.db.query(SPOAllocation)
                .filter(
                    SPOAllocation.company_id == self.company_id,
                    SPOAllocation.source_doc_ref == ref,
                )
                .all()
            )
            if not rows:
                savepoint.commit()
                return DeletionRecordResult(source_ref=ref, outcome=DeletionOutcome.NOT_FOUND)

            any_referenced = False
            for row in rows:
                if is_referenced(self.db, "spo_allocations", row.id):
                    row.line_status = LINE_CLOSED
                    any_referenced = True
                else:
                    self.db.delete(row)
            self.db.flush()
            savepoint.commit()
            outcome = (
                DeletionOutcome.DEACTIVATED if any_referenced else DeletionOutcome.DELETED
            )
            return DeletionRecordResult(source_ref=ref, outcome=outcome)
        except Exception as exc:  # noqa: BLE001 - one record's failure, not the batch's
            if savepoint.is_active:
                savepoint.rollback()
            logger.warning(
                "deletion.record_failed entity=%s source_ref=%s error=%s",
                SHIPPING_ORDERS_ENTITY,
                ref,
                exc,
            )
            return DeletionRecordResult(
                source_ref=ref, outcome=DeletionOutcome.FAILED, errors={"_": str(exc)}
            )

    # ------------------------------------------------------------- one record
    def _delete_one(self, entity_type: str, source_ref: Any) -> DeletionRecordResult:
        ref = source_ref if isinstance(source_ref, str) else str(source_ref)
        entity_id: Optional[str] = None

        # Each record commits or rolls back alone. Without this savepoint a
        # failed flush poisons the session and every later reference in the batch
        # fails too, turning "one row we could not remove" into "nothing removed".
        savepoint = self.db.begin_nested()
        try:
            entity_id = self.refs.resolve(entity_type=entity_type, source_ref=ref)
            if entity_id is None or not self._in_anchor_company(entity_type, entity_id):
                # Another company's row reads exactly like a row that is not
                # there. It is not this caller's to delete, and telling it the
                # difference would confirm the row exists somewhere else.
                savepoint.commit()
                return DeletionRecordResult(
                    source_ref=ref, outcome=DeletionOutcome.NOT_FOUND
                )

            if not self._has_dependents(entity_type, entity_id):
                try:
                    self._hard_delete(entity_type, entity_id)
                    savepoint.commit()
                    return DeletionRecordResult(
                        source_ref=ref,
                        outcome=DeletionOutcome.DELETED,
                        entity_id=str(entity_id),
                    )
                except IntegrityError:
                    # A referrer the catalogue cannot see - a trigger, a deferred
                    # constraint. The failed flush poisons this savepoint, so it
                    # goes back and the fallback runs in a fresh one.
                    logger.info(
                        "deletion.delete_refused entity=%s id=%s falling back to deactivate",
                        entity_type,
                        entity_id,
                    )
                    savepoint.rollback()
                    savepoint = self.db.begin_nested()

            self._deactivate(entity_type, entity_id)
            savepoint.commit()
            return DeletionRecordResult(
                source_ref=ref,
                outcome=DeletionOutcome.DEACTIVATED,
                entity_id=str(entity_id),
            )
        except Exception as exc:  # noqa: BLE001 - one record's failure, not the batch's
            if savepoint.is_active:
                savepoint.rollback()
            logger.warning(
                "deletion.record_failed entity=%s source_ref=%s error=%s",
                entity_type,
                ref,
                exc,
            )
            return DeletionRecordResult(
                source_ref=ref,
                outcome=DeletionOutcome.FAILED,
                entity_id=str(entity_id) if entity_id else None,
                errors={"_": str(exc)},
            )

    def _in_anchor_company(self, entity_type: str, entity_id: str) -> bool:
        """Whether the resolved row belongs to the company this call anchored to.

        `integration_references` is global, so a ref finds its row whatever
        company the caller named. A shared master (`sales_agents`) carries no
        company at all and belongs to every anchor.
        """
        if not _is_company_scoped(entity_type):
            return True
        owner = self.db.execute(
            # Unqualified on purpose - see `app/services/dependent_probe.py`.
            text(f"SELECT company_id FROM {entity_type} WHERE id = :id"),
            {"id": str(entity_id)},
        ).scalar()
        return owner is not None and str(owner) == str(self.company_id)

    # ------------------------------------------------------------- the probe
    def _has_dependents(self, entity_type: str, entity_id: str) -> bool:
        # The entity name IS the table name on this surface, for masters and
        # documents alike (`ENTITY_SPECS`, `DOCUMENT_SPECS`), which is what makes
        # it safe to hand to the catalogue.
        spec = DOCUMENT_SPECS.get(entity_type)
        line_table = spec.line_model.__tablename__ if spec is not None else None
        # The catalogue renders a table name qualified exactly when it is NOT the
        # one that bare name resolves to, so `sales_order_lines` and
        # `projects.sales_order_lines` are told apart by asking the same resolver
        # the probe used. Comparing bare names would skip the module table as if
        # it were the document's own. The document's OWN lines are part of the
        # document, not a dependent on it: they cascade with the header, and what
        # matters is who points at THEM, probed below.
        line_relation = relation_name(self.db, line_table) if line_table else None

        if is_referenced(
            self.db, entity_type, entity_id, skip_relation=line_relation
        ):
            return True

        if spec is None:
            return False

        # Names come from the catalogue and from the spec, never from a payload;
        # the id is always bound. The join asks the same question as "load the
        # line ids, then probe each" in one statement per referrer, and it needs
        # no array binding to do it.
        for referrer, column in referrers_of(self.db, line_table):
            found = self.db.execute(
                text(
                    f"SELECT EXISTS (SELECT 1 FROM {referrer} r "
                    f'JOIN {line_table} l ON r."{column}" = l.id '
                    f"WHERE l.{spec.line_fk} = :id)"
                ),
                {"id": str(entity_id)},
            ).scalar()
            if found:
                return True
        return False

    # ------------------------------------------------------------- the arms
    def _hard_delete(self, entity_type: str, entity_id: str) -> None:
        """Remove the row and its mapping. Lines cascade with their header."""
        row = self.db.get(ENTITY_MODELS[entity_type], str(entity_id))
        if row is None:
            # The reference resolved and the company matched, so the row is
            # there; only a scope filter could hide it, and that is a bug worth
            # naming rather than a silent no-op.
            raise RuntimeError(
                f"{entity_type} {entity_id!r} resolved but is not readable in this company"
            )
        self.db.delete(row)
        self.db.flush()
        self.refs.unlink(entity_type=entity_type, entity_id=str(entity_id))

    def _deactivate(self, entity_type: str, entity_id: str) -> None:
        """Take the row out of use, leaving it and its mapping in place.

        Idempotent by construction: a row already out of use is written the same
        value again and still reports `deactivated`, because the ESB re-drains
        its queue and a second attempt at the same deletion is not an error.
        """
        spec = DOCUMENT_SPECS.get(entity_type)
        row = self.db.get(ENTITY_MODELS[entity_type], str(entity_id))
        if row is None:
            raise RuntimeError(
                f"{entity_type} {entity_id!r} resolved but is not readable in this company"
            )

        if spec is None:
            column, value = MASTER_DEACTIVATION[entity_type]
            setattr(row, column, value)
            self.db.flush()
            return

        # A document has no is_active. Cancelling the header is what takes its
        # demand out of the plans, and the lines have to follow: a line left
        # `open` under a cancelled header still reads as demand to the netting.
        row.status = CANCELLED
        lines = (
            self.db.query(spec.line_model)
            .filter(getattr(spec.line_model, spec.line_fk) == str(entity_id))
            .all()
        )
        for line in lines:
            line.line_status = CANCELLED
        self.db.flush()
