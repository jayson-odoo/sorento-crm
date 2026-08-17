"""Onboarding intake, review and CRM-user provisioning (Slice 1).

Creates the three tables, seeds the ``onboarding_request`` status graph, seeds
the header aliases the phone-list reader resolves against, and creates the five
permissions - granting them to whoever can already add or edit a user, because a
permission granted to nobody is indistinguishable from a broken feature.

**This is also the merge point.** The branch started from TWO alembic heads,
``323_cs_company_backfill`` and ``356_human_source_boost_seed``, so
``down_revision`` is the tuple of both: the graph is left with a single head and
``alembic upgrade head`` works again.

Idempotent throughout (``IF NOT EXISTS`` / SELECT-then-INSERT). The dev database
is shared across worktrees, so a table or a status this migration wants may
already be there from another branch, and a migration that fell over on that
would block every lane.

Revision ID: 360_onboarding_slice1
Revises: 323_cs_company_backfill, 356_human_source_boost_seed
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "360_onboarding_slice1"
down_revision = ("323_cs_company_backfill", "356_human_source_boost_seed")
branch_labels = None
depends_on = None


ENTITY = "onboarding_request"

# (key, label, sort, is_initial, is_terminal, category, colour)
_STATUSES = [
    ("draft", "Draft", 10, True, False, "open", "#94a3b8"),
    ("sent", "Link sent", 20, False, False, "open", "#3b82f6"),
    ("submitted", "Submitted", 30, False, False, "open", "#0ea5e9"),
    ("in_review", "In review", 40, False, False, "open", "#f59e0b"),
    ("processing", "Provisioning", 50, False, False, "open", "#8b5cf6"),
    ("completed", "Completed", 60, False, True, "closed", "#16a34a"),
    # Terminal and NOT an error: some lanes failed, the rest landed. Named as a
    # state of its own so "did this batch finish cleanly" is answerable without
    # walking every person row.
    ("partially_completed", "Completed with failures", 70, False, True, "closed", "#f97316"),
    ("rejected", "Rejected", 80, False, True, "closed", "#ef4444"),
    ("cancelled", "Cancelled", 90, False, True, "closed", "#6b7280"),
]

# (from_key, to_key, label, sort)
_EDGES = [
    ("draft", "sent", "Send the intake link", 10),
    ("sent", "submitted", "Requester submits", 20),
    ("submitted", "in_review", "Start review", 30),
    ("in_review", "processing", "Approve and provision", 40),
    ("processing", "completed", "All lanes landed", 50),
    ("processing", "partially_completed", "Some lanes failed", 60),
    ("in_review", "rejected", "Reject the batch", 70),
    ("draft", "cancelled", "Cancel", 80),
    ("sent", "cancelled", "Cancel", 81),
    ("submitted", "cancelled", "Cancel", 82),
    ("in_review", "cancelled", "Cancel", 83),
]

DOC_TYPE = "onboarding_person"

#: The header spellings a staff phone list actually uses. A client whose sheet
#: says something else is an INSERT here, not a release.
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
    ("email", "E-MAIL"),
]

_VIEW = "user_management.onboarding.view"
_ADD = "user_management.onboarding.add"
_EDIT = "user_management.onboarding.edit"
_DELETE = "user_management.onboarding.delete"
_APPROVE = "user_management.onboarding.approve"

#: (slug, name, description, slug whose holders inherit it)
_PERMISSIONS = [
    (
        _VIEW,
        "View Onboarding Requests",
        "See onboarding requests, the people submitted against them, and their provisioning state.",
        "user_management.users.view",
    ),
    (
        _ADD,
        "Create Onboarding Requests",
        "Create an onboarding request and send its intake link to a requester.",
        "user_management.users.add",
    ),
    (
        _EDIT,
        "Edit Onboarding Requests",
        "Edit submitted people, reject individual rows, and manage onboarding access templates.",
        "user_management.users.edit",
    ),
    (
        _DELETE,
        "Delete Onboarding Requests",
        "Permanently delete an onboarding request and everyone submitted against it.",
        "user_management.users.delete",
    ),
    (
        # Deliberately its own slug rather than riding `.edit`: approving is what
        # creates real users with real access, and it is the Edition-approval
        # convention that the person who reviews is not automatically the person
        # who signs off.
        _APPROVE,
        "Approve Onboarding Requests",
        "Approve a reviewed onboarding request, which queues provisioning for every approved person.",
        "user_management.users.edit",
    ),
]


def _created_at():
    return sa.Column(
        "created_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False
    )


def _updated_at():
    return sa.Column(
        "updated_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "onboarding_templates" not in existing:
        op.create_table(
            "onboarding_templates",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("role_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("company_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column(
                "access_agent_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
            ),
            sa.Column(
                "default_needs_system_account",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "default_needs_respond_contact",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "default_needs_agent_seat",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("captured_from_user_id", sa.String(64), nullable=True),
            sa.Column("created_by_user_id", sa.String(64), nullable=True),
            sa.Column(
                "company_id",
                UUID(as_uuid=False),
                sa.ForeignKey("companies.id"),
                nullable=True,
            ),
            _created_at(),
            _updated_at(),
        )

    # One label per company: two "Salesperson" templates is how a captain picks
    # the wrong one at review and grants access nobody meant to grant.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_onboarding_templates_company_name "
        "ON onboarding_templates (company_id, lower(btrim(name)))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_onboarding_templates_company_active "
        "ON onboarding_templates (company_id, is_active)"
    )

    if "onboarding_requests" not in existing:
        op.create_table(
            "onboarding_requests",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("requester_name", sa.String(150), nullable=False),
            sa.Column("requester_email", sa.String(255), nullable=False),
            sa.Column("requester_phone", sa.String(32), nullable=True),
            sa.Column("token", sa.String(64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=False), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column(
                "status_id", UUID(as_uuid=False), sa.ForeignKey("statuses.id"), nullable=False
            ),
            sa.Column("status_key", sa.String(64), nullable=False),
            sa.Column("requester_note", sa.Text(), nullable=True),
            sa.Column("reviewer_note", sa.Text(), nullable=True),
            sa.Column("created_by_user_id", sa.String(64), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("reviewed_by_user_id", sa.String(64), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("provisioned_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("source_file_name", sa.String(255), nullable=True),
            sa.Column("source_storage_provider", sa.String(16), nullable=True),
            sa.Column("source_storage_key", sa.Text(), nullable=True),
            # NOT NULL: a request whose company nobody chose cannot be
            # provisioned, because company grants and team routing both need one.
            sa.Column(
                "company_id",
                UUID(as_uuid=False),
                sa.ForeignKey("companies.id"),
                nullable=False,
            ),
            _created_at(),
            _updated_at(),
        )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_onboarding_requests_company_status "
        "ON onboarding_requests (company_id, status_key)"
    )

    if "onboarding_people" not in existing:
        op.create_table(
            "onboarding_people",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column(
                "request_id",
                UUID(as_uuid=False),
                sa.ForeignKey("onboarding_requests.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("full_name", sa.String(200), nullable=False),
            sa.Column("nick_name", sa.String(100), nullable=True),
            sa.Column("phone_raw", sa.String(64), nullable=True),
            sa.Column("phone", sa.String(32), nullable=True),
            sa.Column("email_raw", sa.String(255), nullable=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("section_label", sa.String(120), nullable=True),
            sa.Column(
                "template_id",
                UUID(as_uuid=False),
                sa.ForeignKey("onboarding_templates.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("requester_note", sa.Text(), nullable=True),
            sa.Column("reviewer_note", sa.Text(), nullable=True),
            sa.Column(
                "needs_system_account",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "needs_respond_contact",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "needs_agent_seat", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
            sa.Column(
                "review_status", sa.String(20), nullable=False, server_default=sa.text("'proposed'")
            ),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            # `users.id` is a String column, not UUID: a UUID FK here fails to
            # create with "incompatible types: uuid and character varying".
            sa.Column(
                "user_id",
                sa.String(64),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            # VARCHAR rather than a PG enum: Slices 2 and 3 add values to the
            # contact and agent lanes, and adding a value to an enum inside a
            # migration transaction is the migration that goes wrong.
            sa.Column(
                "user_step", sa.String(20), nullable=False, server_default=sa.text("'pending'")
            ),
            sa.Column("user_error", sa.Text(), nullable=True),
            sa.Column("respond_contact_id", UUID(as_uuid=False), nullable=True),
            sa.Column(
                "contact_step", sa.String(20), nullable=False, server_default=sa.text("'pending'")
            ),
            sa.Column("contact_error", sa.Text(), nullable=True),
            sa.Column("linked_respond_user_id", sa.String(64), nullable=True),
            sa.Column(
                "agent_step", sa.String(20), nullable=False, server_default=sa.text("'pending'")
            ),
            sa.Column("agent_error", sa.Text(), nullable=True),
            sa.Column("invite_marked_sent_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("provisioned_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column(
                "company_id",
                UUID(as_uuid=False),
                sa.ForeignKey("companies.id"),
                nullable=True,
            ),
            _created_at(),
            _updated_at(),
            sa.UniqueConstraint(
                "request_id", "row_number", name="uq_onboarding_people_request_row"
            ),
        )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_onboarding_people_request_review "
        "ON onboarding_people (request_id, review_status)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_onboarding_people_email ON onboarding_people (email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_onboarding_people_phone ON onboarding_people (phone)")

    _seed_graph(bind)
    _mark_system(bind)
    _seed_aliases(bind)
    _seed_permissions(bind)


def _mark_system(bind) -> None:
    """Freeze the status keys the service reads by name.

    `update_status` freezes the key only on system rows, so without this an
    admin renaming "sent" in the status UI bricks the workflow - and the 500 it
    produces blames the seed rather than the rename.

    Set by entity_type rather than inside the seed loop, because the seed is
    skip-if-present and therefore cannot correct a row another branch inserted.
    """
    bind.execute(
        sa.text(
            "UPDATE statuses SET is_system = true "
            "WHERE entity_type = :et AND scope_id IS NULL AND is_system = false"
        ),
        {"et": ENTITY},
    )


def _seed_graph(bind) -> None:
    """Insert the graph, skipping whatever is already there.

    Keyed on ``(entity_type, key)`` with ``scope_id IS NULL`` - the default
    graph. A fork belongs to a scope and is somebody's deliberate override, so
    this never touches one.
    """
    ids: dict[str, str] = {}

    for key, label, sort, initial, terminal, category, colour in _STATUSES:
        existing = bind.execute(
            sa.text(
                "SELECT id FROM statuses "
                "WHERE entity_type = :et AND key = :key AND scope_id IS NULL"
            ),
            {"et": ENTITY, "key": key},
        ).scalar()
        if existing:
            ids[key] = existing
            continue

        new_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO statuses "
                "(id, entity_type, key, label, category, color_hex, sort_order, "
                " is_initial, is_terminal, is_active, is_archived, is_default, is_system) "
                "VALUES (:id, :et, :key, :label, :cat, :colour, :sort, "
                " :initial, :terminal, true, false, :initial, true)"
            ),
            {
                "id": new_id,
                "et": ENTITY,
                "key": key,
                "label": label,
                "cat": category,
                "colour": colour,
                "sort": sort,
                "initial": initial,
                "terminal": terminal,
            },
        )
        ids[key] = new_id

    for from_key, to_key, label, sort in _EDGES:
        from_id, to_id = ids.get(from_key), ids.get(to_key)
        if not from_id or not to_id:  # pragma: no cover - both seeded above
            continue
        already = bind.execute(
            sa.text(
                "SELECT 1 FROM status_transitions "
                "WHERE entity_type = :et AND from_status_id = :f AND to_status_id = :t "
                "AND scope_id IS NULL"
            ),
            {"et": ENTITY, "f": from_id, "t": to_id},
        ).scalar()
        if already:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO status_transitions "
                "(id, entity_type, from_status_id, to_status_id, label, sort_order, trigger_mode) "
                "VALUES (:id, :et, :f, :t, :label, :sort, 'manual')"
            ),
            {
                "id": str(uuid.uuid4()),
                "et": ENTITY,
                "f": from_id,
                "t": to_id,
                "label": label,
                "sort": sort,
            },
        )


def _seed_aliases(bind) -> None:
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


def _seed_permissions(bind) -> None:
    """Create the slugs and grant them to whoever already holds the equivalent.

    The registry sync creates permission rows at startup, but a fresh deploy runs
    migrations BEFORE the app starts, and a permission held by no role hides the
    whole feature - including from the admins it was built for.
    """
    for slug, name, description, inherit_from in _PERMISSIONS:
        bind.execute(
            sa.text(
                """
                INSERT INTO user_permissions (id, slug, name, description, created_at)
                SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
                WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
                """
            ),
            {"slug": slug, "name": name, "descr": description},
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
                SELECT gen_random_uuid()::text, rp.role_id, tgt.id, now()
                FROM user_role_permissions rp
                JOIN user_permissions src ON src.id = rp.permission_id AND src.slug = :src
                CROSS JOIN user_permissions tgt
                WHERE tgt.slug = :tgt
                ON CONFLICT (role_id, permission_id) DO NOTHING
                """
            ),
            {"src": inherit_from, "tgt": slug},
        )


def downgrade() -> None:
    bind = op.get_bind()
    # Children first throughout: people reference requests and templates, the
    # graph edges reference the statuses, the grants reference the permissions.
    op.execute("DROP TABLE IF EXISTS onboarding_people CASCADE")
    op.execute("DROP TABLE IF EXISTS onboarding_requests CASCADE")
    op.execute("DROP TABLE IF EXISTS onboarding_templates CASCADE")
    op.execute(f"DELETE FROM status_transitions WHERE entity_type = '{ENTITY}'")
    op.execute(f"DELETE FROM statuses WHERE entity_type = '{ENTITY}'")
    bind.execute(
        sa.text("DELETE FROM import_field_alias WHERE doc_type = :doc"), {"doc": DOC_TYPE}
    )
    slugs = [slug for slug, _, _, _ in _PERMISSIONS]
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = ANY(:slugs))"
        ),
        {"slugs": slugs},
    )
    bind.execute(
        sa.text("DELETE FROM user_permissions WHERE slug = ANY(:slugs)"), {"slugs": slugs}
    )
