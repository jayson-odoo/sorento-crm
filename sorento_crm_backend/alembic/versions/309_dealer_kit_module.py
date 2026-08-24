"""Dealer Kit module foundation - dealer_kit schema, RBAC, catalog row.

Creates the ``dealer_kit`` Postgres schema and its eight tables, adds two small
additive columns to public resource tables, seeds six permission slugs with an
explicit grant sweep, and registers the module in the App-Store catalog.

Cross-schema FKs (dealer_kit.* -> public.*) are normal Postgres FKs.

The two public columns are deliberately nullable and additive, so this migration
cannot break an existing row:
  * ``attachment_types.certification_logo_attachment_id`` - the badge artwork a
    product inherits by holding a document of that type.
  * ``attachments.valid_until`` - expiry lives on the DOCUMENT, so updating it
    once updates every product that holds it. It is also appended to
    ``Attachment.__audit_columns__`` in the model, without which expiry edits
    would be silently unaudited.

Revision ID: 309_dealer_kit_module
Revises: 307_admin_listing_company
Create Date: 2026-07-26

Numbered 309, not 308: another branch is concurrently adding
``308_status_engine``. ``down_revision`` still points at 307, which is a
COMMITTED head on this branch - chaining onto the other branch's in-flight
revision would be chaining onto WIP that may never land in this shape. The two
lines therefore fork on purpose, and whichever merges second resolves it with
``alembic merge``. Verify a single head after that merge; a fork fails the
deploy, not the test suite.
"""
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "309_dealer_kit_module"
down_revision = "307_admin_listing_company"
branch_labels = None
depends_on = None

SCHEMA = "dealer_kit"

# Six slugs. `edition.approve` is deliberately NOT implied by page.edit or
# page.publish: an Edition nobody else looked at must not be able to go live,
# so a Designer cannot approve their own (AC-A9).
_PERMS = [
    ("dealer_kit.page.view", "View catalogue pages", "View Dealer Kit catalogue pages and their versions."),
    ("dealer_kit.page.edit", "Edit catalogue pages", "Create and edit catalogue pages, and move the staging label."),
    ("dealer_kit.page.publish", "Publish catalogue pages", "Move the published label, including rolling back to an earlier version."),
    ("dealer_kit.library.manage", "Manage Dealer Kit library", "Manage assets, tile templates and reusable collections."),
    ("dealer_kit.brochure.create", "Create brochures", "Produce a brochure from an existing published page."),
    ("dealer_kit.edition.approve", "Approve catalogue editions", "Approve or reject a catalogue edition before it goes live."),
]

# Existing roles that must not silently lose access to a screen they should see
# (PRINCIPLES DoD #3). Marketing gets the authoring set; admins get everything.
# "superadmin" is the canonical constant (UserPermissionService.SUPERADMIN_ROLE_SLUG)
# and is listed for parity with the scm migration; it grants only if such a row
# exists. The marketing slugs are the REAL ones in this system - there is no bare
# "marketing" role, and naming one would have silently granted nothing, which is
# the exact failure AC-A5 exists to catch.
_GRANT_ALL_ROLES = ("superadmin", "admin")
_GRANT_MARKETING_ROLES = ("marketing_manager", "marketing_executive")
_MARKETING_SLUGS = {
    "dealer_kit.page.view",
    "dealer_kit.page.edit",
    "dealer_kit.page.publish",
    "dealer_kit.library.manage",
    "dealer_kit.brochure.create",
}


def _created_at():
    return sa.Column(
        "created_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False
    )


def _updated_at():
    return sa.Column(
        "updated_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False
    )


def _company_id():
    return sa.Column(
        "company_id", UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True
    )


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    # Table DDL is skipped when the schema is already populated. Concurrent
    # branch work means this schema can legitimately exist before the revision
    # runs (it was applied out of band while another branch held the alembic
    # chain), and a bare create_table would abort the whole upgrade on a table
    # that is already correct. RBAC and the catalog row below are ON CONFLICT
    # guarded and always run, so a partial state still converges.
    _existing = set(sa.inspect(op.get_bind()).get_table_names(schema=SCHEMA))
    if not _existing:
        _create_tables()

    _post_ddl()


def _create_tables() -> None:

    # ------------------------------------------------------------------ pages
    op.create_table(
        "page",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("print_profile", JSONB, nullable=True),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        _company_id(),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint("company_id", "slug", name="uq_dealer_kit_page_company_slug"),
        schema=SCHEMA,
    )
    op.create_index("ix_dealer_kit_page_company_id", "page", ["company_id"], schema=SCHEMA)

    op.create_table(
        "page_version",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "page_id",
            UUID(as_uuid=False),
            sa.ForeignKey(f"{SCHEMA}.page.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("doc", JSONB, nullable=False),
        sa.Column("commit_message", sa.Text(), nullable=True),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        _created_at(),
        sa.UniqueConstraint("page_id", "version", name="uq_dealer_kit_page_version"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dealer_kit_page_version_page_id", "page_version", ["page_id"], schema=SCHEMA
    )

    op.create_table(
        "page_label",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "page_id",
            UUID(as_uuid=False),
            sa.ForeignKey(f"{SCHEMA}.page.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(20), nullable=False),
        sa.Column(
            "version_id",
            UUID(as_uuid=False),
            sa.ForeignKey(f"{SCHEMA}.page_version.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("updated_by", UUID(as_uuid=False), nullable=True),
        _updated_at(),
        sa.UniqueConstraint("page_id", "label", name="uq_dealer_kit_page_label"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dealer_kit_page_label_page_id", "page_label", ["page_id"], schema=SCHEMA
    )

    # -------------------------------------------------------------- library
    op.create_table(
        "tile_template",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("doc", JSONB, nullable=False),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        _company_id(),
        _created_at(),
        _updated_at(),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dealer_kit_tile_template_company_id", "tile_template", ["company_id"], schema=SCHEMA
    )

    op.create_table(
        "asset",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "attachment_id",
            UUID(as_uuid=False),
            sa.ForeignKey("attachments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="decorative"),
        sa.Column("tags", ARRAY(sa.String()), nullable=True),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        _company_id(),
        _created_at(),
        _updated_at(),
        schema=SCHEMA,
    )
    op.create_index("ix_dealer_kit_asset_company_id", "asset", ["company_id"], schema=SCHEMA)
    op.create_index("ix_dealer_kit_asset_kind", "asset", ["kind"], schema=SCHEMA)

    # ---------------------------------------------------- collections/bundles
    op.create_table(
        "collection",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("scope", sa.String(20), nullable=False, server_default="page"),
        sa.Column(
            "page_id",
            UUID(as_uuid=False),
            sa.ForeignKey(f"{SCHEMA}.page.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("conditions_json", JSONB, nullable=True),
        sa.Column("pinned_product_ids", ARRAY(UUID(as_uuid=False)), nullable=True),
        sa.Column("excluded_product_ids", ARRAY(UUID(as_uuid=False)), nullable=True),
        sa.Column("manual_order", ARRAY(UUID(as_uuid=False)), nullable=True),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        _company_id(),
        _created_at(),
        _updated_at(),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dealer_kit_collection_company_id", "collection", ["company_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_dealer_kit_collection_page_id", "collection", ["page_id"], schema=SCHEMA
    )

    op.create_table(
        "bundle",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("price", sa.Numeric(15, 4), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        _company_id(),
        _created_at(),
        _updated_at(),
        schema=SCHEMA,
    )
    op.create_index("ix_dealer_kit_bundle_company_id", "bundle", ["company_id"], schema=SCHEMA)

    op.create_table(
        "bundle_component",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "bundle_id",
            UUID(as_uuid=False),
            sa.ForeignKey(f"{SCHEMA}.bundle.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(15, 4), nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("bundle_id", "product_id", name="uq_dealer_kit_bundle_component"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dealer_kit_bundle_component_bundle_id", "bundle_component", ["bundle_id"], schema=SCHEMA
    )


def _post_ddl() -> None:
    # ------------------------------------------------- additive public columns
    conn = op.get_bind()
    insp = sa.inspect(conn)

    at_cols = {c["name"] for c in insp.get_columns("attachment_types")}
    if "certification_logo_attachment_id" not in at_cols:
        op.add_column(
            "attachment_types",
            sa.Column(
                "certification_logo_attachment_id",
                UUID(as_uuid=False),
                sa.ForeignKey("attachments.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    a_cols = {c["name"] for c in insp.get_columns("attachments")}
    if "valid_until" not in a_cols:
        op.add_column("attachments", sa.Column("valid_until", sa.Date(), nullable=True))

    # ------------------------------------------------------------------- RBAC
    now = datetime.utcnow()
    perm_ids: dict[str, str] = {}

    for slug, name, desc in _PERMS:
        row = conn.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
        ).fetchone()
        if row is None:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO user_permissions (id, slug, name, description, created_at)
                    VALUES (:id, :slug, :name, :desc, :now)
                    ON CONFLICT (slug) DO NOTHING
                    """
                ),
                {"id": str(uuid.uuid4()), "slug": slug, "name": name, "desc": desc, "now": now},
            )
            row = conn.execute(
                sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
            ).fetchone()
        perm_ids[slug] = row.id

    def _grant(role_slugs, slugs):
        role_ids = [
            r.id
            for r in conn.execute(
                sa.text("SELECT id FROM user_roles WHERE slug = ANY(:slugs)"),
                {"slugs": list(role_slugs)},
            ).fetchall()
        ]
        for rid in role_ids:
            for slug in slugs:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
                        VALUES (:id, :r, :p, :now)
                        ON CONFLICT (role_id, permission_id) DO NOTHING
                        """
                    ),
                    {"id": str(uuid.uuid4()), "r": rid, "p": perm_ids[slug], "now": now},
                )

    _grant(_GRANT_ALL_ROLES, perm_ids.keys())
    _grant(_GRANT_MARKETING_ROLES, _MARKETING_SLUGS)

    # ------------------------------------------------------- App-Store catalog
    # Row present, no tenant_modules row: the module is installable but dormant,
    # exactly like scm shipped.
    conn.execute(
        sa.text(
            """
            INSERT INTO app_modules_catalog
                (id, module_key, display_name, description, sort_order, is_core, dependencies)
            VALUES (:id, 'dealer_kit', :name, :desc, :sort, false,
                    CAST(:deps AS jsonb))
            ON CONFLICT (module_key) DO NOTHING
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "name": "Dealer Sales Kit",
            "desc": "Catalogue page builder, product collections and brochure export.",
            # sort_order is VARCHAR(16) on this table, and dependencies is JSONB.
            "sort": "950",
            "deps": '["base", "product", "resources"]',
        },
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text("DELETE FROM app_modules_catalog WHERE module_key = 'dealer_kit'")
    )

    slugs = [slug for slug, _, _ in _PERMS]
    perm_ids = [
        r.id
        for r in conn.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = ANY(:s)"), {"s": slugs}
        ).fetchall()
    ]
    if perm_ids:
        conn.execute(
            sa.text("DELETE FROM user_role_permissions WHERE permission_id = ANY(:p)"),
            {"p": perm_ids},
        )
        conn.execute(
            sa.text("DELETE FROM user_permissions WHERE id = ANY(:p)"), {"p": perm_ids}
        )

    insp = sa.inspect(conn)
    a_cols = {c["name"] for c in insp.get_columns("attachments")}
    if "valid_until" in a_cols:
        op.drop_column("attachments", "valid_until")

    at_cols = {c["name"] for c in insp.get_columns("attachment_types")}
    if "certification_logo_attachment_id" in at_cols:
        op.drop_column("attachment_types", "certification_logo_attachment_id")

    # Dropping the schema takes every Dealer Kit table with it and leaves every
    # public row untouched - which is the uninstall test the module was designed
    # around (AC-A8).
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
