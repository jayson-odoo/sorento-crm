"""A service job you cannot find again.

The dispatch board is a DAY: it filters on `scheduled_from` inside a single date window.
That is the right question for a dispatcher at 8am and the wrong one for everybody else.
A job starts life Proposed with no date at all, so it belongs to no day and appeared on no
board; a job confirmed for last Tuesday left the board the moment it moved on. Raise a job,
look for it tomorrow, and it has vanished - which is what a user reported, and they were
right, even though the board's query is doing exactly what it says.

So the list is the fix, and these tests pin the part that made the bug possible: no date
window, every state, and a job with no date is included rather than sorted into nowhere.

Run: venv/bin/python -m pytest tests/test_service_job_list.py -q -p no:randomly
"""
from __future__ import annotations

import uuid

import pytest

from app.models.service_jobs import ServiceJob
from app.services import service_job_service
from tests._pg_fixture import pg_session, unique_code


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


def _status_id(db, key: str) -> str:
    row = service_job_service._status_by_key(db, key)
    assert row is not None, f"status {key} is not seeded"
    return row.id


def _job(db, *, key: str = "proposed", scheduled_from=None, **overrides) -> ServiceJob:
    job = ServiceJob(
        id=str(uuid.uuid4()),
        source_entity_type="complaint",
        source_entity_id=str(uuid.uuid4()),
        job_number=unique_code("SV"),
        status_id=_status_id(db, key),
        scheduled_from=scheduled_from,
        **overrides,
    )
    db.add(job)
    db.flush()
    return job


def _numbers(result) -> set[str]:
    return {job.job_number for job in result["data"]}


class TestFindingAJobThatIsOnNoDay:
    def test_a_job_with_no_date_is_listed(self, db):
        # The state every job starts in, and the one the board can never show.
        job = _job(db)
        assert job.job_number in _numbers(
            service_job_service.list_jobs(db, limit=500, query=job.job_number)
        )

    def test_a_job_scheduled_in_the_past_is_listed(self, db):
        from datetime import datetime

        job = _job(db, key="confirmed", scheduled_from=datetime(2020, 1, 1, 9, 0))
        assert job.job_number in _numbers(
            service_job_service.list_jobs(db, limit=500, query=job.job_number)
        )

    def test_a_cancelled_job_is_still_findable(self, db):
        # Terminal is not the same as deleted: somebody will ask what happened to it.
        job = _job(db, key="cancelled")
        assert job.job_number in _numbers(
            service_job_service.list_jobs(db, limit=500, query=job.job_number)
        )


class TestFiltering:
    def test_a_status_filter_narrows_to_that_status(self, db):
        proposed = _job(db, key="proposed")
        confirmed = _job(db, key="confirmed")
        found = _numbers(
            service_job_service.list_jobs(db, limit=500, status_keys=["confirmed"])
        )
        assert confirmed.job_number in found
        assert proposed.job_number not in found

    def test_an_unknown_status_key_matches_nothing_rather_than_everything(self, db):
        """A typo in a saved filter must not read as "no filter applied".

        Silently ignoring it would show the full list under a filter chip claiming to
        narrow it, which is worse than an empty result: the empty result is visibly wrong.
        """
        _job(db, key="proposed")
        assert service_job_service.list_jobs(db, status_keys=["nonsense"])["pagination"][
            "total"
        ] == 0

    def test_search_matches_the_job_number_and_the_site(self, db):
        marker = unique_code("SITE")
        job = _job(db, site_address=f"12 Jalan {marker}, Kajang")
        assert job.job_number in _numbers(
            service_job_service.list_jobs(db, limit=500, query=marker)
        )
        assert job.job_number in _numbers(
            service_job_service.list_jobs(db, limit=500, query=job.job_number)
        )


class TestOrdering:
    def test_a_job_with_no_date_sorts_last_rather_than_arbitrarily(self, db):
        """Sorting BY a date a row does not have puts it somewhere meaningless.

        Postgres defaults NULLs first on DESC, which would top the list with every
        undated job under a column claiming to be sorted by date. Last is at least honest.
        """
        from datetime import datetime

        dated = _job(db, key="confirmed", scheduled_from=datetime(2026, 6, 1, 9, 0))
        undated = _job(db)
        ordered = [
            job.job_number
            for job in service_job_service.list_jobs(
                db, limit=500, sort_field="scheduled_from", sort_dir="desc"
            )["data"]
            if job.job_number in {dated.job_number, undated.job_number}
        ]
        assert ordered == [dated.job_number, undated.job_number]

    def test_the_total_counts_every_match_not_just_the_page(self, db):
        for _ in range(3):
            _job(db, key="cancelled", site_address=f"ZZT-PAGE {unique_code('x')}")
        result = service_job_service.list_jobs(db, limit=1, query="ZZT-PAGE")
        assert result["pagination"]["total"] == 3
        assert len(result["data"]) == 1
