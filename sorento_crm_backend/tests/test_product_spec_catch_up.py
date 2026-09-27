"""S3 - the worker catches the catalogue up on a deploy that changed the shipped rules
(#1286, D10). UAC AC-S3.5, contract section 5.

`catch_up_on_worker_start()` runs once in `worker.py` start-up. It compares the stored
fingerprint (`product_spec_search_policy` row `_derived_rules_fingerprint` -
`product_spec_rederive._FINGERPRINT_KEY`, the SAME key `product_spec_rederive.py`
already reads/writes) with the running one and enqueues one catalogue re-read on
`imports` only when they differ.

Rather than guessing the exact hash algorithm the running fingerprint is computed
with (the contract only says "configured rules, scopes and caps, plus
DERIVATION_VERSION" - underspecified enough that hand-computing an expected value
would pin an implementation choice rather than the contract), both tests bootstrap
the "matches" case FROM the "differs" case: whatever the enqueued job stores when it
runs IS the current running fingerprint by construction, so calling
`catch_up_on_worker_start()` again immediately afterwards must enqueue nothing. This
is robust to whichever hash the coder picks.

Both run on a `blank_session` scratch schema (review S-9, fix round 2): every
`SessionLocal()` the catch-up and its job open is pointed at the test's own session, so
the job re-reads the scratch catalogue rather than the local prod copy, and the
fingerprint row it stores is rolled back with everything else instead of deleting the
real one. LESSONS: seed your own chain, never touch rows you did not make.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests._pg_fixture import blank_session

_FINGERPRINT_KEY = "_derived_rules_fingerprint"


class _Borrowed:
    """A context manager lending the test's session without closing it."""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        return False


@pytest.fixture
def scratch(monkeypatch):
    import app.database as database
    from app.services import product_spec_rederive

    with blank_session() as db:
        monkeypatch.setattr(database, "SessionLocal", lambda: _Borrowed(db))
        monkeypatch.setattr("app.tasks.product_spec_tasks.SessionLocal", lambda: _Borrowed(db))
        monkeypatch.setattr(product_spec_rederive, "_already_queued", lambda job_id: False)
        calls: list[tuple] = []

        def _fake_enqueue(func, *args, **kwargs):
            calls.append((func, args, kwargs))
            return "job-1"

        monkeypatch.setattr(product_spec_rederive, "enqueue_job", _fake_enqueue, raising=False)
        yield db, calls


def _stored_fingerprint(db) -> str | None:
    return db.execute(
        text("SELECT help_text FROM product_spec_search_policy WHERE policy_key = :key"),
        {"key": _FINGERPRINT_KEY},
    ).scalar()


def _run_queued(call) -> None:
    """Run the queued job the way the worker would: queue options are not its arguments."""
    func, args, kwargs = call
    func(*args, **{k: v for k, v in kwargs.items() if k not in {"queue_name", "job_id"}})


def test_ac_s3_5_a_differing_fingerprint_enqueues_exactly_one_catchup_and_the_job_stores_the_new_one(
    scratch,
):
    from app.services import product_spec_rederive

    db, calls = scratch
    assert _stored_fingerprint(db) is None

    product_spec_rederive.catch_up_on_worker_start()

    assert len(calls) == 1, "no stored fingerprint at all must count as differing, and enqueue once"
    _func, args, kwargs = calls[0]
    assert kwargs.get("queue_name") == "imports" or "imports" in args, (
        "the catch-up re-read must be queued on the imports queue"
    )

    # Run the job the way the worker eventually would, so it stores the fingerprint
    # it ran against.
    _run_queued(calls[0])

    assert _stored_fingerprint(db) is not None, "the job must store a fingerprint once it finishes"

    # Second call, same process state: the fingerprint just stored IS the current
    # running one by construction, so nothing should be queued this time.
    calls.clear()
    product_spec_rederive.catch_up_on_worker_start()
    assert calls == [], "a matching fingerprint must enqueue nothing"


def test_ac_s3_5_a_matching_fingerprint_enqueues_nothing(scratch):
    from app.services import product_spec_rederive

    db, calls = scratch

    # First call always differs (nothing stored yet) - bootstrap the "matches" case
    # from it, exactly as the sibling test does.
    product_spec_rederive.catch_up_on_worker_start()
    assert len(calls) == 1
    _run_queued(calls[0])

    calls.clear()
    product_spec_rederive.catch_up_on_worker_start()

    assert calls == [], "when the stored fingerprint already matches the running one, nothing is queued"
