"""Status engine as CORE: statuses + status_transitions; drop workflow_stages.

Configurable per-entity state machines (ADR-0001). Ported from
``foundryx-shared-service`` with the divergences recorded in that ADR and in
``app/models/status.py``.

Two details worth reading before editing this file:

**NULLS NOT DISTINCT.** The source's uniqueness constraint spans
``(entity_type, tenant_id, scope_id, key)``. On Postgres, NULLs compare distinct,
so for a DEFAULT graph -- where ``tenant_id`` and ``scope_id`` are both NULL, the
overwhelmingly common case -- that constraint is a no-op and duplicate keys insert
happily. Both unique indexes here are ``NULLS NOT DISTINCT`` (Postgres 15+;
this deployment is 17.5) so the default graph is actually constrained.

**workflow_stages is dropped, not migrated.** It was left behind by the deleted
``commercial_core`` module (commit c77560009, removed in 7f0eb94f1). It holds zero
rows and the only references to it anywhere in the app are its own model file and
its ``app/models/__init__`` export -- no service, route, or query reads it. Verified
by ``tests/test_status_engine_additive.py``, which fails if a reader reappears.
The down-revision recreates it empty.

Idempotent raw SQL, safe to re-run.

Revision ID: 308_status_engine
Revises: 307_admin_listing_company
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "308_status_engine"
down_revision = "307_admin_listing_company"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS statuses (
            id            uuid PRIMARY KEY,
            entity_type   varchar(64)  NOT NULL,
            key           varchar(64)  NOT NULL,
            category      varchar(64),
            label         varchar(120) NOT NULL,
            color_hex     varchar(7),
            description   text,
            sort_order    integer      NOT NULL DEFAULT 0,
            is_initial    boolean      NOT NULL DEFAULT false,
            is_terminal   boolean      NOT NULL DEFAULT false,
            is_active     boolean      NOT NULL DEFAULT true,
            is_archived   boolean      NOT NULL DEFAULT false,
            is_default    boolean      NOT NULL DEFAULT false,
            is_system     boolean      NOT NULL DEFAULT false,
            position_x    double precision,
            position_y    double precision,
            tenant_id     varchar(64),
            scope_id      uuid,
            created_at    timestamp    NOT NULL DEFAULT now(),
            updated_at    timestamp    NOT NULL DEFAULT now(),
            CONSTRAINT ck_statuses_initial_not_terminal
                CHECK (NOT (is_initial AND is_terminal))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_statuses_entity_scope_key
            ON statuses (entity_type, tenant_id, scope_id, key) NULLS NOT DISTINCT
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_statuses_entity_type ON statuses (entity_type)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_statuses_tenant_id ON statuses (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_statuses_scope_id ON statuses (scope_id)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_statuses_entity_scope_sort
            ON statuses (entity_type, scope_id, sort_order)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS status_transitions (
            id              uuid PRIMARY KEY,
            entity_type     varchar(64)  NOT NULL,
            tenant_id       varchar(64),
            scope_id        uuid,
            from_status_id  uuid         NOT NULL
                REFERENCES statuses (id) ON DELETE CASCADE,
            to_status_id    uuid         NOT NULL
                REFERENCES statuses (id) ON DELETE CASCADE,
            label           varchar(120) NOT NULL,
            sort_order      integer      NOT NULL DEFAULT 0,
            trigger_mode    varchar(16)  NOT NULL DEFAULT 'manual',
            conditions_json jsonb,
            created_at      timestamp    NOT NULL DEFAULT now(),
            updated_at      timestamp    NOT NULL DEFAULT now(),
            CONSTRAINT ck_status_transitions_no_self_loop
                CHECK (from_status_id <> to_status_id),
            CONSTRAINT ck_status_transitions_trigger_mode
                CHECK (trigger_mode IN ('manual', 'auto')),
            -- An auto edge with no conditions would fire immediately and
            -- unconditionally, which is never what an admin means.
            CONSTRAINT ck_status_transitions_auto_needs_conditions
                CHECK (trigger_mode <> 'auto' OR conditions_json IS NOT NULL)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_status_transitions_edge
            ON status_transitions
               (entity_type, tenant_id, scope_id, from_status_id, to_status_id)
            NULLS NOT DISTINCT
        """
    )
    for column in ("entity_type", "tenant_id", "scope_id", "from_status_id", "to_status_id"):
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_status_transitions_{column} "
            f"ON status_transitions ({column})"
        )

    # Superseded by the engine above. Zero rows, zero readers (see docstring).
    op.execute("DROP TABLE IF EXISTS workflow_stages")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS status_transitions")
    op.execute("DROP TABLE IF EXISTS statuses")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_stages (
            id                uuid PRIMARY KEY,
            domain            varchar(32)  NOT NULL,
            code              varchar(50)  NOT NULL,
            label             varchar(100) NOT NULL,
            color_hex         varchar(7),
            description       text,
            sort_order        integer      NOT NULL DEFAULT 0,
            is_terminal       boolean      NOT NULL DEFAULT false,
            allows_conversion boolean,
            can_go_back       boolean      NOT NULL DEFAULT false,
            is_active         boolean      NOT NULL DEFAULT true,
            is_cancelled      boolean      NOT NULL DEFAULT false,
            created_at        timestamp    NOT NULL DEFAULT now(),
            updated_at        timestamp    NOT NULL DEFAULT now(),
            CONSTRAINT ck_workflow_stages_domain CHECK (
                domain IN ('lead','quotation','tender','task','order','project')
            ),
            CONSTRAINT uq_workflow_stages_domain_code UNIQUE (domain, code)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_stages_domain_sort "
        "ON workflow_stages (domain, sort_order)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_stages_domain_active "
        "ON workflow_stages (domain, is_active)"
    )
