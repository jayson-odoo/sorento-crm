"""S6 - the Service Job's shape, and the four rules that hold it apart from the Complaint.

A Service Job is *someone going to a site to do something about it*. The Complaint is the
case. Keeping them separate is the whole of ADR-0009, and every assertion below defends a
boundary that is cheap to hold now and expensive to recover once code assumes otherwise.

1. **A Service Job is requester-agnostic** (ADR-0009, AC-A6). It points at its source with
   `(source_entity_type, source_entity_id)` and declares NO foreign key to `complaints`.
   Today every job comes from a complaint, which is exactly why the FK is tempting - and
   exactly why adding it would silently make "a job for a dealer's own showroom" or "a job
   raised from a stock inquiry" a schema migration instead of a new row. The guard is
   structural because a code review cannot catch the FK somebody adds in eight months.

2. **A Technician is not a user.** No `users` row is ever created for one (AC-F8, AC-F21).
   That is what forces technician metrics onto the job's own columns rather than the SLA
   engine, since form SLA resolves assignees through `agent_teams -> team_members -> users`.
   A technician with a login would quietly re-open that door.

3. **Money out is independent of money in** (AC-M30). A warranty job can be free to the
   consumer and still cost Sorento a plumber's fee, so `case_cost_lines` is never part of
   `charge_state` and neither derives from the other. Ms Tan's costing question is the
   requirement's whole origin, and one number per complaint does not answer it - which is
   why a cost line says what it was FOR (labour / parts / travel, AC-M29).

4. **The waiting vocabulary is S4a's, and there is exactly one.** S6 reads the same two
   lookup sets rather than seeding its own. Two vocabularies for "who are we waiting on"
   means two reports that disagree, and the disagreement surfaces in a board meeting.

Run: venv/bin/python -m pytest tests/test_service_jobs_foundation.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import uuid

import pytest

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402,F401

from ._pg_fixture import TEST_PREFIX, blank_session  # noqa: E402

MODELS = "app.models.service_jobs"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _models():
    if importlib.util.find_spec(MODELS) is None:
        raise AssertionError(
            f"{MODELS} does not exist. The Service Job is its own entity, not a column on "
            "the Complaint: ADR-0009 makes it requester-agnostic so a job can outlive the "
            "one source that happens to raise every job today."
        )
    return importlib.import_module(MODELS)


# ======================================================= 1. requester-agnostic


def test_a_service_job_points_at_its_source_without_a_foreign_key(db):
    """AC-A6, asserted structurally because a review cannot catch a later FK.

    Every job today comes from a complaint. That is the reason the FK is tempting and the
    reason it must not exist: with it, the first job raised from anything else becomes a
    migration rather than a row.
    """
    ServiceJob = getattr(_models(), "ServiceJob", None)
    assert ServiceJob is not None, "S6 needs a ServiceJob model."

    columns = {c.name for c in ServiceJob.__table__.columns}
    assert {"source_entity_type", "source_entity_id"} <= columns

    for fk in ServiceJob.__table__.foreign_keys:
        target = fk.column.table.name
        assert target != "complaints", (
            "service_jobs declares a foreign key to complaints. ADR-0009 makes the job "
            "requester-agnostic; the polymorphic pair is the link."
        )


def test_the_service_job_module_imports_nothing_from_complaints():
    """The other half of AC-A6. A model with no FK still couples if it imports the class.

    Parsed as an AST rather than grepped: the first version searched the raw source and
    matched the module's own docstring explaining the rule, so it failed on a file that
    obeyed it. A guard that cannot tell an import from a sentence about imports is a guard
    that gets deleted the first time it cries wolf.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(_models()))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)

    offenders = [m for m in imported if m.startswith("app.models.complaints")]
    assert not offenders, (
        f"The service-jobs module imports {offenders}. The FK guard above is worth nothing "
        "if the module reaches for the class anyway."
    )


def test_the_source_pair_is_indexed(db):
    """Every read starts 'the jobs for this case'. Without the index that is a sequential
    scan of every job Sorento has ever done, on the screen CS opens most.
    """
    ServiceJob = _models().ServiceJob
    indexed = {
        tuple(c.name for c in ix.columns) for ix in ServiceJob.__table__.indexes
    }
    assert any(
        "source_entity_type" in cols and "source_entity_id" in cols for cols in indexed
    ), "service_jobs needs an index on (source_entity_type, source_entity_id)."


# =========================================================== 2. not a user


def test_a_technician_is_not_a_user(db):
    """No `users` row is ever created for a technician (AC-F8).

    This is what keeps technician metrics on the job's own columns: form SLA resolves
    assignees through agent_teams -> team_members -> users, so a technician with a login
    would re-open a door AC-F21 deliberately closed.
    """
    Technician = getattr(_models(), "Technician", None)
    assert Technician is not None, "S6 needs a Technician model."

    for fk in Technician.__table__.foreign_keys:
        assert fk.column.table.name != "users", (
            "technicians references users. A Technician is deliberately not a user - that "
            "is the premise the whole clocks-off-the-SLA-engine decision rests on."
        )


def test_a_technician_is_reachable_on_whatsapp_rather_than_by_login(db):
    """The technician portal is a link they open, not an account they sign in to."""
    Technician = _models().Technician
    columns = {c.name for c in Technician.__table__.columns}
    assert "respond_contact_id" in columns
    assert "phone" in columns


def test_a_technician_can_be_an_employee_or_a_contractor(db):
    """The discovery study shows the role blurring - an outstation technician may be
    somebody else's staff. Modelling only employees would make the common case unstorable.
    """
    Technician = _models().Technician
    assert "employment_type" in {c.name for c in Technician.__table__.columns}


# ================================================== 3. money out, money in


def test_a_cost_line_is_not_attached_to_chargeability(db):
    """AC-M30. A warranty job is free to the consumer AND costs Sorento a plumber fee.

    If a cost line carried `charge_state`, or the job derived one from the other, that
    ordinary case would be unrepresentable.
    """
    CaseCostLine = getattr(_models(), "CaseCostLine", None)
    assert CaseCostLine is not None, "S6 needs a CaseCostLine model."

    columns = {c.name for c in CaseCostLine.__table__.columns}
    assert "charge_state" not in columns
    assert "charge_amount" not in columns


def test_a_cost_line_says_what_it_was_for(db):
    """AC-M29. One number per complaint does not answer the costing question that produced
    this requirement, so labour / parts / travel is part of the record, not a note.
    """
    CaseCostLine = _models().CaseCostLine
    assert "cost_kind" in {c.name for c in CaseCostLine.__table__.columns}


def test_a_cost_line_hangs_off_the_case_polymorphically(db):
    """Same shape as the job (ADR-0009): a cost belongs to the CASE, and cases are not
    only complaints.
    """
    CaseCostLine = _models().CaseCostLine
    columns = {c.name for c in CaseCostLine.__table__.columns}
    assert {"source_entity_type", "source_entity_id"} <= columns
    for fk in CaseCostLine.__table__.foreign_keys:
        assert fk.column.table.name != "complaints"


def test_an_external_provider_is_generic_rather_than_a_plumber_table(db):
    """AC-M28. The study already shows the role blurring - 'forward the details to the
    plumber; can be an outstation technician'. A `plumbers` table would need a sibling
    within the month.

    Deliberately NOT `suppliers`, which carries payment terms, lead times and SPO linkage
    and would couple after-sales to procurement for nothing.
    """
    ExternalProvider = getattr(_models(), "ExternalProvider", None)
    assert ExternalProvider is not None, "S6 needs an ExternalProvider model."
    assert "provider_type" in {c.name for c in ExternalProvider.__table__.columns}


# ============================================ 4. one waiting vocabulary, S4a's


def test_the_job_carries_the_waiting_columns_it_reads_from_s4a(db):
    """S4a's Ruling 1 puts these on the SLA tracker - and a Service Job deliberately runs
    NO tracker of its own (AC-F21), so the job carries them directly.

    Values, not ids, exactly as S4a stores them: the lookup binding validates bound columns
    against option VALUES, and an id column would fail that validation the first time
    anything wrote to it.
    """
    ServiceJob = _models().ServiceJob
    columns = {c.name for c in ServiceJob.__table__.columns}
    assert {"waiting_on_party", "waiting_on_reason", "waiting_since"} <= columns
    assert "waiting_on_reason_id" not in columns, (
        "A bound lookup column holds the option VALUE, never an id."
    )


def test_no_second_waiting_vocabulary_is_seeded(db):
    """One question, one answer set. Two vocabularies for 'who are we waiting on' produce
    two reports that disagree, and the disagreement surfaces in a board meeting.
    """
    from app.services.sla_waiting_service import seed_sla_waiting_lookups

    seed_sla_waiting_lookups(db)
    db.flush()

    module = _models()
    for name in dir(module):
        assert "seed_waiting" not in name.lower(), (
            f"{name} looks like a second waiting-vocabulary seeder. S6 reads S4a's."
        )


# ==================================================== the job's own clocks


def test_the_job_keeps_its_own_timestamps_rather_than_an_sla_tracker(db):
    """AC-F21 to AC-F23. Attend time is `confirmed_at` -> `arrived_at`, computed from the
    job, because the SLA engine cannot resolve a technician who is not a user.
    """
    ServiceJob = _models().ServiceJob
    columns = {c.name for c in ServiceJob.__table__.columns}
    assert {"proposed_at", "confirmed_at", "arrived_at", "completed_at"} <= columns


def test_a_job_cannot_be_confirmed_without_a_date_and_an_agreement(db):
    """AC-F5. 'Service Date: TBA' is not a Confirmed job - it is a Proposed one wearing a
    status that stops anybody chasing it.
    """
    ServiceJob = _models().ServiceJob
    columns = {c.name for c in ServiceJob.__table__.columns}
    assert {"scheduled_from", "customer_agreed_by"} <= columns


def test_the_site_is_copied_onto_the_job_rather_than_read_from_the_dealer(db):
    """AC-M37 / AC-B3. The Site is whatever was REPORTED. Deriving it from the customer
    record sends a technician to a shop.
    """
    ServiceJob = _models().ServiceJob
    columns = {c.name for c in ServiceJob.__table__.columns}
    assert {"site_address", "site_latitude", "site_longitude"} <= columns
