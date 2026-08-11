"""seed template defaults for the two form-action-undo WhatsApp use cases

Staff undo notifications (your task was voided / the form is back with you) send as
free text while the recipient's 24h WhatsApp window is open. Out-of-window, Respond.io
only accepts an APPROVED template, chosen per use_case via respond_template_defaults.
Without these rows the delivery raises TemplateSendSkipped and the recipient hears
nothing until they next message us.

Both map to the approved generic `update` template (slots: sender_name / message /
link), which carries the full notification body verbatim - no new Meta approval
needed. Admins can remap them later in the template-defaults UI like any other
use case.

Looked up by template NAME at upgrade time and skipped when absent (fresh installs
have no synced templates yet; the send path then records a visible skipped log
instead of failing silently). Idempotent via NOT EXISTS.

Revision ID: 312c_seed_undo_template_defaults
"""
from alembic import op


revision = "312c_seed_undo_template_defaults"
down_revision = "312b_seed_form_action_task"
branch_labels = None
depends_on = None

_USE_CASES = ("form_action_voided", "form_action_reopened")


def upgrade() -> None:
    for use_case in _USE_CASES:
        op.execute(
            f"""
            INSERT INTO respond_template_defaults
                (id, use_case, template_id, template_name_snapshot, param_mapping,
                 created_at, updated_at)
            SELECT gen_random_uuid(),
                   '{use_case}',
                   t.id,
                   t.name,
                   '{{"1": "sender_name", "2": "message", "3": "form_url"}}'::jsonb,
                   now(), now()
            FROM respond_message_templates t
            WHERE t.name = 'update'
              AND NOT EXISTS (
                  SELECT 1 FROM respond_template_defaults
                  WHERE use_case = '{use_case}'
              )
            LIMIT 1;
            """
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM respond_template_defaults "
        "WHERE use_case IN ('form_action_voided', 'form_action_reopened');"
    )
