"""S6 - what a Service Job is allowed to do, and the two facts the metrics rest on.

The foundation gate (`test_service_jobs_foundation.py`) defends the SHAPE. This one
defends the BEHAVIOUR, and every assertion here traces to a sentence somebody at Sorento
actually said.

**"Service Date: TBA" is not a Confirmed job** (AC-F5). This is the whole reason the slice
has a state machine rather than a date column. A job that reads Confirmed with no date has
told CS it is handled, and nobody chases it; the office finds out when the consumer calls
back. So `confirm()` refuses without BOTH a date and a recorded customer agreement, and two
tests below prove each half separately, because a guard that only checks the date passes a
test that supplies both.

**A rejected visit is kept, never overwritten** (R12). The consumer cancels, the job goes
back to Proposed, and the attempt stays in history - because the technician did nothing
wrong and S9's attend-time metric has to be able to exclude it. A metric that punishes
somebody for a customer's cancellation is worse than no metric, and it is worse precisely
because it looks like data.

**Attend time is the job's own subtraction** (AC-F21 to AC-F23). Form SLA resolves
assignees through `agent_teams -> team_members -> users`, and a Technician is deliberately
not a user, so no tracker can see one. The job holds its clocks and the metric reads them.

Run: venv/bin/python -m pytest tests/test_service_job_dispatch.py -q -p no:randomly
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402,F401

from ._pg_fixture import TEST_PREFIX, blank_session  # noqa: E402

pytestmark = pytest.mark.usefixtures("db")


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def graph(db):
    """The default graph, seeded once per test. Every transition below needs it."""
    from app.services.service_job_status_graph import seed_service_job_status_graph

    seed_service_job_status_graph(db)
    db.flush()


@pytest.fixture
def job(db, graph):
    from app.services.service_job_service import create_job

    return create_job(
        db,
        source_entity_type="complaint",
        source_entity_id=str(uuid.uuid4()),
        site_address=f"{TEST_PREFIX} 12 Jalan Damai, Shah Alam",
        site_contact_name=f"{TEST_PREFIX} Consumer",
        site_contact_phone="+60127770099",
    )


@pytest.fixture
def technician(db):
    from app.models.service_jobs import Technician

    row = Technician(
        id=str(uuid.uuid4()),
        name=f"{TEST_PREFIX} Technician",
        phone="+60123334455",
        employment_type="employee",
    )
    db.add(row)
    db.flush()
    return row


def _key(db, job):
    from app.models.status import Status

    if not job.status_id:
        return None
    row = db.query(Status).filter(Status.id == job.status_id).first()
    return row.key if row else None


# ================================================================= the graph


def test_the_graph_starts_a_job_at_proposed(db, graph, job):
    """A new job is a proposal, not a commitment. Nothing has been agreed with anybody
    at the moment CS raises it.
    """
    assert _key(db, job) == "proposed"


def test_the_entity_rides_the_engine_on_its_status_id_column(db, graph):
    """Unlike complaints, `service_jobs.status_id` is a real FK, so the entity uses the
    engine's default `status_attr` rather than a key-valued VARCHAR.
    """
    from app.services.service_job_status_graph import (
        SERVICE_JOB_ENTITY_TYPE,
        register_service_job_status_entity,
    )
    from app.status_engine.registry import get_status_entity

    register_service_job_status_entity()
    entity = get_status_entity(SERVICE_JOB_ENTITY_TYPE)
    assert entity is not None
    assert entity.status_attr == "status_id"
    assert entity.record_label_attr == "job_number"


def test_the_graph_has_exactly_one_initial_status(db, graph):
    """`validate_graph` raises on a second flagged row, and it runs after every admin
    write - so two would 422 the first edit anybody made to a service-job status.
    """
    from app.services import status_service
    from app.services.service_job_status_graph import SERVICE_JOB_ENTITY_TYPE

    status_service.validate_graph(db, SERVICE_JOB_ENTITY_TYPE)


def test_the_seed_repairs_a_drifted_row_rather_than_skipping_it(db, graph):
    """Insert-if-absent can never fix a prior bad run, which is the whole reason a seed
    gets re-run.
    """
    from app.models.status import Status
    from app.services.service_job_status_graph import (
        SERVICE_JOB_ENTITY_TYPE,
        seed_service_job_status_graph,
    )

    row = (
        db.query(Status)
        .filter(Status.entity_type == SERVICE_JOB_ENTITY_TYPE, Status.key == "confirmed")
        .first()
    )
    row.label = "Wrong"
    db.flush()

    seed_service_job_status_graph(db)
    db.flush()
    db.refresh(row)
    assert row.label != "Wrong"


# ====================================================== AC-F5, the two halves


def test_a_job_cannot_be_confirmed_without_a_date(db, graph, job):
    """"Service Date: TBA" is a Proposed job wearing a status that stops anybody chasing
    it. The whole point of the state machine.
    """
    from app.services.error_handler import AppException
    from app.services.service_job_service import confirm_job

    with pytest.raises(AppException):
        confirm_job(db, job.id, scheduled_from=None, customer_agreed_by="Consumer on WhatsApp")


def test_a_job_cannot_be_confirmed_without_a_recorded_agreement(db, graph, job):
    """The other half, asserted separately: a guard that only checked the date would pass
    a single test that supplied both.
    """
    from app.services.error_handler import AppException
    from app.services.service_job_service import confirm_job

    with pytest.raises(AppException):
        confirm_job(
            db,
            job.id,
            scheduled_from=datetime(2026, 8, 10, 10, 0),
            customer_agreed_by="   ",
        )


def test_a_job_with_both_becomes_confirmed_and_starts_its_clock(db, graph, job):
    from app.services.service_job_service import confirm_job

    confirmed = confirm_job(
        db,
        job.id,
        scheduled_from=datetime(2026, 8, 10, 10, 0),
        customer_agreed_by="Consumer agreed on WhatsApp 2026-08-04",
    )
    assert _key(db, confirmed) == "confirmed"
    # The clock the attend-time metric subtracts from.
    assert confirmed.confirmed_at is not None


# ============================================ R12, a rejected visit is kept


def test_a_rejected_visit_returns_the_job_to_proposed(db, graph, job, technician):
    from app.services.service_job_service import assign_technician, confirm_job, reject_visit

    confirm_job(
        db,
        job.id,
        scheduled_from=datetime(2026, 8, 10, 10, 0),
        customer_agreed_by="Consumer agreed",
    )
    assign_technician(db, job.id, technician.id)
    reject_visit(db, job.id, reason="Consumer asked to postpone")

    assert _key(db, job) == "proposed"


def test_the_rejected_attempt_survives_in_history(db, graph, job, technician):
    """Never overwritten. The row is what lets S9 exclude the attempt from the
    technician's metric, and the exclusion has to be explicit in the query rather than
    assumed - which is impossible if the row is gone.
    """
    from app.models.service_jobs import ServiceJobAssignment
    from app.services.service_job_service import assign_technician, confirm_job, reject_visit

    confirm_job(
        db,
        job.id,
        scheduled_from=datetime(2026, 8, 10, 10, 0),
        customer_agreed_by="Consumer agreed",
    )
    assign_technician(db, job.id, technician.id)
    reject_visit(db, job.id, reason="Consumer asked to postpone")

    rows = (
        db.query(ServiceJobAssignment)
        .filter(ServiceJobAssignment.service_job_id == job.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].state == "rejected"


def test_a_second_attempt_is_a_second_row_not_an_edit(db, graph, job, technician):
    """Reassigning after a rejection must not silently rewrite who was sent the first
    time. Two attempts is a fact about the case.
    """
    from app.models.service_jobs import ServiceJobAssignment
    from app.services.service_job_service import assign_technician, confirm_job, reject_visit

    confirm_job(
        db,
        job.id,
        scheduled_from=datetime(2026, 8, 10, 10, 0),
        customer_agreed_by="Consumer agreed",
    )
    assign_technician(db, job.id, technician.id)
    reject_visit(db, job.id, reason="Consumer asked to postpone")
    assign_technician(db, job.id, technician.id)

    rows = (
        db.query(ServiceJobAssignment)
        .filter(ServiceJobAssignment.service_job_id == job.id)
        .all()
    )
    assert len(rows) == 2
    assert {row.state for row in rows} == {"rejected", "assigned"}


def test_a_rejection_attributes_the_wait_to_the_customer(db, graph, job, technician):
    """S4a's vocabulary, and its VALUES rather than its ids. The consumer postponed, so
    the case is not sitting on Sorento, and the waiting report has to say so.
    """
    from app.services.service_job_service import assign_technician, confirm_job, reject_visit

    confirm_job(
        db,
        job.id,
        scheduled_from=datetime(2026, 8, 10, 10, 0),
        customer_agreed_by="Consumer agreed",
    )
    assign_technician(db, job.id, technician.id)
    reject_visit(db, job.id, reason="Consumer asked to postpone")

    assert job.waiting_on_party == "customer"
    assert job.waiting_on_reason == "awaiting_visit_date"
    assert job.waiting_since is not None


def test_the_wait_clears_the_moment_a_new_date_is_agreed(db, graph, job, technician):
    """A case still marked "waiting on the customer" after the customer answered is the
    reason waiting reports stop being believed.
    """
    from app.services.service_job_service import assign_technician, confirm_job, reject_visit

    confirm_job(
        db,
        job.id,
        scheduled_from=datetime(2026, 8, 10, 10, 0),
        customer_agreed_by="Consumer agreed",
    )
    assign_technician(db, job.id, technician.id)
    reject_visit(db, job.id, reason="Consumer asked to postpone")
    confirm_job(
        db,
        job.id,
        scheduled_from=datetime(2026, 8, 14, 10, 0),
        customer_agreed_by="Consumer agreed the new date",
    )

    assert job.waiting_on_party is None
    assert job.waiting_since is None


# ==================================================== the job's own clocks


def test_arriving_and_completing_stamp_the_job_not_a_tracker(db, graph, job, technician):
    from app.services.service_job_service import (
        arrive_at_site,
        assign_technician,
        complete_job,
        confirm_job,
        start_travel,
    )

    confirm_job(
        db,
        job.id,
        scheduled_from=datetime(2026, 8, 10, 10, 0),
        customer_agreed_by="Consumer agreed",
    )
    assign_technician(db, job.id, technician.id)
    start_travel(db, job.id)
    arrive_at_site(db, job.id)
    assert job.arrived_at is not None

    complete_job(db, job.id)
    assert job.completed_at is not None
    assert _key(db, job) == "completed"


def test_attend_time_is_confirmed_to_arrived(db, graph, job):
    """AC-F22. CS is accountable for a confirmed date, the technician for arriving - so
    the measurement starts where the technician's responsibility does.
    """
    from app.services.service_job_service import attend_seconds

    job.confirmed_at = datetime(2026, 8, 10, 9, 0)
    job.arrived_at = datetime(2026, 8, 10, 11, 30)
    assert attend_seconds(job) == 2.5 * 3600


def test_attend_time_is_nothing_rather_than_zero_when_the_job_has_not_arrived(db, graph, job):
    """Zero would enter the average as a perfect score for a visit that never happened."""
    from app.services.service_job_service import attend_seconds

    job.confirmed_at = datetime(2026, 8, 10, 9, 0)
    job.arrived_at = None
    assert attend_seconds(job) is None


def test_a_rejected_attempt_is_excluded_from_the_technician_metric(db, graph, technician):
    """R12's real consequence, and the reason the rejected row is kept rather than
    deleted: the exclusion is explicit in the query.
    """
    from app.services.service_job_service import (
        arrive_at_site,
        assign_technician,
        confirm_job,
        create_job,
        reject_visit,
        technician_attend_samples,
    )

    cancelled = create_job(
        db, source_entity_type="complaint", source_entity_id=str(uuid.uuid4())
    )
    confirm_job(
        db,
        cancelled.id,
        scheduled_from=datetime(2026, 8, 10, 10, 0),
        customer_agreed_by="Consumer agreed",
    )
    assign_technician(db, cancelled.id, technician.id)
    reject_visit(db, cancelled.id, reason="Consumer asked to postpone")

    attended = create_job(
        db, source_entity_type="complaint", source_entity_id=str(uuid.uuid4())
    )
    confirm_job(
        db,
        attended.id,
        scheduled_from=datetime(2026, 8, 11, 10, 0),
        customer_agreed_by="Consumer agreed",
    )
    assign_technician(db, attended.id, technician.id)
    arrive_at_site(db, attended.id)
    db.flush()

    samples = technician_attend_samples(db, technician.id)
    assert len(samples) == 1


# ============================================== the dispatch board (AC-F3, F4)


def test_the_board_groups_by_day_and_technician(db, graph, technician):
    """AC-F3. No availability grid, skills matrix or optimiser - the board is a day and
    the people working it, which is what a dispatcher already draws on paper.
    """
    from app.services.service_job_service import (
        assign_technician,
        confirm_job,
        create_job,
        dispatch_board,
    )

    job = create_job(db, source_entity_type="complaint", source_entity_id=str(uuid.uuid4()))
    confirm_job(
        db,
        job.id,
        scheduled_from=datetime(2026, 8, 10, 10, 0),
        customer_agreed_by="Consumer agreed",
    )
    assign_technician(db, job.id, technician.id)
    db.flush()

    board = dispatch_board(db, date_from=datetime(2026, 8, 10), date_to=datetime(2026, 8, 11))
    days = {row["day"] for row in board}
    assert "2026-08-10" in days
    assigned = [row for row in board if row["technician_id"] == technician.id]
    assert assigned and assigned[0]["jobs"]


def test_an_unassigned_confirmed_job_still_appears_on_the_board(db, graph):
    """A confirmed job nobody is going to is the single most important thing on the
    screen. Grouping it out of existence because it has no technician is how it gets
    missed until the consumer calls.
    """
    from app.services.service_job_service import confirm_job, create_job, dispatch_board

    job = create_job(db, source_entity_type="complaint", source_entity_id=str(uuid.uuid4()))
    confirm_job(
        db,
        job.id,
        scheduled_from=datetime(2026, 8, 10, 10, 0),
        customer_agreed_by="Consumer agreed",
    )
    db.flush()

    board = dispatch_board(db, date_from=datetime(2026, 8, 10), date_to=datetime(2026, 8, 11))
    unassigned = [row for row in board if row["technician_id"] is None]
    assert unassigned and unassigned[0]["jobs"]


def test_a_job_past_its_date_and_still_proposed_is_a_stall(db, graph):
    """AC-F4. The date passed and nobody agreed anything: the case is drifting, and the
    board says so with the elapsed time rather than leaving it to be noticed.
    """
    from app.services.service_job_service import create_job, stalled_jobs

    job = create_job(db, source_entity_type="complaint", source_entity_id=str(uuid.uuid4()))
    job.scheduled_from = datetime.utcnow() - timedelta(days=3)
    db.flush()

    stalls = stalled_jobs(db, now=datetime.utcnow())
    mine = [row for row in stalls if row["service_job_id"] == job.id]
    assert mine, "A proposed job three days past its date is a stall."
    assert mine[0]["stalled_seconds"] > 2 * 86400


def test_a_confirmed_job_past_its_date_is_not_a_stall(db, graph):
    """It has an agreed date and an accountable technician. Reporting it as a stall would
    bury the jobs that genuinely have nobody behind them.
    """
    from app.services.service_job_service import confirm_job, create_job, stalled_jobs

    job = create_job(db, source_entity_type="complaint", source_entity_id=str(uuid.uuid4()))
    confirm_job(
        db,
        job.id,
        scheduled_from=datetime.utcnow() - timedelta(days=3),
        customer_agreed_by="Consumer agreed",
    )
    db.flush()

    stalls = stalled_jobs(db, now=datetime.utcnow())
    assert not [row for row in stalls if row["service_job_id"] == job.id]


# ================================================ money out (AC-M29 to M31)


def test_a_cost_line_is_recorded_without_an_approval_step(db, graph, job):
    """AC-M31. Bookkeeping, not a workflow. An approval queue for a RM80 callout adds
    friction exactly where CS already gates the case.
    """
    from app.services.service_job_service import record_cost_line

    line = record_cost_line(
        db,
        source_entity_type="complaint",
        source_entity_id=job.source_entity_id,
        cost_kind="labour",
        amount="80.00",
        recorded_by=f"{TEST_PREFIX} CS",
    )
    assert line.id
    assert line.cost_kind == "labour"


def test_a_cost_line_refuses_a_kind_it_cannot_report_on(db, graph, job):
    """AC-M29. Free-text kinds produce a costing report with a long tail of one-offs,
    which is the report Ms Tan already cannot get.
    """
    from app.services.error_handler import AppException
    from app.services.service_job_service import record_cost_line

    with pytest.raises(AppException):
        record_cost_line(
            db,
            source_entity_type="complaint",
            source_entity_id=job.source_entity_id,
            cost_kind="miscellaneous",
            amount="80.00",
        )


def test_case_costs_total_across_kinds(db, graph, job):
    from app.services.service_job_service import case_cost_total, record_cost_line

    for kind, amount in (("labour", "80.00"), ("parts", "45.50"), ("travel", "12.00")):
        record_cost_line(
            db,
            source_entity_type="complaint",
            source_entity_id=job.source_entity_id,
            cost_kind=kind,
            amount=amount,
        )
    db.flush()

    total = case_cost_total(db, "complaint", job.source_entity_id)
    assert float(total) == pytest.approx(137.50)


def test_money_out_does_not_touch_money_in(db, graph, job):
    """AC-M30. A warranty job is free to the consumer and still costs a plumber's fee.
    Recording the cost must leave chargeability exactly where CS left it.
    """
    from app.services.service_job_service import record_cost_line

    job.charge_state = "under_warranty"
    db.flush()

    record_cost_line(
        db,
        source_entity_type="complaint",
        source_entity_id=job.source_entity_id,
        cost_kind="labour",
        amount="80.00",
    )
    db.flush()
    db.refresh(job)
    assert job.charge_state == "under_warranty"
