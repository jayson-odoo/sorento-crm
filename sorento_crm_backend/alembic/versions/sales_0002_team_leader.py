"""Sales module, S6 fix lane round 2 (W1): a team leader on `sales.teams`.

Owner ruling 26 Sep ~13:25Z (PR #1260, verbatim): "I need it to be able to set a sales leader,
which is also a sales agent".

1. `sales.teams.leader_sales_agent_id`, nullable, foreign key `fk_sales_teams_leader_sales_agent_id`
   to `sales_agents.id` ON DELETE SET NULL (a deleted agent leads nothing). A current attribute
   of the team, not dated history; no backfill, every team starts with no leader.
2. The membership rule `trg_sales_teams_leader_is_member`: a team's leader has an open membership
   row (`valid_to IS NULL`) in that team. A pair of DEFERRABLE INITIALLY DEFERRED constraint
   triggers, one on `sales.teams` (the leader set or changed) and one on `sales.team_members`
   (an open row closed or deleted), sharing one function. The DDL is
   `app.models.sales.leader_rule_ddl`, the same copy `create_all` uses.

Permissions: none new; `sales.teams.edit` covers setting the leader.

Downgrade drops both triggers, the function and the column.

Revision ID: sales_0002_team_leader
Revises: sales_0001_teams
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.sales import leader_rule_ddl, translated_schema

revision = "sales_0002_team_leader"
down_revision = "sales_0001_teams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # `sales`, or the migration test's scratch copy of it: alembic's ALTER TABLE ignores
    # `schema_translate_map`, so the schema is named explicitly.
    schema = translated_schema(bind)
    op.add_column(
        "teams",
        sa.Column("leader_sales_agent_id", postgresql.UUID(as_uuid=False), nullable=True),
        schema=schema,
    )
    op.create_foreign_key(
        "fk_sales_teams_leader_sales_agent_id",
        "teams",
        "sales_agents",
        ["leader_sales_agent_id"],
        ["id"],
        source_schema=schema,
        ondelete="SET NULL",
    )
    for statement in leader_rule_ddl(schema):
        bind.execute(sa.text(statement))


def downgrade() -> None:
    bind = op.get_bind()
    schema = translated_schema(bind)
    bind.execute(
        sa.text(f'DROP TRIGGER IF EXISTS trg_sales_team_members_leader_is_member ON "{schema}".team_members')
    )
    bind.execute(sa.text(f'DROP TRIGGER IF EXISTS trg_sales_teams_leader_is_member ON "{schema}".teams'))
    bind.execute(sa.text(f'DROP FUNCTION IF EXISTS "{schema}".sales_team_leader_is_member()'))
    op.drop_constraint(
        "fk_sales_teams_leader_sales_agent_id", "teams", type_="foreignkey", schema=schema
    )
    op.drop_column("teams", "leader_sales_agent_id", schema=schema)
