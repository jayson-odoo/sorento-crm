"""Form SLA escalation: event trigger columns + clock reset + manual-escalate permission.

- conversation_sla_event_log: add `trigger` ('auto'|'manual', default 'auto') +
  `triggered_by_id` (nullable FK users) - distinguishes manual from auto escalations.
- Rollout reset: for unresolved form-SLA trackers at current_tier >= 2, reset
  current_tier_started_at = now and recompute due_at / due_at_resolution from the
  current tier's hours, so dropping the old escalated_at guard does NOT escalate
  every already-overdue frozen tier-2 row on the first scan tick.
- Seed `sla.form.escalate` permission and grant it to ALL roles (manual escalate
  is available to all users; slug exists so it can be tightened later).

Revision ID: 235_form_sla_event_trigger_and_escalate_perm
Revises: 234_user_respond_contact_link_prefs
Create Date: 2026-06-17
"""
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "235_form_sla_event_trigger_and_escalate_perm"
down_revision = "234_user_respond_contact_link_prefs"
branch_labels = None
depends_on = None

_PERM_SLUG = "sla.form.escalate"


def upgrade() -> None:
    op.add_column(
        "conversation_sla_event_log",
        sa.Column("trigger", sa.String(16), nullable=False, server_default="auto"),
    )
    op.add_column(
        "conversation_sla_event_log",
        sa.Column("triggered_by_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversation_sla_event_log_triggered_by_id",
        "conversation_sla_event_log",
        "users",
        ["triggered_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    conn = op.get_bind()

    # --- Rollout clock reset (avoid escalation burst) ---
    from sqlalchemy.orm import Session as SASession
    from app.services.form_sla_service import _working_due_naive, FORM_SLA_TYPES

    now = datetime.utcnow()
    sess = SASession(bind=conn)
    placeholders = ", ".join(f":t{i}" for i in range(len(FORM_SLA_TYPES)))
    params = {f"t{i}": v for i, v in enumerate(FORM_SLA_TYPES)}
    rows = conn.execute(
        sa.text(
            f"""
            SELECT t.id AS id, tr.response_hours AS rh, tr.resolution_hours AS reso
            FROM conversation_sla_tracking t
            JOIN sla_policy_tiers tr
              ON tr.policy_id = t.policy_id AND tr.tier_level = t.current_tier
            WHERE t.is_resolved = false
              AND t.current_tier >= 2
              AND t.source_entity_type IN ({placeholders})
            """
        ),
        params,
    ).fetchall()
    for r in rows:
        due = _working_due_naive(sess, now, float(r.rh or 24))
        due_res = _working_due_naive(sess, now, float(r.reso or 24))
        conn.execute(
            sa.text(
                """
                UPDATE conversation_sla_tracking
                SET current_tier_started_at = :now, due_at = :due, due_at_resolution = :dres
                WHERE id = :id
                """
            ),
            {"now": now, "due": due, "dres": due_res, "id": r.id},
        )

    # --- Seed permission + grant to all roles ---
    perm = conn.execute(
        sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": _PERM_SLUG}
    ).fetchone()
    if perm is None:
        perm_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO user_permissions (id, slug, name, description, created_at) "
                "VALUES (:id, :slug, :name, :desc, :now)"
            ),
            {
                "id": perm_id,
                "slug": _PERM_SLUG,
                "name": "Escalate form SLA",
                "desc": "Manually force-escalate a form SLA stage to the next tier.",
                "now": now,
            },
        )
    else:
        perm_id = perm.id

    role_ids = [r.id for r in conn.execute(sa.text("SELECT id FROM user_roles")).fetchall()]
    for rid in role_ids:
        exists = conn.execute(
            sa.text(
                "SELECT 1 FROM user_role_permissions WHERE role_id = :r AND permission_id = :p"
            ),
            {"r": rid, "p": perm_id},
        ).fetchone()
        if not exists:
            conn.execute(
                sa.text(
                    "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
                    "VALUES (:id, :r, :p, :now)"
                ),
                {"id": str(uuid.uuid4()), "r": rid, "p": perm_id, "now": now},
            )


def downgrade() -> None:
    conn = op.get_bind()
    perm = conn.execute(
        sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": _PERM_SLUG}
    ).fetchone()
    if perm is not None:
        conn.execute(
            sa.text("DELETE FROM user_role_permissions WHERE permission_id = :p"), {"p": perm.id}
        )
        conn.execute(sa.text("DELETE FROM user_permissions WHERE id = :p"), {"p": perm.id})
    op.drop_constraint(
        "fk_conversation_sla_event_log_triggered_by_id",
        "conversation_sla_event_log",
        type_="foreignkey",
    )
    op.drop_column("conversation_sla_event_log", "triggered_by_id")
    op.drop_column("conversation_sla_event_log", "trigger")
    # Clock reset is one-way (no precise downgrade).
