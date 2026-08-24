"""Status engine - configurable per-entity state machines (ADR-0001).

CORE, always on: this is plumbing that other modules depend on, not a sellable
capability. Ported from ``foundryx-shared-service`` (``app/models/status.py`` +
``status_transition.py``) with four deliberate divergences, each recorded in
ADR-0001:

1. **UUID primary keys**, not the source's ``Column(String)``. The
   pg-UUID-vs-varchar drift is what broke ``user_sessions.id`` auth on production
   (migration 301).
2. **Global, not company-scoped.** No ``company_id``, no ``CompanyScopedMixin``:
   SRT and MOCHA share one pipeline definition. ``tenant_id`` comes across for
   forward compatibility but stays NULL while the tenant is a stub.
3. **``category`` stays nullable and cosmetic.** Cross-graph reporting groups by
   ``key``, which the source documents as "machine key, stable per entity_type".
   The source marks ``category`` a "LEGACY cosmetic mirror ... behavior branches
   on the trait flags, never here", so reporting on it would resurrect a field its
   author deliberately demoted.
4. **``blocks_access`` is not ported.** It gates tenant sign-in in the source;
   sorento registers no tenant entity on the engine.

**Two-tier graphs.** ``scope_id IS NULL`` is an entity's DEFAULT graph. A scope
(e.g. a project template) that overrides gets its own forked copy of every row,
stamped with ``scope_id``. Resolution is "forked rows if any exist for this scope,
else the default" - so a template that never overrides keeps inheriting, and
changing the default afterwards does not silently rewrite a tuned fork.

**NULL uniqueness.** The source's ``UniqueConstraint(entity_type, tenant_id,
scope_id, key)`` is a no-op for default graphs on Postgres, because NULLs compare
distinct: two ``(project, NULL, NULL, 'registered')`` rows would both insert. The
unique index here is declared ``NULLS NOT DISTINCT`` (Postgres 15+) so the
common case is actually constrained.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


# ``scope_id``/``tenant_id`` are plain columns, never FKs: the scope table varies
# per entity (a project template today, something else tomorrow), so integrity is
# enforced in the service layer the way the source does it.

TRIGGER_MANUAL = "manual"
TRIGGER_AUTO = "auto"


class Status(Base):
    """One state a registered entity's records can hold."""

    __tablename__ = "statuses"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    entity_type = Column(String(64), nullable=False, index=True)

    # Machine key, stable per entity_type (e.g. "registered", "po_received").
    # THIS is what cross-graph reporting groups by -- a forked graph reuses the
    # same key for the same rung, so roll-ups work across forks.
    key = Column(String(64), nullable=False)

    # Cosmetic mirror only. Never branch behaviour on it (see module docstring).
    category = Column(String(64), nullable=True)

    label = Column(String(120), nullable=False)
    color_hex = Column(String(7), nullable=True)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)

    # ---- trait flags: the machine semantics ----
    # Records of this entity start here. Exactly one per graph, asserted app-side.
    is_initial = Column(Boolean, nullable=False, server_default="false", default=False)
    # No outgoing transitions are allowed out of a terminal status.
    is_terminal = Column(Boolean, nullable=False, server_default="false", default=False)
    # Deactivated statuses are hidden from pickers and new edges; existing records
    # keep them.
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    # Records holding this status drop out of the default ("active") list view.
    is_archived = Column(Boolean, nullable=False, server_default="false", default=False)
    # Pre-selected in a status picker for new records.
    is_default = Column(Boolean, nullable=False, server_default="false", default=False)
    # Seeded rows: key and flags immutable, row non-deletable.
    is_system = Column(Boolean, nullable=False, server_default="false", default=False)

    # Canvas coordinates for the graph editor. NULL = auto-layout.
    # AC-I2: how likely a record at this rung is to land, as a percentage. On the STATUS
    # so management tunes the forecast with no deploy. Nullable and NOT defaulted: an
    # unconfigured rung has no opinion, and inventing 50% would put a number in front of
    # management that nobody chose.
    win_probability = Column(Numeric(5, 2), nullable=True)
    # AC-H4: how long a record may sit at this rung before it is stale. Per status, because
    # a Registered project may fairly sit 30 days while a Negotiating one may not sit 7.
    stale_after_days = Column(Integer, nullable=True)

    position_x = Column(Float, nullable=True)
    position_y = Column(Float, nullable=True)

    tenant_id = Column(String(64), nullable=True, index=True)
    # NULL = the entity's default graph; set = a fork owned by that scope record.
    scope_id = Column(UUID(as_uuid=False), nullable=True, index=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # postgresql_nulls_not_distinct is what makes this bite for default
        # graphs, where tenant_id and scope_id are both NULL.
        Index(
            "uq_statuses_entity_scope_key",
            "entity_type",
            "tenant_id",
            "scope_id",
            "key",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_statuses_entity_scope_sort", "entity_type", "scope_id", "sort_order"),
        CheckConstraint(
            "NOT (is_initial AND is_terminal)",
            name="ck_statuses_initial_not_terminal",
        ),
    )


class StatusTransition(Base):
    """A legal edge between two statuses of the same entity and scope.

    ``trigger_mode='manual'`` is a user-facing action (a button, a board drag).
    ``'auto'`` is fired by the engine when ``conditions_json`` becomes true, and
    is excluded from the user-facing transition surfaces. An auto edge without
    conditions would fire unconditionally and instantly, so it is rejected at save
    AND by a CHECK constraint.
    """

    __tablename__ = "status_transitions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    entity_type = Column(String(64), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=True, index=True)
    scope_id = Column(UUID(as_uuid=False), nullable=True, index=True)

    from_status_id = Column(
        UUID(as_uuid=False),
        ForeignKey("statuses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_status_id = Column(
        UUID(as_uuid=False),
        ForeignKey("statuses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    label = Column(String(120), nullable=False)
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    trigger_mode = Column(
        String(16), nullable=False, server_default=TRIGGER_MANUAL, default=TRIGGER_MANUAL
    )
    # Rule-engine condition tree, stored as authored. NULL = unconditional.
    conditions_json = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_status_transitions_edge",
            "entity_type",
            "tenant_id",
            "scope_id",
            "from_status_id",
            "to_status_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "from_status_id <> to_status_id",
            name="ck_status_transitions_no_self_loop",
        ),
        CheckConstraint(
            f"trigger_mode IN ('{TRIGGER_MANUAL}', '{TRIGGER_AUTO}')",
            name="ck_status_transitions_trigger_mode",
        ),
        CheckConstraint(
            f"trigger_mode <> '{TRIGGER_AUTO}' OR conditions_json IS NOT NULL",
            name="ck_status_transitions_auto_needs_conditions",
        ),
    )
