"""dealer kit: tag template immutable versions + published pointer (PLAN D7)

Two tables become one table plus one pointer column, mirroring
``ai_prompt.AIPromptVersion``/``AIPromptLabel`` and this schema's own
``Page``/``PageVersion``:

* ``tag_template_version`` - immutable, append-only snapshot per
  ``(template_id, version_no)``. Publish writes ``max(version_no) + 1``; a
  version row is never edited in place, which is what makes View and Restore
  free - the older document is still there.
* ``tag_template.published_version_id`` - the movable pointer. Publish
  repoints it; Unpublish sets it NULL. The editor's own ``doc``/``print_size``
  columns stay the DRAFT throughout and are never touched by either.

The backfill makes every existing template immediately visible to the request
designer once ``PR#478``'s resolution ships filtering on the pointer: each row
gets a v1 snapshot of its current doc/print_size and the pointer moves to it,
so nothing that already renders on a tag sheet goes dark the moment this lands.

Guarded like ``453_shared_brand_attach``: the shared local Postgres converges
through ``Base.metadata.create_all``, not ``alembic upgrade``, so this DDL was
hand-applied there already with ``alembic_version`` stuck on ``ptag_0003`` -
every step below probes ``information_schema``/``pg_indexes`` first and the
backfill INSERT is a ``WHERE NOT EXISTS``, so replaying this migration on that
database (or re-running it anywhere) is a no-op.

Revision ID: 454_tag_template_versions
Revises: 453_shared_brand_attach
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "454_tag_template_versions"
down_revision = "453_shared_brand_attach"
branch_labels = None
depends_on = None

SCHEMA = "dealer_kit"


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :s AND table_name = :t"
            ),
            {"s": SCHEMA, "t": table},
        ).first()
    )


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = :t"
            ),
            {"s": SCHEMA, "t": table},
        )
    }


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.table_constraints "
                "WHERE constraint_schema = :s AND constraint_name = :n"
            ),
            {"s": SCHEMA, "n": name},
        ).first()
    )


def _index_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_indexes WHERE schemaname = :s AND indexname = :n"),
            {"s": SCHEMA, "n": name},
        ).first()
    )


def upgrade() -> None:
    if not _table_exists("tag_template_version"):
        op.create_table(
            "tag_template_version",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("template_id", UUID(as_uuid=False), nullable=False),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("doc", JSONB(), nullable=False),
            sa.Column(
                "print_size", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
            ),
            sa.Column("note", sa.String(500), nullable=True),
            # String, not UUID - ``users.id`` is TEXT, and a UUID-typed column
            # cannot join to it without an explicit cast (see the model docstring).
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["template_id"], [f"{SCHEMA}.tag_template.id"], ondelete="CASCADE"
            ),
            sa.UniqueConstraint(
                "template_id", "version_no", name="uq_dealer_kit_tag_template_version"
            ),
            schema=SCHEMA,
        )

    if not _index_exists("ix_dealer_kit_tag_template_version_template_id"):
        op.create_index(
            "ix_dealer_kit_tag_template_version_template_id",
            "tag_template_version",
            ["template_id"],
            schema=SCHEMA,
        )

    if "published_version_id" not in _columns("tag_template"):
        op.add_column(
            "tag_template",
            sa.Column("published_version_id", UUID(as_uuid=False), nullable=True),
            schema=SCHEMA,
        )

    if not _constraint_exists("fk_dealer_kit_tag_template_published_version"):
        op.create_foreign_key(
            "fk_dealer_kit_tag_template_published_version",
            "tag_template",
            "tag_template_version",
            ["published_version_id"],
            ["id"],
            source_schema=SCHEMA,
            referent_schema=SCHEMA,
            ondelete="SET NULL",
        )

    # Backfill: every existing template becomes v1, published - no live outage
    # for request design (AC-S5-4). ``WHERE NOT EXISTS`` makes a second run a
    # no-op instead of a duplicate-version-number error.
    op.execute(
        f"""
        INSERT INTO {SCHEMA}.tag_template_version
            (id, template_id, version_no, doc, print_size, note, created_by, created_at)
        SELECT gen_random_uuid(), t.id, 1, t.doc, t.print_size, NULL, t.created_by, now()
        FROM {SCHEMA}.tag_template AS t
        WHERE NOT EXISTS (
            SELECT 1 FROM {SCHEMA}.tag_template_version AS v
            WHERE v.template_id = t.id AND v.version_no = 1
        )
        """
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}.tag_template AS t
        SET published_version_id = v.id
        FROM {SCHEMA}.tag_template_version AS v
        WHERE v.template_id = t.id AND v.version_no = 1 AND t.published_version_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_dealer_kit_tag_template_published_version",
        "tag_template",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_column("tag_template", "published_version_id", schema=SCHEMA)
    op.drop_index(
        "ix_dealer_kit_tag_template_version_template_id",
        table_name="tag_template_version",
        schema=SCHEMA,
    )
    op.drop_table("tag_template_version", schema=SCHEMA)
