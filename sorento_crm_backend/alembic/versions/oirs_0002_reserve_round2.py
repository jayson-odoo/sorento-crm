"""Order inquiry: request CS to reserve - review round 2 (`PLAN-oi-request-cs-reserve.md`
section 6c, `oi-request-cs-reserve-acceptance-criteria.md` AC-RS-54/AC-RS-60).

One new table (`projects.order_inquiry_reserve_events`, F3's own per-line history: the
dialog's History tab lists `reserved`/`unreserved` rows off it, `requested`/`cancelled`
derive straight off `order_inquiry_reserve_requests` and are never copied here) and one
new `system_settings` column (`oi_reserve_default_pool_warehouse_id`, F1's configurable
default pool - "list all the site pool with this BRW (configurable as default)").

Chained onto `oirs_0001_reserve_requests` rather than amending it in place - that
migration is already applied on two databases (the CI DB and the :8080 lane stack) - same
hand-written, IF NOT EXISTS / IF EXISTS shape and the same reason: the shared dev
database converges through `create_all` and `blank_session()` builds its scratch schema
from `Base.metadata`, which already carries the new table and column the moment the ORM
models exist, so this migration's own `upgrade()` must be a no-op reaching a database
that already has them.

`_schema()`/`_t()` are the same per-file copy `oirs_0001_reserve_requests.py` and
`421_order_inquiry_links.py` carry - `schema_translate_map` only rewrites ORM/`Table`
constructs, not a bare identifier in a raw `text()` statement, and a test running on a
scratch schema (`tests/_pg_fixture.py` names them `<default>_projects`) needs the real
one resolved at runtime. `system_settings` and `warehouses` carry no schema (public),
so they need no such prefix.

Revision ID: oirs_0002_reserve_round2
Revises: oirs_0001_reserve_requests
Create Date: 2026-09-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "oirs_0002_reserve_round2"
down_revision = "oirs_0001_reserve_requests"
branch_labels = None
depends_on = None


def _schema(bind, module: str) -> str:
    """Where a module's tables live, for RAW SQL, under BOTH substrates - copied from
    `oirs_0001_reserve_requests.py`'s own helper (see that file's docstring for why)."""
    current = bind.exec_driver_sql("SELECT current_schema()").scalar()
    return module if current in (None, "public") else f"{current}_{module}"


def _create_events_table(bind) -> None:
    projects = _schema(bind, "projects")
    bind.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS "{projects}".order_inquiry_reserve_events (
                id UUID PRIMARY KEY,
                company_id UUID REFERENCES companies(id),
                reserve_request_row_id UUID NOT NULL
                    REFERENCES "{projects}".order_inquiry_reserve_request_rows(id)
                    ON DELETE CASCADE,
                kind VARCHAR(16) NOT NULL
                    CONSTRAINT ck_order_inquiry_reserve_events_kind
                    CHECK (kind IN ('reserved', 'unreserved')),
                qty NUMERIC(15, 4) NOT NULL
                    CONSTRAINT ck_order_inquiry_reserve_events_qty_positive CHECK (qty > 0),
                warehouse_id UUID REFERENCES warehouses(id) ON DELETE SET NULL,
                note TEXT,
                actor_id VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMP NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS ix_order_inquiry_reserve_events_row
                ON "{projects}".order_inquiry_reserve_events (reserve_request_row_id);
            """
        )
    )


def _add_settings_column(bind) -> None:
    bind.execute(
        sa.text(
            "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS "
            "oi_reserve_default_pool_warehouse_id UUID "
            "REFERENCES warehouses(id) ON DELETE SET NULL"
        )
    )
    # Seeded to the BRW pool BY CODE, never by id (the id is a fresh per-install UUID) -
    # only when a BRW warehouse actually exists, and only into a row that has not
    # already been given an explicit value (a re-run of this migration on a database an
    # admin has since edited must not clobber their choice).
    bind.execute(
        sa.text(
            """
            UPDATE system_settings
            SET oi_reserve_default_pool_warehouse_id = (
                SELECT id FROM warehouses WHERE warehouse_code = 'BRW'
                ORDER BY created_at ASC LIMIT 1
            )
            WHERE oi_reserve_default_pool_warehouse_id IS NULL
              AND EXISTS (SELECT 1 FROM warehouses WHERE warehouse_code = 'BRW')
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    _create_events_table(bind)
    _add_settings_column(bind)


def downgrade() -> None:
    bind = op.get_bind()
    projects = _schema(bind, "projects")
    bind.execute(
        sa.text(f'DROP TABLE IF EXISTS "{projects}".order_inquiry_reserve_events')
    )
    bind.execute(
        sa.text(
            "ALTER TABLE system_settings "
            "DROP COLUMN IF EXISTS oi_reserve_default_pool_warehouse_id"
        )
    )
