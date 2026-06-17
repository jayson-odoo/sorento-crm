"""User <-> RespondContact link + per-channel notification prefs + unique phone.

Adds:
- users.respond_contact_id  (nullable FK -> respond_contacts.id, ON DELETE SET NULL)
- users.notify_whatsapp           (bool, default false)  -- escalation + assignment pings
- users.notify_whatsapp_summary   (bool, default false)  -- daily summary template

Normalises existing users.contact_number to E.164 digits (MY) and adds a UNIQUE
constraint on it. If two users normalise to the same number the migration FAILS
LOUDLY so the collision is resolved by hand (we will not silently drop a phone).

Revision ID: 234_user_respond_contact_link_prefs
Revises: 233_attachment_type_is_direct_access
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa


revision = "234_user_respond_contact_link_prefs"
down_revision = "233_attachment_type_is_direct_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("respond_contact_id", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column("notify_whatsapp", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "users",
        sa.Column("notify_whatsapp_summary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # Normalise existing phone numbers, detecting collisions before writing.
    from app.services.phone_utils import normalize_msisdn

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, contact_number FROM users WHERE contact_number IS NOT NULL AND contact_number <> ''")
    ).fetchall()
    seen: dict[str, str] = {}
    norm_map: dict[str, str] = {}
    collisions: list[tuple[str, str, str]] = []
    for r in rows:
        n = normalize_msisdn(r.contact_number)
        if not n:
            continue
        if n in seen and seen[n] != r.id:
            collisions.append((n, seen[n], r.id))
        seen[n] = r.id
        norm_map[r.id] = n
    if collisions:
        raise RuntimeError(
            "users.contact_number collisions after E.164 normalisation "
            f"(number, user_a, user_b): {collisions}. Resolve duplicates before migrating."
        )
    for uid, n in norm_map.items():
        conn.execute(sa.text("UPDATE users SET contact_number = :n WHERE id = :id"), {"n": n, "id": uid})

    op.create_index("ix_users_respond_contact_id", "users", ["respond_contact_id"])
    op.create_foreign_key(
        "fk_users_respond_contact_id",
        "users",
        "respond_contacts",
        ["respond_contact_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_users_contact_number", "users", ["contact_number"])


def downgrade() -> None:
    op.drop_constraint("uq_users_contact_number", "users", type_="unique")
    op.drop_constraint("fk_users_respond_contact_id", "users", type_="foreignkey")
    op.drop_index("ix_users_respond_contact_id", table_name="users")
    op.drop_column("users", "notify_whatsapp_summary")
    op.drop_column("users", "notify_whatsapp")
    op.drop_column("users", "respond_contact_id")
