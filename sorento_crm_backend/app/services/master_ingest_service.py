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

**One company per call.** The caller names it (``company_anchor.py``) and it is
required here, not defaulted: nearly every table below is partitioned per
company, and their business codes are unique only within one. Both halves of the
ingest have to honour it or the anchor is decorative -- the INSERT stamps it, and
adoption matches inside it, because adopting across companies would silently
retarget another company's hand-entered row. The exception is ``sales_agents``
(``SHARED_TABLES``), whose row deliberately carries no company at all: the same
agents sell for both, and splitting them would give one person two demand
classes. The anchor still bounds the call, it simply has nothing to stamp.

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
    CanonicalCustomer,
    CanonicalProductCategory,
    CanonicalSalesAgent,
    CanonicalUnitOfMeasure,
    CanonicalProduct,
    CanonicalSupplier,
    CanonicalWarehouse,
)
from app.services.integration_reference_service import (
    IntegrationReferenceService,
    ReferenceConflict,
)
# The agent code's one normalisation, imported rather than restated: the master
# screen, the outstanding-SO import and this ingest all have to agree on what
# `sean i` is, or the captain's demand class lands on one of three rows.
from app.services.scm.sales_agent_service import normalize_code as _normalize_agent_code

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
    # Fixed-vocabulary notices that do not fail the record - e.g. a back-created
    # customer or an unresolved warehouse NULLed onto the line (D9/D10). Same
    # rule as `errors`: omitted from `as_dict()` when empty.
    warnings: list[str] = field(default_factory=list)
    # Documents only (D11): per-line outcome counts for this record - adopted
    # (an xlsx-era ref-less row claimed by the three-step match), created,
    # updated (matched by its own existing source_ref), deleted, cancelled.
    # None for a master record (there are no lines) and omitted from
    # `as_dict()` in that case, same rule as `diff`.
    lines: Optional[dict[str, int]] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_ref": self.source_ref,
            "outcome": self.outcome.value,
            "entity_id": self.entity_id,
            **({"errors": self.errors} if self.errors else {}),
            **({"diff": self.diff} if self.diff is not None else {}),
            **({"warnings": self.warnings} if self.warnings else {}),
            **({"lines": self.lines} if self.lines is not None else {}),
        }


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
            "records": [r.as_dict() for r in self.records],
        }


@dataclass
class EntitySpec:
    """How one canonical shape maps onto a Sorento table."""

    table: str
    schema: type[BaseModel]
    code_column: str
    # canonical payload -> column values. May raise MissingReference.
    to_columns: Callable[[BaseModel, Session, str], dict[str, Any]]
    # Whether adoption matches ``upper(btrim())`` on BOTH sides instead of the
    # stored string. True only where the column has one canonical spelling that
    # the rows do not all carry yet -- see ``_lookup_id``.
    normalized_code: bool = False


# Tables where a row serves every company (``company_id`` NULL). Listed rather
# than derived from the model, because the question here is what the RAW SQL
# below must write, and a mixin the SQL never consults cannot answer it.
# Everything else in ENTITY_SPECS is company-scoped.
SHARED_TABLES = {"sales_agents"}


def _is_company_scoped(table: str) -> bool:
    return table not in SHARED_TABLES


def _category_columns(payload: Any, db: Session, company_id: str) -> dict[str, Any]:
    return {
        "category_code": payload.code,
        "category_name": payload.name,
        "description": payload.description,
        "is_active": payload.is_active,
    }


def _uom_columns(payload: Any, db: Session, company_id: str) -> dict[str, Any]:
    return {
        "uom_code": payload.code,
        "uom_name": payload.name,
        # Canonical divisibility (plan 6.4). A source that does not state it lands on
        # 0, the same rollout fallback the backfill gives an unknown unit name.
        "decimal_places": payload.decimal_places,
        "description": payload.description,
        "is_active": payload.is_active,
    }


def _warehouse_columns(payload: Any, db: Session, company_id: str) -> dict[str, Any]:
    return {
        "warehouse_code": payload.code,
        "warehouse_name": payload.name,
        "location": payload.location,
        "is_active": payload.is_active,
    }


def _supplier_columns(payload: Any, db: Session, company_id: str) -> dict[str, Any]:
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


def _customer_columns(payload: Any, db: Session, company_id: str) -> dict[str, Any]:
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


def _lookup_id(
    db: Session,
    table: str,
    column: str,
    value: str,
    company_id: str,
    *,
    normalized: bool = False,
) -> Optional[str]:
    """A row matched by business code, WITHIN the anchored company.

    Unscoped this is a coin toss: ``warehouse_code`` and ``product_code`` are
    unique per company only (migration 305) and thousands of codes exist in both,
    so the row returned was whichever the scan reached first. A shared table has
    no company of its own, so its rows match on NULL as well.

    ``normalized`` compares ``upper(btrim())`` on both sides, which the agent
    master needs and the other five must not have. The agent code has one
    canonical spelling, but the rows do not all carry it: the AutoCount mirror
    wrote whatever AutoCount said, so a push spelled `sean i` that matched the
    stored string exactly would fail to find `SEAN I`, create a second agent and
    split one person's demand class - the duplicate the master exists to prevent.
    Turning this on everywhere would instead make `abc-1` adopt `ABC-1`, and for
    a product code those are two products.
    """
    if _is_company_scoped(table):
        scope = "company_id = :cid"
    else:
        scope = "(company_id IS NULL OR company_id = :cid)"
    if normalized:
        match = f"upper(btrim({column})) = upper(btrim(:v))"
    else:
        match = f"{column} = :v"
    row = db.execute(
        text(f"SELECT id FROM {table} WHERE {match} AND {scope} LIMIT 1"),
        {"v": value, "cid": company_id},
    ).first()
    return str(row[0]) if row else None


def _product_columns(payload: Any, db: Session, company_id: str) -> dict[str, Any]:
    # products.category_id and base_uom_id are NOT NULL, so an unresolved code
    # makes the row uncreatable. That is a sequencing problem, not bad data.
    if not payload.category_code:
        raise MissingReference("category_code", "")
    category_id = _lookup_id(
        db, "product_categories", "category_code", payload.category_code, company_id
    )
    if category_id is None:
        raise MissingReference("category_code", payload.category_code)

    if not payload.uom_code:
        raise MissingReference("uom_code", "")
    uom_id = _lookup_id(db, "units_of_measure", "uom_code", payload.uom_code, company_id)
    if uom_id is None:
        raise MissingReference("uom_code", payload.uom_code)

    columns: dict[str, Any] = {
        "product_code": payload.code,
        "product_name": payload.name,
        "description": payload.description,
        "category_id": category_id,
        "base_uom_id": uom_id,
        "list_price": payload.list_price if payload.list_price is not None else 0,
        "cost_price": payload.cost_price,
        "is_active": payload.is_active,
    }
    # D14: `barcode` is CRM-owned. Only written when the incoming value is
    # non-empty - the key is left OUT of the dict otherwise, so `_update`'s
    # blind `SET col = :col` never touches it and a manually entered barcode
    # (or one from an earlier sync) survives a push that carries none. On
    # CREATE the same omission leaves the column at its NULL default.
    if payload.bar_code:
        columns["barcode"] = payload.bar_code
    return columns


def _sales_agent_columns(payload: Any, db: Session, company_id: str) -> dict[str, Any]:
    """The four columns AutoCount owns on an agent, and no others.

    ``internal_note``, ``follow_up``, ``demand_class``, ``location_group`` and
    ``source`` are absent on purpose. They are the captain's annotations, made on
    the master screen; a weekly re-sync that restated them from a payload which
    never carried them would blank his classification every Monday and make
    fulfilment priority flap. Absent from the written set, they cannot be touched
    by any path through this module - which is a stronger promise than "we do not
    send them".

    ``source`` stays untouched for the same reason plus one more: it records how
    a row got here, and an agent an outstanding-SO upload created is still
    `import` even after AutoCount confirms it exists.
    """
    return {
        "sales_agent": _normalize_agent_code(payload.code),
        "description": payload.description,
        "is_active": payload.is_active,
        "person_label": payload.person_label,
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
    # The only shared master here: the row carries no company (see SHARED_TABLES)
    # and its code is matched normalised, because the rows already in the table
    # carry AutoCount's spelling rather than ours.
    "sales_agents": EntitySpec(
        "sales_agents",
        CanonicalSalesAgent,
        "sales_agent",
        _sales_agent_columns,
        normalized_code=True,
    ),
}


class MasterIngestService:
    def __init__(
        self, db: Session, integration_id: Optional[str] = None, *, company_id: str
    ):
        self.db = db
        self.integration_id = integration_id
        # Required, deliberately. A default would be the incumbent company, and a
        # push meant for the other one would land there silently -- the failure
        # this whole anchor exists to prevent.
        self.company_id = company_id
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
        columns = spec.to_columns(payload, self.db, self.company_id)

        existing_id = self.refs.resolve(entity_type=entity_type, source_ref=payload.source_ref)
        if existing_id is not None:
            self._require_same_company(spec, existing_id, payload.source_ref)
            diff = self._diff(spec, existing_id, columns)
            self._update(spec, existing_id, columns)
            self._link(entity_type, existing_id, payload)
            return IngestOutcome.UPDATED, existing_id, diff

        # First sync: adopt a local record with the same business code rather
        # than creating a duplicate under a new id.
        adopted = _lookup_id(
            self.db,
            spec.table,
            spec.code_column,
            payload.code,
            self.company_id,
            normalized=spec.normalized_code,
        )
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
        # Raw SQL bypasses the ORM auto-stamp, so the anchor is written by hand.
        # Without it the row lands with a NULL company -- rejected outright on the
        # live schema (NOT NULL, migration 305) and, where the column is still
        # nullable, invisible to every scoped read afterwards. A shared table is
        # left alone: NULL there means "serves both companies".
        insert_columns = dict(columns)
        if _is_company_scoped(spec.table):
            insert_columns["company_id"] = self.company_id
        cols = ", ".join(["id", *insert_columns])
        binds = ", ".join([":id", *(f":{c}" for c in insert_columns)])
        self.db.execute(
            text(f"INSERT INTO {spec.table} ({cols}) VALUES ({binds})"),
            {"id": new_id, **insert_columns},
        )
        self._link(entity_type, new_id, payload)
        # Nothing existed to overwrite, so there is no diff to report. Distinct
        # from {} -- see RecordResult.diff.
        return IngestOutcome.CREATED, new_id, None

    def _require_same_company(self, spec: EntitySpec, entity_id: str, source_ref: str) -> None:
        """Refuse a reference that resolves into another company.

        ``integration_references`` is global, so a source_ref finds its row
        whatever company the request anchored to. Updating it would be a
        cross-company write wearing the clothes of an ordinary re-sync, and the
        row it overwrites belongs to a company this caller did not name. Failed
        per record, so the rest of the batch still lands.
        """
        if not _is_company_scoped(spec.table):
            return
        owner = self.db.execute(
            text(f"SELECT company_id FROM {spec.table} WHERE id = :id"), {"id": entity_id}
        ).scalar()
        if str(owner) != str(self.company_id):
            raise ReferenceConflict(
                f"source_ref {source_ref!r} is linked to a record in another company"
            )

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
