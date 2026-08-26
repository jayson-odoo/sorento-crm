"""The four agents the captain ruled retail, so their next order is not refused

Revision ID: 427_sales_agents_class_backfill
Revises: 426_committed_v_form_leg_scope
Create Date: 2026-08-26 22:30:00.000000

The second half of the Friday station-1 trap (`PLAN-scm-purchasing-uat-journey.md` P4, QP1).

An SO upload classifies a document through four sources in order: the order type the header
carries, the order type the file states, the customer's market segment, and last the demand
class held against the AGENT who sold it. The real AutoCount export carries no order type
column, so the last two are the only live ones - 425 filled the customers, and this fills
the agents the captain has ruled on.

Ruled RETAIL on 26 Aug 2026, being the agents whose NULL-class orders the captain called
retail, with their open-order load at the time:

    LCL            123 open orders
    KATHERINE       10
    XUAN             3
    JAMYN CHANG      2

STILL BLANK afterwards, and deliberately so - nobody has ruled on them:

    JACKSON I        2 open orders, and its 2 customers carry no market segment either
    JACKSON IV       1 open order, same
    ZZT Loh Han Cong, ZZT Agnes Tan   test residue on the prod copy, 0 open orders

JACKSON I and JACKSON IV are the residual trap and are named in the report for a ruling: a
NEW document for one of their debtors would be refused, because neither the customer nor the
agent can answer for it. Left alone rather than defaulted, which is the whole of QP1 - a
guessed class is stable and no later upload surfaces it.

Matched on the agent CODE, normalised the way `sales_agent_service` stores it (upper,
trimmed), and only where the class is still NULL: an agent somebody has classified since is
theirs, not ours.

REVERSIBLE through `scm.agent_class_backfill_427`, which records every agent row this
migration writes, so the downgrade restores a NULL on exactly those.

No application code is imported: the class is written out as a literal, because a migration
describes a point in history (`tests/scm/test_committed_v_migration_chain.py`).
"""
from alembic import op

revision = "427_sales_agents_class_backfill"
down_revision = "426_committed_v_form_leg_scope"
branch_labels = None
depends_on = None


#: The class the ruling gives them. Frozen as a literal, see above.
_RETAIL = "retail"

#: The agent codes the captain ruled on, and ONLY those.
_RULED_RETAIL = ("LCL", "KATHERINE", "XUAN", "JAMYN CHANG")

_MARKER = "scm.agent_class_backfill_427"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS scm")
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_MARKER} (
            sales_agent_id uuid PRIMARY KEY,
            stamped_at timestamp NOT NULL DEFAULT now()
        )
        """
    )
    codes = ", ".join(f"'{code}'" for code in _RULED_RETAIL)
    # Recorded BEFORE the update, and only rows still NULL, so the table names exactly what
    # this migration changed and a second run adds nothing.
    op.execute(
        f"""
        INSERT INTO {_MARKER} (sales_agent_id)
        SELECT id FROM sales_agents
        WHERE demand_class IS NULL
          AND upper(trim(sales_agent)) IN ({codes})
        ON CONFLICT (sales_agent_id) DO NOTHING
        """
    )
    op.execute(
        f"""
        UPDATE sales_agents SET demand_class = '{_RETAIL}'
        WHERE id IN (SELECT sales_agent_id FROM {_MARKER})
          AND demand_class IS NULL
        """
    )


def downgrade() -> None:
    # Only the rows this migration stamped, and only while they still read what it wrote.
    # Guarded on the table existing, like 425's: a downgrade run twice, or on a database
    # that never saw the upgrade, must not die on `relation does not exist`.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('{_MARKER}') IS NOT NULL THEN
                UPDATE sales_agents SET demand_class = NULL
                WHERE demand_class = '{_RETAIL}'
                  AND id IN (SELECT sales_agent_id FROM {_MARKER});
            END IF;
        END $$;
        """
    )
    op.execute(f"DROP TABLE IF EXISTS {_MARKER}")
