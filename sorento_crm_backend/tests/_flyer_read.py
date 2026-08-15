"""Run a queued flyer read inline, on the test's own session.

The read moved out of the request: both POSTs answer 202 and an RQ job does the
extraction (`documentation/plans/dealer-kit/PLAN-flyer-read-background-job.md`).
The suites that walk a flyer end to end must not therefore need Redis, a worker
process, or a second database session - so they queue the read the way the route
does, and then run it here.

Two seams make that possible, and they are the only two:

* ``flyer_reading_service._enqueue`` is a thin module-level function that does
  nothing but hand the job to RQ. Replaced here with a recorder, so the enqueue
  is asserted on rather than performed. The failure handling AROUND it
  (``_enqueue_or_fail``: mark the row failed, discard the staged object) is NOT
  replaced, which is what lets a test raise from this seam and exercise the real
  Redis-is-down path.
* ``read_flyer`` takes a keyword-only ``_db``. Given one it neither opens nor
  closes a session and restores the company scope it found, so the job runs
  inside the test's rolled-back transaction and everything it wrote is visible
  to the very next assertion.

Usage, in a suite's ``api`` fixture, beside ``patch_storage``::

    reads = patch_flyer_read(monkeypatch, db)

and then, after a POST::

    finish_reads()

``finish_reads`` is a module function rather than a method so a suite's
module-level ``_upload`` helper can call it without every test having to thread
the recorder through its fixture unpacking.
"""
from __future__ import annotations

import sys
from typing import Optional


class InlineFlyerRead:
    """Records every queued read, and runs them on the test's session.

    ``queued`` is the assertion surface for "one job, on the right queue, with
    the right arguments": each entry is
    ``(reading_id, staged_provider, staged_key)`` exactly as the route passed
    them. ``results`` holds what each run returned, so a test can check the job
    reported ``done`` / ``failed`` / ``gone`` without re-reading the row.
    """

    def __init__(self, db) -> None:
        self.db = db
        self.queued: list[tuple[str, Optional[str], Optional[str]]] = []
        self.results: list[dict] = []
        self._pending: list[tuple[str, Optional[str], Optional[str]]] = []

    def __call__(self, record, staged_provider, staged_key) -> str:
        """Stands in for ``_enqueue``, and returns what it returns: a job id."""
        entry = (str(record.id), staged_provider, staged_key)
        self.queued.append(entry)
        self._pending.append(entry)
        return f"zzt-job-{len(self.queued)}"

    def run_pending(self) -> list[dict]:
        """Run every read queued since the last call, oldest first."""
        pending, self._pending = self._pending, []
        results = [self.run(*entry) for entry in pending]
        return results

    def run(
        self,
        reading_id: str,
        staged_provider: Optional[str] = None,
        staged_key: Optional[str] = None,
    ) -> dict:
        """Run ONE read, exactly as the worker would."""
        from app.tasks.flyer_read_tasks import read_flyer

        result = read_flyer(reading_id, staged_provider, staged_key, _db=self.db)
        self.results.append(result)
        return result


def patch_flyer_read(monkeypatch, db) -> InlineFlyerRead:
    """Queue reads into a recorder instead of Redis, runnable on ``db``."""
    from app.services.dealer_kit import flyer_reading_service

    recorder = InlineFlyerRead(db)
    monkeypatch.setattr(flyer_reading_service, "_enqueue", recorder)
    # Set through monkeypatch so it is restored at teardown and one suite's
    # recorder can never be left visible to the next.
    monkeypatch.setattr(sys.modules[__name__], "_CURRENT", recorder)
    return recorder


def finish_reads() -> list[dict]:
    """Run every read the current test has queued and not yet run."""
    if _CURRENT is None:  # pragma: no cover - a fixture that forgot the patch
        raise AssertionError(
            "patch_flyer_read(monkeypatch, db) was never installed for this test"
        )
    return _CURRENT.run_pending()


def run_read_inline(db, reading_id: str, staged_provider=None, staged_key=None) -> dict:
    """Run a read by id, for a test that built the row itself."""
    from app.tasks.flyer_read_tasks import read_flyer

    return read_flyer(reading_id, staged_provider, staged_key, _db=db)


_CURRENT: Optional[InlineFlyerRead] = None

__all__ = [
    "InlineFlyerRead",
    "finish_reads",
    "patch_flyer_read",
    "run_read_inline",
]
