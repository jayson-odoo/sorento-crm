"""Seed the ranker's `human_source_boost`, so a spec a person set outranks a parsed one.

No DDL, on purpose. The rest of this slice changes what the merge MEANS - a value
somebody set survives re-derivation, a removal stays removed - and none of that needs a
column: the tombstone is a flag inside the provenance entry a row already carries. The
one artifact that does need to exist is this policy row, because the ranker's
source-keyed boost reads it, and a missing row would quietly multiply by 1.

Seeded at 1.5, matching `flyer_source_boost`, so the later migration that promotes flyer
values to authored ones is ranking-neutral on the day it runs rather than a 1.5x to 1.0x
demotion for 695 codes.

Written as INSERT ... WHERE NOT EXISTS rather than by calling the seeder, so it is
self-contained and cannot drift when the seed list changes. Idempotent: a second run
inserts nothing.

Revision ID: 356_human_source_boost_seed
Revises: 885010d94677
"""
from alembic import op

revision = "356_human_source_boost_seed"
down_revision = "885010d94677"
branch_labels = None
depends_on = None

POLICY_KEY = "human_source_boost"
LABEL = "A spec a person set counts extra"
HELP_TEXT = (
    "A multiplier on the match, like the flyer boost and deliberately a separate knob "
    "so the two can be tuned apart. A value somebody set by hand, or a supplier "
    "confirmed, is the best evidence there is: nobody types a spec that is already "
    "right. Set it to 1 to treat a hand-set spec like a parsed one."
)


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO product_spec_search_policy (id, policy_key, label, value, help_text)
        SELECT gen_random_uuid(), '{POLICY_KEY}', '{LABEL}', 1.5, '{HELP_TEXT}'
        WHERE NOT EXISTS (
            SELECT 1 FROM product_spec_search_policy WHERE policy_key = '{POLICY_KEY}'
        )
        """
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM product_spec_search_policy WHERE policy_key = '{POLICY_KEY}'"
    )
