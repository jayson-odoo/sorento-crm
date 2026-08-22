"""sales_orders.demand_class - re-rank rows the agent wrongly outranked the customer segment on.

`outstanding_import_service._classify_demand` reads, per document: the stored order type, then
the file's own stated type, then the customer's market segment, and the sales agent's class
LAST - a tendency about the seller, read only when the first three are silent. Both
`_backfill_null_class_orders` (`app/services/scm/sales_agent_service.py`, fixed alongside this
migration) and the earlier `397_so_class_from_agent` one-off filled a NULL-class order straight
from its agent WITHOUT checking the customer's segment first, so a row like FANNY III's (agent
classified retail) whose customer sits on a project segment landed on `retail` - the ladder
answers `project` for that same row.

Idempotent, JOIN-based, and a correction rather than a fill: scoped to `order_type` empty (the
first two rungs are silent, same as at import), the customer's segment stating something (the
third rung answers), and the CURRENT value disagreeing with what the segment says - so a row
already correctly classified, however it got there, is left alone, and re-running finds nothing
left to change. This exact statement was already run by hand against the shared dev database on
19 Aug 2026 (63 rows) before this migration existed, so `upgrade()` here is expected to match 0
rows there - that IS the idempotency check.

Revision ID: 401_so_class_segment_rank
Revises: 400_oi_place_on_po
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa


revision = "401_so_class_segment_rank"
down_revision = "400_oi_place_on_po"
branch_labels = None
depends_on = None

# Same substring match as `app.services.scm.demand_class.class_of` / `PROJECT_SEGMENTS`,
# spelled out in SQL because a migration must not import application code (it runs against
# whatever schema state existed at this revision, not today's models). Keep the two in sync
# by hand if the vocabulary ever changes - `demand_class.py`'s own docstring calls out that a
# third class is a migration on the check constraint anyway, so this would be touched then too.
_PROJECT_SEGMENT_MATCH_SQL = (
    "lower(trim(coalesce(c.market_segment_code, ''))) LIKE '%project%' "
    "OR lower(trim(coalesce(c.market_segment_code, ''))) LIKE '%projects%' "
    "OR lower(trim(coalesce(c.market_segment_code, ''))) LIKE '%contract%'"
)

_SEGMENT_CLASS_CASE_SQL = f"CASE WHEN ({_PROJECT_SEGMENT_MATCH_SQL}) THEN 'project' ELSE 'retail' END"


def apply(bind) -> int:
    """Re-rank every `sales_orders` row the segment outranks the agent (or a stale value) on.

    Returns the number of rows changed.
    """
    return (
        bind.execute(
            sa.text(
                f"""
                UPDATE sales_orders AS so
                   SET demand_class = {_SEGMENT_CLASS_CASE_SQL}
                  FROM customers AS c
                 WHERE c.id = so.customer_id
                   AND coalesce(trim(so.order_type), '') = ''
                   AND coalesce(trim(c.market_segment_code), '') <> ''
                   AND so.demand_class IS DISTINCT FROM ({_SEGMENT_CLASS_CASE_SQL})
                """
            )
        ).rowcount
        or 0
    )


def revert(bind) -> int:
    """No-op. Which rows this corrected, and what they held before (a wrong agent-derived
    value, or something else), is not recorded anywhere once written - there is nothing to
    tell apart on the way back down, and reverting to a KNOWN-wrong value would be a second
    bug wearing the first one's clothes. Rows changed: always 0.
    """
    return 0


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
