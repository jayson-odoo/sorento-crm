"""Price-floor approval gate on a quotation document (S14-S16).

Three things, and each is required for the feature to be usable rather than merely present:

1. ``project_quotation_documents.approval_status_id`` (FK statuses, NULLABLE) plus
   ``approval_rejected_reason``. Nullable is the design, not laziness: NULL means "this
   quotation has never needed a manager", so the overwhelming majority of documents carry no
   graph position at all and their Issue flow is untouched. There is deliberately NO backfill
   stamping existing rows onto `draft` - that would enrol every quotation ever written into an
   approval lifecycle, which is exactly the regression the slice is guarding against.

2. The ``quotation`` status graph, seeded here as well as by ``project_seed_service`` on boot.
   The seeder covers a fresh install; this covers an install that is already running, where the
   boot seeder has already been past and would be skipped by its own wholesale guard on the next
   restart only if rows existed - they do not, so in practice either path fills it. Both are
   guarded on "does this graph have any rows", so they cannot fight.

3. ``projects.quotations.approve``, seeded AND swept to the roles that should hold it. A new
   permission with no grant path silently 403s the feature for everybody and the failure looks
   like a bug in the button (PRINCIPLES.md DoD #3). Swept to: any role already holding the
   sales-manager grant ``projects.projects.manage``, plus a role named "Project Sales Manager",
   which is the role the client named. Nothing else - the whole point of the slug is that it is
   narrow.

Defensively re-runnable (``_has_*`` guards), because the dev database is a copy of production
and this branch's revisions have been applied there by hand more than once.

Revision ID: 330_quotation_approval_gate
Revises: 329_quotation_templates
"""
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID


revision = "330_quotation_approval_gate"
down_revision = "329_quotation_templates"
branch_labels = None
depends_on = None


_PERM_SLUG = "projects.quotations.approve"
_ENTITY = "quotation"

# Mirrors project_seed_service.DEFAULT_QUOTATION_STATUSES / _EDGES exactly. Duplicated rather
# than imported because a migration must keep working when the service module later moves on.
_STATUSES = (
    # (key, label, sort_order, is_initial)
    ("draft", "Draft", 0, True),
    ("rejected", "Rejected", 1, False),
    ("pending_approval", "Pending Approval", 2, False),
    ("approved", "Approved", 3, False),
    ("issued", "Issued", 4, False),
)
_EDGES = (
    ("draft", "pending_approval", "Send for approval", 0),
    ("pending_approval", "approved", "Approve", 0),
    ("pending_approval", "rejected", "Reject", 1),
    ("rejected", "draft", "Back to draft", 0),
    ("approved", "issued", "Issued to the customer", 0),
    ("issued", "pending_approval", "Send for approval", 0),
)


# Both guards pin the CURRENT schema. An unqualified information_schema lookup also matches the
# throwaway `zzt_blank_*` schemas the Postgres test fixtures create, and a suite running while
# this migration is applied made an earlier guard answer "already there" about somebody else's
# schema, so the upgrade no-opped and stamped a revision whose DDL never ran.
def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            text(
                "select 1 from information_schema.columns "
                "where table_name = :t and column_name = :c "
                "and table_schema = current_schema()"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def _has_index(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            text("select 1 from pg_indexes where indexname = :n and schemaname = current_schema()"),
            {"n": name},
        ).scalar()
    )


def _seed_graph(conn) -> None:
    """Idempotent on the graph as a whole, exactly like the boot seeder.

    Wholesale rather than per-rung: adding back a status somebody deliberately deleted, on every
    deploy, would be worse than not seeding at all.
    """
    already = conn.execute(
        text(
            "select 1 from statuses where entity_type = :e and scope_id is null limit 1"
        ),
        {"e": _ENTITY},
    ).scalar()
    if already:
        return

    now = datetime.utcnow()
    ids = {}
    for key, label, sort_order, is_initial in _STATUSES:
        ids[key] = str(uuid.uuid4())
        conn.execute(
            text(
                "insert into statuses (id, entity_type, key, label, sort_order, is_initial, "
                "is_terminal, is_active, is_archived, is_default, is_system, created_at, "
                "updated_at) values (:id, :e, :k, :l, :s, :init, false, true, false, :init, "
                "false, :now, :now)"
            ),
            {
                "id": ids[key],
                "e": _ENTITY,
                "k": key,
                "l": label,
                "s": sort_order,
                "init": is_initial,
                "now": now,
            },
        )
    for from_key, to_key, label, sort_order in _EDGES:
        conn.execute(
            text(
                "insert into status_transitions (id, entity_type, from_status_id, "
                "to_status_id, label, sort_order, trigger_mode, created_at, updated_at) "
                "values (:id, :e, :f, :t, :l, :s, 'manual', :now, :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "e": _ENTITY,
                "f": ids[from_key],
                "t": ids[to_key],
                "l": label,
                "s": sort_order,
                "now": now,
            },
        )


def _seed_and_sweep_permission(conn) -> None:
    now = datetime.utcnow()
    perm = conn.execute(
        text("select id from user_permissions where slug = :s"), {"s": _PERM_SLUG}
    ).fetchone()
    if perm is None:
        perm_id = str(uuid.uuid4())
        conn.execute(
            text(
                "insert into user_permissions (id, slug, name, description, created_at) "
                "values (:id, :slug, :name, :desc, :now)"
            ),
            {
                "id": perm_id,
                "slug": _PERM_SLUG,
                "name": "Approve Below-Floor Quotations",
                "desc": (
                    "Sales-manager grant: approve or reject a quotation carrying a line "
                    "priced below its price floor, which is what lets it be issued to the "
                    "customer."
                ),
                "now": now,
            },
        )
    else:
        perm_id = perm.id

    # The sweep. JOIN-shaped "grant where missing" rather than "insert if the table is empty",
    # which is the only form that also corrects a half-applied earlier run.
    role_ids = [
        row.id
        for row in conn.execute(
            text(
                """
                select r.id
                from user_roles r
                where lower(r.name) = 'project sales manager'
                   or exists (
                        select 1
                        from user_role_permissions rp
                        join user_permissions p on p.id = rp.permission_id
                        where rp.role_id = r.id
                          and p.slug = 'projects.projects.manage'
                   )
                """
            )
        ).fetchall()
    ]
    for role_id in role_ids:
        exists = conn.execute(
            text(
                "select 1 from user_role_permissions where role_id = :r and permission_id = :p"
            ),
            {"r": role_id, "p": perm_id},
        ).fetchone()
        if not exists:
            conn.execute(
                text(
                    "insert into user_role_permissions (id, role_id, permission_id, "
                    "assigned_at) values (:id, :r, :p, :now)"
                ),
                {"id": str(uuid.uuid4()), "r": role_id, "p": perm_id, "now": now},
            )


def upgrade() -> None:
    if not _has_column("project_quotation_documents", "approval_status_id"):
        op.add_column(
            "project_quotation_documents",
            sa.Column("approval_status_id", UUID(as_uuid=False), nullable=True),
        )
        op.create_foreign_key(
            "fk_project_quotation_documents_approval_status",
            "project_quotation_documents",
            "statuses",
            ["approval_status_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if not _has_column("project_quotation_documents", "approval_rejected_reason"):
        op.add_column(
            "project_quotation_documents",
            sa.Column("approval_rejected_reason", sa.Text(), nullable=True),
        )
    if not _has_index("ix_project_quotation_documents_approval_status"):
        op.create_index(
            "ix_project_quotation_documents_approval_status",
            "project_quotation_documents",
            ["approval_status_id"],
        )

    conn = op.get_bind()
    _seed_graph(conn)
    _seed_and_sweep_permission(conn)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text(
            "delete from user_role_permissions where permission_id in "
            "(select id from user_permissions where slug = :s)"
        ),
        {"s": _PERM_SLUG},
    )
    conn.execute(text("delete from user_permissions where slug = :s"), {"s": _PERM_SLUG})
    conn.execute(
        text(
            "delete from status_transitions where entity_type = :e and scope_id is null"
        ),
        {"e": _ENTITY},
    )
    # Documents pointing at a rung that is about to go: cleared first, because the FK is
    # ON DELETE SET NULL and the column is dropped straight after anyway.
    conn.execute(text("update project_quotation_documents set approval_status_id = null"))
    conn.execute(
        text("delete from statuses where entity_type = :e and scope_id is null"),
        {"e": _ENTITY},
    )

    op.drop_index(
        "ix_project_quotation_documents_approval_status",
        table_name="project_quotation_documents",
    )
    op.drop_constraint(
        "fk_project_quotation_documents_approval_status",
        "project_quotation_documents",
        type_="foreignkey",
    )
    op.drop_column("project_quotation_documents", "approval_rejected_reason")
    op.drop_column("project_quotation_documents", "approval_status_id")
