"""Seed the complaint default status graph on the adopted status engine.

No DDL. The tables come from ``308_status_engine`` (the engine this branch ADOPTS
rather than porting a second time, see ``documentation/adr/0012``); this only puts
the ``complaint`` entity's 12 rungs and 18 edges into them.

Why the seed lives in a service and is merely called here, rather than being
spelled out as INSERTs: it is the same function the application and its tests use,
so the graph cannot drift between what a test asserts and what a deploy creates.
The RBAC permission seed (``061_seed_rbac_permissions``) established the idiom.

Re-runnable on purpose. ``seed_complaint_status_graph`` is "set where mismatch",
not "insert where absent", so a second run repairs a drifted label, colour or flag
in place rather than skipping it. Insert-if-absent can never correct a prior bad
run, which is why this repo requires the converging form.

The 12 keys are reproduced verbatim from live code, including ``resolved`` (a live
comparison target in ``_VOID_BLOCKED_STATUSES`` and in both frontend pill maps)
and ``voided`` (assigned in code, never yet reached). ``complaints.status`` stays a
plain VARCHAR holding the key: no ``status_id`` FK is added and the live rows are
not rewritten, which is what keeps registration a behavioural no-op.

Revision ID: 310_seed_complaint_graph
Revises: 309_merge_status_engine
Create Date: 2026-08-01

"""
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "310_seed_complaint_graph"
down_revision = "309_merge_status_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.complaint_status_graph import seed_complaint_status_graph

    session = Session(bind=op.get_bind())
    try:
        seed_complaint_status_graph(session)
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    """Deliberately empty.

    Deleting the graph would strand any complaint whose status key no longer
    resolves, and the engine's own guard already fails closed on a status outside
    the graph. Leaving the rows is the safe direction: they are inert
    configuration that a re-run of ``upgrade`` converges anyway.
    """
