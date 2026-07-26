"""Ingest master data pushed in by the ESB (Phase C).

Three semantics carry this module, and each exists because of a specific way
the naive version fails:

**Per-record isolation.** Masters quarantine, they never block (AC-AC-15): a
batch of 10,000 products with 12 bad ones must import 9,988. That needs more
than a try/except -- a failed flush leaves the SQLAlchemy session unusable, so
one bad record would take out every record after it. Each record therefore runs
inside its own SAVEPOINT.

**Retryable is not failed.** A record referencing a master that has not been
synced yet is a sequencing artefact, not bad data (AC-AC-16). Reported
distinctly so the ESB re-drains it automatically, and deliberately *not*
persisted -- a half-written record with a dangling reference is worse than none.
Retrying genuinely invalid data, by contrast, is a queue that never drains.

**Adoption over duplication.** On first sync a record usually already exists
locally, matched by its business code. Creating a second one under a new id
would corrupt master data in a way that is painful to unpick, so an unclaimed
local match is adopted and linked instead.

**Dry run is a real run that is taken back.** ``ingest(..., dry_run=True)``
resolves and applies every record exactly as a live sync would, then rolls the
transaction back. Simulating the resolution separately would create a second
code path that can disagree with the first, and a preview that disagrees with
the sync it predicts is worse than no preview: it is trusted and wrong. For
records that would overwrite an existing row -- an adoption above all, where the
row holds hand-entered data -- the result carries a field-level diff of what
would be replaced.

Ingest emits **no lifecycle events** (AC-AC-18). A record arriving *from*
AutoCount must never trigger a write back to it. Nothing here calls an emitter,
and nothing here should ever be given one.
"""
from __future__ import annotations

import enum
import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional

from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.canonical_masters import (
    CanonicalCreditTerm,
    CanonicalCustomer,
    CanonicalPaymentMethod,
    CanonicalProductCategory,
    CanonicalSalesAgent,
    CanonicalTaxCode,
    CanonicalTaxEntity,
    CanonicalUnitOfMeasure,
    CanonicalProduct,
    CanonicalSupplier,
    CanonicalWarehouse,
)
from app.services.integration_reference_service import (
    IntegrationReferenceService,
    ReferenceConflict,
)

logger = logging.getLogger(__name__)


class UnsupportedIngestEntity(ValueError):
    """Raised for an entity this endpoint does not ingest."""


class MissingReference(Exception):
    """A referenced master is not present yet. Retryable, not a data error."""

    def __init__(self, field_name: str, code: str):
        self.field_name = field_name
        self.code = code
        super().__init__(f"{field_name}={code!r} not found")


class IngestOutcome(str, enum.Enum):
    CREATED = "created"
    UPDATED = "updated"
    FAILED = "failed"
    RETRYABLE = "retryable"


@dataclass
class RecordResult:
    source_ref: Optional[str]
    outcome: IngestOutcome
    entity_id: Optional[str] = None
    # field -> reason. Machine-readable so the ESB quarantines per record
    # without parsing prose (AC-AC-13).
    errors: dict[str, str] = field(default_factory=dict)
    # Dry run only. column -> {"current": ..., "incoming": ...} for the values
    # this record would overwrite on an existing row. None when nothing would be
    # overwritten (a create), which is a different statement from an empty dict
    # (an existing row matched, but no value actually changes).
    diff: Optional[dict[str, dict[str, Any]]] = None


@dataclass
class IngestResult:
    records: list[RecordResult] = field(default_factory=list)
    dry_run: bool = False

    @property
    def created(self) -> int:
        return sum(1 for r in self.records if r.outcome is IngestOutcome.CREATED)

    @property
    def updated(self) -> int:
        return sum(1 for r in self.records if r.outcome is IngestOutcome.UPDATED)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.records if r.outcome is IngestOutcome.FAILED)

    @property
    def retryable(self) -> int:
        return sum(1 for r in self.records if r.outcome is IngestOutcome.RETRYABLE)

    def as_dict(self) -> dict[str, Any]:
        return {
            # Echoed so a caller can never mistake a preview for a completed
            # sync -- the two responses are otherwise identical in shape, which
            # is deliberate but would be dangerous without this flag.
            "dry_run": self.dry_run,
            "summary": {
                "total": len(self.records),
                "created": self.created,
                "updated": self.updated,
                "failed": self.failed,
                "retryable": self.retryable,
            },
            "records": [
                {
                    "source_ref": r.source_ref,
                    "outcome": r.outcome.value,
                    "entity_id": r.entity_id,
                    **({"errors": r.errors} if r.errors else {}),
                    **({"diff": r.diff} if r.diff is not None else {}),
                }
                for r in self.records
            ],
        }


@dataclass
class EntitySpec:
    """How one canonical shape maps onto a Sorento table."""

    table: str
    schema: type[BaseModel]
    code_column: str
    # canonical payload -> column values. May raise MissingReference.
    to_columns: Callable[[BaseModel, Session], dict[str, Any]]


def _category_columns(payload: Any, db: Session) -> dict[str, Any]:
    return {
        "category_code": payload.code,
        "category_name": payload.name,
        "description": payload.description,
        "is_active": payload.is_active,
    }


def _uom_columns(payload: Any, db: Session) -> dict[str, Any]:
    return {
        "uom_code": payload.code,
        "uom_name": payload.name,
        "description": payload.description,
        "is_active": payload.is_active,
    }


def _warehouse_columns(payload: Any, db: Session) -> dict[str, Any]:
    return {
        "warehouse_code": payload.code,
        "warehouse_name": payload.name,
        "location": payload.location,
        "is_active": payload.is_active,
    }


def _resolve_payment_terms_days(
    db: Session, payment_terms_code: Optional[str], fallback_days: Optional[int]
) -> Optional[int]:
    """Days for a supplier/customer, resolved from the credit_terms master.

    Slice 1 landed credit_terms, so a ``payment_terms_code`` now resolves to a
    real ``term_days`` instead of being reported retryable forever. The code is
    the AutoCount DisplayTerm, matched against ``credit_terms.display_term``.

    Resolution order: an explicit numeric ``payment_terms_days`` on the payload
    wins (the ESB already knew the number); otherwise the code is looked up. A
    code that does not resolve is still retryable -- the credit term may simply
    not have synced yet -- never silently dropped.
    """
    if fallback_days is not None:
        return fallback_days
    if not payment_terms_code:
        return None
    row = db.execute(
        text("SELECT term_days FROM credit_terms WHERE display_term = :v LIMIT 1"),
        {"v": payment_terms_code},
    ).first()
    if row is None:
        raise MissingReference("payment_terms_code", payment_terms_code)
    # A matched-but-null term_days is a resolved term with no day count (e.g.
    # "Cash"); that is a real answer, not a miss.
    return row[0]


def _credit_term_columns(payload: Any, db: Session) -> dict[str, Any]:
    return {
        "display_term": payload.code,
        "terms": payload.terms,
        "term_days": payload.term_days,
        "is_active": payload.is_active,
    }


def _tax_code_columns(payload: Any, db: Session) -> dict[str, Any]:
    return {
        "tax_code": payload.code,
        "supply_purchase": payload.supply_purchase,
        "tax_rate": payload.tax_rate,
        "is_active": payload.is_active,
    }


def _sales_agent_columns(payload: Any, db: Session) -> dict[str, Any]:
    return {
        "sales_agent": payload.code,
        "description": payload.description,
        "is_active": payload.is_active,
    }


def _payment_method_columns(payload: Any, db: Session) -> dict[str, Any]:
    return {
        "payment_method": payload.code,
        "description": payload.description,
        "bank_account": payload.bank_account,
        "journal_type": payload.journal_type,
        "is_active": payload.is_active,
    }


def _tax_entity_columns(payload: Any, db: Session) -> dict[str, Any]:
    return {
        "tax_entity_id": payload.code,
        "name": payload.name,
        "tin": payload.tin,
        "identity_no": payload.identity_no,
        "tax_branch_id": payload.tax_branch_id,
        "tax_classification": payload.tax_classification,
        "gst_register_no": payload.gst_register_no,
        "sst_register_no": payload.sst_register_no,
        "tourism_tax_register_no": payload.tourism_tax_register_no,
        "trade_name": payload.trade_name,
        "business_activity_desc": payload.business_activity_desc,
        "msic_code": payload.msic_code,
        "address": payload.address,
        "post_code": payload.post_code,
        "city": payload.city,
        "state_code": payload.state_code,
        "country_code": payload.country_code,
        "phone": payload.phone,
        "email_address": payload.email_address,
        "is_active": payload.is_active,
    }


def _supplier_columns(payload: Any, db: Session) -> dict[str, Any]:
    terms = _resolve_payment_terms_days(db, payload.payment_terms_code, payload.payment_terms_days)
    return {
        "supplier_code": payload.code,
        "supplier_name": payload.name,
        "email": payload.email,
        "phone_number": payload.phone_number,
        "payment_terms_days": terms,
        "is_active": payload.is_active,
    }


def _customer_columns(payload: Any, db: Session) -> dict[str, Any]:
    terms = _resolve_payment_terms_days(db, payload.payment_terms_code, payload.payment_terms_days)
    return {
        "customer_code": payload.code,
        "customer_name": payload.name,
        "email": payload.email,
        "phone_number": payload.phone_number,
        "registration_number": payload.registration_number,
        "tax_id": payload.tax_id,
        "credit_limit": payload.credit_limit,
        "payment_terms_days": terms,
        "country": payload.country,
        "is_active": payload.is_active,
    }


def _lookup_id(db: Session, table: str, column: str, value: str) -> Optional[str]:
    row = db.execute(
        text(f"SELECT id FROM {table} WHERE {column} = :v LIMIT 1"), {"v": value}
    ).first()
    return str(row[0]) if row else None


def _product_columns(payload: Any, db: Session) -> dict[str, Any]:
    # products.category_id and base_uom_id are NOT NULL, so an unresolved code
    # makes the row uncreatable. That is a sequencing problem, not bad data.
    if not payload.category_code:
        raise MissingReference("category_code", "")
    category_id = _lookup_id(db, "product_categories", "category_code", payload.category_code)
    if category_id is None:
        raise MissingReference("category_code", payload.category_code)

    if not payload.uom_code:
        raise MissingReference("uom_code", "")
    uom_id = _lookup_id(db, "units_of_measure", "uom_code", payload.uom_code)
    if uom_id is None:
        raise MissingReference("uom_code", payload.uom_code)

    return {
        "product_code": payload.code,
        "product_name": payload.name,
        "description": payload.description,
        "category_id": category_id,
        "base_uom_id": uom_id,
        "list_price": payload.list_price if payload.list_price is not None else 0,
        "cost_price": payload.cost_price,
        "is_active": payload.is_active,
    }


ENTITY_SPECS: dict[str, EntitySpec] = {
    # Categories and UoMs first: products.category_id and base_uom_id are
    # NOT NULL, so a product whose category has not synced yet is retryable
    # and stays that way until these land.
    "product_categories": EntitySpec(
        "product_categories", CanonicalProductCategory, "category_code", _category_columns
    ),
    "units_of_measure": EntitySpec(
        "units_of_measure", CanonicalUnitOfMeasure, "uom_code", _uom_columns
    ),
    "warehouses": EntitySpec("warehouses", CanonicalWarehouse, "warehouse_code", _warehouse_columns),
    "suppliers": EntitySpec("suppliers", CanonicalSupplier, "supplier_code", _supplier_columns),
    "customers": EntitySpec("customers", CanonicalCustomer, "customer_code", _customer_columns),
    "products": EntitySpec("products", CanonicalProduct, "product_code", _product_columns),
    # Slice 1: credit_terms unblocks supplier/customer payment_terms_code;
    # tax_codes is the resolve-target for document-line TaxCode in later slices.
    "credit_terms": EntitySpec("credit_terms", CanonicalCreditTerm, "display_term", _credit_term_columns),
    "tax_codes": EntitySpec("tax_codes", CanonicalTaxCode, "tax_code", _tax_code_columns),
    # Slice 2: flat reference masters.
    "sales_agents": EntitySpec("sales_agents", CanonicalSalesAgent, "sales_agent", _sales_agent_columns),
    "payment_methods": EntitySpec("payment_methods", CanonicalPaymentMethod, "payment_method", _payment_method_columns),
    "tax_entities": EntitySpec("tax_entities", CanonicalTaxEntity, "tax_entity_id", _tax_entity_columns),
}


class MasterIngestService:
    def __init__(self, db: Session, integration_id: Optional[str] = None):
        self.db = db
        self.integration_id = integration_id
        self.refs = IntegrationReferenceService(db)
        # Set for the duration of a dry-run ingest. Read by _apply to decide
        # whether to capture a before/after diff; the rollback that makes the
        # run harmless is handled in ingest().
        self._dry_run = False

    def ingest(
        self, entity_type: str, records: list[dict], *, dry_run: bool = False
    ) -> IngestResult:
        """Apply a batch of canonical records.

        With ``dry_run`` the records are resolved and applied exactly as they
        would be for real -- adoption matching, reference conflicts, unique
        constraints and all -- and the whole transaction is then rolled back.
        Simulating the resolution instead would produce a preview that can
        disagree with the sync it claims to predict, which is worse than no
        preview at all; the only way to know what the database would do is to
        ask it and then take it back.
        """
        spec = ENTITY_SPECS.get(entity_type)
        if spec is None:
            raise UnsupportedIngestEntity(
                f"Unsupported ingest entity {entity_type!r}. "
                f"Expected one of: {', '.join(sorted(ENTITY_SPECS))}"
            )

        result = IngestResult(dry_run=dry_run)
        self._dry_run = dry_run
        try:
            for raw in records:
                result.records.append(self._ingest_one(entity_type, spec, raw))
        finally:
            self._dry_run = False
            if dry_run:
                # In a finally, so an unexpected error mid-batch cannot leave a
                # partially-applied preview sitting in the session for whatever
                # commits next.
                self.db.rollback()
        return result

    def _ingest_one(self, entity_type: str, spec: EntitySpec, raw: dict) -> RecordResult:
        source_ref = raw.get("source_ref") if isinstance(raw, dict) else None

        try:
            payload = spec.schema(**raw)
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

        # Each record commits or rolls back alone. Without this savepoint a
        # failed flush poisons the session and every later record in the batch
        # fails too -- turning "12 bad rows" into "nothing imported".
        savepoint = self.db.begin_nested()
        try:
            outcome, entity_id, diff = self._apply(entity_type, spec, payload)
            savepoint.commit()
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=outcome,
                entity_id=entity_id,
                diff=diff,
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
        except Exception as exc:  # noqa: BLE001 - one record's failure, not the batch's
            savepoint.rollback()
            logger.warning(
                "ingest.record_failed entity=%s source_ref=%s error=%s",
                entity_type,
                payload.source_ref,
                exc,
            )
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.FAILED,
                errors={"_": str(exc)},
            )

    def _apply(
        self, entity_type: str, spec: EntitySpec, payload: Any
    ) -> tuple[IngestOutcome, str, Optional[dict[str, dict[str, Any]]]]:
        columns = spec.to_columns(payload, self.db)

        existing_id = self.refs.resolve(entity_type=entity_type, source_ref=payload.source_ref)
        if existing_id is not None:
            diff = self._diff(spec, existing_id, columns)
            self._update(spec, existing_id, columns)
            self._link(entity_type, existing_id, payload)
            return IngestOutcome.UPDATED, existing_id, diff

        # First sync: adopt a local record with the same business code rather
        # than creating a duplicate under a new id.
        adopted = _lookup_id(self.db, spec.table, spec.code_column, payload.code)
        if adopted is not None:
            if self.refs.origin_of(entity_type=entity_type, entity_id=adopted) is not None:
                # Already claimed by a different source document -- surfacing
                # beats silently retargeting someone else's record.
                raise ReferenceConflict(
                    f"{spec.code_column}={payload.code!r} is already linked to another source"
                )
            # Captured before the UPDATE, and the reason the dry run exists: an
            # adoption overwrites a row somebody typed in by hand, and the
            # operator gets no other chance to see what it replaces.
            diff = self._diff(spec, adopted, columns)
            self._update(spec, adopted, columns)
            self._link(entity_type, adopted, payload)
            return IngestOutcome.UPDATED, adopted, diff

        new_id = str(uuid.uuid4())
        cols = ", ".join(["id", *columns])
        binds = ", ".join([":id", *(f":{c}" for c in columns)])
        self.db.execute(
            text(f"INSERT INTO {spec.table} ({cols}) VALUES ({binds})"),
            {"id": new_id, **columns},
        )
        self._link(entity_type, new_id, payload)
        # Nothing existed to overwrite, so there is no diff to report. Distinct
        # from {} -- see RecordResult.diff.
        return IngestOutcome.CREATED, new_id, None

    def _diff(
        self, spec: EntitySpec, entity_id: str, columns: dict[str, Any]
    ) -> Optional[dict[str, dict[str, Any]]]:
        """Values this record would replace on an existing row.

        Dry run only: a real ingest is about to write these anyway, and reading
        every row back would cost a SELECT per record for nothing.

        Only columns whose value actually changes are reported. An operator
        reviewing a sync is asking "what am I about to lose?", and burying three
        real changes in twelve unchanged fields answers a different question.
        """
        if not self._dry_run:
            return None

        # Column names come from the module's own to_columns mappings, never
        # from the payload, so interpolating them is safe -- same basis as the
        # UPDATE and INSERT below.
        selected = ", ".join(columns)
        row = (
            self.db.execute(
                text(f"SELECT {selected} FROM {spec.table} WHERE id = :id"), {"id": entity_id}
            )
            .mappings()
            .first()
        )
        if row is None:
            return None

        return {
            column: {"current": row.get(column), "incoming": incoming}
            for column, incoming in columns.items()
            if _value_changed(row.get(column), incoming)
        }

    def _update(self, spec: EntitySpec, entity_id: str, columns: dict[str, Any]) -> None:
        assignments = ", ".join(f"{c} = :{c}" for c in columns)
        self.db.execute(
            text(f"UPDATE {spec.table} SET {assignments} WHERE id = :id"),
            {"id": entity_id, **columns},
        )

    def _link(self, entity_type: str, entity_id: str, payload: Any) -> None:
        self.refs.link(
            entity_type=entity_type,
            entity_id=entity_id,
            source_ref=payload.source_ref,
            source_doc_no=payload.source_doc_no,
            integration_id=self.integration_id,
        )


def _value_changed(current: Any, incoming: Any) -> bool:
    """Whether writing ``incoming`` over ``current`` would change anything.

    Numbers are compared by value rather than by type. The database hands back
    ``Decimal('0.00')`` where the canonical payload carries ``Decimal('0')`` or
    an int, and reporting that as a change would fill an operator's diff with
    edits that are not edits -- which trains them to skim the one that is.
    """
    if current is None or incoming is None:
        return (current is None) != (incoming is None)

    numeric = (int, float, Decimal)
    if (
        isinstance(current, numeric)
        and isinstance(incoming, numeric)
        # bool subclasses int, so without this guard Decimal(str(True)) raises
        # InvalidOperation. Booleans fall through to plain equality, which is
        # what they want -- and since is_active is on every canonical shape,
        # this is the common path, not an edge case.
        and not isinstance(current, bool)
        and not isinstance(incoming, bool)
    ):
        try:
            return Decimal(str(current)) != Decimal(str(incoming))
        except (InvalidOperation, ValueError):
            return str(current) != str(incoming)

    return current != incoming


def _field_errors(exc: ValidationError) -> dict[str, str]:
    """Flatten pydantic errors to field -> reason."""
    out: dict[str, str] = {}
    for err in exc.errors():
        location = ".".join(str(p) for p in err.get("loc", ())) or "_"
        out[location] = err.get("msg", "invalid")
    return out
