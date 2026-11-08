"""NPA-FORM-SLA: the New Product Application's two Form SLA stage rows, pre-filled from the SI's.

Data only, idempotent. Each NPA row copies the Stock Inquiry row of the same team set (agent,
team set, policy, active / notify flags), so the NPA routes to the SI's teams and tiers and keeps
its own row, editable in SLA Management > Form SLA Config:

- `npa_approval` (team set `project_sales`): starts on submitted / resubmitted, resolves on
  approved / rejected.
- `npa_purchasing` (team set `purchasing`): starts on approved, the response clock stops on the
  purchasing response save, resolves on completed / rejected.

A row is inserted only while no NPA row holds that team set, and only from an existing SI row, so
a database without the SI's rows (CI, a fresh tenant) gets nothing and a second run adds nothing.
`grace_seconds` is not copied: the NPA has no deferred-action path (form_action_dispatch).

Grants: every role holding the SI's project_sales_approve gets NPA view + approve, every role
holding the SI's purchasing_reject gets NPA view + open_code (crew pass 8 Nov: the assignees
could not open the NPA). The downgrade leaves grants alone: they may have been set by hand since.

Also: the seeded `stock_inquiry_created` email row's button label becomes the notice's own
`button_label` (the NPA sends that notice too), only while the row is exactly as seeded.

Plan: documentation/plans/procurement/PLAN-npa-form-sla-08nov.md.

Revision ID: npasla_0001_seed_configs
Revises: lpcui_0001_list_price_changed
"""
import json

from alembic import op
from sqlalchemy import text

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "npasla_0001_seed_configs"
down_revision = "lpcui_0001_list_price_changed"
branch_labels = None
depends_on = None

#: (NPA stage code, the SI team set it copies, start, respond, resolve).
STAGES = (
    ("npa_approval", "project_sales", "submitted,resubmitted", None, "approved,rejected"),
    ("npa_purchasing", "purchasing", "approved", "purchasing_respond", "completed,rejected"),
)


def _insert(stage_code: str, team_set: str, start: str, respond, resolve: str) -> str:
    respond_sql = f"'{respond}'" if respond else "NULL"
    return (
        "INSERT INTO form_sla_configs (id, source_entity_type, stage_code, policy_id, agent_code, "
        "team_set_code, start_event, respond_event, resolve_event, is_active, notify_assignee, "
        "notify_on_escalation, created_at, updated_at) "
        f"SELECT gen_random_uuid(), 'new_product_application', '{stage_code}', si.policy_id, "
        f"si.agent_code, si.team_set_code, '{start}', {respond_sql}, '{resolve}', si.is_active, "
        "si.notify_assignee, si.notify_on_escalation, now(), now() "
        "FROM form_sla_configs si "
        f"WHERE si.source_entity_type = 'stock_inquiry' AND si.team_set_code = '{team_set}' "
        "AND NOT EXISTS (SELECT 1 FROM form_sla_configs n "
        "WHERE n.source_entity_type = 'new_product_application' "
        f"AND n.team_set_code = '{team_set}') "
        "ORDER BY si.is_active DESC, si.created_at ASC LIMIT 1"
    )


SEED = tuple(_insert(*stage) for stage in STAGES)


def _team_notice_layout(button_label: str) -> str:
    """The SI team notice's block document (eml_0002_seed_layouts), with its button label."""
    return json.dumps(
        {
            "blocks": [
                {"type": "brand_header"},
                {"text": "{{ heading }}", "type": "heading"},
                {"text": "{{ intro }}", "type": "intro"},
                {"label": button_label, "type": "button", "url": "{{ view_url }}"},
                {"note": "This is a system-generated email. Please do not reply.", "type": "footer"},
            ],
            "version": 1,
        }
    )


#: The NPA sends the SI's team notice too (owner 8 Nov), so the seeded `stock_inquiry_created`
#: row's fixed "Open stock inquiry" button reads its `button_label` (the SI still passes "Open
#: stock inquiry"). Only a row still carrying the seeded document is changed: an admin's edit
#: is theirs.
SEEDED_LAYOUT = _team_notice_layout("Open stock inquiry")
LABELLED_LAYOUT = _team_notice_layout("{{ button_label or 'Open stock inquiry' }}")
TEMPLATE_UPDATE = (
    "UPDATE email_templates SET layout_json = CAST(:new AS jsonb), updated_at = now() "
    "WHERE code = 'stock_inquiry_created' AND layout_json = CAST(:old AS jsonb)"
)


#: Crew pass 8 Nov (owner answer pending, option a): whoever acts on the SI stage acts on the NPA
#: stage. (SI slug its holders have, NPA slug they get.) Copied from the SI's own holders, as
#: npa_0001 did for `create`; no role is named. Additive and idempotent.
_GRANT_FROM_SI = (
    ("procurement.stock_inquiries.project_sales_approve", "procurement.new_product_applications.view"),
    ("procurement.stock_inquiries.project_sales_approve", "procurement.new_product_applications.approve"),
    ("procurement.stock_inquiries.purchasing_reject", "procurement.new_product_applications.view"),
    ("procurement.stock_inquiries.purchasing_reject", "procurement.new_product_applications.open_code"),
)


def _grant(src: str, tgt: str) -> str:
    return (
        "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
        "SELECT DISTINCT ON (urp.role_id) gen_random_uuid()::text, urp.role_id, tgt.id, now() "
        "FROM user_role_permissions urp "
        "JOIN user_permissions src ON src.id = urp.permission_id "
        "CROSS JOIN user_permissions tgt "
        f"WHERE src.slug = '{src}' AND tgt.slug = '{tgt}' "
        "AND NOT EXISTS (SELECT 1 FROM user_role_permissions existing "
        "WHERE existing.role_id = urp.role_id AND existing.permission_id = tgt.id)"
    )


GRANTS = tuple(_grant(src, tgt) for src, tgt in _GRANT_FROM_SI)


def upgrade() -> None:
    for statement in SEED:
        op.execute(text(statement))
    for statement in GRANTS:
        op.execute(text(statement))
    op.get_bind().execute(text(TEMPLATE_UPDATE), {"new": LABELLED_LAYOUT, "old": SEEDED_LAYOUT})


def downgrade() -> None:
    op.get_bind().execute(text(TEMPLATE_UPDATE), {"new": SEEDED_LAYOUT, "old": LABELLED_LAYOUT})
    # Only the rows this revision names; an admin's own NPA rows (other stage codes) stay.
    op.execute(
        text(
            "DELETE FROM form_sla_configs WHERE source_entity_type = 'new_product_application' "
            "AND stage_code IN ('npa_approval', 'npa_purchasing')"
        )
    )
