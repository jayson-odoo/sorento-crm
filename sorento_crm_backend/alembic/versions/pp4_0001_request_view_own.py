"""PORTAL-P4-REQUESTS: "only theirs" on the four request forms, granted to the salesperson.

Plan: documentation/plans/portal/PLAN-portal-p4-requests-28oct.md (Architecture item 1).

Creates the four request-form `view_own` slugs (Stock Inquiry, Complaint, Purchase Request,
Sponsorship Form) and `projects.registrations.submit` (owned here for lane
PROJECT-REGISTER-V2), then grants role `salesperson` those five plus the four forms' `.add`.
Holding a form's `view_own` without its `view` narrows that form's staff routes to the user's
own rows (`app/services/own_scope.py`). Insert-only and guarded, so it is safe to re-run on the
dev copy of production; a role absent on an install is skipped.

Downgrade drops the five slugs it created (with every grant of them) and the salesperson's
four `.add` grants; the `.add` slugs themselves predate this revision and stay.

Revision ID: pp4_0001_request_view_own
Revises: pp3_0001_salesperson_grants
Create Date: 2026-10-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Kept <= 32 chars: alembic_version.version_num is varchar(32).
revision = "pp4_0001_request_view_own"
down_revision = "pp3_0001_salesperson_grants"
branch_labels = None
depends_on = None

# Copied, not imported from app.rbac.permission_registry: a migration must keep working when
# the registry later moves on.
_PERMS = (
    (
        "procurement.stock_inquiries.view_own",
        "View Own Stock Inquiries",
        "See only the stock inquiries your own contact submitted. Ignored when View Stock "
        "Inquiries is also held.",
    ),
    (
        "complaint_management.complaints.view_own",
        "View Own Complaints",
        "See only the complaints your own contact submitted. Ignored when View Complaints is "
        "also held.",
    ),
    (
        "procurement.purchase_requests.view_own",
        "View Own Purchase Requests",
        "See only the purchase requests your own contact submitted. Ignored when View Purchase "
        "Requests is also held.",
    ),
    (
        "procurement.sponsorship_forms.view_own",
        "View Own Sponsorship Forms",
        "See only the sponsorship forms your own contact submitted. Ignored when View "
        "Sponsorship Forms is also held.",
    ),
    (
        "projects.registrations.submit",
        "Submit project registrations",
        "Register a project from the CRM, the way a portal contact registers one.",
    ),
)

_ADD = (
    "procurement.stock_inquiries.add",
    "complaint_management.complaints.add",
    "procurement.purchase_requests.add",
    "procurement.sponsorship_forms.add",
)


def upgrade() -> None:
    bind = op.get_bind()
    for slug, name, descr in _PERMS:
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
            SELECT gen_random_uuid()::text, r.id, p.id, now()
            FROM user_roles r
            CROSS JOIN user_permissions p
            WHERE r.slug = 'salesperson' AND p.slug = ANY(:slugs)
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"slugs": [slug for slug, _name, _descr in _PERMS] + list(_ADD)},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM user_role_permissions
            WHERE role_id IN (SELECT id FROM user_roles WHERE slug = 'salesperson')
              AND permission_id IN (SELECT id FROM user_permissions WHERE slug = ANY(:slugs))
            """
        ),
        {"slugs": list(_ADD)},
    )
    for slug, _name, _descr in _PERMS:
        bind.execute(
            sa.text(
                "DELETE FROM user_role_permissions WHERE permission_id IN "
                "(SELECT id FROM user_permissions WHERE slug = :slug)"
            ),
            {"slug": slug},
        )
        bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": slug})
