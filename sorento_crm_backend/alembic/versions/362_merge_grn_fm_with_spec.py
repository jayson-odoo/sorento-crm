"""Join main's GRN forward-matching merge with the spec-authoring lineage.

No DDL. A merge revision only joins two lineages so `alembic upgrade head` has ONE
head to aim at.

**What happened.** This branch was cut when `356_human_source_boost_seed` and
`323_cs_company_backfill` were the two open heads, and `360_merge_container_status_spec`
joined exactly those two before hanging `361_spec_registry_grant_sweep` off it. While
the branch was in flight, `357_merge_grn_spo_fm_heads` landed on main and joined the
same two heads plus a third, `324_grn_line_spo_number_raw`:

    322_merge_dealer_kit_customers
      |-- 323_cs_company_backfill      --.
      |-- 356_human_source_boost_seed  --+-- 357_merge_grn_spo_fm_heads   (main)
      |-- 324_grn_line_spo_number_raw  --'
      `-- (323 + 356) ----------------- 360 -- 361_spec_registry_grant_sweep (this branch)

Two merges over an overlapping set of parents is still a fork: `357` is not an ancestor
of `361` and `361` is not an ancestor of `357`, so the merged result carries two heads.
CI's `bootstrap_env` job aborts on it with "Multiple heads are present; please specify a
single target revision", which took out both `Backend test suite (Postgres)` and
`Dealer Kit PDF render (real browser)` before a single test ran.

Fixed forward with a merge revision rather than by re-pointing `360` at `357`: `360` and
`361` have already been applied to databases from this branch, and rewriting a revision
that is in somebody's `alembic_version` is how two environments end up disagreeing about
what has been applied.

The id is 26 characters: `scripts/bootstrap_env.py` stamps the head into an
`alembic_version` table created with `version_num varchar(32)`, so any head id must stay
<= 32 (see 322's docstring).

Revision ID: 362_merge_grn_fm_with_spec
Revises: 357_merge_grn_spo_fm_heads, 361_spec_registry_grant_sweep
Create Date: 2026-08-15
"""

revision = "362_merge_grn_fm_with_spec"
down_revision = (
    "357_merge_grn_spo_fm_heads",
    "361_spec_registry_grant_sweep",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""
