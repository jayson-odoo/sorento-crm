"""DB retention: settings columns and the daily retention tasks

PLAN-db-retention-12nov. Adds one system_settings column per retention value (plus the
four knobs every rule shares), indexes the recommendation link on
scm.order_summary_location_allocation, and seeds the seven daily scheduled tasks; the existing
`api_call_log_prune` row is left alone. No rows are deleted here: the tasks do that,
in batches, from their first night (02:00 Malaysia time = 18:00 UTC).

Revision ID: dbr_0001_retention_settings
Revises: il_0002_integration_log_search
"""
import sqlalchemy as sa
from alembic import op

revision = "dbr_0001_retention_settings"
down_revision = "il_0002_integration_log_search"
branch_labels = None
depends_on = None

# (column, type, server default)
_COLUMNS = [
    ("integration_log_payload_retention_days", sa.Integer(), "30"),
    ("integration_log_row_retention_days", sa.Integer(), "180"),
    ("chatbot_turn_trace_retention_days", sa.Integer(), "90"),
    ("scheduled_task_run_retention_days", sa.Integer(), "90"),
    ("reorder_run_retention_days", sa.Integer(), "90"),
    ("embedding_superseded_retention_days", sa.Integer(), "90"),
    ("plan_exception_superseded_grace_days", sa.Integer(), "1"),
    ("data_retention_dry_run", sa.Boolean(), "false"),
    ("data_retention_batch_size", sa.Integer(), "5000"),
    ("data_retention_batch_sleep_ms", sa.Integer(), "200"),
    ("data_retention_max_run_minutes", sa.Integer(), "30"),
]

# (key, name, description)
_TASKS = [
    (
        "plan_exception_prune",
        "Plan exceptions clean-up",
        "Daily: removes undecided plan exceptions from batches a newer batch has replaced. "
        "The newest batch of each planning run and every decided exception are kept.",
    ),
    (
        "integration_log_prune",
        "Integration log clean-up",
        "Daily: clears request and response bodies and headers after 30 days and removes "
        "log rows after 180 days. Calls still pending or processing, and failed-audit "
        "records, are kept.",
    ),
    (
        "chatbot_turn_trace_prune",
        "Chat turn trace clean-up",
        "Daily: clears the step-by-step trace of chat turns older than 90 days. The turn "
        "itself is kept.",
    ),
    (
        "scheduled_task_runs_prune",
        "Scheduled task history clean-up",
        "Daily: removes scheduled task run history older than 90 days, keeping the latest "
        "run of every task.",
    ),
    (
        "reorder_run_prune",
        "Old planning runs clean-up",
        "Daily: removes replaced planning runs older than 90 days with their "
        "recommendations, unless someone changed or decided anything on them.",
    ),
    (
        "embedding_superseded_prune",
        "Old AI search data clean-up",
        "Daily: removes AI search text that was replaced more than 90 days ago. Current "
        "AI search data is never removed.",
    ),
    (
        "import_job_rows_prune",
        "Import row detail clean-up",
        "Daily: removes per-row import detail older than 90 days. Each import keeps its "
        "totals and summary.",
    ),
]

# Next 18:00 UTC (02:00 Malaysia time), stored as naive UTC like every scheduled_tasks time.
_NEXT_2AM_MYT = (
    "(date_trunc('day', now() AT TIME ZONE 'utc') + interval '18 hours' "
    "+ CASE WHEN (now() AT TIME ZONE 'utc') >= date_trunc('day', now() AT TIME ZONE 'utc') "
    "+ interval '18 hours' THEN interval '1 day' ELSE interval '0' END)"
)


def upgrade():
    conn = op.get_bind()

    present = {c["name"] for c in sa.inspect(conn).get_columns("system_settings")}
    for name, type_, default in _COLUMNS:
        if name not in present:
            op.add_column(
                "system_settings",
                sa.Column(name, type_, nullable=False, server_default=default),
            )

    # Deleting a recommendation SETs NULL on this column (reorder_run_prune); without an
    # index each deleted recommendation scans the table. A plain build, not CONCURRENTLY
    # (app/utils/online_index.py): the table is small (under 50 MB) and only the daily
    # reorder run writes it, so the share lock lasts seconds under the migration
    # lock_timeout.
    op.create_index(
        "ix_scm_order_summary_location_alloc_rec",
        "order_summary_location_allocation",
        ["reorder_recommendation_id"],
        schema="scm",
        if_not_exists=True,
    )

    for key, name, description in _TASKS:
        conn.execute(
            sa.text(
                f"""
                INSERT INTO scheduled_tasks
                    (id, key, name, description, enabled, interval_unit, interval_value,
                     timezone, start_at, next_run_at, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :key, :name, :description, true, 'days', 1,
                     'UTC', {_NEXT_2AM_MYT}, {_NEXT_2AM_MYT},
                     now() AT TIME ZONE 'utc', now() AT TIME ZONE 'utc')
                ON CONFLICT (key) DO NOTHING
                """
            ),
            {"key": key, "name": name, "description": description},
        )


def downgrade():
    conn = op.get_bind()
    op.drop_index(
        "ix_scm_order_summary_location_alloc_rec",
        table_name="order_summary_location_allocation",
        schema="scm",
        if_exists=True,
    )
    for key, _name, _description in _TASKS:
        conn.execute(sa.text("DELETE FROM scheduled_tasks WHERE key = :key"), {"key": key})
    for name, _type, _default in reversed(_COLUMNS):
        op.drop_column("system_settings", name)
