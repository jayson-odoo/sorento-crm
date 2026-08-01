"""Portal submission of workflow forms by a contact (F2b).

Two columns on the definition declare the portal stance, four on the submission record who
filed it, what spawned it and where its chat lives, plus a latch for portal editability.

**The gate is two columns on purpose.** `portal_submittable` is the door and defaults to
FALSE; `portal_party_kinds` is a narrowing where empty means "no narrowing". Folding them
into one would make "open to everyone" inexpressible without a magic sentinel, and the
natural empty-list reading flips to fail-OPEN on the one column in this platform where that
would expose data. Both server defaults are load-bearing: the columns are NOT NULL on tables
that already have rows.

**`respondent_contact_id` is TEXT, not UUID.** `respond_contacts.id` is a TEXT column, and a
uuid column cannot hold a foreign key to a text one. Every existing FK into that table is a
string, for the same reason `users.id` forces String FKs elsewhere. `ON DELETE SET NULL`
follows the convention of the other attribution FKs into that table: CASCADE would delete a
customer's filed form when their contact record is cleaned up.

**`portal_locked_at` exists because "initial rung" is not monotonic.** For a deriving
definition the initial rung IS the derived open key, and the header returns there whenever a
line is un-decided, so gating portal edits on the rung alone would hand editing back to the
customer after staff had started work. The latch is stamped the first time the submission
leaves its initial rung and never clears.

Note `source_entity_type` / `source_entity_id` here mean "what spawned this form", which is
the ADR-0009 polymorphic idiom. On `conversation_sla_tracking` the same two names mean the
form TYPE and the form's own id. Same schema, opposite referents; kept anyway so after-sales
stays consistent with its own ADR. `source_entity_id` is a string because a polymorphic
pointer cannot assume every target table has a uuid primary key.

Revision ID: 314_wf_submission_portal
Revises: 313_wf_submission_sla
Create Date: 2026-08-01

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "314_wf_submission_portal"
down_revision = "313_wf_submission_sla"
branch_labels = None
depends_on = None

_DEFS = "workflow_form_definitions"
_SUBS = "workflow_submissions"


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set:
    return {c["name"] for c in _inspector().get_columns(table)}


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    """Idempotent: the shared dev database is stamped on another worktree's chain, so
    columns get applied there by hand and a plain add_column would abort."""
    if column.name not in _columns(table):
        op.add_column(table, column)


def _create_index_if_missing(name: str, table: str, columns: list) -> None:
    if name not in {ix["name"] for ix in _inspector().get_indexes(table)}:
        op.create_index(name, table, columns)


def upgrade() -> None:
    _add_column_if_missing(
        _DEFS,
        sa.Column(
            "portal_submittable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    _add_column_if_missing(
        _DEFS,
        sa.Column(
            "portal_party_kinds",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    _add_column_if_missing(_SUBS, sa.Column("respondent_contact_id", sa.Text(), nullable=True))
    _add_column_if_missing(_SUBS, sa.Column("source_entity_type", sa.String(length=64), nullable=True))
    _add_column_if_missing(_SUBS, sa.Column("source_entity_id", sa.String(length=128), nullable=True))
    _add_column_if_missing(_SUBS, sa.Column("respond_inbox_url", sa.Text(), nullable=True))
    _add_column_if_missing(_SUBS, sa.Column("portal_locked_at", sa.DateTime(timezone=False), nullable=True))

    fks = {fk.get("name") for fk in _inspector().get_foreign_keys(_SUBS)}
    if "fk_workflow_submissions_respondent_contact_id" not in fks:
        op.create_foreign_key(
            "fk_workflow_submissions_respondent_contact_id",
            _SUBS,
            "respond_contacts",
            ["respondent_contact_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # (contact, created_at): the portal lists a contact's own submissions newest first.
    _create_index_if_missing(
        "ix_workflow_submissions_respondent_created", _SUBS, ["respondent_contact_id", "created_at"]
    )
    _create_index_if_missing(
        "ix_workflow_submissions_source_entity", _SUBS, ["source_entity_type", "source_entity_id"]
    )


def downgrade() -> None:
    for name in ("ix_workflow_submissions_source_entity", "ix_workflow_submissions_respondent_created"):
        if name in {ix["name"] for ix in _inspector().get_indexes(_SUBS)}:
            op.drop_index(name, table_name=_SUBS)

    if "fk_workflow_submissions_respondent_contact_id" in {
        fk.get("name") for fk in _inspector().get_foreign_keys(_SUBS)
    }:
        op.drop_constraint("fk_workflow_submissions_respondent_contact_id", _SUBS, type_="foreignkey")

    for table, columns in (
        (
            _SUBS,
            (
                "portal_locked_at",
                "respond_inbox_url",
                "source_entity_id",
                "source_entity_type",
                "respondent_contact_id",
            ),
        ),
        (_DEFS, ("portal_party_kinds", "portal_submittable")),
    ):
        present = _columns(table)
        for column in columns:
            if column in present:
                op.drop_column(table, column)
