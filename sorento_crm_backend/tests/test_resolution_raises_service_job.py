"""The resolution decides whether somebody has to go to the site.

Today Agnes picks a resolution and then has to remember, unaided, whether that particular
resolution means a technician is needed - and press a second button if it does. The table
of which-resolution-implies-a-visit exists only in her head, so the visit depends on her
recalling it while working a queue. A missed press is a consumer waiting for a van that was
never dispatched, and nothing on the screen looks wrong.

So the flag lives on the resolution (AC-V1) and setting a requiring resolution raises the
job (AC-V2). The rest of these tests are about the ways that could go wrong: raising two
jobs for one case, raising one for a case that already has somebody going, or losing a
clinical decision because dispatch failed.

Run: venv/bin/python -m pytest tests/test_resolution_raises_service_job.py -q -p no:randomly
"""
from __future__ import annotations

import uuid

import pytest

from app.models.complaint_master_data import ComplaintResolution
from app.models.complaints import Complaint
from app.models.service_jobs import ServiceJob
from app.schemas.complaints import ComplaintUpdate
from app.services import service_job_intake, service_job_service
from app.services.complaints_service import ComplaintService
from tests._pg_fixture import pg_session, unique_code


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


def _resolution(db, *, requires: bool) -> ComplaintResolution:
    row = ComplaintResolution(
        id=str(uuid.uuid4()),
        name=unique_code("RES"),
        requires_service_job=requires,
    )
    db.add(row)
    db.flush()
    return row


def _complaint(db, **overrides) -> Complaint:
    overrides.setdefault("site_address", "12 Jalan Ujian, 43000 Kajang, Selangor, Malaysia")
    row = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=unique_code("CMP"),
        status="submitted",
        **overrides,
    )
    db.add(row)
    db.flush()
    return row


def _jobs_for(db, complaint) -> list[ServiceJob]:
    return (
        db.query(ServiceJob)
        .filter(
            ServiceJob.source_entity_type == "complaint",
            ServiceJob.source_entity_id == str(complaint.id),
        )
        .all()
    )


def _set_resolution(db, complaint, resolution) -> None:
    ComplaintService(db).update_complaint(
        str(complaint.id), ComplaintUpdate(resolution_id=str(resolution.id))
    )


class TestTheFlagItself:
    def test_a_resolution_defaults_to_not_needing_a_visit(self, db):
        """AC-V1. Silence must mean "no visit".

        The opposite default would raise a job for every resolution an admin adds and
        forgets to configure, which is a van dispatched by an omission.
        """
        row = ComplaintResolution(id=str(uuid.uuid4()), name=unique_code("RES"))
        db.add(row)
        db.flush()
        db.refresh(row)
        assert row.requires_service_job is False


class TestRaisingTheJob:
    def test_a_requiring_resolution_raises_one_job(self, db):
        # AC-V2.
        complaint = _complaint(db)
        _set_resolution(db, complaint, _resolution(db, requires=True))

        jobs = _jobs_for(db, complaint)
        assert len(jobs) == 1
        assert service_job_service._status_key(db, jobs[0]) == "proposed"

    def test_the_job_carries_the_site_the_complaint_reported(self, db):
        """AC-V2, and AC-B3 behind it.

        The site is what was REPORTED, never the customer record's address: a dealer's
        owner reporting a fault in his own home would otherwise send a technician to a shop.
        """
        complaint = _complaint(db, site_address="9 Lorong Rumah, 43300 Kajang")
        _set_resolution(db, complaint, _resolution(db, requires=True))

        assert _jobs_for(db, complaint)[0].site_address == "9 Lorong Rumah, 43300 Kajang"

    def test_a_non_requiring_resolution_raises_nothing(self, db):
        # AC-V5. Advice given, goods swapped at the dealer - nobody travels.
        complaint = _complaint(db)
        _set_resolution(db, complaint, _resolution(db, requires=False))

        assert _jobs_for(db, complaint) == []


class TestNotRaisingTwice:
    def test_re_saving_the_same_resolution_does_not_raise_a_second_job(self, db):
        """AC-V3. A duplicate job reads as a REVISIT in every report that counts them.

        Agnes saves a complaint more than once - correcting a phone number, adding a
        note - and every one of those saves carries the resolution again.
        """
        complaint = _complaint(db)
        resolution = _resolution(db, requires=True)
        _set_resolution(db, complaint, resolution)
        _set_resolution(db, complaint, resolution)

        assert len(_jobs_for(db, complaint)) == 1

    def test_a_manually_raised_job_stops_the_automatic_one(self, db):
        # Same rule from the other direction: Agnes pressing the button first must not
        # mean two vans.
        complaint = _complaint(db)
        service_job_service.create_job(
            db,
            source_entity_type="complaint",
            source_entity_id=str(complaint.id),
            site_address=complaint.site_address,
        )
        db.flush()

        _set_resolution(db, complaint, _resolution(db, requires=True))

        assert len(_jobs_for(db, complaint)) == 1

    def test_a_cancelled_job_is_not_a_visit_so_a_new_one_is_raised(self, db):
        """AC-V4. Cancelled means nobody is going.

        Treating it as "already has a job" would leave a complaint whose only visit was
        called off with no way to get another except by hand - which is the state this
        slice exists to remove.
        """
        complaint = _complaint(db)
        job = service_job_service.create_job(
            db,
            source_entity_type="complaint",
            source_entity_id=str(complaint.id),
            site_address=complaint.site_address,
        )
        service_job_service._move_to(db, job, "cancelled")
        db.flush()

        _set_resolution(db, complaint, _resolution(db, requires=True))

        assert len(_jobs_for(db, complaint)) == 2


class TestNotLosingTheDecision:
    def test_the_resolution_saves_even_when_dispatch_fails(self, db, monkeypatch):
        """AC-V6. The clinical decision is not lost to a dispatch problem.

        Numbering can be unconfigured and the status graph can be unseeded. Either would
        raise from `create_job`, and letting that propagate would refuse to record what
        the technical team decided - the more valuable of the two facts.
        """
        def boom(*_args, **_kwargs):
            raise RuntimeError("numbering rule missing")

        # Patched where it is USED, not where it is defined. Pointing this at
        # `service_job_service` instead made the test pass while the job was raised
        # perfectly normally - green, and proving nothing.
        monkeypatch.setattr(service_job_intake, "raise_job_for_source", boom)

        complaint = _complaint(db)
        resolution = _resolution(db, requires=True)
        _set_resolution(db, complaint, resolution)

        db.refresh(complaint)
        assert complaint.resolution_id == str(resolution.id)
        assert _jobs_for(db, complaint) == []  # the failure really happened

    def test_clearing_the_resolution_never_deletes_a_job(self, db):
        """AC-V5. Somebody may already have been dispatched.

        Un-setting a resolution is a record correction; cancelling a visit is a phone call
        to a consumer. Conflating them would silently strand a technician.
        """
        complaint = _complaint(db)
        _set_resolution(db, complaint, _resolution(db, requires=True))
        assert len(_jobs_for(db, complaint)) == 1

        ComplaintService(db).update_complaint(
            str(complaint.id), ComplaintUpdate(resolution_id=None)
        )

        assert len(_jobs_for(db, complaint)) == 1


class TestTheFlagReachesTheFrontend:
    def test_the_list_endpoint_carries_the_flag(self, db):
        """The manual-dict-builder trap, caught in the act.

        `list_resolutions` hand-builds its response dict field by field, so a column that
        exists on the model, in the schema and in the database is still dropped unless it
        is named there. It was: the detail endpoint returned the real value while the list
        returned the schema default, so every resolution read as "does not raise a job"
        while the database said otherwise - and the admin screen that exists to show this
        setting showed the opposite of the truth.

        Asserted against the SERVICE, because that is where the dict is built. A schema
        test would pass against the same bug.
        """
        from app.services.complaint_master_data_service import ComplaintResolutionService

        resolution = _resolution(db, requires=True)
        listed = ComplaintResolutionService(db).list_resolutions(
            page=1, limit=200, query=resolution.name
        )
        row = next(r for r in listed["data"] if r["id"] == resolution.id)
        assert row["requires_service_job"] is True
