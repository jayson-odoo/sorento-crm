"""Seed the service-job status graph and its running-number rule.

No DDL. Migration 325 made the tables; this puts the seven states, their edges, and one
numbering rule into them.

**The seed is a service call, not a list of INSERTs.** Same function the application and
its tests use, so the graph cannot drift between what a test asserts and what a deploy
creates. `061_seed_rbac_permissions` established the idiom and `310_seed_complaint_graph`
followed it. It is also converging ("set where mismatch"), so a re-run repairs a drifted
label or flag rather than skipping it: insert-if-absent can never correct a prior bad run,
which is the only reason anybody re-runs a seed.

**The number format deviates from the plan's literal text, deliberately.** The plan wrote
`SV{year}/{month}-`, which the numbering service would render as `SV2026/8-0001`: an
unpadded month sorts `10` before `8` in every list and export, and the four-digit year
makes the number longer than every sibling document type. This seeds `SV{yy}/{month:02d}-`
with a MONTHLY reset, giving `SV26/08-0001` - the plan's year-and-month intent, the
repo's `{yy}` convention (CMP26-, SI26-, PR26-), and a number that sorts.

The rule is `enabled` and admin-editable in System Management -> Running Numbers, so if
Sorento wants the four-digit year they change it there without a deploy.

Revision ID: 326_seed_service_job_graph
Revises: 325_service_jobs
"""
from alembic import op
from sqlalchemy.orm import Session

revision = "326_seed_service_job_graph"
down_revision = "325_service_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.service_job_status_graph import seed_service_job_status_graph

    session = Session(bind=op.get_bind())
    try:
        seed_service_job_status_graph(session)
        session.commit()
    finally:
        session.close()

    # Idempotent: only seed if a rule is not already present, so an admin's edited
    # prefix survives a re-run.
    op.execute(
        """
        INSERT INTO document_numbering_rules (
            id, doc_type, enabled, prefix_template, number_digits,
            next_value, start_value, reset_policy, last_reset_key
        )
        SELECT
            gen_random_uuid()::text, 'service_job', true, 'SV{yy}/{month:02d}-', 4,
            1, 1, 'monthly', NULL
        WHERE NOT EXISTS (
            SELECT 1 FROM document_numbering_rules WHERE doc_type = 'service_job'
        )
        """
    )


def downgrade() -> None:
    """Drops only the numbering rule.

    The graph rows stay, for the same reason `310_seed_complaint_graph` leaves the
    complaint graph: deleting statuses would strand every job pointing at one, and the
    engine's own guard fails closed on a status outside the graph. They are inert
    configuration that a re-run of `upgrade` converges anyway.
    """
    op.execute("DELETE FROM document_numbering_rules WHERE doc_type = 'service_job'")
