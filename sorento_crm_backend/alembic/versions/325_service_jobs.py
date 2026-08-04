"""S6 - Service Jobs, technicians, external providers and what a case costs.

Four tables, and the shape of each is a decision rather than a transcription.

**`service_jobs` declares NO foreign key to `complaints`** (ADR-0009, AC-A6). Every job
today comes from a complaint, which is precisely why the FK is tempting - and precisely why
it must not exist. With it, the first job raised from anything else (a dealer's own showroom,
a stock inquiry, a scheduled inspection) becomes a migration instead of a row. The
polymorphic `(source_entity_type, source_entity_id)` pair is the link, and it is indexed
because every read starts "the jobs for this case".

**`technicians` declares no `users` row** (AC-F8). A Technician is reached on WhatsApp, not
through a login. That is the premise the whole clocks decision rests on: form SLA resolves
assignees through `agent_teams -> team_members -> users`, so a technician with an account
would quietly re-open the door AC-F21 closed, and technician metrics would drift onto an
engine that cannot see them.

**`service_jobs` carries the three waiting columns directly.** S4a's Ruling 1 puts them on
the SLA tracker - but a Service Job deliberately runs no tracker of its own, so it holds them
itself and reads S4a's two lookup sets. `waiting_on_reason` is a VARCHAR holding the option
VALUE, never an id: the lookup binding validates bound columns against values, and an id
column fails that validation on first write. S4a learned this the expensive way.

**`case_cost_lines` knows nothing about chargeability** (AC-M30). A warranty job is free to
the consumer and still costs Sorento a plumber's fee; money out and money in live side by
side on the case and neither derives from the other. Each line says what it was FOR
(AC-M29), because one number per complaint does not answer the costing question that
produced the requirement.

**`external_providers` is generic** (AC-M28). The discovery study already shows the role
blurring - "forward the details to the plumber; can be an outstation technician" - so a
`plumbers` table would need a sibling within the month. Deliberately not `suppliers`, which
carries payment terms, lead times and SPO linkage and would couple after-sales to
procurement for nothing.

Revision ID: 325_service_jobs
Revises: 324_complaint_intake_burst
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "325_service_jobs"
down_revision = "324_complaint_intake_burst"
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    return bool(bind.execute(sa.text("SELECT to_regclass(:n)"), {"n": f"public.{name}"}).scalar())


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "technicians"):
        op.create_table(
            "technicians",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("phone", sa.String(32), nullable=True),
            # TEXT to match respond_contacts.id, which is not a uuid.
            sa.Column(
                "respond_contact_id",
                sa.Text(),
                sa.ForeignKey("respond_contacts.id", ondelete="SET NULL"),
                nullable=True,
                unique=True,
            ),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            # employee | contractor. An outstation technician is often somebody else's
            # staff, and modelling only employees makes the common case unstorable.
            sa.Column("employment_type", sa.String(20), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
        )

    if not _has_table(bind, "external_providers"):
        op.create_table(
            "external_providers",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            # plumber | contract_technician | courier | ... A discriminator, not a table
            # per role.
            sa.Column("provider_type", sa.String(32), nullable=False),
            sa.Column("phone", sa.String(32), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        )

    if not _has_table(bind, "service_jobs"):
        op.create_table(
            "service_jobs",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("job_number", sa.String(64), nullable=True, unique=True),
            # NO FK. See the module docstring - this is AC-A6, and it is the one thing in
            # this migration that a later well-meaning change would undo.
            sa.Column("source_entity_type", sa.String(40), nullable=False),
            sa.Column("source_entity_id", UUID(as_uuid=False), nullable=False),
            sa.Column(
                "status_id",
                UUID(as_uuid=False),
                sa.ForeignKey("statuses.id", ondelete="SET NULL"),
                nullable=True,
            ),
            # The Site as REPORTED, copied from the case. Deriving it from the customer
            # record sends a technician to a shop (AC-B3).
            sa.Column("site_address", sa.Text(), nullable=True),
            sa.Column("site_contact_name", sa.Text(), nullable=True),
            sa.Column("site_contact_phone", sa.Text(), nullable=True),
            sa.Column("site_latitude", sa.Numeric(10, 7), nullable=True),
            sa.Column("site_longitude", sa.Numeric(10, 7), nullable=True),
            sa.Column("site_place_id", sa.String(128), nullable=True),
            sa.Column("scheduled_from", sa.DateTime(timezone=False), nullable=True),
            sa.Column("scheduled_to", sa.DateTime(timezone=False), nullable=True),
            # The job's own clocks. Technician metrics compute from these because the SLA
            # engine cannot resolve somebody who is not a user (AC-F21 to AC-F23).
            sa.Column("proposed_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=False), nullable=True),
            # A date alone is not a Confirmed job: "Service Date: TBA" is a Proposed one
            # wearing a status that stops anybody chasing it (AC-F5).
            sa.Column("customer_agreed_by", sa.Text(), nullable=True),
            sa.Column("arrived_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column(
                "diagnosis_root_cause_id",
                UUID(as_uuid=False),
                sa.ForeignKey("complaint_root_causes.id", ondelete="SET NULL"),
                nullable=True,
            ),
            # Money IN. Independent of case_cost_lines, which is money OUT (AC-M30).
            sa.Column("charge_state", sa.String(24), nullable=True),
            sa.Column("charge_amount", sa.Numeric(12, 2), nullable=True),
            sa.Column("charge_accepted_at", sa.DateTime(timezone=False), nullable=True),
            # S4a's vocabulary, read not re-seeded. VALUES, never ids.
            sa.Column("waiting_on_party", sa.String(150), nullable=True),
            sa.Column("waiting_on_reason", sa.String(150), nullable=True),
            sa.Column("waiting_since", sa.DateTime(timezone=False), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
        )
        op.create_index(
            "ix_service_jobs_source",
            "service_jobs",
            ["source_entity_type", "source_entity_id"],
        )

    if not _has_table(bind, "service_job_assignments"):
        op.create_table(
            "service_job_assignments",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column(
                "service_job_id",
                UUID(as_uuid=False),
                sa.ForeignKey("service_jobs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "technician_id",
                UUID(as_uuid=False),
                sa.ForeignKey("technicians.id", ondelete="SET NULL"),
                nullable=True,
            ),
            # A rejected attempt is KEPT rather than overwritten (R12): the history is what
            # excludes it from the technician's attend-time metric, and a metric that
            # punishes the wrong person is worse than no metric.
            sa.Column("state", sa.String(20), nullable=True),
            sa.Column("assigned_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(
            "ix_service_job_assignments_job", "service_job_assignments", ["service_job_id"]
        )

    if not _has_table(bind, "case_cost_lines"):
        op.create_table(
            "case_cost_lines",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            # Polymorphic like the job: a cost belongs to the CASE, and cases are not only
            # complaints.
            sa.Column("source_entity_type", sa.String(40), nullable=False),
            sa.Column("source_entity_id", UUID(as_uuid=False), nullable=False),
            sa.Column(
                "external_provider_id",
                UUID(as_uuid=False),
                sa.ForeignKey("external_providers.id", ondelete="SET NULL"),
                nullable=True,
            ),
            # labour | parts | travel. One number per complaint does not answer the
            # costing question this requirement came from (AC-M29).
            sa.Column("cost_kind", sa.String(24), nullable=False),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("currency", sa.String(3), nullable=True),
            sa.Column("incurred_on", sa.Date(), nullable=True),
            # Recording needs no approval (AC-M31): it is bookkeeping, and an approval
            # queue for a RM80 callout adds friction where CS already gates the case.
            sa.Column("recorded_by", sa.Text(), nullable=True),
            sa.Column("recorded_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(
            "ix_case_cost_lines_source", "case_cost_lines", ["source_entity_type", "source_entity_id"]
        )


def downgrade() -> None:
    for name in (
        "case_cost_lines",
        "service_job_assignments",
        "service_jobs",
        "external_providers",
        "technicians",
    ):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {name} CASCADE"))
