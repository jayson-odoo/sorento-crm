"""Join the GRN forward-matching head with main's two heads off 322.

No DDL. A merge revision only joins lineages so `alembic upgrade head` has ONE
head to aim at.

All three lineages hang directly off `322_merge_dealer_kit_customers`:

    323_cs_company_backfill    (main: container-status company backfill lane)
    356_human_source_boost_seed (main: spec-search ranker seed lane)
    324_grn_line_spo_number_raw (this branch: durable stated SPO on GRN lines)

`324` deliberately chains onto `322`, not onto either sibling lane, because those
lanes landed on main independently while this branch was in flight. Neither
sibling is an ancestor of the other either - main itself carries two heads - so
this merge joins all three at once. Three heads is not a warning, it is a broken
deploy: CI's `bootstrap_env` job and `alembic upgrade head` both fail with
"Multiple heads are present".

The sibling revision files are vendored into this branch verbatim so the graph
is complete on a branch-only checkout too; content is byte-identical to main's,
so the eventual git merge is a no-op on them.

The id is 26 characters: `scripts/bootstrap_env.py` stamps the head into an
`alembic_version` table created with `version_num varchar(32)`, so any head id
must stay <= 32 (see 322's docstring).
"""

revision = "357_merge_grn_spo_fm_heads"
down_revision = (
    "323_cs_company_backfill",
    "356_human_source_boost_seed",
    "324_grn_line_spo_number_raw",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to undo. Downgrading past this re-forks the graph, which is
    correct: the three lineages genuinely are independent below this point."""
