"""Merge the S6b reference-data head with the price-tag chain head.

Two PRs merged the same afternoon each carried its own migration head:
#289 ended on 447_merge_ptag_ac and #411 on s6b_reference_data_manage_perm.
Empty merge revision, exactly like 348's.

Revision ID: 448_merge_s6b_ptag
Revises: 447_merge_ptag_ac, s6b_reference_data_manage_perm
"""

revision = "448_merge_s6b_ptag"
down_revision = ("447_merge_ptag_ac", "s6b_reference_data_manage_perm")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
