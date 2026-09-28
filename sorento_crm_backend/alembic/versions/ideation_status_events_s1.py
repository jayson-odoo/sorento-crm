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
    return sa.inspect(op.get_bind()).has_table(_TABLE)


def _has_index() -> bool:
    return any(
        ix["name"] == _INDEX for ix in sa.inspect(op.get_bind()).get_indexes("integration_log")
    )


def upgrade() -> None:
    if not _has_table():
        op.create_table(
            _TABLE,
            sa.Column("feed_base_url", sa.Text(), primary_key=True),
            sa.Column("after_seq", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
    if not _has_index():
        op.create_index(
            _INDEX,
            "integration_log",
            ["business_id"],
            unique=True,
            postgresql_where=sa.text("business_table = 'ideation_status_events'"),
        )


def downgrade() -> None:
    if _has_index():
        op.drop_index(_INDEX, table_name="integration_log")
    if _has_table():
        op.drop_table(_TABLE)
