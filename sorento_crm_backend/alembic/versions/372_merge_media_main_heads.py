"""Join the multimodal-media lane with the three heads main grew beside it.

No DDL. A merge revision only joins lineages so `alembic upgrade head` (and the
`alembic stamp head` that `scripts/bootstrap_env.py` runs on a fresh CI
database) has ONE head to aim at.

Four heads met here, all of them forked off `367_promote_flyer_provenance` or a
merge of it, so none is an ancestor of any other:

    369_merge_tickets_media       (this branch: the 356..361 chatbot media /
                                   AI-config chain, already joined to the
                                   intervention-ticket lane)
    369_merge_onboarding_tickets  (main, PR #198: onboarding intake slice 1)
    370_merge_tickets_spec_verif  (main, PR #195: product spec verification)
    371_brand_member_routing      (main, PR #197: brand-aware SLA routing)

The last three landed on main concurrently and each joined forward onto
`368_merge_tickets_main` rather than onto each other, so main itself carries
three heads at this point; pulling it into the media branch makes four. Two
heads is not a warning, it is a broken deploy: `alembic upgrade head` refuses to
guess, and `bootstrap_env` aborts its stamp with "Multiple heads are present"
before a single test runs.

Join forward, never renumber a landed revision - rewriting one strands every
database that already recorded the old id.

The four lanes touch disjoint tables (media jobs, AI provider config and voice
notices; onboarding requests; product spec verifications; brand tags on team
members), so order between them genuinely does not matter.

The id is 26 characters. A database provisioned by a plain `alembic stamp` gets
`alembic_version.version_num varchar(32)`, so any head id must stay within it
(see `tests/test_alembic_revision_ids.py`).

Revision ID: 372_merge_media_main_heads
Revises: 369_merge_tickets_media, 369_merge_onboarding_tickets, 370_merge_tickets_spec_verif, 371_brand_member_routing
Create Date: 2026-08-17
"""

# revision identifiers, used by Alembic.
revision = "372_merge_media_main_heads"
down_revision = (
    "369_merge_tickets_media",
    "369_merge_onboarding_tickets",
    "370_merge_tickets_spec_verif",
    "371_brand_member_routing",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do. A merge revision only joins lineages."""


def downgrade() -> None:
    """Nothing to undo. Downgrading past this re-forks the graph, which is
    correct: the four lineages genuinely are independent below this point."""
