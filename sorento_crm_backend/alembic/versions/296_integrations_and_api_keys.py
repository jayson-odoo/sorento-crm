"""Integration counterparty records and per-integration API keys

Replaces the single shared EXTERNAL_API_KEY env var with first-class records.
Today that one static secret is shared by n8n and the MCP server, compared with
a plain `!=` in app/dependencies.py, on a dependency that applies no permission
check at all -- an inadequate trust boundary for a caller that will write master
data and raise purchase orders.

Schema only. Seeding the legacy key, creating the integration users/roles and
retiring the env fallback happen in a later migration in this group, so that a
failure here rolls back without touching live authentication.

`integrations.act_as_user_id` is nullable in this revision: the users it points
at are created by the seed migration that follows. It is tightened once those
rows exist.

Deliberately NO scopes column. Sorento already has 230 permission slugs and
require_permission_with_api_key; a second authorization vocabulary beside a
working one produces disagreements nobody spots at review.

Revision ID: 296_integrations_and_api_keys
Revises: 294_chat_latency_percentile
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "296_integrations_and_api_keys"
down_revision = "294_chat_latency_percentile"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "integrations" not in existing_tables:
        op.create_table(
            "integrations",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("type", sa.String(50), nullable=False),
            # UNVERIFIED until a call actually succeeds. A fresh row has proven
            # nothing; defaulting to ACTIVE would misreport health.
            sa.Column(
                "status", sa.String(20), nullable=False, server_default="UNVERIFIED"
            ),
            # The real users row this integration acts as, so every write it
            # makes is attributable. Replaces the fake {"id": "system"}.
            # RESTRICT: deleting the principal out from under a live integration
            # would silently break authentication rather than fail loudly.
            sa.Column(
                "act_as_user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=True,
            ),
            # Non-secret and displayable (ESB base URL, AutoCount company code).
            sa.Column("config_json", postgresql.JSONB(), nullable=True),
            # Fernet ciphertext, write-only over the API, never echoed by a read
            # endpoint. Empty for inbound-only integrations such as n8n.
            sa.Column("credentials_json", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("last_used_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint("name", name="uq_integrations_name"),
        )
        op.create_index("ix_integrations_type", "integrations", ["type"])
        op.create_index("ix_integrations_is_active", "integrations", ["is_active"])

    if "integration_api_keys" not in existing_tables:
        op.create_table(
            "integration_api_keys",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column(
                "integration_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("integrations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            # Hex SHA-256 of the key. The plaintext is shown once at creation and
            # never persisted anywhere.
            sa.Column("key_hash", sa.String(64), nullable=False),
            # Short non-secret fragment, shown in the UI to tell keys apart.
            sa.Column("key_prefix", sa.String(16), nullable=False),
            # Both null on a freshly issued key: it lives until rotated or
            # revoked. A default expiry would silently kill untouched integrations.
            sa.Column("expires_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column(
                "rotated_from_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("integration_api_keys.id", ondelete="SET NULL"),
                nullable=True,
            ),
            # Lets an admin confirm the caller actually migrated before the grace
            # window closes. Without it, rotation is a coin flip.
            sa.Column("last_used_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            # Unique because verification is a single indexed lookup on this
            # column; a collision would make the caller's identity ambiguous.
            sa.UniqueConstraint("key_hash", name="uq_integration_api_keys_key_hash"),
        )
        op.create_index(
            "ix_integration_api_keys_integration_id",
            "integration_api_keys",
            ["integration_id"],
        )

    user_columns = {c["name"] for c in inspector.get_columns("users")}
    if "is_integration" not in user_columns:
        # Deliberately not is_protected: that flag already selects notification
        # recipients in automation_service.py, so reusing it would enrol every
        # integration principal into automation email.
        op.add_column(
            "users",
            sa.Column(
                "is_integration",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "is_integration" in {c["name"] for c in inspector.get_columns("users")}:
        op.drop_column("users", "is_integration")

    existing_tables = set(inspector.get_table_names())
    if "integration_api_keys" in existing_tables:
        op.drop_index(
            "ix_integration_api_keys_integration_id", table_name="integration_api_keys"
        )
        op.drop_table("integration_api_keys")
    if "integrations" in existing_tables:
        op.drop_index("ix_integrations_is_active", table_name="integrations")
        op.drop_index("ix_integrations_type", table_name="integrations")
        op.drop_table("integrations")
