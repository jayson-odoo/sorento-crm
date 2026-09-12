"""Link Sorento records to the external documents they came from (Phase B).

A polymorphic mapping table has no foreign keys to lean on, so the two
invariants a FK would have given us for free are enforced here instead:

1. **entity_type is an allowlist.** It resolves to a table name and it arrives
   from an ingest payload. Interpolating an unchecked value into SQL is an
   injection surface, so unknown types raise rather than being passed through.

2. **A reference whose target no longer exists does not resolve.** Nothing
   cascades on delete, so without this a stale row would make ingest believe a
   record is already present and 'update' something that is gone. The check
   happens on the read path and cleans up what it finds -- deliberately not via
   a scheduled sweep, because ``ENABLE_SCHEDULER`` is opt-in and defaults off,
   and a correctness guarantee must not depend on an env var somebody forgot.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.integration_reference import IntegrationReference

logger = logging.getLogger(__name__)


class UnsupportedEntityType(ValueError):
    """Raised for an entity_type outside the allowlist."""


class ReferenceConflict(ValueError):
    """Raised when a source reference is already claimed by another record.

    Surfaced rather than silently ignored: the caller believes it linked its
    record, and returning the pre-existing mapping would leave it pointing
    somewhere else entirely while reporting success.

    `field_name` names the verdict-error key a catching `_ingest_one` should
    file this under - defaults to `"source_ref"`, the document/master's own
    identity field, which is what every pre-v2 raise site means. A caller
    naming a SPECIFIC field instead (v2's per-master ladder, e.g.
    `"customer_ref"`) passes it explicitly so the verdict names which
    reference conflicted, not just that the record failed.
    """

    def __init__(self, message: str, *, field_name: str = "source_ref"):
        super().__init__(message)
        self.field_name = field_name


# The tables the ESB writes. Values are real table names and are only ever
# used after membership in this set has been confirmed.
SUPPORTED_ENTITY_TYPES = {
    "products",
    "product_categories",
    "units_of_measure",
    "stock",
    "warehouses",
    "suppliers",
    "customers",
    "sales_agents",
    # Group A3: the documents. `orders` / `order_lines` below are the LEGACY
    # order tables and are a different thing entirely - these two are
    # public.sales_orders / public.purchase_orders, which the SCM planner reads.
    "sales_orders",
    "purchase_orders",
    "picking_headers",
    "picking_lines",
    "orders",
    "order_lines",
    # autocount-brands-ingest AC-15: brands joined the ingest surface.
    "brands",
}

# Tables where a row serves every company (`company_id` NULL). Moved here from
# `master_ingest_service` (autocount-brands-ingest BL-056, D11): this service
# needs it too now, for its own `company_id` column, and the refs service
# cannot import the ingest service (circular) - `master_ingest_service`
# re-exports both names, so `deletion_service.py` and `master_read_service.py`
# keep importing from where they always have.
SHARED_TABLES = {"sales_agents"}


def _is_company_scoped(table: str) -> bool:
    return table not in SHARED_TABLES


DEFAULT_SOURCE_SYSTEM = "autocount"


def _require_supported(entity_type: str) -> str:
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        raise UnsupportedEntityType(
            f"Unsupported entity_type {entity_type!r}. "
            f"Expected one of: {', '.join(sorted(SUPPORTED_ENTITY_TYPES))}"
        )
    return entity_type


class IntegrationReferenceService:
    def __init__(self, db: Session, *, company_id: Optional[str] = None):
        self.db = db
        # BL-056 (D14, strict - captain's ruling on fix round 1): the anchor
        # company a scoped `resolve()`/`link()` reads and writes under. Every
        # real caller (the six ingest/read/deletion constructors) always has
        # one. A scoped call with no anchor raises `ValueError` rather than
        # guessing - never a global fallback, never inferred from the entity's
        # own row.
        self.company_id = company_id

    # ------------------------------------------------------------------ write

    def link(
        self,
        *,
        entity_type: str,
        entity_id: str,
        source_ref: str,
        source_system: str = DEFAULT_SOURCE_SYSTEM,
        source_doc_no: Optional[str] = None,
        integration_id: Optional[str] = None,
    ) -> IntegrationReference:
        """Record that ``entity_id`` originated from ``source_ref``.

        Re-linking the same pair updates in place, which is what makes ingest
        idempotent: a re-push must never create a second record.

        BL-056 (D12/D14): the same ``source_ref`` may exist once PER COMPANY
        for a scoped ``entity_type`` - so "already linked" is scoped to the
        anchor too, and linking the same ref under a different company is a
        brand new row, never a conflict with this one.
        """
        _require_supported(entity_type)
        anchor = self._require_anchor_if_scoped(entity_type)

        existing_query = self.db.query(IntegrationReference).filter(
            IntegrationReference.source_system == source_system,
            IntegrationReference.entity_type == entity_type,
            IntegrationReference.source_ref == source_ref,
        )
        if anchor is not None:
            existing_query = existing_query.filter(IntegrationReference.company_id == anchor)
        else:
            existing_query = existing_query.filter(IntegrationReference.company_id.is_(None))
        existing = existing_query.first()
        if existing is not None:
            if str(existing.entity_id) != str(entity_id):
                # One external document maps to one local record. A second
                # claimant means either duplicate ingest or a genuine data
                # conflict upstream -- both need a human, not a silent no-op.
                raise ReferenceConflict(
                    f"{source_system} {entity_type} {source_ref!r} is already linked to "
                    f"{existing.entity_id!r}; refusing to relink to {entity_id!r}"
                )
            # DocNo is expected to change; the key it resolves by is not.
            if source_doc_no is not None:
                existing.source_doc_no = source_doc_no
            if integration_id is not None:
                existing.integration_id = integration_id
            existing.last_synced_at = datetime.utcnow()
            self.db.flush()
            return existing

        # Fix-round-2 BUG A, layer 1: `entity_id` may already be registered
        # under a DIFFERENT source_ref - the masters push linked this product
        # as "ac_sim:57", and a document's own code rung then resolves the
        # SAME product and tries to link it again as "ac_sim:174". The unique
        # index is on `(entity_type, entity_id)` alone (one entity, one
        # reference, ever), so the INSERT below would hit it and surface as a
        # raw `IntegrityError` to whichever caller forgot to check first.
        # Checked here too, not only in `MasterRefResolver` (layer 2), so ANY
        # caller of `link()` gets a domain exception instead of a DB one.
        by_entity = (
            self.db.query(IntegrationReference)
            .filter(
                IntegrationReference.entity_type == entity_type,
                IntegrationReference.entity_id == str(entity_id),
            )
            .first()
        )
        if by_entity is not None and by_entity.source_ref != source_ref:
            raise ReferenceConflict(
                f"{entity_type} {entity_id} is already registered under another reference"
            )

        row = IntegrationReference(
            entity_type=entity_type,
            entity_id=str(entity_id),
            source_system=source_system,
            source_ref=source_ref,
            source_doc_no=source_doc_no,
            integration_id=integration_id,
            company_id=anchor,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _require_anchor_if_scoped(self, entity_type: str) -> Optional[str]:
        """The company_id to read/write for `entity_type`, or None for a
        shared type (BL-056 D14, strict).

        A scoped type with no anchor at construction raises `ValueError` -
        never a global fallback (`resolve()`) and never inferred from the
        entity's own row (`link()`). Every real caller (the six ingest/read/
        deletion constructors) always has an anchor; this only fires for a
        caller with none of its own to give.
        """
        if not _is_company_scoped(entity_type):
            return None
        if self.company_id is None:
            raise ValueError(
                f"company-scoped entity_type {entity_type!r} requires an anchor company_id"
            )
        return self.company_id

    def unlink(self, *, entity_type: str, entity_id: str) -> int:
        """Drop the mapping for a record. Call when deleting the record itself."""
        _require_supported(entity_type)
        removed = (
            self.db.query(IntegrationReference)
            .filter(
                IntegrationReference.entity_type == entity_type,
                IntegrationReference.entity_id == str(entity_id),
            )
            .delete(synchronize_session=False)
        )
        self.db.flush()
        return removed

    # ------------------------------------------------------------------- read

    def resolve(
        self,
        *,
        entity_type: str,
        source_ref: str,
        source_system: str = DEFAULT_SOURCE_SYSTEM,
    ) -> Optional[str]:
        """Local record id for an external reference, or None if unknown.

        **Always returns a string, never a UUID object.** ``entity_id`` is a
        varchar because it addresses nine tables whose primary keys are not all
        the same type. Most of them are Postgres ``uuid``, so a caller holding a
        ``UUID`` must not compare with ``==`` -- ``UUID(x) == str(x)`` is False,
        and silently treating an existing record as new is exactly the duplicate
        this table exists to prevent. Compare with ``str()`` on both sides, or
        pass the value straight into a query filter, where SQLAlchemy casts it.

        Returns None -- and removes the mapping -- when the referenced record has
        since been deleted, so ingest treats it as new rather than updating a
        row that is gone.

        BL-056 (D14, strict): a scoped ``entity_type`` resolves only within
        THIS instance's anchor company - a ref linked under a different
        company is reported exactly like one that was never linked at all.
        A scoped call with no anchor raises ``ValueError`` rather than
        guessing which company to search; every real caller (the six ingest/
        read/deletion services) always has one.
        """
        _require_supported(entity_type)
        anchor = self._require_anchor_if_scoped(entity_type)

        query = self.db.query(IntegrationReference).filter(
            IntegrationReference.source_system == source_system,
            IntegrationReference.entity_type == entity_type,
            IntegrationReference.source_ref == source_ref,
        )
        if anchor is not None:
            query = query.filter(IntegrationReference.company_id == anchor)
        else:
            query = query.filter(IntegrationReference.company_id.is_(None))
        row = query.first()
        if row is None:
            return None

        if not self._entity_exists(entity_type, row.entity_id):
            logger.info(
                "integration_reference.orphan_cleared entity_type=%s source_ref=%s entity_id=%s",
                entity_type,
                source_ref,
                row.entity_id,
            )
            self.db.delete(row)
            self.db.flush()
            return None

        return row.entity_id

    def origin_of(
        self, *, entity_type: str, entity_id: str
    ) -> Optional[IntegrationReference]:
        """Where a record came from, or None when it was created locally."""
        _require_supported(entity_type)
        return (
            self.db.query(IntegrationReference)
            .filter(
                IntegrationReference.entity_type == entity_type,
                IntegrationReference.entity_id == str(entity_id),
            )
            .first()
        )

    def is_externally_sourced(self, *, entity_type: str, entity_id: str) -> bool:
        """True when a record came from an upstream system.

        Absence of a reference means locally created -- there is no `manual` row
        for every pre-existing record, by design.
        """
        return self.origin_of(entity_type=entity_type, entity_id=entity_id) is not None

    # -------------------------------------------------------------- internals

    def _entity_exists(self, entity_type: str, entity_id: str) -> bool:
        # entity_type is interpolated only after passing the allowlist; the id
        # is always a bound parameter.
        table = _require_supported(entity_type)
        try:
            found = self.db.execute(
                # Unqualified on purpose, and it matters now that
                # `sales_orders` / `purchase_orders` are here: those names exist a
                # SECOND time in the `projects` schema, so this resolves through
                # `search_path`. Production reaches `public` first, and the test
                # substrate deliberately orders its scratch schemas so the core
                # tables win (`_pg_fixture.blank_session`). Hard-coding `public.`
                # instead would point every read at the REAL database from a
                # scratch-schema test and clear live mappings as orphans.
                text(f"SELECT 1 FROM {table} WHERE id = :entity_id LIMIT 1"),
                {"entity_id": str(entity_id)},
            ).first()
        except Exception:
            # If the existence check itself fails, keep the mapping rather than
            # deleting data on the strength of a failed query.
            logger.exception(
                "integration_reference.existence_check_failed entity_type=%s", entity_type
            )
            return True
        return found is not None
