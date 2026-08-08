"""Company-aware assignment routing: a team belongs to exactly one company.

``agent_teams`` mapped (agent, team-set code, tier) to a team with no company axis,
so a Mocha conversation and a Sorento conversation resolved to the same team. The
workaround was to encode the company in the code itself
(``marketing_promotion_sorento`` / ``marketing_promotion_mocha``), which does not
survive escalation and does not compose with an SLA policy per team set.

What this adds:

* ``teams.company_id`` NOT NULL. A team is a list of people belonging to one brand;
  a ladder shared by both brands is modelled as one team per company holding the
  same people.
* ``agent_teams.company_id`` NOT NULL, with a COMPOSITE FK ``(team_id, company_id)``
  into ``teams(id, company_id)``. The column is a denormalised copy that exists so
  ``(agent_id, code, tier, company_id)`` is indexable and the resolver needs no
  join - the composite FK is what makes it impossible for that copy to drift from
  the team's real company. Same trick for ``policy_id``.
* ``sla_policies.company_id`` NOT NULL, so each company owns its policies. The
  global ``sla_policies_code_key`` is replaced by ``(code, company_id)``: any code
  path assuming a globally unique policy code has to filter by company now.
* ``conversation_sla_tracking.company_id`` NOT NULL, stamped at creation and read
  back on every escalation, so a tier-2 escalation of a Mocha conversation cannot
  land on Sorento.

What this deliberately does NOT do:

* create any Mocha row. Mocha teams, team sets and policies are configured by an
  admin BEFORE any contact is tagged Mocha - that provisioning order is what makes
  the "no team for this company" hard 404 safe rather than an outage.
* collapse the company-suffixed team-set codes. Rewriting those rewrites live
  routing, so a human re-points them after this lands.
* delete a team membership that violates the new company-grant rule. It reports
  them; removing someone from a team silently changes who gets assigned.

Revision ID: 320_company_aware_routing
Revises: 319_picking_header_provenance
"""
import logging

from alembic import op
from sqlalchemy import text as sa_text

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "320_company_aware_routing"
down_revision = "319_picking_header_provenance"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

# Sorento. Every pre-multi-company row belongs to it.
DEFAULT_COMPANY_ID = "00000000-0000-0000-0000-000000000001"

# (table, constraint name, definition) for the constraints added here. Postgres has
# no ADD CONSTRAINT IF NOT EXISTS, so each goes through a DO block that swallows
# duplicate_object - keeps the migration re-runnable against a partially migrated
# database (the shared dev database gets its DDL applied by hand).
_CONSTRAINTS = [
    ("teams", "uq_teams_id_company", "UNIQUE (id, company_id)"),
    (
        "teams",
        "fk_teams_company_id",
        "FOREIGN KEY (company_id) REFERENCES companies(id)",
    ),
    ("sla_policies", "uq_sla_policies_id_company", "UNIQUE (id, company_id)"),
    (
        "sla_policies",
        "fk_sla_policies_company_id",
        "FOREIGN KEY (company_id) REFERENCES companies(id)",
    ),
    (
        "sla_policies",
        "uq_sla_policies_code_company",
        "UNIQUE (code, company_id)",
    ),
    (
        "agent_teams",
        "fk_agent_teams_company_id",
        "FOREIGN KEY (company_id) REFERENCES companies(id)",
    ),
    # The anti-drift constraints. A link row can only point at a team / policy that
    # really does belong to the company stamped on the link.
    (
        "agent_teams",
        "fk_agent_teams_team_company",
        "FOREIGN KEY (team_id, company_id) REFERENCES teams(id, company_id)",
    ),
    (
        "agent_teams",
        "fk_agent_teams_policy_company",
        "FOREIGN KEY (policy_id, company_id) REFERENCES sla_policies(id, company_id)",
    ),
    (
        "conversation_sla_tracking",
        "fk_conversation_sla_tracking_company_id",
        "FOREIGN KEY (company_id) REFERENCES companies(id)",
    ),
]


def _add_constraint(table: str, name: str, definition: str) -> None:
    op.execute(
        f"""
        DO $$ BEGIN
            ALTER TABLE {table} ADD CONSTRAINT {name} {definition};
        EXCEPTION
            WHEN duplicate_object THEN NULL;
            WHEN duplicate_table THEN NULL;
        END $$;
        """
    )


def _add_company_column(table: str) -> None:
    """Add, backfill and lock down ``company_id`` on one table.

    Nullable first, then backfilled, then NOT NULL: adding the column already NOT
    NULL would fail outright on a non-empty table.

    The Sorento server default is deliberate and is what makes this safe to deploy
    blue/green: during the rollover, old containers still INSERT without a
    company_id, and a bare NOT NULL would turn every one of those into an error for
    the length of the deploy. Sorento is the documented incumbent for exactly these
    rows anyway. It cannot paper over a wrong company on the link tables - the
    composite FKs below reject a link whose company disagrees with its team.
    """
    op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS company_id uuid")
    op.execute(
        f"UPDATE {table} SET company_id = '{DEFAULT_COMPANY_ID}' WHERE company_id IS NULL"
    )
    op.execute(
        f"ALTER TABLE {table} ALTER COLUMN company_id SET DEFAULT '{DEFAULT_COMPANY_ID}'"
    )
    op.execute(f"ALTER TABLE {table} ALTER COLUMN company_id SET NOT NULL")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_{table}_company_id ON {table} (company_id)"
    )


def upgrade():
    bind = op.get_bind()

    # --- teams ------------------------------------------------------------
    _add_company_column("teams")

    # --- sla_policies -----------------------------------------------------
    _add_company_column("sla_policies")

    # --- agent_teams ------------------------------------------------------
    # Backfilled FROM the team rather than from the default constant, so the link's
    # company is the team's company by construction even if a team is somehow not
    # Sorento by the time this runs.
    op.execute("ALTER TABLE agent_teams ADD COLUMN IF NOT EXISTS company_id uuid")
    op.execute(
        """
        UPDATE agent_teams AS at
        SET company_id = t.company_id
        FROM teams AS t
        WHERE t.id = at.team_id AND at.company_id IS DISTINCT FROM t.company_id
        """
    )
    op.execute(
        f"UPDATE agent_teams SET company_id = '{DEFAULT_COMPANY_ID}' WHERE company_id IS NULL"
    )
    op.execute(
        f"ALTER TABLE agent_teams ALTER COLUMN company_id SET DEFAULT '{DEFAULT_COMPANY_ID}'"
    )
    op.execute("ALTER TABLE agent_teams ALTER COLUMN company_id SET NOT NULL")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_teams_company_id ON agent_teams (company_id)"
    )

    # A link whose policy belongs to another company would fail the composite FK
    # below. Nothing can be in that state today (one company), but a partially
    # hand-migrated database could be, and a failed ALTER mid-migration is worse
    # than an explicit null-out of the offending pointer.
    op.execute(
        """
        UPDATE agent_teams AS at SET policy_id = NULL
        FROM sla_policies AS p
        WHERE p.id = at.policy_id AND p.company_id IS DISTINCT FROM at.company_id
        """
    )

    # --- conversation_sla_tracking ---------------------------------------
    _add_company_column("conversation_sla_tracking")

    # --- constraints ------------------------------------------------------
    for table, name, definition in _CONSTRAINTS:
        _add_constraint(table, name, definition)

    # The old global policy-code uniqueness is what made per-company policies
    # impossible. Dropped only AFTER (code, company_id) is in place.
    op.execute("ALTER TABLE sla_policies DROP CONSTRAINT IF EXISTS sla_policies_code_key")

    # --- agent_teams uniqueness gains the company -------------------------
    # Same (code, tier) under different companies is the new normal, so the old
    # keys would reject exactly the rows this feature exists to allow.
    op.execute("DROP INDEX IF EXISTS uq_agent_teams_agent_code_tier_null")
    op.execute("DROP INDEX IF EXISTS uq_agent_teams_agent_code_tier_not_null")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_teams_agent_code_company_tier_null
        ON agent_teams (agent_id, code, company_id) WHERE tier IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_teams_agent_code_company_tier
        ON agent_teams (agent_id, code, tier, company_id) WHERE tier IS NOT NULL
        """
    )

    # --- report, never repair --------------------------------------------
    # A team's parent must be in the same company: a parent team's members can see
    # and act on every descendant team's work at any depth, so a cross-company
    # parent is a data leak. Trivially satisfied right after the backfill; checked
    # anyway because this migration is re-runnable.
    crossing = bind.execute(
        sa_text(
            """
            SELECT count(*) FROM teams c JOIN teams p ON p.id = c.parent_team_id
            WHERE p.company_id <> c.company_id
            """
        )
    ).scalar()
    if crossing:
        raise RuntimeError(
            f"{crossing} team(s) have a parent in another company. Re-point them "
            "before migrating: a parent team's members can act on every descendant."
        )

    orphans = bind.execute(
        sa_text(
            """
            SELECT count(*) FROM team_members tm
            WHERE NOT EXISTS (
                SELECT 1 FROM user_companies uc
                WHERE uc.user_id = tm.user_id AND uc.company_id = (
                    SELECT company_id FROM teams t WHERE t.id = tm.team_id
                )
            )
            """
        )
    ).scalar()
    if orphans:
        logger.warning(
            "company-aware routing: %s team membership(s) belong to a user with no "
            "company grant for that team's company. Left in place on purpose - "
            "removing someone from a team changes who gets assigned. Grant the "
            "company or remove the membership by hand.",
            orphans,
        )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_agent_teams_agent_code_company_tier_null")
    op.execute("DROP INDEX IF EXISTS uq_agent_teams_agent_code_company_tier")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_teams_agent_code_tier_null
        ON agent_teams (agent_id, code) WHERE tier IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_teams_agent_code_tier_not_null
        ON agent_teams (agent_id, code, tier) WHERE tier IS NOT NULL
        """
    )

    for table, name, _definition in reversed(_CONSTRAINTS):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")

    # Restore the global policy-code uniqueness this migration replaced. Only
    # possible while no two companies share a code, which is true on the way back
    # down from a single-company install.
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE sla_policies ADD CONSTRAINT sla_policies_code_key UNIQUE (code);
        EXCEPTION
            WHEN duplicate_object THEN NULL;
            WHEN duplicate_table THEN NULL;
        END $$;
        """
    )

    for table in (
        "conversation_sla_tracking",
        "agent_teams",
        "sla_policies",
        "teams",
    ):
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_company_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS company_id")
