"""S6 - raising a Service Job from the case that needs one.

The dispatch board existed before anything could put a job on it. This is the missing link,
and where it lives is the whole design question.

**The server copies the Site, not the client** (AC-B3, AC-M37). The Site is whatever was
REPORTED - a dealer's owner reporting a fault in his own home carries a dealer binding and a
residential address on the same row - and deriving it from the customer record sends a
technician to a shop. A client that posted the address it happened to have on screen would
be a second place that decision gets made, and the second place is always the one that is
wrong. So the caller names the case and the server reads the site off it.

**This module knows about complaints; `service_job_service` still must not.** ADR-0009 makes
the job requester-agnostic, and the AST guard in `test_service_jobs_foundation.py` keeps the
model honest. That guarantee only survives if the complaint-shaped knowledge lives somewhere
else, which is why this is its own file with a registry keyed by source type rather than an
`if source_entity_type == "complaint"` inside the service.

**A case can have more than one job.** A revisit is a second visit, not an edit of the first,
and the count is a fact about how badly the case went. So raising is not idempotent by
design - the guard against double-raising is that the section shows what already exists.

Run: venv/bin/python -m pytest tests/test_service_job_intake.py -q -p no:randomly
"""
from __future__ import annotations

import uuid

import pytest

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402,F401

from ._pg_fixture import TEST_PREFIX, blank_session  # noqa: E402


@pytest.fixture
def db():
    with blank_session() as session:
        from app.services.service_job_status_graph import seed_service_job_status_graph

        seed_service_job_status_graph(session)
        session.flush()
        yield session


@pytest.fixture
def complaint(db):
    """A complaint carrying a REPORTED site that differs from any customer record."""
    from app.models.complaints import Complaint

    row = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=f"{TEST_PREFIX}-CMP-0001",
        customer_name=f"{TEST_PREFIX} Dealer Sdn Bhd",
        customer_address="Lot 5, Jalan Industri (the DEALER's shop, not the site)",
        contact_person="Puan Aminah",
        contact_number="+60127770099",
        site_address="12 Jalan Damai, Shah Alam",
        site_contact_name="Puan Aminah",
        site_contact_phone="+60127770099",
        latitude="3.0738000",
        longitude="101.5183000",
        status="new",
    )
    db.add(row)
    db.flush()
    return row


def test_a_job_can_be_raised_from_a_complaint(db, complaint):
    from app.services.service_job_intake import raise_job_for_source

    job = raise_job_for_source(db, source_entity_type="complaint", source_entity_id=complaint.id)
    assert job.id
    assert job.source_entity_type == "complaint"
    assert job.source_entity_id == complaint.id


def test_the_reported_site_is_copied_not_the_customer_address(db, complaint):
    """AC-B3, and the reason this function exists at all.

    The complaint carries both: a dealer's shop in `customer_address` and the house the
    fault is in as the Site. Copying the wrong one sends a van to a shop, and the failure is
    invisible on screen because both are real addresses.
    """
    from app.services.service_job_intake import raise_job_for_source

    job = raise_job_for_source(db, source_entity_type="complaint", source_entity_id=complaint.id)
    assert job.site_address == "12 Jalan Damai, Shah Alam"
    assert "DEALER" not in (job.site_address or "")


def test_the_pin_is_copied_too_because_that_is_what_gets_navigated_to(db, complaint):
    """AC-M37. The address is for documents; the coordinates are what a technician taps."""
    from app.services.service_job_intake import raise_job_for_source

    job = raise_job_for_source(db, source_entity_type="complaint", source_entity_id=complaint.id)
    assert job.site_latitude is not None
    assert job.site_longitude is not None


def test_the_site_contact_is_carried_over(db, complaint):
    """Whoever is at the house. The technician phones this person, not the account."""
    from app.services.service_job_intake import raise_job_for_source

    job = raise_job_for_source(db, source_entity_type="complaint", source_entity_id=complaint.id)
    assert job.site_contact_name == "Puan Aminah"
    assert job.site_contact_phone == "+60127770099"


def test_a_complaint_with_no_site_still_raises_a_job(db):
    """Most live complaints predate the Site columns and hold nothing in them.

    Refusing would mean the feature only works for cases lodged after S1, which is nearly
    none of them. A job with a blank site is a job CS fills in; a job that cannot be raised
    is a phone call.
    """
    from app.models.complaints import Complaint
    from app.services.service_job_intake import raise_job_for_source

    bare = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=f"{TEST_PREFIX}-CMP-0002",
        customer_name=f"{TEST_PREFIX} Old Case",
        status="new",
    )
    db.add(bare)
    db.flush()

    job = raise_job_for_source(db, source_entity_type="complaint", source_entity_id=bare.id)
    assert job.id
    assert job.site_address is None


def test_an_unknown_source_type_is_refused_by_name(db):
    """The registry is the list of cases a job can be raised from. An unregistered type is a
    wiring mistake, and saying so beats creating a job pointing at nothing.
    """
    from app.services.error_handler import AppException
    from app.services.service_job_intake import raise_job_for_source

    with pytest.raises(AppException) as caught:
        raise_job_for_source(
            db, source_entity_type="purchase_request", source_entity_id=str(uuid.uuid4())
        )
    assert "purchase_request" in str(caught.value.detail)


def test_a_missing_case_is_refused_rather_than_orphaning_a_job(db):
    from app.services.error_handler import AppException
    from app.services.service_job_intake import raise_job_for_source

    with pytest.raises(AppException):
        raise_job_for_source(
            db, source_entity_type="complaint", source_entity_id=str(uuid.uuid4())
        )


def test_a_second_job_on_the_same_case_is_allowed(db, complaint):
    """A revisit is a second visit, not an edit of the first, and how many visits a case
    took is one of the few honest measures of how badly it went. Silently returning the
    first job would erase that.
    """
    from app.services.service_job_intake import raise_job_for_source
    from app.services.service_job_service import jobs_for_source

    first = raise_job_for_source(db, source_entity_type="complaint", source_entity_id=complaint.id)
    second = raise_job_for_source(db, source_entity_type="complaint", source_entity_id=complaint.id)
    assert first.id != second.id
    assert len(jobs_for_source(db, "complaint", complaint.id)) == 2


def test_the_new_job_starts_proposed(db, complaint):
    """Nothing has been agreed with anybody at the moment CS raises it."""
    from app.services.service_job_intake import raise_job_for_source
    from app.services.service_job_service import status_key_of

    job = raise_job_for_source(db, source_entity_type="complaint", source_entity_id=complaint.id)
    assert status_key_of(db, job) == "proposed"


def test_the_service_job_service_still_knows_nothing_about_complaints():
    """The reason this module exists. `service_job_service` stays requester-agnostic
    (ADR-0009); the complaint-shaped knowledge lives here, behind a registry.
    """
    import ast
    import inspect

    from app.services import service_job_service

    tree = ast.parse(inspect.getsource(service_job_service))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)

    offenders = [m for m in imported if "models.complaints" in m]
    assert not offenders, (
        f"service_job_service imports {offenders}. Source-specific knowledge belongs in "
        "service_job_intake, or the job stops being requester-agnostic."
    )
