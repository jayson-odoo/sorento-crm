"""Add the project ladder's missing manual edges (Sample Submission, Final Negotiation, Sponsorship Form).

Prod's default project graph already has the rungs sample_submission, final_negotiation and
sponsorship_form (made in the admin editor), but no edges into or out of most of them, so
the header offered no move to or from those stages. This adds the 12 manual edges of the
document's ladder: the forward steps, PO received from the last two rungs, the way back one
rung, and Mark lost / Mark dormant from the last two.

Default graph only (scope_id NULL), and only where both rungs exist and no edge between
them exists yet, so an edge an admin already made keeps its own label and running this twice
adds nothing. A fresh database seeds quoted / tendering instead, so there it is a no-op.
Win % and stale days are left alone. The downgrade removes only edges matching one of the
exact (from, to, label) triples below.

Revision ID: stg_0001_project_ladder_edges
Revises: gemprice_0001_gemini_prices
"""
from alembic import op
import sqlalchemy as sa


revision = "stg_0001_project_ladder_edges"
down_revision = "gemprice_0001_gemini_prices"
branch_labels = None
depends_on = None


_EDGES = (
    ("specified", "sample_submission", "Sample submitted"),
    ("sample_submission", "final_negotiation", "Final negotiation"),
    ("final_negotiation", "sponsorship_form", "Sponsorship"),
    ("sponsorship_form", "po_received", "PO received"),
    ("final_negotiation", "po_received", "PO received"),
    ("sample_submission", "specified", "Back to Spec In"),
    ("final_negotiation", "sample_submission", "Back to sample submission"),
    ("sponsorship_form", "final_negotiation", "Back to final negotiation"),
    ("final_negotiation", "lost", "Mark lost"),
    ("final_negotiation", "dormant", "Mark dormant"),
    ("sponsorship_form", "lost", "Mark lost"),
    ("sponsorship_form", "dormant", "Mark dormant"),
)

_VALUES = ", ".join(f"('{f}', '{t}', '{lbl}')" for f, t, lbl in _EDGES)


def upgrade() -> None:
    op.execute(
        sa.text(
            "insert into status_transitions "
            "(id, entity_type, tenant_id, scope_id, from_status_id, to_status_id, label, "
            " sort_order, trigger_mode, conditions_json, created_at, updated_at) "
            "select gen_random_uuid(), 'project', f.tenant_id, null, f.id, t.id, e.label, 0, "
            "       'manual', null, now(), now() "
            f"from (values {_VALUES}) as e(from_key, to_key, label) "
            "join statuses f on f.entity_type = 'project' and f.scope_id is null "
            "  and f.key = e.from_key "
            "join statuses t on t.entity_type = 'project' and t.scope_id is null "
            "  and t.key = e.to_key and t.tenant_id is not distinct from f.tenant_id "
            "where not exists (select 1 from status_transitions x "
            "                  where x.entity_type = 'project' and x.scope_id is null "
            "                    and x.tenant_id is not distinct from f.tenant_id "
            "                    and x.from_status_id = f.id and x.to_status_id = t.id)"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "delete from status_transitions x using statuses f, statuses t, "
            f"(values {_VALUES}) as e(from_key, to_key, label) "
            "where x.entity_type = 'project' and x.scope_id is null "
            "  and x.from_status_id = f.id and x.to_status_id = t.id "
            "  and f.entity_type = 'project' and f.scope_id is null and f.key = e.from_key "
            "  and t.entity_type = 'project' and t.scope_id is null and t.key = e.to_key "
            "  and x.label = e.label"
        )
    )
