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

Ingest emits **no lifecycle events** (AC-AC-18). A record arriving *from*
AutoCount must never trigger a write back to it. Nothing here calls an emitter,
and nothing here should ever be given one.
"""
from __future__ import annotations

import enum
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.canonical_masters import (
    CanonicalCustomer,
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


@dataclass
class IngestResult:
    records: list[RecordResult] = field(default_factory=list)

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


def _warehouse_columns(payload: Any, db: Session) -> dict[str, Any]:
    return {
        "warehouse_code": payload.code,
        "warehouse_name": payload.name,
        "location": payload.location,
        "is_active": payload.is_active,
    }


def _supplier_columns(payload: Any, db: Session) -> dict[str, Any]:
    terms = payload.payment_terms_days
    if payload.payment_terms_code:
        # The payment-terms master does not exist until Phase D. Rather than
        # silently dropping the code -- which would persist a supplier with the
        # wrong terms and no signal -- report it retryable so the ESB re-drains
        # once that master lands.
        raise MissingReference("payment_terms_code", payload.payment_terms_code)
    return {
        "supplier_code": payload.code,
        "supplier_name": payload.name,
        "email": payload.email,
        "phone_number": payload.phone_number,
        "payment_terms_days": terms,
        "is_active": payload.is_active,
    }


def _customer_columns(payload: Any, db: Session) -> dict[str, Any]:
    if payload.payment_terms_code:
        raise MissingReference("payment_terms_code", payload.payment_terms_code)
    return {
        "customer_code": payload.code,
        "customer_name": payload.name,
        "email": payload.email,
        "phone_number": payload.phone_number,
        "registration_number": payload.registration_number,
        "tax_id": payload.tax_id,
        "credit_limit": payload.credit_limit,
        "payment_terms_days": payload.payment_terms_days,
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
    category_id = _lookup_id(db, "product_categories", "category_name", payload.category_code)
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
    "warehouses": EntitySpec("warehouses", CanonicalWarehouse, "warehouse_code", _warehouse_columns),
    "suppliers": EntitySpec("suppliers", CanonicalSupplier, "supplier_code", _supplier_columns),
    "customers": EntitySpec("customers", CanonicalCustomer, "customer_code", _customer_columns),
    "products": EntitySpec("products", CanonicalProduct, "product_code", _product_columns),
}


class MasterIngestService:
    def __init__(self, db: Session, integration_id: Optional[str] = None):
        self.db = db
        self.integration_id = integration_id
        self.refs = IntegrationReferenceService(db)

    def ingest(self, entity_type: str, records: list[dict]) -> IngestResult:
        spec = ENTITY_SPECS.get(entity_type)
        if spec is None:
            raise UnsupportedIngestEntity(
                f"Unsupported ingest entity {entity_type!r}. "
                f"Expected one of: {', '.join(sorted(ENTITY_SPECS))}"
            )

        result = IngestResult()
        for raw in records:
            result.records.append(self._ingest_one(entity_type, spec, raw))
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
            outcome, entity_id = self._apply(entity_type, spec, payload)
            savepoint.commit()
            return RecordResult(
                source_ref=payload.source_ref, outcome=outcome, entity_id=entity_id
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

    def _apply(self, entity_type: str, spec: EntitySpec, payload: Any) -> tuple[IngestOutcome, str]:
        columns = spec.to_columns(payload, self.db)

        existing_id = self.refs.resolve(entity_type=entity_type, source_ref=payload.source_ref)
        if existing_id is not None:
            self._update(spec, existing_id, columns)
            self._link(entity_type, existing_id, payload)
            return IngestOutcome.UPDATED, existing_id

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
            self._update(spec, adopted, columns)
            self._link(entity_type, adopted, payload)
            return IngestOutcome.UPDATED, adopted

        new_id = str(uuid.uuid4())
        cols = ", ".join(["id", *columns])
        binds = ", ".join([":id", *(f":{c}" for c in columns)])
        self.db.execute(
            text(f"INSERT INTO {spec.table} ({cols}) VALUES ({binds})"),
            {"id": new_id, **columns},
        )
        self._link(entity_type, new_id, payload)
        return IngestOutcome.CREATED, new_id

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


def _field_errors(exc: ValidationError) -> dict[str, str]:
    """Flatten pydantic errors to field -> reason."""
    out: dict[str, str] = {}
    for err in exc.errors():
        location = ".".join(str(p) for p in err.get("loc", ())) or "_"
        out[location] = err.get("msg", "invalid")
    return out
