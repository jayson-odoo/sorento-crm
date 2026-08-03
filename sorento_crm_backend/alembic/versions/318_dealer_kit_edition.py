"""dealer_kit.edition plus its status graph (S2.5.1).

The Edition rides the CORE status engine (AC-L1), so this migration seeds a
``dealer_kit_edition`` graph rather than adding an enum column. Five statuses,
six edges, all manual.

**``done`` is terminal and there is no reopen edge.** AC-L8 originally asked for
``done -> draft``; that was withdrawn on 2026-08-03 because its real worry - the
live catalogue must not vanish when a revision starts - is already answered by
AC-L9, which duplicates a finished Edition into a NEW one at ``draft`` while the
old one keeps the ``published`` label.

**``approved -> pending_approval`` exists and is deliberately blunt.** AC-L4/L5
wanted price-only edits to keep an approval alive. That is deferred (the document
stores no prices, so an Edition cannot detect a price change by diffing its own
versions), so for now ANY edit to an approved Edition sends it back. Stricter
than the AC, and it cannot ship a silently altered catalogue.

Idempotent throughout. The dev database is shared across worktrees, and the
statuses table already carries graphs seeded from another branch, so every insert
is ON CONFLICT guarded and the DDL is skipped when the table already exists.
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "318_dealer_kit_edition"
down_revision = "317_attachment_dealer_kit_asset"
branch_labels = None
depends_on = None

SCHEMA = "dealer_kit"
ENTITY = "dealer_kit_edition"

# (key, label, sort, is_initial, is_terminal, category, colour)
_STATUSES = [
    ("draft", "Draft", 10, True, False, "open", "#94a3b8"),
    ("pending_approval", "Pending approval", 20, False, False, "open", "#f59e0b"),
    ("approved", "Approved", 30, False, False, "open", "#3b82f6"),
    ("rejected", "Rejected", 40, False, False, "open", "#ef4444"),
    ("done", "Done", 50, False, True, "closed", "#16a34a"),
]

# (from_key, to_key, label, sort)
_EDGES = [
    ("draft", "pending_approval", "Send for approval", 10),
    ("pending_approval", "approved", "Approve", 20),
    ("pending_approval", "rejected", "Reject", 30),
    # The Designer picking rejected work back up. `rejected` is a state rather
    # than an event so the reason survives on screen until they act on it.
    ("rejected", "draft", "Reopen for editing", 40),
    ("approved", "done", "Publish", 50),
    # Any edit to an approved Edition. Blunt on purpose - see the module note.
    ("approved", "pending_approval", "Re-submit after changes", 60),
]

# The open states, matching the model's partial unique index. Named rather than
# derived as "not done" so a status added later has to be classified on purpose.
_OPEN_KEYS = ("draft", "pending_approval", "approved", "rejected")


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

    existing = set(sa.inspect(bind).get_table_names(schema=SCHEMA))
    if "edition" not in existing:
        op.create_table(
            "edition",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column(
                "page_id",
                UUID(as_uuid=False),
                sa.ForeignKey(f"{SCHEMA}.page.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column(
                "status_id",
                UUID(as_uuid=False),
                sa.ForeignKey("statuses.id"),
                nullable=False,
            ),
            # Denormalised so the partial unique index below can be expressed:
            # a partial index cannot reach through a foreign key.
            sa.Column("status_key", sa.String(64), nullable=False),
            sa.Column(
                "approved_version_id",
                UUID(as_uuid=False),
                sa.ForeignKey(f"{SCHEMA}.page_version.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "done_version_id",
                UUID(as_uuid=False),
                sa.ForeignKey(f"{SCHEMA}.page_version.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "previous_edition_id",
                UUID(as_uuid=False),
                sa.ForeignKey(f"{SCHEMA}.edition.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("submitted_by", UUID(as_uuid=False), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("approved_by", UUID(as_uuid=False), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            sa.Column("created_by", UUID(as_uuid=False), nullable=True),
            _created_at(),
            _updated_at(),
            sa.Column(
                "company_id",
                UUID(as_uuid=False),
                sa.ForeignKey("companies.id"),
                nullable=True,
            ),
            schema=SCHEMA,
        )

    open_list = ", ".join(f"'{key}'" for key in _OPEN_KEYS)
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS uq_dealer_kit_edition_one_open_per_page "
        f"ON {SCHEMA}.edition (page_id) WHERE status_key IN ({open_list})"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_dealer_kit_edition_company_page "
        f"ON {SCHEMA}.edition (company_id, page_id)"
    )

    _seed_graph(bind)


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
                " is_initial, is_terminal, is_active, is_archived, is_default) "
                "VALUES (:id, :et, :key, :label, :cat, :colour, :sort, "
                " :initial, :terminal, true, false, :initial)"
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
                "(id, entity_type, from_status_id, to_status_id, label, sort_order, "
                " trigger_mode) "
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


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.edition CASCADE")
    # Edges first: they reference the statuses by FK.
    op.execute(f"DELETE FROM status_transitions WHERE entity_type = '{ENTITY}'")
    op.execute(f"DELETE FROM statuses WHERE entity_type = '{ENTITY}'")
