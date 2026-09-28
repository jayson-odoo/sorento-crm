"""Ideation status-event feed: the cursor table and the per-event log guarantee (#1355).

The CRM pulls the shared service's idea status-event feed every 60 s and sends the
``ideation_status_update`` template to the requester
(documentation/plans/ideation/PLAN-ideation-status-update-29sep.md).

- ``ideation_status_event_cursors``: one row per feed base URL, ``after_seq`` moved
  in the same commit as each handled event's log row.
- ``uq_integration_log_ideation_status_event``: a partial unique index on
  ``integration_log (business_id) WHERE business_table = 'ideation_status_events'``,
  so the feed's at-least-once redelivery can never produce a second row (or send)
  for the same ``event_id``. Other tables keep repeating business ids freely.

Also the merge point for main's two heads at branch time (``sales_agent_aliases_r7``
and ``scm_reorder_run_scope_desc``). Additive and guarded, so a database that
already holds both objects (the shared dev copy converges through ``create_all``)
is left alone.

Revision ID: ideation_status_events_s1
Revises: sales_agent_aliases_r7, scm_reorder_run_scope_desc
"""
import sqlalchemy as sa
from alembic import op

revision = "ideation_status_events_s1"
down_revision = ("sales_agent_aliases_r7", "scm_reorder_run_scope_desc")
branch_labels = None
depends_on = None

_TABLE = "ideation_status_event_cursors"
_INDEX = "uq_integration_log_ideation_status_event"


def _has_table() -> bool:
    """Checked in current_schema(), like the index below: the inspector reads the
    connection's cached default schema, which can differ from the search_path."""
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name = :t"
            ),
            {"t": _TABLE},
        )
        .scalar()
    )


def _index_valid(bind):
    """None when the index is absent, else whether Postgres marks it valid."""
    return bind.execute(
        sa.text(
            "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE c.relname = :n AND c.relnamespace = current_schema()::regnamespace"
        ),
        {"n": _INDEX},
    ).scalar()


def _ensure_index(bind, concurrently: bool) -> None:
    """Build the partial unique index. CONCURRENTLY in production so the build never
    holds a SHARE lock over every integration_log write; an interrupted concurrent
    build leaves an INVALID index, which is dropped and rebuilt (aud_0001's pattern)."""
    c = "CONCURRENTLY" if concurrently else ""
    drop = f"DROP INDEX {c} IF EXISTS {_INDEX}"
    create = (
        f"CREATE UNIQUE INDEX {c} IF NOT EXISTS {_INDEX} ON integration_log (business_id) "
        "WHERE business_table = 'ideation_status_events'"
    )
    if _index_valid(bind) is False:
        bind.execute(sa.text(drop))
    bind.execute(sa.text(create))
    if _index_valid(bind) is False:
        bind.execute(sa.text(drop))
        bind.execute(sa.text(create))


def _upgrade(concurrently: bool) -> None:
    if not _has_table():
        op.create_table(
            _TABLE,
            sa.Column("feed_base_url", sa.Text(), primary_key=True),
            sa.Column("after_seq", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
    if concurrently:
        with op.get_context().autocommit_block():
            _ensure_index(op.get_bind(), True)
    else:
        _ensure_index(op.get_bind(), False)


def upgrade() -> None:
    _upgrade(concurrently=True)


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX}")
    if _has_table():
        op.drop_table(_TABLE)
