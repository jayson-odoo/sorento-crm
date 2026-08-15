"""Onboarding: a role the requester types, and the retirement of the sheet reader.

Two things, both consequences of the same review round (captain, 2026-08-15).

1. ``onboarding_people.role_label`` - free text, 120 characters. The requester
   knows what somebody does; the reviewer is the one who turns that into a CRM
   role. Asking her to pick from the role list would expose the very list the
   access templates exist to hide (UAC AC-5.4), so this is prose, not a
   foreign key.

2. The ``onboarding_person`` header aliases go. They existed only so the
   workbook reader could resolve ``STAFF NAME`` and friends, and that reader was
   withdrawn with the upload path. Deleted HERE rather than by editing migration
   360, which has already run on shared databases; the downgrade puts them back,
   so the pair is reversible.

``onboarding_people.section_label`` is deliberately NOT dropped. Nothing reads
or writes it any more, but dropping a populated column is destructive and buys
nothing.

Revision ID: 361_onboarding_role_label
Revises: 360_onboarding_slice1
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "361_onboarding_role_label"
down_revision = "360_onboarding_slice1"
branch_labels = None
depends_on = None

DOC_TYPE = "onboarding_person"

#: What migration 360 seeded. Repeated here so the downgrade can restore exactly
#: what this migration removed rather than leaving the database short.
_ALIASES = [
    ("full_name", "STAFF NAME"),
    ("full_name", "NAME"),
    ("full_name", "FULL NAME"),
    ("full_name", "EMPLOYEE NAME"),
    ("full_name", "STAFF"),
    ("nick_name", "NICK NAME"),
    ("nick_name", "NICKNAME"),
    ("nick_name", "SHORT NAME"),
    ("nick_name", "PREFERRED NAME"),
    ("phone", "PHONE"),
    ("phone", "PHONE NO"),
    ("phone", "PHONE NUMBER"),
    ("phone", "MOBILE"),
    ("phone", "MOBILE NO"),
    ("phone", "HP"),
    ("phone", "CONTACT NO"),
    ("email", "EMAIL"),
    ("email", "EMAIL ADDRESS"),
]


def upgrade() -> None:
    # IF NOT EXISTS throughout: the dev database is shared across worktrees, so a
    # column this migration wants may already be there from another lane.
    op.execute(
        "ALTER TABLE onboarding_people ADD COLUMN IF NOT EXISTS role_label VARCHAR(120)"
    )
    op.get_bind().execute(
        sa.text("DELETE FROM import_field_alias WHERE doc_type = :doc"), {"doc": DOC_TYPE}
    )


def downgrade() -> None:
    bind = op.get_bind()
    for field, alias in _ALIASES:
        bind.execute(
            sa.text(
                """
                INSERT INTO import_field_alias (id, doc_type, field, alias, created_at)
                SELECT gen_random_uuid(), :doc, :field, :alias, now()
                WHERE NOT EXISTS (
                    SELECT 1 FROM import_field_alias
                    WHERE doc_type = :doc AND field = :field AND alias = :alias
                )
                """
            ),
            {"doc": DOC_TYPE, "field": field, "alias": alias},
        )
    op.execute("ALTER TABLE onboarding_people DROP COLUMN IF EXISTS role_label")
