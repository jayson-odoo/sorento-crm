"""Rejoin main's push-notification/idea-board merge with the product-sets head.

No DDL of its own. A merge revision only joins lineages so `alembic upgrade head`
(and the `alembic stamp head` that `scripts/bootstrap_env.py` runs on a fresh CI
database) has ONE target.

**Why there are two.** Main landed `411_idea_board_perm` and
`411_notify_push_msg_scope` above `410_trgm_norm_idx` and immediately joined them
with `412_merge_push_idea`, while this branch stacked its own product-sets chain
above the same base:

    410_trgm_norm_idx
      -> 411_product_sets (this branch)
      -> 412_link_provenance
      -> 413_product_set_proposals
      -> 414_product_set_grant_sweep

They are siblings off `410_trgm_norm_idx`, so merging main in leaves two heads.
Two heads is not a warning, it is a broken deploy: `alembic upgrade head` refuses
to guess and `bootstrap_env` aborts its stamp with "Multiple heads are present"
before a single test runs. This revision joins forward from both.

No `depends_on` is needed: the push/idea-board chain adds notification scope and
idea-board permission rows, the product-sets chain adds product-set tables,
provenance links, proposal rows and a permission grant sweep, and neither reads
nor writes anything the other touches, so the order between the two branches does
not matter.

Neither parent is renumbered or deleted; both are landed on their branches and any
database stamped with either must still be able to upgrade. Join forward, never
renumber a landed revision. Note that both branches also each contain a revision
numbered 412 with a different revision id (`412_merge_push_idea` here vs. this
branch's separate `412_link_provenance`); ids are what alembic keys on, so that is
fine, not a collision.

The id is 23 characters, well under the 32-char `alembic_version.version_num`
width a plain `alembic stamp` provisions (see 386's docstring and
`tests/test_alembic_revision_ids.py`).

Revision ID: 415_merge_pset_pushidea
Revises: 412_merge_push_idea, 414_product_set_grant_sweep
Create Date: 2026-08-24
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "415_merge_pset_pushidea"
down_revision = (
    "412_merge_push_idea",
    "414_product_set_grant_sweep",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
