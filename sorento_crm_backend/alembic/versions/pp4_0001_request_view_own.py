"""PORTAL-P4-REQUESTS: "only theirs" on the four request forms, granted to the salesperson.

Plan: documentation/plans/portal/PLAN-portal-p4-requests-28oct.md (Architecture item 1).

Creates the four request-form `view_own` slugs (Stock Inquiry, Complaint, Purchase Request,
Sponsorship Form), `dealer_kit.price_tag_requests.view_own` and `projects.registrations.submit`
(owned here for lane PROJECT-REGISTER-V2), then grants role `salesperson` those six, the four
forms' `.add` and (card v1.2) the write side of the other MY REQUESTS kinds: sample request and
new product application `view_own` + `.create`, sales opportunity `view_own` + `.add` + `.edit`,
price tag request `.create` (never `dealer_kit.page.view`).
Holding a form's `view_own` without its `view` narrows that form's staff routes to the user's
own rows (`app/services/own_scope.py`). Insert-only and guarded, so it is safe to re-run on the
dev copy of production; a role absent on an install is skipped.

Downgrade drops the six slugs it created (with every grant of them) and the salesperson's
grants of the slugs that predate this revision; those slugs themselves stay.

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
        "dealer_kit.price_tag_requests.view_own",
        "View Own Price Tag Requests",
        "See only the price tag requests your own contact submitted. Ignored when View Price Tag "
        "Requests is also held.",
    ),
    (
        "projects.registrations.submit",
        "Submit project registrations",
        "Register a project from the CRM, the way a portal contact registers one.",
    ),
)

_GRANTED = (
    "procurement.stock_inquiries.add",
    "complaint_management.complaints.add",
    "procurement.purchase_requests.add",
    "procurement.sponsorship_forms.add",
    # Card v1.2: the other MY REQUESTS kinds. Every slug here predates this revision.
    "projects.sample_requests.view_own",
    "projects.sample_requests.create",
    "procurement.new_product_applications.view_own",
    "procurement.new_product_applications.create",
    "sales.opportunities.view_own",
    "sales.opportunities.add",
    "sales.opportunities.edit",
    "dealer_kit.price_tag_requests.create",
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
        {"slugs": [slug for slug, _name, _descr in _PERMS] + list(_GRANTED)},
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
        {"slugs": list(_GRANTED)},
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
