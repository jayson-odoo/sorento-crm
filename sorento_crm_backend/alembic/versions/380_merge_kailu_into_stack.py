"""Rejoin the Kailu packing-list alias seed with the integration branch's head.

No DDL. A merge revision only joins lineages so `alembic upgrade head` (and the
`alembic stamp head` that `scripts/bootstrap_env.py` runs on a fresh CI database)
has ONE target.

**Why there are two.** The Kailu lane sits directly on main's Project Sales merge,
while the integration branch had stacked the SCM lanes above that same revision:

    375_kailu_packing_list_aliases  (Kailu: revises 374_merge_proj_media_flyer)
    379_merge_proforma_into_stack   (integration: joins 378_merge_stage2_into_stack
                                     and 375_scm_proforma_invoice, which also sits on
                                     374_merge_proj_media_flyer)

They are siblings, so merging the Kailu branch in leaves two heads. Two heads is not
a warning, it is a broken deploy: `alembic upgrade head` refuses to guess and
`bootstrap_env` aborts its stamp with "Multiple heads are present" before a single
test runs. This revision joins forward from both.

**Two different revisions are numbered 375** - `375_kailu_packing_list_aliases` and
`375_scm_proforma_invoice` - because two lanes were open against the same parent at
once. The NUMBER is only a filename convention; the revision ID is the identity, and
those differ, so nothing about this is ambiguous to alembic. It is called out because
a reader scanning filenames will otherwise assume one of them is a stray copy.

No `depends_on` is needed. Both 375s insert into `import_field_alias`, whose key is
`(doc_type, field, alias)`, and their rows are disjoint by doc type: 13 `packing_list`
rows on the Kailu side, `proforma_invoice` rows on the other. Both inserts are
`ON CONFLICT DO NOTHING` in any case, so the order between the two branches genuinely
does not matter.

Neither parent is renumbered or deleted; both are landed on their branches and any
database stamped with either must still be able to upgrade. Join forward, never
renumber a landed revision.

The id is 26 characters. A database provisioned by a plain `alembic stamp` gets
`alembic_version.version_num varchar(32)`, so any head id must stay at or under 32
(see 322's docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 380_merge_kailu_into_stack
Revises: 379_merge_proforma_into_stack, 375_kailu_packing_list_aliases
Create Date: 2026-08-18
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "380_merge_kailu_into_stack"
down_revision = (
    "379_merge_proforma_into_stack",
    "375_kailu_packing_list_aliases",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
