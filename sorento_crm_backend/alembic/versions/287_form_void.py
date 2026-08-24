"""Form void: terminal status='voided' + reason quad on the three form tables.

Adds ``void_reason`` (TEXT), ``voided_by`` (FK -> users.id; type matches each
table's existing user-id column - String(100) on purchase_requests, TEXT on
complaints / stock_inquiries) and ``voided_at`` (naive TIMESTAMP) to
``purchase_requests`` (PR + sponsorship form), ``complaints`` and
``stock_inquiries``.

The ``status`` value ``'voided'`` needs no schema change: none of the three
tables carry a CHECK constraint on ``status`` (it is a free String(50)), so the
new terminal value is accepted as-is. (If a CHECK is ever added, extend it here.)

Also seeds the four per-form void RBAC slugs and grants each to the roles that
already hold the sibling finalize permission (grant sweep, so the action doesn't
silently 403 / hide for existing roles).

Idempotent (safe to re-run) and reversible.

Revision ID: 287_form_void
Revises: 286_form_cs_routing_conditions
Create Date: 2026-07-19
"""
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "287_form_void"
down_revision = "286_form_cs_routing_conditions"
branch_labels = None
depends_on = None


# table -> (voided_by column type)
_VOID_TABLES: dict[str, sa.types.TypeEngine] = {
    "purchase_requests": sa.String(100),
    "complaints": sa.Text(),
    "stock_inquiries": sa.Text(),
}

# void slug -> sibling finalize slug whose holder-roles get the grant sweep.
# PR + SF share one slug (shared router + detail component); repo convention
# domain.entity.void.
_VOID_GRANTS: dict[str, str] = {
    "procurement.purchase_requests.void": "procurement.purchase_requests.close",
    "complaint_management.complaints.void": "complaint_management.complaints.close",
    "procurement.stock_inquiries.void": "procurement.stock_inquiries.reopen",
}

_VOID_SLUG_META: dict[str, tuple[str, str]] = {
    "procurement.purchase_requests.void": ("Void Purchase Requests / Sponsorship Forms", "Void a purchase request or sponsorship form (irreversible)."),
    "complaint_management.complaints.void": ("Void Complaints", "Void a complaint (irreversible)."),
    "procurement.stock_inquiries.void": ("Void Stock Inquiries", "Void a stock inquiry (irreversible)."),
}


def _has_column(insp, table: str, column: str) -> bool:
    return any(c["name"] == column for c in insp.get_columns(table))


def _fk_name(table: str) -> str:
    return f"fk_{table}_voided_by_users"


def _has_fk(insp, table: str, name: str) -> bool:
    return any(fk.get("name") == name for fk in insp.get_foreign_keys(table))


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)

    for table, voided_by_type in _VOID_TABLES.items():
        if not _has_column(insp, table, "void_reason"):
            op.add_column(table, sa.Column("void_reason", sa.Text(), nullable=True))
        if not _has_column(insp, table, "voided_by"):
            op.add_column(table, sa.Column("voided_by", voided_by_type, nullable=True))
        if not _has_column(insp, table, "voided_at"):
            op.add_column(table, sa.Column("voided_at", sa.DateTime(timezone=False), nullable=True))

        insp = inspect(conn)  # refresh so FK check sees the freshly-added column
        fk = _fk_name(table)
        if not _has_fk(insp, table, fk):
            op.create_foreign_key(
                fk, table, "users", ["voided_by"], ["id"], ondelete="SET NULL"
            )
        insp = inspect(conn)

    # --- RBAC: seed the four void slugs + grant sweep to sibling-holding roles ---
    from sqlalchemy.orm import Session

    from app.rbac.permission_registry import sync_permissions

    session = Session(bind=conn)
    try:
        sync_permissions(session)
    finally:
        session.close()

    now = datetime.utcnow()

    def _perm_id(slug: str) -> str | None:
        row = conn.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
        ).fetchone()
        if row is not None:
            return row.id
        pid = str(uuid.uuid4())
        name, desc = _VOID_SLUG_META[slug]
        conn.execute(
            sa.text(
                "INSERT INTO user_permissions (id, slug, name, description, created_at) "
                "VALUES (:id, :slug, :name, :desc, :now)"
            ),
            {"id": pid, "slug": slug, "name": name, "desc": desc, "now": now},
        )
        return pid

    for void_slug, sibling_slug in _VOID_GRANTS.items():
        void_pid = _perm_id(void_slug)
        if void_pid is None:
            continue
        role_rows = conn.execute(
            sa.text(
                "SELECT DISTINCT rp.role_id AS role_id "
                "FROM user_role_permissions rp "
                "JOIN user_permissions p ON p.id = rp.permission_id "
                "WHERE p.slug = :sib"
            ),
            {"sib": sibling_slug},
        ).fetchall()
        for r in role_rows:
            exists = conn.execute(
                sa.text(
                    "SELECT 1 FROM user_role_permissions WHERE role_id = :r AND permission_id = :p"
                ),
                {"r": r.role_id, "p": void_pid},
            ).fetchone()
            if not exists:
                conn.execute(
                    sa.text(
                        "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
                        "VALUES (:id, :r, :p, :now)"
                    ),
                    {"id": str(uuid.uuid4()), "r": r.role_id, "p": void_pid, "now": now},
                )


def downgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)

    for table in _VOID_TABLES:
        fk = _fk_name(table)
        if _has_fk(insp, table, fk):
            op.drop_constraint(fk, table, type_="foreignkey")
        for column in ("voided_at", "voided_by", "void_reason"):
            if _has_column(insp, table, column):
                op.drop_column(table, column)
        insp = inspect(conn)

    # Remove the void RBAC grants + permission rows (re-upgrade re-seeds them).
    for slug in _VOID_GRANTS:
        row = conn.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
        ).fetchone()
        if row is not None:
            conn.execute(
                sa.text("DELETE FROM user_role_permissions WHERE permission_id = :p"),
                {"p": row.id},
            )
            conn.execute(sa.text("DELETE FROM user_permissions WHERE id = :p"), {"p": row.id})
