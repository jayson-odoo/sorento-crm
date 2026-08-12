"""Skip the next SLA stage: config columns, complaint wiring, permission grant.

Three nullable columns on form_sla_configs let a stage declare itself skippable.
NULL skip_event = unskippable = exactly today's behaviour, so every existing row is
untouched by the DDL.

The data half wires the ONE consumer (complaint "Settled on site"):

  * appends `settled_on_site` to complaint.main's resolve_event. Append-only and
    idempotent so it can never clobber an admin's edit. `advance_on_event` stays
    'approved' - that is what stops customer service spawning.
    Without this row change the skip emits an event no config matches, the `main`
    tracker never resolves, and a closed complaint keeps escalating and messaging
    assignees for days. Too quiet a failure to leave to a manual admin step.

  * grants complaint_management.complaints.settle_on_site to every role that already
    holds .approve. A permission granted to nobody is indistinguishable from a broken
    feature - the gear item would be invisible for every role including the technical
    team.

Revision ID: 310_form_sla_skip_stage
Revises: 309_merge_status_engine
"""
from alembic import op
import sqlalchemy as sa


revision = "310_form_sla_skip_stage"
down_revision = "309_merge_status_engine"
branch_labels = None
depends_on = None


SKIP_EVENT = "settled_on_site"
SKIP_LABEL = "Settled on site"
APPROVE_SLUG = "complaint_management.complaints.approve"
SETTLE_SLUG = "complaint_management.complaints.settle_on_site"


def _has_column(bind, table: str, column: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()

    # --- DDL: additive and idempotent ------------------------------------- #
    for name, type_ in (
        ("skip_event", sa.String(length=100)),
        ("skip_terminal_status", sa.String(length=100)),
        ("skip_action_label", sa.String(length=120)),
    ):
        if not _has_column(bind, "form_sla_configs", name):
            op.add_column("form_sla_configs", sa.Column(name, type_, nullable=True))

    # --- Data: wire the complaint technical stage -------------------------- #
    # Append-only on resolve_event: only adds the token when absent, and only to the
    # complaint `main` row. Re-running is a no-op; an admin's own additions survive.
    bind.execute(
        sa.text(
            """
            UPDATE form_sla_configs
            SET resolve_event = CASE
                    WHEN resolve_event IS NULL OR btrim(resolve_event) = '' THEN :evt
                    ELSE resolve_event || ',' || :evt
                END,
                skip_event = :evt,
                skip_terminal_status = :evt,
                skip_action_label = :label
            WHERE source_entity_type = 'complaint'
              AND stage_code = 'main'
              AND (
                    resolve_event IS NULL
                 OR :evt <> ALL (string_to_array(resolve_event, ','))
              )
            """
        ),
        {"evt": SKIP_EVENT, "label": SKIP_LABEL},
    )
    # Re-run safety: the guard above skips rows that already carry the token, so stamp
    # the three skip columns separately for those.
    bind.execute(
        sa.text(
            """
            UPDATE form_sla_configs
            SET skip_event = :evt,
                skip_terminal_status = :evt,
                skip_action_label = :label
            WHERE source_entity_type = 'complaint'
              AND stage_code = 'main'
              AND (skip_event IS DISTINCT FROM :evt
                   OR skip_terminal_status IS DISTINCT FROM :evt
                   OR skip_action_label IS DISTINCT FROM :label)
            """
        ),
        {"evt": SKIP_EVENT, "label": SKIP_LABEL},
    )

    # --- Data: permission + grant ------------------------------------------ #
    # The registry sync at startup creates the permission row, but a fresh deploy runs
    # migrations first - insert it here so the grant below always has a target.
    bind.execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {
            "slug": SETTLE_SLUG,
            "name": "Settle Complaints On Site",
            "descr": (
                "Close a complaint as settled on site when the technician fixed the issue "
                "during the visit: resolves the technical stage WITHOUT spawning customer "
                "service, so no replacement is arranged."
            ),
        },
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, rp.role_id, tgt.id, now()
            FROM user_role_permissions rp
            JOIN user_permissions src ON src.id = rp.permission_id AND src.slug = :approve
            CROSS JOIN user_permissions tgt
            WHERE tgt.slug = :settle
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"approve": APPROVE_SLUG, "settle": SETTLE_SLUG},
    )


def downgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            DELETE FROM user_role_permissions
            WHERE permission_id IN (SELECT id FROM user_permissions WHERE slug = :settle)
            """
        ),
        {"settle": SETTLE_SLUG},
    )
    bind.execute(
        sa.text("DELETE FROM user_permissions WHERE slug = :settle"), {"settle": SETTLE_SLUG}
    )
    # Strip the token from resolve_event without disturbing the admin's other events.
    bind.execute(
        sa.text(
            """
            UPDATE form_sla_configs
            SET resolve_event = NULLIF(
                    array_to_string(
                        array_remove(string_to_array(resolve_event, ','), :evt), ','
                    ), ''
                )
            WHERE source_entity_type = 'complaint' AND stage_code = 'main'
            """
        ),
        {"evt": SKIP_EVENT},
    )
    for name in ("skip_action_label", "skip_terminal_status", "skip_event"):
        if _has_column(bind, "form_sla_configs", name):
            op.drop_column("form_sla_configs", name)
