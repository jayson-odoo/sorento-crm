"""respond_contact_cs_routing - per-salesman → CS PIC pin (pin-point assignment).

Overrides round-robin at procurement form-SLA CS-stage spawn. One active pin per
(respond_contact_id, use_case); use_case ∈ {purchase_request, sponsorship_form}.
See docs/plans/PLAN-procurement-cs-handoff-and-pinpoint-routing.md.
"""
from alembic import op
import sqlalchemy as sa


revision = "231_respond_contact_cs_routing"
down_revision = "230_form_sla_advance_on_event"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "respond_contact_cs_routing",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "respond_contact_id",
            sa.Text(),
            sa.ForeignKey("respond_contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cs_pic_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("use_case", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "respond_contact_id", "use_case", name="uq_cs_routing_contact_use_case"
        ),
    )
    op.create_index(
        "ix_cs_routing_contact", "respond_contact_cs_routing", ["respond_contact_id"]
    )
    op.create_index(
        "ix_cs_routing_cs_pic", "respond_contact_cs_routing", ["cs_pic_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_cs_routing_cs_pic", table_name="respond_contact_cs_routing")
    op.drop_index("ix_cs_routing_contact", table_name="respond_contact_cs_routing")
    op.drop_table("respond_contact_cs_routing")
