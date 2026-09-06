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
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional

from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.models.inventory import Warehouse
from app.models.order import Customer
from app.models.procurement import Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.sales_agent import SalesAgent
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
from app.services.rules.customer_rules import customer_identity
# The agent code's one normalisation, imported rather than restated: the master
# screen, the outstanding-SO import and this ingest all have to agree on what
# `sean i` is, or the captain's demand class lands on one of three rows.
from app.services.scm.sales_agent_service import normalize_code as _normalize_agent_code

logger = logging.getLogger(__name__)

#: SEC3 (review round 1). The verdict body is read by the ESB and logged
#: wherever it forwards; a non-domain exception's own `str(exc)` routinely
#: quotes the failed SQL statement, a table/column name, or a raw UUID -
#: an internal detail an external caller has no business seeing. Every
#: generic `except Exception` across the three ingest surfaces and the
#: deletion service returns this fixed string instead and logs the real one
#: with `exc_info=True`. A DOMAIN exception (`MissingReference`,
#: `ReferenceConflict`, `_UnknownStatus`, a pydantic `ValidationError`) is
#: authored FOR the caller and keeps its own message - only the catch-all
#: is sanitised.
INTERNAL_ERROR_MESSAGE = "internal error; see server logs"


def integrity_conflict_errors(exc: IntegrityError) -> dict[str, str]:
    """A per-record verdict body for a unique-constraint violation (fix round 4,
    BUG B), shared by all three ingest surfaces (masters/documents/shipping
    orders) so a two-company push that races a code/number can name what
    collided instead of falling through to `INTERNAL_ERROR_MESSAGE`.

    Reads psycopg2's own diagnostics off ``exc.orig`` rather than ``str(exc)``,
    which quotes the failed statement in full - `constraint_name` says WHICH
    unique index collided (e.g. `uq_warehouses_company_warehouse_code`) and
    `message_detail` is the bare DETAIL line ("Key (company_id,
    warehouse_code)=(..., BRW) already exists."), never the SQL itself.

    `errors["code"]` when the constraint parsed (the expected shape for a
    natural-key collision on any of these surfaces - `code` is the wire field
    every `CanonicalXxx.code` masters payload and the v2 ladder's code rungs
    are spelled under); `errors["_"]` for the "unknown constraint" case where
    the DBAPI driver exposed no diagnostics at all to name one by.
    """
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None) if diag else None
    detail = getattr(diag, "message_detail", None) if diag else None
    if constraint:
        message = f"conflict: {constraint}"
        if detail:
            message = f"{message} ({detail})"
        return {"code": message}
    return {"_": "conflict: unique constraint"}


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
    # canonical payload -> column values (present fields only, D14). May raise
    # MissingReference.
    to_columns: Callable[[BaseModel, Session, str], dict[str, Any]]
    # The ORM model class the D18 writer upserts through, so audit, embedding
    # and CompanyScopedMixin listeners fire on flush.
    model: type
    # Whether adoption matches ``upper(btrim())`` on BOTH sides instead of the
    # stored string. True only where the column has one canonical spelling that
    # the rows do not all carry yet -- see ``_lookup_id``.
    normalized_code: bool = False
    # Overrides the default code-only adoption match. None means the default
    # (``_lookup_id`` on ``code_column`` alone). Customers are the only user so
    # far (D13): the (code, name) pair, not the code alone.
    adopt_lookup: Optional[Callable[[Session, Any, str], Optional[str]]] = None


# Tables where a row serves every company (``company_id`` NULL). Listed rather
# than derived from the model, because the question here is what the RAW SQL
# below must write, and a mixin the SQL never consults cannot answer it.
# Everything else in ENTITY_SPECS is company-scoped.
SHARED_TABLES = {"sales_agents"}


def _is_company_scoped(table: str) -> bool:
    return table not in SHARED_TABLES


#: D15: fields that stay on the canonical schemas so an old payload still
#: validates, but are never written to any column - flagged with the
#: `deprecated_field` warning instead. Removed at S4's contract 2.1 cutover.
_DEPRECATED_FIELDS: dict[str, set[str]] = {
    "customers": {"credit_limit", "payment_terms_days", "payment_terms_code"},
    "suppliers": {"payment_terms_code"},
}


def _deprecated_warnings(entity_type: str, payload: Any) -> list[str]:
    deprecated = _DEPRECATED_FIELDS.get(entity_type)
    if deprecated and deprecated & payload.model_fields_set:
        return ["deprecated_field"]
    return []




def _present(payload: Any, columns: dict[str, Any], *names: str) -> None:
    """D14: absent vs null. Copies ``payload.<name>`` into ``columns`` only for
    fields the caller actually SET - an omitted field must never overwrite a
    stored value, only an explicit ``null`` may."""
    for name in names:
        if name in payload.model_fields_set:
            columns[name] = getattr(payload, name)


def _category_columns(payload: Any, db: Session, company_id: str) -> dict[str, Any]:
    columns: dict[str, Any] = {"category_code": payload.code, "category_name": payload.name}
    _present(payload, columns, "description", "is_active")
    return columns


def _uom_columns(payload: Any, db: Session, company_id: str) -> dict[str, Any]:
    columns: dict[str, Any] = {"uom_code": payload.code, "uom_name": payload.name}
    # Canonical divisibility (plan 6.4). Absent (D14) leaves the row untouched on
    # update, or the model's own 0 default on create - never a value this
    # module invents.
    _present(payload, columns, "decimal_places", "description", "is_active")
    return columns


def _warehouse_columns(payload: Any, db: Session, company_id: str) -> dict[str, Any]:
    columns: dict[str, Any] = {"warehouse_code": payload.code, "warehouse_name": payload.name}
    _present(payload, columns, "location", "is_active")
    return columns


def _supplier_columns(payload: Any, db: Session, company_id: str) -> dict[str, Any]:
    columns: dict[str, Any] = {"supplier_code": payload.code, "supplier_name": payload.name}
    # D15: the contact/address block AutoCount carries and this module used to
    # drop on the floor. D14: absent vs null on every one of them, plus
    # `payment_terms_days` (model default 30 fills an absent value on create -
    # see `_insert`). `payment_terms_code` is deprecated (see
    # `_DEPRECATED_FIELDS`): accepted, warned, never written and never a
    # MissingReference - the payment-terms master this used to wait for still
    # does not exist, but a supplier no longer has to stay unsynced for it.
    _present(
        payload,
        columns,
        "contact_name",
        "email",
        "phone_number",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "postal_code",
        "country",
        "payment_terms_days",
        "is_active",
    )
    return columns


def _customer_columns(payload: Any, db: Session, company_id: str) -> dict[str, Any]:
    # `credit_limit` / `payment_terms_days` / `payment_terms_code` are
    # deprecated (D15, see `_DEPRECATED_FIELDS`): `customers` has no matching
    # column, so they are accepted-and-warned, never written - same as before
    # fix-round-2 BUG B, now with a warning instead of silence.
    columns: dict[str, Any] = {"customer_code": payload.code, "customer_name": payload.name}
    _present(
        payload,
        columns,
        "email",
        "phone_number",
        "registration_number",
        "tax_id",
        "country",
        "is_active",
    )
    return columns


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
    columns: dict[str, Any] = {"product_code": payload.code, "product_name": payload.name}
    _present(payload, columns, "description", "is_active")

    # products.category_id and base_uom_id are NOT NULL, so an unresolved code
    # makes the row uncreatable - a sequencing problem, not bad data. D14: only
    # resolved (and only required) when the payload actually sends the field;
    # an update that omits it leaves the existing link untouched.
    if "category_code" in payload.model_fields_set:
        if not payload.category_code:
            raise MissingReference("category_code", "")
        category_id = _lookup_id(
            db, "product_categories", "category_code", payload.category_code, company_id
        )
        if category_id is None:
            raise MissingReference("category_code", payload.category_code)
        columns["category_id"] = category_id

    if "uom_code" in payload.model_fields_set:
        if not payload.uom_code:
            raise MissingReference("uom_code", "")
        uom_id = _lookup_id(db, "units_of_measure", "uom_code", payload.uom_code, company_id)
        if uom_id is None:
            raise MissingReference("uom_code", payload.uom_code)
        columns["base_uom_id"] = uom_id

    if "list_price" in payload.model_fields_set:
        columns["list_price"] = payload.list_price
    if "cost_price" in payload.model_fields_set:
        columns["cost_price"] = payload.cost_price

    # D14: `barcode` is CRM-owned. Only written when the incoming value is
    # non-empty - the key is left OUT of the dict otherwise, so an update never
    # touches it and a manually entered barcode (or one from an earlier sync)
    # survives a push that carries none. On CREATE the same omission leaves the
    # column at its own NULL default.
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
    columns: dict[str, Any] = {"sales_agent": _normalize_agent_code(payload.code)}
    _present(payload, columns, "description", "is_active", "person_label")
    return columns


def _adopt_customer(db: Session, payload: Any, company_id: str) -> Optional[str]:
    """D13: adoption match for a customer is the (code, name) pair, never the
    code alone - the same key as `uq_customers_company_code_name_lower` and
    `order_service.CustomerService.create_customer`, via the shared
    `customer_identity` rule."""
    code_norm, name_norm = customer_identity(payload.code, payload.name)
    row = db.execute(
        text(
            "SELECT id FROM customers WHERE lower(btrim(customer_code)) = :code "
            "AND lower(btrim(customer_name)) = :name AND company_id = :cid LIMIT 1"
        ),
        {"code": code_norm, "name": name_norm, "cid": company_id},
    ).first()
    return str(row[0]) if row else None


ENTITY_SPECS: dict[str, EntitySpec] = {
    # Categories and UoMs first: products.category_id and base_uom_id are
    # NOT NULL, so a product whose category has not synced yet is retryable
    # and stays that way until these land.
    "product_categories": EntitySpec(
        "product_categories", CanonicalProductCategory, "category_code", _category_columns,
        ProductCategory,
    ),
    "units_of_measure": EntitySpec(
        "units_of_measure", CanonicalUnitOfMeasure, "uom_code", _uom_columns, UnitOfMeasure
    ),
    "warehouses": EntitySpec(
        "warehouses", CanonicalWarehouse, "warehouse_code", _warehouse_columns, Warehouse
    ),
    "suppliers": EntitySpec(
        "suppliers", CanonicalSupplier, "supplier_code", _supplier_columns, Supplier
    ),
    "customers": EntitySpec(
        "customers", CanonicalCustomer, "customer_code", _customer_columns, Customer,
        adopt_lookup=_adopt_customer,
    ),
    "products": EntitySpec("products", CanonicalProduct, "product_code", _product_columns, Product),
    # The only shared master here: the row carries no company (see SHARED_TABLES)
    # and its code is matched normalised, because the rows already in the table
    # carry AutoCount's spelling rather than ours.
    "sales_agents": EntitySpec(
        "sales_agents",
        CanonicalSalesAgent,
        "sales_agent",
        _sales_agent_columns,
        SalesAgent,
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
        except TypeError:
            # SEC3-style (fix-round-2): a malformed body, never the caller's
            # business - logged with exc_info, never echoed.
            logger.warning(
                "ingest.record_malformed entity=%s source_ref=%s",
                entity_type,
                source_ref,
                exc_info=True,
            )
            return RecordResult(
                source_ref=source_ref,
                outcome=IngestOutcome.FAILED,
                errors={"_": INTERNAL_ERROR_MESSAGE},
            )

        # Each record commits or rolls back alone. Without this savepoint a
        # failed flush poisons the session and every later record in the batch
        # fails too -- turning "12 bad rows" into "nothing imported".
        savepoint = self.db.begin_nested()
        try:
            outcome, entity_id, diff, warnings = self._apply(entity_type, spec, payload)
            savepoint.commit()
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=outcome,
                entity_id=entity_id,
                diff=diff,
                warnings=warnings,
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
        except IntegrityError as exc:
            # Fix round 4, BUG B: a unique-constraint race (two companies, or a
            # concurrent push of the same code) - named by constraint, never by
            # `str(exc)`'s full SQL statement.
            savepoint.rollback()
            logger.warning(
                "ingest.integrity_conflict entity=%s source_ref=%s",
                entity_type,
                payload.source_ref,
                exc_info=True,
            )
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.FAILED,
                errors=integrity_conflict_errors(exc),
            )
        except Exception:  # noqa: BLE001 - one record's failure, not the batch's
            savepoint.rollback()
            # SEC3 (fix-round-2): never echo a non-domain exception's own
            # message - it routinely quotes SQL, a table/column name or a raw
            # UUID. Logged with exc_info=True instead.
            logger.warning(
                "ingest.record_failed entity=%s source_ref=%s",
                entity_type,
                payload.source_ref,
                exc_info=True,
            )
            return RecordResult(
                source_ref=payload.source_ref,
                outcome=IngestOutcome.FAILED,
                errors={"_": INTERNAL_ERROR_MESSAGE},
            )

    def _apply(
        self, entity_type: str, spec: EntitySpec, payload: Any
    ) -> tuple[IngestOutcome, str, Optional[dict[str, dict[str, Any]]], list[str]]:
        warnings = _deprecated_warnings(entity_type, payload)
        columns = spec.to_columns(payload, self.db, self.company_id)

        existing_id = self.refs.resolve(entity_type=entity_type, source_ref=payload.source_ref)
        if existing_id is not None:
            self._require_same_company(spec, existing_id, payload.source_ref)
            diff = self._diff(spec, existing_id, columns)
            self._update(spec, existing_id, columns)
            self._link(entity_type, existing_id, payload)
            return IngestOutcome.UPDATED, existing_id, diff, warnings

        # First sync: adopt a local record with the same business identity
        # rather than creating a duplicate under a new id. Customers override
        # this with the (code, name) pair (D13); everything else matches on
        # the bare business code.
        if spec.adopt_lookup is not None:
            adopted = spec.adopt_lookup(self.db, payload, self.company_id)
        else:
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
            return IngestOutcome.UPDATED, adopted, diff, warnings

        new_id = self._insert(entity_type, spec, columns)
        self._link(entity_type, new_id, payload)
        # Nothing existed to overwrite, so there is no diff to report. Distinct
        # from {} -- see RecordResult.diff.
        return IngestOutcome.CREATED, new_id, None, warnings

    def _insert(self, entity_type: str, spec: EntitySpec, columns: dict[str, Any]) -> str:
        """D18: the ORM insert, so `before_insert` company-stamping, the audit
        `before_flush` listener and the embedding `after_insert` listener all
        fire - none of which a raw ``INSERT`` statement ever reached.

        ``company_scope`` is pinned to the anchor for the duration, not read
        off the ambient session scope: a caller (this parity test fixture,
        certainly a batch ingest) can run two companies through the same
        session without resetting global state between them, and an insert or
        the row lookup in ``_update`` must never drift onto whichever company
        happened to be ambient last.
        """
        insert_columns = dict(columns)
        # `products.list_price` is NOT NULL with no column-level default (unlike
        # `is_active`/UOM `decimal_places`/supplier `payment_terms_days`, which
        # the model's own Python default fills on flush when left unset) - so
        # D14's create-only default has to be filled here instead.
        if entity_type == "products":
            insert_columns.setdefault("list_price", Decimal("0"))
        # The audit `before_flush` listener reads a pending object's PK straight
        # off the instance attribute - a PK still waiting on its column default
        # reads as None there and the create goes unrecorded (same gap
        # `Customer`'s own `"init"` event exists to close, order.py:174). Every
        # entity here gets the same fix at the one call site that creates all
        # of them, rather than one `"init"` listener per model.
        insert_columns.setdefault("id", str(uuid.uuid4()))

        with company_scope(self.db, frozenset({self.company_id})):
            row = spec.model(**insert_columns)
            if _is_company_scoped(spec.table):
                row.company_id = self.company_id
            if entity_type == "sales_agents":
                # D18: only on create - an existing agent's provenance (manual,
                # import) is never overwritten by a later AutoCount confirmation.
                row.source = "autocount"
            self.db.add(row)
            self.db.flush()
            return str(row.id)

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
        """D18: setattr on the ORM row, not a blind ``UPDATE`` - so the audit
        `before_flush` listener and the embedding `after_update` listener both
        fire, and only the columns this record actually sent are touched (D14).

        `updated_at` is stamped explicitly rather than left to `onupdate` -
        several of these tables (``customers`` among them) declare the column
        plain-nullable with no `onupdate=func.now()`, the same gap their own
        manual-service `update_*` methods paper over ad hoc (see
        `product_service.update_product`, `inventory_service.update_warehouse`)."""
        with company_scope(self.db, frozenset({self.company_id})):
            row = self.db.query(spec.model).filter(spec.model.id == entity_id).first()
            if row is None:
                return
            for column, value in columns.items():
                setattr(row, column, value)
            if hasattr(row, "updated_at"):
                row.updated_at = datetime.utcnow()
            self.db.flush()

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
