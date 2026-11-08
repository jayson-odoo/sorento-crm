"""NPA-FORM-SLA: the New Product Application's two Form SLA stage rows, pre-filled from the SI's.

Data only, idempotent. Each NPA row copies the Stock Inquiry row of the same team set (agent,
team set, policy, active / notify flags), so the NPA routes to the SI's teams and tiers and keeps
its own row, editable in SLA Management > Form SLA Config:

- `npa_approval` (team set `project_sales`): starts on submitted / resubmitted, resolves on
  approved / rejected.
- `npa_purchasing` (team set `purchasing`): starts on approved, the response clock stops on the
  purchasing response save, resolves on completed / rejected.

A row is inserted only while no NPA row holds that team set, and only from an existing SI row, so
a database without the SI's rows (CI, a fresh tenant) gets nothing and a second run adds nothing.
`grace_seconds` is not copied: the NPA has no deferred-action path (form_action_dispatch).

Plan: documentation/plans/procurement/PLAN-npa-form-sla-08nov.md.

Revision ID: npasla_0001_seed_configs
Revises: npasi_0001_lineage
"""
from alembic import op
from sqlalchemy import text

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "npasla_0001_seed_configs"
down_revision = "npasi_0001_lineage"
branch_labels = None
depends_on = None

#: (NPA stage code, the SI team set it copies, start, respond, resolve).
STAGES = (
    ("npa_approval", "project_sales", "submitted,resubmitted", None, "approved,rejected"),
    ("npa_purchasing", "purchasing", "approved", "purchasing_respond", "completed,rejected"),
)


def _insert(stage_code: str, team_set: str, start: str, respond, resolve: str) -> str:
    respond_sql = f"'{respond}'" if respond else "NULL"
    return (
        "INSERT INTO form_sla_configs (id, source_entity_type, stage_code, policy_id, agent_code, "
        "team_set_code, start_event, respond_event, resolve_event, is_active, notify_assignee, "
        "notify_on_escalation, created_at, updated_at) "
        f"SELECT gen_random_uuid(), 'new_product_application', '{stage_code}', si.policy_id, "
        f"si.agent_code, si.team_set_code, '{start}', {respond_sql}, '{resolve}', si.is_active, "
        "si.notify_assignee, si.notify_on_escalation, now(), now() "
        "FROM form_sla_configs si "
        f"WHERE si.source_entity_type = 'stock_inquiry' AND si.team_set_code = '{team_set}' "
        "AND NOT EXISTS (SELECT 1 FROM form_sla_configs n "
        "WHERE n.source_entity_type = 'new_product_application' "
        f"AND n.team_set_code = '{team_set}') "
        "ORDER BY si.is_active DESC, si.created_at ASC LIMIT 1"
    )


SEED = tuple(_insert(*stage) for stage in STAGES)


def upgrade() -> None:
    for statement in SEED:
        op.execute(text(statement))


def downgrade() -> None:
    # Only the rows this revision names; an admin's own NPA rows (other stage codes) stay.
    op.execute(
        text(
            "DELETE FROM form_sla_configs WHERE source_entity_type = 'new_product_application' "
            "AND stage_code IN ('npa_approval', 'npa_purchasing')"
        )
    )
