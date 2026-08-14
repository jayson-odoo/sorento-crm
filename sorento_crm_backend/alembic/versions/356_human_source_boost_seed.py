"""Seed the ranker's `human_source_boost`, so a spec a person set outranks a parsed one.

No DDL, on purpose. The rest of this slice changes what the merge MEANS - a value
somebody set survives re-derivation, a removal stays removed - and none of that needs a
column: the tombstone is a flag inside the provenance entry a row already carries. The
one artifact that does need to exist is this policy row, because the ranker's
source-keyed boost reads it, and a missing row would quietly multiply by 1.

Seeded at 1.5, matching `flyer_source_boost`, so the later migration that promotes flyer
values to authored ones is ranking-neutral on the day it runs rather than a 1.5x to 1.0x
demotion for 695 codes.

Written as a plain INSERT rather than by calling the seeder, so it is self-contained and
cannot drift when the seed list changes. Idempotent through the unique constraint on
`policy_key` (`uq_product_spec_search_policy_key`, from 311m): a second run conflicts and
does nothing, with no read-then-write window for a concurrent run to slip through.

On a FRESH database `311m`'s `seed_search_policy` has already inserted this row by the
time this revision runs, so `upgrade()` no-ops there and `downgrade()` deletes a row that
`311m` created rather than one this revision did. That asymmetry is inherent to seeding
reference data idempotently from two places; it is stated here so nobody reads the
downgrade as removing something it did not add.

Revision ID: 356_human_source_boost_seed
Revises: 322_merge_dealer_kit_customers
"""
import sqlalchemy as sa
from alembic import op

revision = "356_human_source_boost_seed"
down_revision = "322_merge_dealer_kit_customers"
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
        sa.text(
            """
            INSERT INTO product_spec_search_policy (id, policy_key, label, value, help_text)
            VALUES (gen_random_uuid(), :policy_key, :label, 1.5, :help_text)
            ON CONFLICT (policy_key) DO NOTHING
            """
        ).bindparams(policy_key=POLICY_KEY, label=LABEL, help_text=HELP_TEXT)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM product_spec_search_policy WHERE policy_key = :policy_key"
        ).bindparams(policy_key=POLICY_KEY)
    )
