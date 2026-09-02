"""Saved views (segments), plus the publish slug S4 gates on.

`saved_views` holds a saved view of a LISTING (not a report): its filters, sort and
column layout, under a name, keyed by the same `listing_key` the column-config
personalization endpoints already use. Generalised from `report_views`
(422_report_views_and_perms) - see `app/models/saved_view.py` for what changed and why.

Personal by default; a holder of `list_query.saved_views.publish` can share one and mark
one shared view the default for everyone within a listing key - so the database, not the
code, enforces at most one default per listing key (partial unique index) and one name
per owner per listing key.

The publish grant is copied from `scm.recommendation.manage` rather than invented,
because a permission granted to nobody is indistinguishable from a broken feature, and
the reorder plan grid (the first consumer, PLAN-scm-reorder-oi-feedback-1sep.md S4) is
edited by whoever already holds that slug.

Idempotent raw SQL, safe to re-run. The table creation is guarded by an existence check
for the same reason 422 guards `report_views`: the shared local database converges
through `create_all` rather than through migrations, so the table can already be there.

Chains onto 454_order_inquiry_born_ack (PR #471), not 453_shared_brand_attach directly:
both this migration and #471 were authored on top of 453, and #471 is declared to merge
first in the 1 Sep batch order, so this revision was renumbered 454 -> 455 and rechained
to avoid two heads on main the moment both land.

S1 (PR #489 review round, captain ruling pending confirm 2 Sep): `saved_views` gained
`company_id` (`CompanyScopedMixin`, `app/models/saved_view.py`) after this migration was
first written - a shared/published view's filters can name another company's suppliers,
products or warehouses, and the listing key alone does not stop that from crossing a
company boundary. Added additively (nullable, indexed, FK to `companies`) rather than
rewritten, and backfilled to the incumbent company for the ADD-COLUMN branch, the same
shape migration 320 (`app/services/company_scope.py:DEFAULT_COMPANY_ID`) established -
the CREATE-TABLE branch below never needs a backfill because it starts empty.

Revision ID: 455_saved_views_and_perms
Revises: 454_order_inquiry_born_ack
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "455_saved_views_and_perms"
down_revision = "454_order_inquiry_born_ack"
branch_labels = None
depends_on = None

# The incumbent company (Sorento) - see `app/services/company_scope.py`.
_DEFAULT_COMPANY_ID = "00000000-0000-0000-0000-000000000001"

# (slug, name, description, the slug whose holders inherit it)
_PERMS = (
    (
        "list_query.saved_views.publish",
        "Publish Saved Views",
        "Permission to share a saved listing view (segment) and set the default for everyone.",
        "scm.recommendation.manage",
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


def _has_column(bind, table: str, column: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "saved_views"):
        op.create_table(
            "saved_views",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("listing_key", sa.Text(), nullable=False),
            sa.Column(
                "owner_user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("view", postgresql.JSONB(), nullable=False),
            sa.Column(
                "company_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("companies.id"),
                nullable=True,
            ),
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
                "listing_key", "owner_user_id", "name", name="uq_saved_views_owner_name"
            ),
        )
        op.create_index("ix_saved_views_listing_key", "saved_views", ["listing_key"])
        op.create_index("ix_saved_views_company_id", "saved_views", ["company_id"])
        # At most one default per listing key, enforced where it cannot be forgotten.
        op.create_index(
            "uq_saved_views_one_default",
            "saved_views",
            ["listing_key"],
            unique=True,
            postgresql_where=sa.text("is_default"),
        )
    elif not _has_column(bind, "saved_views", "company_id"):
        # The table already exists (the shared local database converges through
        # `create_all`, not through this migration - see `sorento_crm_backend/CLAUDE.md`)
        # but predates S1's `company_id` column. Added additively and backfilled to the
        # incumbent company (S1's module docstring above), rather than dropped and
        # recreated, so a saved view nobody has touched yet is not silently discarded.
        op.add_column(
            "saved_views",
            sa.Column("company_id", postgresql.UUID(as_uuid=False), nullable=True),
        )
        op.create_foreign_key(
            "saved_views_company_id_fkey", "saved_views", "companies", ["company_id"], ["id"]
        )
        op.create_index("ix_saved_views_company_id", "saved_views", ["company_id"])
        bind.execute(
            sa.text("UPDATE saved_views SET company_id = :c WHERE company_id IS NULL"),
            {"c": _DEFAULT_COMPANY_ID},
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

    if _has_table(bind, "saved_views"):
        op.drop_table("saved_views")
