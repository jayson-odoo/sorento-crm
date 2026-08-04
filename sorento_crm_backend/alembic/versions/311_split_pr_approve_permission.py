"""Split the PR / SF approver decision out of send_for_approval.

`procurement.purchase_requests.send_for_approval` gated two unrelated duties, while
change-to-pending was ungated entirely. Granting the slug so a sales admin could
reject a submitted request also made them an approver of anything already pending.

After this migration:

    send_for_approval -> triage a SUBMITTED request (change to pending, or reject)
    approve           -> approver decision on a PENDING APPROVAL request

The grant sweep keeps today's behaviour intact: every role that can decide today
(i.e. holds send_for_approval) also receives `approve`, so no approver loses the
buttons. Separately, the sales-admin roles gain `send_for_approval` so they can
triage - Project Sales Manager locally, Project Sales Coordinator in production;
both are granted, and a name absent from an environment is simply skipped.

Revision ID: 311_split_pr_approve_permission
Revises: 310_form_sla_skip_stage
"""
from alembic import op
from sqlalchemy import text

revision = "311_split_pr_approve_permission"
down_revision = "310_form_sla_skip_stage"
branch_labels = None
depends_on = None

APPROVE = "procurement.purchase_requests.approve"
TRIAGE = "procurement.purchase_requests.send_for_approval"
TRIAGE_ROLES = ("Project Sales Manager", "Project Sales Coordinator")


def upgrade() -> None:
    conn = op.get_bind()

    # 1. The permission row. `sync_permissions` also creates it from the registry at
    #    startup, but seeding here keeps the migration self-sufficient and lets the
    #    grants below run in the same transaction.
    conn.execute(
        text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug,
                   'Approve / reject purchase request / sponsorship form',
                   'Approver decision on a request that is PENDING APPROVAL: the in-system '
                   'Approve / Reject buttons, identical in effect to the emailed approval link.',
                   now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": APPROVE},
    )

    # 2. Grant sweep - every role that can decide today keeps that ability.
    conn.execute(
        text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, urp.role_id, new_p.id, now()
            FROM user_role_permissions urp
            JOIN user_permissions old_p ON old_p.id = urp.permission_id AND old_p.slug = :triage
            CROSS JOIN (SELECT id FROM user_permissions WHERE slug = :approve) AS new_p
            WHERE NOT EXISTS (
                SELECT 1 FROM user_role_permissions x
                WHERE x.role_id = urp.role_id AND x.permission_id = new_p.id
            )
            """
        ),
        {"triage": TRIAGE, "approve": APPROVE},
    )

    # 3. Sales admin can now triage. Skips silently where the role name is absent.
    conn.execute(
        text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, r.id, p.id, now()
            FROM user_roles r
            CROSS JOIN (SELECT id FROM user_permissions WHERE slug = :triage) AS p
            WHERE r.name = ANY(:roles)
              AND NOT EXISTS (
                SELECT 1 FROM user_role_permissions x
                WHERE x.role_id = r.id AND x.permission_id = p.id
              )
            """
        ),
        {"triage": TRIAGE, "roles": list(TRIAGE_ROLES)},
    )


def downgrade() -> None:
    conn = op.get_bind()
    # Drop the grants for the new permission, then the permission itself. The
    # send_for_approval grants added in step 3 are left in place: removing them could
    # also revoke a triage ability the role legitimately had before this ran.
    conn.execute(
        text(
            """
            DELETE FROM user_role_permissions
            WHERE permission_id IN (SELECT id FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": APPROVE},
    )
    conn.execute(text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": APPROVE})
