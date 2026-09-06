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
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.sales_agent import SalesAgent
from app.models.user import SystemSetting
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
from app.services.rules import product_rules
from app.services.rules import customer_rules
from app.services.rules.customer_rules import customer_identity
from app.services.rules.master_rules import clean_supplier_name, resolve_master_by_code
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

    Security review advisory (d): every caller catches a bare
    ``except IntegrityError`` - not only a unique-constraint collision, but
    also a FK, NOT NULL or CHECK violation can raise one, and THOSE carry a
    DETAIL line that can name a value from a different row, table or
    caller's own request than the one this record wrote. `message_detail` is
    therefore only ever echoed for `pgcode == "23505"` (unique_violation);
    every other IntegrityError maps to a field-less `conflict` with no
    DETAIL text at all, constraint name included - the constraint name alone
    (still logged with `exc_info=True` at the call site) is enough for an
    operator, and is never sent to the ESB either way.
    """
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    pgcode = getattr(orig, "pgcode", None)
    if pgcode != "23505":
        return {"_": "conflict"}
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
    # MissingReference. The fourth argument is a mutable warnings list the
    # builder may append fixed-vocabulary notices to (`category_created`, ...) -
    # only `_product_columns` uses it today.
    to_columns: Callable[[BaseModel, Session, str, list[str]], dict[str, Any]]
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


def _present(payload: Any, columns: dict[str, Any], *names: str) -> None:
    """D14: absent vs null. Copies ``payload.<name>`` into ``columns`` only for
    fields the caller actually SET - an omitted field must never overwrite a
    stored value, only an explicit ``null`` may."""
    for name in names:
        if name in payload.model_fields_set:
            columns[name] = getattr(payload, name)


# Live fix, 2026-09-06: every one of these columns is NOT NULL with no
# server-side default the ORM insert can fall back on when the attribute is
# explicitly set to `None` (a column-level Python `default=` only fires when
# the attribute is never touched at all, so an explicit `None` bypasses it
# the same way a bare `INSERT` naming the column as NULL would). D14 says "an
# explicit null clears it" - but there is nothing to CLEAR a NOT NULL column
# TO except its own create default, so that is what a `null` (or, on a
# genuine create, an entirely ABSENT field - see `_insert`'s own use of this
# table) resolves to here. One table, checked against the SAME default the
# manual create form / bulk import already apply for that column - `EA`-style
# FK fallbacks (`products.category_id`/`base_uom_id`) are NOT here, because
# they need a lookup/creation rather than a static value; see
# `_fill_create_only_product_gaps`.
#: Distinguishes "never queried the singleton `system_settings` row yet" from
#: "queried it and there was no row" (perf review S6) - `None` is a real,
#: valid cached answer, not an unset marker.
_UNSET = object()

_NOT_NULL_DEFAULTS: dict[str, dict[str, Any]] = {
    "product_categories": {"is_active": True},
    "units_of_measure": {"is_active": True, "decimal_places": 0},
    "warehouses": {"is_active": True},
    "suppliers": {"is_active": True},
    "customers": {"is_active": True},
    "sales_agents": {"is_active": True},
    "products": {"is_active": True, "list_price": Decimal("0")},
}


def _apply_not_null_defaults(entity_type: str, columns: dict[str, Any]) -> None:
    """An explicit ``null`` on a NOT NULL column (with no server default the ORM
    can rely on) maps to that column's create default instead of reaching the
    DB - on BOTH the create and the update path, since an update's blind
    ``setattr`` would violate the constraint exactly the same way an insert
    does. Only touches a key already IN ``columns`` (D14: an absent field is
    untouched on update; the absent-on-CREATE case is `_insert`'s own
    ``setdefault`` pass over this same table)."""
    for column, default in _NOT_NULL_DEFAULTS.get(entity_type, {}).items():
        if column in columns and columns[column] is None:
            columns[column] = default


def _category_columns(payload: Any, db: Session, company_id: str, warnings: list[str]) -> dict[str, Any]:
    columns: dict[str, Any] = {"category_code": payload.code, "category_name": payload.name}
    _present(payload, columns, "description", "is_active")
    return columns


def _uom_columns(payload: Any, db: Session, company_id: str, warnings: list[str]) -> dict[str, Any]:
    columns: dict[str, Any] = {"uom_code": payload.code, "uom_name": payload.name}
    # Canonical divisibility (plan 6.4). Absent (D14) leaves the row untouched on
    # update, or the model's own 0 default on create - never a value this
    # module invents.
    _present(payload, columns, "decimal_places", "description", "is_active")
    return columns


def _warehouse_columns(payload: Any, db: Session, company_id: str, warnings: list[str]) -> dict[str, Any]:
    columns: dict[str, Any] = {"warehouse_code": payload.code, "warehouse_name": payload.name}
    _present(payload, columns, "location", "is_active")
    return columns


def _supplier_columns(payload: Any, db: Session, company_id: str, warnings: list[str]) -> dict[str, Any]:
    # D2: AutoCount's trailing currency note (`"ACME (RMB)"`) is not part of
    # the legal name - same rule the manual create and the outstanding-PO
    # upload apply, via `master_rules.clean_supplier_name`.
    columns: dict[str, Any] = {
        "supplier_code": payload.code,
        "supplier_name": clean_supplier_name(payload.name),
    }
    # D15: the contact/address block AutoCount carries and this module used to
    # drop on the floor. D14: absent vs null on every one of them, plus
    # `payment_terms_days` (model default 30 fills an absent value on create -
    # see `_insert`). `payment_terms_code` is REMOVED (D15 end state, S4) -
    # `extra="forbid"` now rejects it outright rather than accepting and
    # warning; the payment-terms master it once waited for still does not
    # exist, and a supplier no longer needs a placeholder for it at all.
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


def _customer_columns(payload: Any, db: Session, company_id: str, warnings: list[str]) -> dict[str, Any]:
    # `credit_limit` / `payment_terms_days` / `payment_terms_code` are REMOVED
    # (D15 end state, S4) - `customers` never had a matching column for any
    # of the three, and `extra="forbid"` now rejects a payload naming one
    # outright rather than accepting and warning.
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
        "region",
    )
    # D16 (S2): folded through the same rule the customer importer uses
    # (`customer_rules.fold_market_segment`) so the two can never map a
    # spelling two different ways. An unrecognised value is dropped with
    # warning `segment_unknown` rather than failing the whole customer over
    # one optional column - `market_segment_code` is a foreign key.
    if "market_segment_code" in payload.model_fields_set and payload.market_segment_code:
        canonical = customer_rules.fold_market_segment(db, payload.market_segment_code)
        if canonical is None:
            warnings.append("segment_unknown")
        else:
            columns["market_segment_code"] = canonical
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


def _product_columns(
    payload: Any, db: Session, company_id: str, warnings: list[str]
) -> dict[str, Any]:
    # D24 (captain 2026-09-06): `product_name` is ALWAYS the AutoCount item
    # code, matching the xlsx import's own convention (product_name = Item
    # Code); `description` holds the AutoCount Description text - the
    # payload's own `description` when it sends one, else `name`
    # (transitional: the ESB currently maps Item.Description onto `name`).
    # Both are forced on EVERY push, create and update, so an existing row
    # loaded under the old wrong mapping (product_name = the text,
    # description empty) is corrected the very next time it is pushed.
    columns: dict[str, Any] = {
        "product_code": payload.code,
        "product_name": payload.code,
        "description": payload.description if payload.description else payload.name,
    }
    _present(payload, columns, "is_active", "remark")

    # D3: an unknown category/uom/brand on a product push is CREATED (code =
    # name = the raw value), never retryable any more - `ensure_reference`
    # also gives this the case/whitespace-insensitive match D17 wants (D3
    # subsumes D17 here: a match is a match, whichever rule found it).
    if "category_code" in payload.model_fields_set:
        if not payload.category_code:
            raise MissingReference("category_code", "")
        category_id, created = product_rules.ensure_reference(
            db, ProductCategory, payload.category_code, company_id
        )
        if created:
            warnings.append("category_created")
        columns["category_id"] = category_id

    if "uom_code" in payload.model_fields_set:
        if payload.uom_code:
            uom_id, created = product_rules.ensure_reference(
                db, UnitOfMeasure, payload.uom_code, company_id
            )
            if created:
                warnings.append("uom_created")
        else:
            # A blank uom_code resolves to the configured default, exactly as
            # `bulk_import_products` does for a row with no uom column value.
            uom_id = product_rules.resolve_default_uom(db, company_id)
        if uom_id:
            columns["base_uom_id"] = uom_id

    if "brand_code" in payload.model_fields_set and payload.brand_code:
        brand_id, created = product_rules.ensure_reference(db, Brand, payload.brand_code, company_id)
        if created:
            warnings.append("brand_created")
        columns["brand_id"] = brand_id

    if "list_price" in payload.model_fields_set:
        columns["list_price"] = payload.list_price
    if "cost_price" in payload.model_fields_set:
        columns["cost_price"] = payload.cost_price

    # D4: dimensions_* are derived in `_finalize_product_derived` instead of
    # here, once the caller knows whether this is a create or an update and
    # can read the row's stored name/description for the effective-text
    # merge (live finding, 2026-09-06: gating on "description in columns"
    # missed the ESB, which sends its Description text as `name` and no
    # `description` at all).

    # D14: `barcode` is CRM-owned. Only written when the incoming value is
    # non-empty - the key is left OUT of the dict otherwise, so an update never
    # touches it and a manually entered barcode (or one from an earlier sync)
    # survives a push that carries none. On CREATE the same omission leaves the
    # column at its own NULL default.
    if payload.bar_code:
        columns["barcode"] = payload.bar_code
    return columns


def _sales_agent_columns(payload: Any, db: Session, company_id: str, warnings: list[str]) -> dict[str, Any]:
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
        # Perf review (S6): `system_settings` is a single row read once per
        # BATCH, not once per product record - `_post_write_product_hooks`
        # used to re-query it for every product, the same N+1 shape
        # `bulk_import_products` already caches once for its own run.
        # `_UNSET` (not `None`) distinguishes "never queried yet" from "queried
        # and there is no row" - a real, if unusual, state on a fresh install.
        self._settings_cache: Any = _UNSET

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
        """Pins `company_scope` for the WHOLE record, not just `_insert`/`_update`'s
        own writes: `_product_columns` (`ensure_reference`/`resolve_master_by_code`)
        and the generic adopt-fallback below both run ordinary ORM queries against
        company-scoped tables, and without this those queries are filtered by
        whatever the ambient session scope happens to be - which a caller running
        two companies through one session (this module's own parity tests) never
        resets between calls. See `_insert`'s own docstring for the fuller version
        of this note.
        """
        with company_scope(self.db, frozenset({self.company_id})):
            return self._apply_scoped(entity_type, spec, payload)

    def _apply_scoped(
        self, entity_type: str, spec: EntitySpec, payload: Any
    ) -> tuple[IngestOutcome, str, Optional[dict[str, dict[str, Any]]], list[str]]:
        warnings: list[str] = []
        columns = spec.to_columns(payload, self.db, self.company_id, warnings)
        _apply_not_null_defaults(entity_type, columns)

        existing_id = self.refs.resolve(entity_type=entity_type, source_ref=payload.source_ref)
        if existing_id is not None:
            self._require_same_company(spec, existing_id, payload.source_ref)
            if entity_type == "products":
                self._finalize_product_derived(payload, columns, existing_id)
            if entity_type == "customers":
                self._finalize_customer_segment_fill_only(columns, existing_id)
            diff = self._diff(spec, existing_id, columns)
            self._update(spec, existing_id, columns)
            self._link(entity_type, existing_id, payload)
            self._post_write_product_hooks(entity_type, existing_id)
            return IngestOutcome.UPDATED, existing_id, diff, warnings

        # First sync: adopt a local record with the same business identity
        # rather than creating a duplicate under a new id. Customers override
        # this with the (code, name) pair (D13); everything else matches on
        # the bare business code. Sales agents keep their own normalised-code
        # match (`_lookup_id`) - shared table, not company-scoped the way
        # `resolve_master_by_code` assumes. Every other master matches
        # case/whitespace-insensitively (D17), through the same function the
        # manual create services now use too.
        if spec.adopt_lookup is not None:
            adopted = spec.adopt_lookup(self.db, payload, self.company_id)
        elif spec.normalized_code:
            adopted = _lookup_id(
                self.db, spec.table, spec.code_column, payload.code, self.company_id, normalized=True
            )
        else:
            adopted = resolve_master_by_code(self.db, spec.model, payload.code, self.company_id)
        if adopted is not None:
            if self.refs.origin_of(entity_type=entity_type, entity_id=adopted) is not None:
                # Already claimed by a different source document -- surfacing
                # beats silently retargeting someone else's record.
                raise ReferenceConflict(
                    f"{spec.code_column}={payload.code!r} is already linked to another source"
                )
            if entity_type == "products":
                self._finalize_product_derived(payload, columns, adopted)
            if entity_type == "customers":
                self._finalize_customer_segment_fill_only(columns, adopted)
            # Captured before the UPDATE, and the reason the dry run exists: an
            # adoption overwrites a row somebody typed in by hand, and the
            # operator gets no other chance to see what it replaces.
            diff = self._diff(spec, adopted, columns)
            self._update(spec, adopted, columns)
            self._link(entity_type, adopted, payload)
            self._post_write_product_hooks(entity_type, adopted)
            return IngestOutcome.UPDATED, adopted, diff, warnings

        if entity_type == "products":
            self._finalize_product_derived(payload, columns, None)
            self._fill_create_only_product_gaps(columns)
        new_id = self._insert(entity_type, spec, columns)
        self._link(entity_type, new_id, payload)
        self._post_write_product_hooks(entity_type, new_id)
        # Nothing existed to overwrite, so there is no diff to report. Distinct
        # from {} -- see RecordResult.diff.
        return IngestOutcome.CREATED, new_id, None, warnings

    def _fill_create_only_product_gaps(self, columns: dict[str, Any]) -> None:
        """Live fix, 2026-09-06: `category_id`/`base_uom_id` are NOT NULL FKs
        `_product_columns` leaves OUT of `columns` entirely when the payload
        never names a category/uom at all - D14's "absent = untouched" is
        correct for an UPDATE, but there is nothing to leave untouched on a
        genuine CREATE, and the insert crashed with a `NotNullViolation`
        instead. Called ONLY from the CREATE branch, immediately before
        `_insert` - an UPDATE never reaches this and keeps D14's rule
        unchanged.

        `category_id` has no usable default - the manual create form
        requires it too, with none - so an absent category is retryable, the
        same verdict an unresolvable `category_code` already gets.
        `base_uom_id` DOES have one: the same configured-default/`EA`
        fallback `_product_columns` already applies when `uom_code` is sent
        BLANK, widened here to the ABSENT case too.
        """
        if "category_id" not in columns:
            raise MissingReference("category_code", "")
        if "base_uom_id" not in columns:
            columns["base_uom_id"] = product_rules.resolve_default_uom(self.db, self.company_id)

    def _finalize_product_derived(
        self, payload: Any, columns: dict[str, Any], existing_row_id: Optional[str]
    ) -> None:
        """D2/D4/D24: `is_discontinued` and `dimensions_*` are both derived
        from `description` ONLY, never `name` - D24 (captain 2026-09-06)
        makes `_product_columns` force `description` to the AutoCount
        Description text on every push (the payload's own `description`
        when it sends one, else `name`, transitionally), so both channels'
        rules can read the one column the xlsx import always used.

        An explicit `is_discontinued` flag still wins over the derived one;
        dimensions have no equivalent explicit-value override, so a parsed
        value is written whenever it differs from what the row already
        holds - which keeps an unrelated push (price-only, say) from
        re-deriving a no-op back onto a manually corrected dimension: the
        "differs" check is against the CURRENT stored value. True->False
        resets the notify watermark, same rule `product_service.update_product`
        applies manually.
        """
        current_discontinued = None
        current_length = current_width = current_height = None
        if existing_row_id is not None:
            row = self.db.execute(
                text(
                    "SELECT is_discontinued, dimensions_length, dimensions_width, "
                    "dimensions_height FROM products WHERE id = :id"
                ),
                {"id": existing_row_id},
            ).first()
            if row is not None:
                (
                    current_discontinued,
                    current_length,
                    current_width,
                    current_height,
                ) = row

        description = columns.get("description")

        if "is_discontinued" in payload.model_fields_set:
            new_flag = bool(payload.is_discontinued)
        else:
            new_flag = product_rules.is_discontinued(None, description)
        columns["is_discontinued"] = new_flag

        if existing_row_id is not None and current_discontinued and not new_flag:
            columns["discontinued_notified_at"] = None
            columns["discontinued_notify_batch_id"] = None

        length_mm, width_mm, height_mm = product_rules.parse_dimensions(description)
        if length_mm is not None and length_mm != current_length:
            columns["dimensions_length"] = length_mm
        if width_mm is not None and width_mm != current_width:
            columns["dimensions_width"] = width_mm
        if height_mm is not None and height_mm != current_height:
            columns["dimensions_height"] = height_mm

    def _finalize_customer_segment_fill_only(
        self, columns: dict[str, Any], existing_row_id: Optional[str]
    ) -> None:
        """D16: a segment already set by hand is never overwritten - the row's
        OWN value wins over whatever this push resolved, on an update only (a
        create has nothing to protect)."""
        if existing_row_id is None or "market_segment_code" not in columns:
            return
        current = self.db.execute(
            text("SELECT market_segment_code FROM customers WHERE id = :id"),
            {"id": existing_row_id},
        ).scalar()
        if current:
            columns.pop("market_segment_code")

    def _system_settings(self) -> Optional[SystemSetting]:
        """The singleton `system_settings` row, read ONCE per batch (perf
        review S6) - this hook used to re-query it for every product record,
        an N+1 the ESB's own 11.7k-product pushes pay for on every one of
        them. Cached on the instance, which lives for exactly one batch
        (`MasterIngestService` is constructed per request), the same
        lifetime `bulk_import_products` already caches its own settings read
        for."""
        if self._settings_cache is _UNSET:
            self._settings_cache = self.db.query(SystemSetting).first()
        return self._settings_cache

    def _post_write_product_hooks(self, entity_type: str, product_id: str) -> None:
        """D5: the default-supplier `product_suppliers` link, on create AND
        update - exactly as the Excel import applies it, moved to
        `product_rules.link_default_supplier` so this and the manual
        create/edit path (`ProductService._ensure_default_supplier_lead_time`)
        share the one body."""
        if entity_type != "products":
            return
        product_rules.link_default_supplier(self.db, product_id, self._system_settings())

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
        # Live fix, 2026-09-06: a NOT NULL column absent from `columns`
        # entirely (never sent by the payload) reads as None to the ORM
        # constructor below the same way an explicit null does - the model's
        # own Python `default=` only fires when the attribute is never
        # assigned at all, so this MUST run before `spec.model(**insert_columns)`,
        # not rely on it. `_apply_not_null_defaults` (same table) already
        # fixed the "explicit null" case for both create and update, before
        # this method was ever called - `setdefault` here only ever fills a
        # key that is genuinely missing, so the two never fight.
        for column, default in _NOT_NULL_DEFAULTS.get(entity_type, {}).items():
            insert_columns.setdefault(column, default)
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
