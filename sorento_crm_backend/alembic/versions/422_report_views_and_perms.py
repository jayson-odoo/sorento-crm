"""Saved report views, plus the two slugs the reporting foundation is gated on.

`report_views` holds a saved view: the filters, the detail columns and the pivot, under a
name. Personal by default; a holder of `reports.views.publish` can share one and mark one
shared view the default for everyone - so the database, not the code, enforces at most one
default per report (partial unique index) and one name per owner per report.

Grants are copied rather than invented, because a permission granted to nobody is
indistinguishable from a broken feature:

- `procurement.sponsorship_forms.report` goes to every role that may already SEE a
  sponsorship form. The report shows the same rows the listing does.
- `reports.views.publish` goes to every role that may EDIT one. Publishing a view changes
  what everybody else opens the page on, which is the same kind of authority.

Idempotent raw SQL, safe to re-run. The table creation is guarded by an existence check for
the same reason: the shared local database converges through `create_all` rather than through
migrations, so the table can already be there.

Revision ID: 422_report_views_and_perms
Revises: 421_merge_closeconvo_searchable
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "422_report_views_and_perms"
down_revision = "421_merge_closeconvo_searchable"
branch_labels = None
depends_on = None

# (slug, name, description, the slug whose holders inherit it)
_PERMS = (
    (
        "procurement.sponsorship_forms.report",
        "View Sponsorship Report",
        "Permission to open the Sponsorship report.",
        "procurement.sponsorship_forms.view",
    ),
    (
        "reports.views.publish",
        "Publish Report Views",
        "Permission to share a saved report view and set the default for everyone.",
        "procurement.sponsorship_forms.edit",
    ),
)


def _has_table(bind, table: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name = :t"
            ),
            {"t": table},
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "report_views"):
        op.create_table(
            "report_views",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("report_key", sa.Text(), nullable=False),
            sa.Column(
                "owner_user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("view", postgresql.JSONB(), nullable=False),
            sa.Column(
                "is_shared", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
            sa.Column(
                "is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
            sa.Column(
                "created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
            ),
            sa.UniqueConstraint(
                "report_key", "owner_user_id", "name", name="uq_report_views_owner_name"
            ),
        )
        op.create_index("ix_report_views_report_key", "report_views", ["report_key"])
        # At most one default per report, enforced where it cannot be forgotten.
        op.create_index(
            "uq_report_views_one_default",
            "report_views",
            ["report_key"],
            unique=True,
            postgresql_where=sa.text("is_default"),
        )

    for slug, name, descr, source in _PERMS:
        bind.execute(
            sa.text(
                """
                INSERT INTO user_permissions (id, slug, name, description, created_at)
                SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
                WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
                """
            ),
            {"slug": slug, "name": name, "descr": descr},
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
                SELECT gen_random_uuid()::text, urp.role_id, tgt.id, now()
                  FROM user_role_permissions urp
                  JOIN user_permissions src ON src.id = urp.permission_id
                 CROSS JOIN user_permissions tgt
                 WHERE src.slug = :source_slug
                   AND tgt.slug = :slug
                   AND NOT EXISTS (
                       SELECT 1
                         FROM user_role_permissions existing
                        WHERE existing.role_id = urp.role_id
                          AND existing.permission_id = tgt.id
                   )
                """
            ),
            {"source_slug": source, "slug": slug},
        )


def downgrade() -> None:
    bind = op.get_bind()

    for slug, _name, _descr, _source in _PERMS:
        bind.execute(
            sa.text(
                """
                DELETE FROM user_role_permissions
                 WHERE permission_id IN (SELECT id FROM user_permissions WHERE slug = :slug)
                """
            ),
            {"slug": slug},
        )
        bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": slug})

    if _has_table(bind, "report_views"):
        op.drop_table("report_views")
