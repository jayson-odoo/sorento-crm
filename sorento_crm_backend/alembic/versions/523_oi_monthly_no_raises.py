"""Monthly OI number, fixed raised date, raise history (S1,
`PLAN-oi-header-list-detail.md`, `oi-header-list-detail-acceptance-criteria.md`,
AC-NO-01..04, AC-RD-01..03).

R3/R5 (owner rulings, 21 Sep 2026): the inquiry number becomes `OI-YYMM-NNNN` - the
MONTH of the header's own FIRST raise, four digits, per company per month - fixed for
life once minted; the header's `raised_at`/`raised_by` become the FIRST raise, fixed
for life, and every later reconfirm is its own row on the new `projects.
order_inquiry_raises` table instead of overwriting them.

Three pieces:

1. `projects.order_inquiry_raises` - one row per raise/reconfirm (`kind`, `raised_by`,
   `raised_at`). `create_raises_table` is idempotent (`_has_table` guard), for the
   shared dev DB that converges through `create_all` rather than `alembic upgrade`
   (`sorento_crm_backend/CLAUDE.md`).
2. `order_inquiries.legacy_inquiry_no VARCHAR(20) NULL` - the pre-renumber value, kept
   so a number already quoted in an old email still finds its OI (search matches it
   too); downgrade restores `inquiry_no` from it.
3. `backfill_raises` / `renumber_inquiries` - exposed as module-level functions
   (precedent: `tests/test_migration_454_order_inquiry_born_ack.py`,
   `421_order_inquiry_links.py`) so a test can drive them on a scratch schema, and so
   `upgrade()` and the lane's own by-hand apply (the shared dev DB, per CLAUDE.md) are
   the SAME code path. Both are safe to call twice: `backfill_raises` skips any header
   that already holds a raise row, `renumber_inquiries` skips any header whose
   `legacy_inquiry_no` is no longer NULL.

`backfill_raises` MUST run before `renumber_inquiries`: the renumber orders headers by
`raised_at`, and the backfill is what moves a header's `raised_at` back to its first
raise (rather than its last reconfirm) before that ordering is read.

Revision ID: 523_oi_monthly_no_raises
Revises: ptag_0013_r10
Create Date: 2026-09-21
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "523_oi_monthly_no_raises"
down_revision = "ptag_0013_r10"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.523_oi_monthly_no_raises")


# --------------------------------------------------------------------------- schema helpers
#
# Copied from `421_order_inquiry_links.py`, not adapted: same reason - a hard-coded
# `projects.order_inquiries` inside a `text()` statement would reach the REAL schema
# from a test running on `tests/_pg_fixture.py`'s scratch copy (named
# `<default>_projects`), writing live data while the test believes it is isolated.


def _schema(bind, module: str) -> str:
    current = bind.exec_driver_sql("SELECT current_schema()").scalar()
    return module if current in (None, "public") else f"{current}_{module}"


def _inquiries(bind) -> str:
    return f'"{_schema(bind, "projects")}"."order_inquiries"'


def _rows(bind) -> str:
    return f'"{_schema(bind, "projects")}"."order_inquiry_rows"'


def _raises(bind) -> str:
    return f'"{_schema(bind, "projects")}"."order_inquiry_raises"'


def _has_table(bind, table_name: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :table"
            ),
            {"schema": _schema(bind, "projects"), "table": table_name},
        ).first()
    )


def _has_column(bind, table_name: str, column: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = :table "
                "AND column_name = :column"
            ),
            {"schema": _schema(bind, "projects"), "table": table_name, "column": column},
        ).first()
    )


# --------------------------------------------------------------------------- data steps


def backfill_raises(bind) -> int:
    """One `order_inquiry_raises` row (AC-RD-02) per header that has none yet.

    `raised` at the earlier of the header's own `raised_at` and its earliest row's
    `created_at` - a header a re-confirm has already re-stamped once (the pre-S1
    behaviour) has a `raised_at` LATER than the instruction that actually raised it, so
    reading the row is what recovers the true first raise. `reconfirmed` at the OLD
    `raised_at` / `raised_by` only when that differs from the first raise by more than a
    minute - two writes landing in the same request (server-default `now()` on both) are
    one event, not two. The header's own `raised_at` is then moved to the first of the
    two, which is R5's whole point: fixed from here on, never re-stamped again.

    A header with no rows at all answers `raised` alone, at its own `raised_at` - there
    is nothing earlier to recover.

    Snapshotted into a TEMP TABLE before any write (matching `renumber_inquiries`'s own
    two-pass shape below): computing "which headers still need backfilling" freshly
    inside each INSERT would see the FIRST insert's own new rows and wrongly skip the
    SECOND insert for the very same headers.
    """
    inquiries = _inquiries(bind)
    rows = _rows(bind)
    raises = _raises(bind)

    bind.exec_driver_sql("DROP TABLE IF EXISTS zzt_oi_backfill_targets")
    bind.exec_driver_sql(
        f"""
        CREATE TEMP TABLE zzt_oi_backfill_targets AS
        SELECT h.id AS order_inquiry_id, h.company_id, h.raised_by, h.raised_at,
               COALESCE(agg.earliest, h.raised_at) AS earliest_row_at
        FROM {inquiries} h
        LEFT JOIN (
            SELECT order_inquiry_id, MIN(created_at) AS earliest
            FROM {rows}
            GROUP BY order_inquiry_id
        ) agg ON agg.order_inquiry_id = h.id
        WHERE NOT EXISTS (
            SELECT 1 FROM {raises} r WHERE r.order_inquiry_id = h.id
        )
        """
    )
    touched = bind.exec_driver_sql(
        "SELECT COUNT(*) FROM zzt_oi_backfill_targets"
    ).scalar() or 0

    bind.exec_driver_sql(
        f"""
        INSERT INTO {raises} (id, company_id, order_inquiry_id, kind, raised_by, raised_at)
        SELECT gen_random_uuid(), t.company_id, t.order_inquiry_id, 'raised',
               -- S4 (reviewer, fix round 22 Sep 2026): the header's own `raised_by` is
               -- who did the FIRST raise only when it was never re-stamped after (no
               -- `reconfirmed` row is being written below for this same header) - once a
               -- later reconfirm exists, `t.raised_by` names the LAST reconfirmer, not
               -- the original raiser, and attributing the 'raised' row to them would be
               -- a wrong name, not a missing one, so it stays NULL.
               CASE
                   WHEN t.raised_at - LEAST(t.raised_at, t.earliest_row_at) > interval '1 minute'
                   THEN NULL
                   ELSE t.raised_by
               END,
               LEAST(t.raised_at, t.earliest_row_at)
        FROM zzt_oi_backfill_targets t
        """
    )
    bind.exec_driver_sql(
        f"""
        INSERT INTO {raises} (id, company_id, order_inquiry_id, kind, raised_by, raised_at)
        SELECT gen_random_uuid(), t.company_id, t.order_inquiry_id, 'reconfirmed',
               t.raised_by, t.raised_at
        FROM zzt_oi_backfill_targets t
        WHERE t.raised_at - LEAST(t.raised_at, t.earliest_row_at) > interval '1 minute'
        """
    )
    bind.exec_driver_sql(
        f"""
        UPDATE {inquiries} h
        SET raised_at = LEAST(t.raised_at, t.earliest_row_at)
        FROM zzt_oi_backfill_targets t
        WHERE h.id = t.order_inquiry_id
        """
    )
    bind.exec_driver_sql("DROP TABLE zzt_oi_backfill_targets")
    return int(touched)


def renumber_inquiries(bind) -> int:
    """Every header gapless, per company per month of its (by now backfilled) first
    raise, ordered `raised_at` then `id` (AC-NO-04).

    Two passes, a TEMP TABLE holding the rank in between - a single UPDATE straight to
    the final `OI-YYMM-NNNN` risks tripping `uq_project_order_inquiry_no` mid-statement
    if an old and a new number ever collided; the intermediate `ZTMP-<grn>` value never
    can, since no real number is ever shaped that way.

    Guarded on `legacy_inquiry_no IS NULL` AND the old number still being LEGACY-shaped
    (`OI-NNNNNN`, six digits, no month) - a header already renumbered by an earlier run
    of this same function keeps the value it got, so re-running (the shared dev DB's own
    by-hand apply, per `sorento_crm_backend/CLAUDE.md`) is a no-op the second time. The
    shape guard matters on top of the NULL one: a header born AFTER this migration (the
    ORM's own `before_insert` mints it a dated number directly, `legacy_inquiry_no` stays
    NULL forever) would otherwise still match `legacy_inquiry_no IS NULL` on a second run
    and be renumbered again as if it were rank 1 of its own one-row partition - landing on
    a number an already-renumbered header already holds, a real collision on
    `uq_project_order_inquiry_no`.

    `inquiry_no` is `VARCHAR(20)` (`OI-2609-0001` is 12), so pass 1's placeholder is
    `ZTMP-<row's own global rank in this run>` rather than the row's own id (a UUID is
    36 characters on its own - too long once prefixed).

    The month is read off `raised_at` AT Asia/Kuala_Lumpur, converted from the naive-UTC
    wall clock the column stores (the same double `AT TIME ZONE` conversion
    `order_inquiry_worklist_service.py`'s own `_RAISED_DAY` uses).
    """
    inquiries = _inquiries(bind)

    bind.exec_driver_sql("DROP TABLE IF EXISTS zzt_oi_renumber_targets")
    bind.exec_driver_sql(
        f"""
        CREATE TEMP TABLE zzt_oi_renumber_targets AS
        SELECT id, company_id, inquiry_no AS old_no,
               to_char(
                   raised_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kuala_Lumpur', 'YYMM'
               ) AS ym,
               ROW_NUMBER() OVER (
                   PARTITION BY company_id, to_char(
                       raised_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kuala_Lumpur', 'YYMM'
                   )
                   ORDER BY raised_at ASC, id ASC
               ) AS rn,
               ROW_NUMBER() OVER () AS grn
        FROM {inquiries}
        WHERE legacy_inquiry_no IS NULL
          AND inquiry_no ~ '^OI-[0-9]{{6}}$'
        """
    )
    touched = bind.exec_driver_sql(
        "SELECT COUNT(*) FROM zzt_oi_renumber_targets"
    ).scalar() or 0

    # Pass 1: park the old number on `legacy_inquiry_no` and the row under a value no
    # real number can ever collide with.
    bind.exec_driver_sql(
        f"""
        UPDATE {inquiries} h
        SET legacy_inquiry_no = t.old_no,
            inquiry_no = 'ZTMP-' || t.grn::text
        FROM zzt_oi_renumber_targets t
        WHERE h.id = t.id
        """
    )
    # Pass 2: the real number, gapless within its own company/month.
    bind.exec_driver_sql(
        f"""
        UPDATE {inquiries} h
        SET inquiry_no = 'OI-' || t.ym || '-' || lpad(t.rn::text, 4, '0')
        FROM zzt_oi_renumber_targets t
        WHERE h.id = t.id
        """
    )
    bind.exec_driver_sql("DROP TABLE zzt_oi_renumber_targets")
    return int(touched)


def restore_legacy_numbers(bind) -> int:
    """Downgrade's own data step (AC-S3), exposed so a test can drive it directly rather
    than only through `downgrade()`'s inline SQL.

    Two passes:

    1. Every header that still holds a `legacy_inquiry_no` gets it back verbatim - these
       values were unique before `renumber_inquiries` ever ran, so writing them back
       cannot collide with each other, and they never collide with a dated
       `OI-YYMM-NNNN` number either (different shape entirely).
    2. A header with NO `legacy_inquiry_no` was born AFTER this migration (the ORM's own
       `before_insert` minted it a dated number directly) and has no old number to
       restore, yet the reverted `next_inquiry_no` (MAX+1 over the flat `OI-NNNNNN`
       series) must never be able to hand its number to someone else. So it is minted
       its own legacy-shaped number here, per company, ordered by `raised_at` then `id`,
       strictly PAST the highest number just restored for that company - anything at or
       below that max is a number the old minter could still reissue.

    `legacy_inquiry_no` is cleared once restored, so the column reads empty even if a
    caller (this migration's own `downgrade()`) leaves the column in place a moment
    longer before dropping it.
    """
    inquiries = _inquiries(bind)

    bind.exec_driver_sql(
        f"""
        UPDATE {inquiries}
        SET inquiry_no = legacy_inquiry_no
        WHERE legacy_inquiry_no IS NOT NULL
        """
    )

    bind.exec_driver_sql("DROP TABLE IF EXISTS zzt_oi_restore_targets")
    bind.exec_driver_sql(
        f"""
        CREATE TEMP TABLE zzt_oi_restore_targets AS
        SELECT h.id,
               ROW_NUMBER() OVER (
                   PARTITION BY h.company_id ORDER BY h.raised_at ASC, h.id ASC
               ) AS rn,
               COALESCE(mx.max_tail, 0) AS company_max_tail
        FROM {inquiries} h
        LEFT JOIN (
            SELECT company_id, MAX(substring(inquiry_no from 4)::int) AS max_tail
            FROM {inquiries}
            WHERE inquiry_no ~ '^OI-[0-9]{{6}}$'
            GROUP BY company_id
        ) mx ON mx.company_id = h.company_id
        WHERE h.legacy_inquiry_no IS NULL
        """
    )
    touched = bind.exec_driver_sql(
        "SELECT COUNT(*) FROM zzt_oi_restore_targets"
    ).scalar() or 0

    bind.exec_driver_sql(
        f"""
        UPDATE {inquiries} h
        SET inquiry_no = 'OI-' || lpad((t.company_max_tail + t.rn)::text, 6, '0')
        FROM zzt_oi_restore_targets t
        WHERE h.id = t.id
        """
    )
    bind.exec_driver_sql("DROP TABLE zzt_oi_restore_targets")

    bind.exec_driver_sql(
        f"UPDATE {inquiries} SET legacy_inquiry_no = NULL WHERE legacy_inquiry_no IS NOT NULL"
    )
    return int(touched)


# ------------------------------------------------------------------------------ schema


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "order_inquiry_raises"):
        op.create_table(
            "order_inquiry_raises",
            sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=False), nullable=True),
            sa.Column("order_inquiry_id", postgresql.UUID(as_uuid=False), nullable=False),
            sa.Column("kind", sa.String(length=16), nullable=False),
            sa.Column("raised_by", sa.String(length=100), nullable=True),
            sa.Column(
                "raised_at",
                sa.DateTime(timezone=False),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(
                ["order_inquiry_id"],
                ["projects.order_inquiries.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["raised_by"], ["users.id"], ondelete="SET NULL"),
            schema="projects",
        )

    for name, columns in (
        ("ix_order_inquiry_raises_company_id", "company_id"),
        ("ix_order_inquiry_raises_inquiry", "order_inquiry_id"),
    ):
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {name} ON {_raises(bind)} ({columns})"
        )

    if not _has_column(bind, "order_inquiries", "legacy_inquiry_no"):
        op.execute(
            f"ALTER TABLE {_inquiries(bind)} ADD COLUMN IF NOT EXISTS "
            "legacy_inquiry_no VARCHAR(20)"
        )

    backfilled = backfill_raises(bind)
    renumbered = renumber_inquiries(bind)
    logger.info(
        "523_oi_monthly_no_raises: backfilled %s raise row set(s), renumbered %s header(s)",
        backfilled,
        renumbered,
    )


def downgrade() -> None:
    bind = op.get_bind()
    # The old number survives on `legacy_inquiry_no` for exactly this - restore it,
    # never re-derive it. A header born after this migration never held one; it is
    # minted its own legacy-shaped number, past every restored one, so the reverted
    # MAX+1 minter cannot reissue it (`restore_legacy_numbers`, AC-S3).
    restore_legacy_numbers(bind)
    op.execute(f"ALTER TABLE {_inquiries(bind)} DROP COLUMN IF EXISTS legacy_inquiry_no")
    op.execute(f"DROP TABLE IF EXISTS {_raises(bind)}")
