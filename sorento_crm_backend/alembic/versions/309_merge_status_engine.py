"""Rejoin the status engine with main's head.

Empty on purpose. `308_status_engine` and `308_requestor_uploader_attr` were both
numbered 308 off the same parent, `307_admin_listing_company`, on two different
branches. They are therefore sibling heads, not a sequence: the numeric prefix on a
revision filename looks like an ordering and is not one.

Without this, `alembic heads` reports two heads and `alembic upgrade head` aborts, so
a deploy fails on a migration set that is individually valid. Nothing to migrate here;
this only rejoins the graph.

**Anyone chaining a new revision onto the engine should chain onto THIS revision, not
onto `308_status_engine`.** Chaining onto 308 recreates the fork. In particular the
project-sales branch currently has `309_project_sales_core` pointing at
`308_status_engine`; that `down_revision` should be repointed to
`309_merge_status_engine` when it rebases, which is a one-line change.

Revision ID: 309_merge_status_engine
Revises: 308_requestor_uploader_attr, 308_status_engine
Create Date: 2026-08-01

"""

# revision identifiers, used by Alembic.
revision = "309_merge_status_engine"
down_revision = ("308_requestor_uploader_attr", "308_status_engine")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
