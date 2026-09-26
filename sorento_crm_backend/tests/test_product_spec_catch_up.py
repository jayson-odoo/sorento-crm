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

The `_derived_rules_fingerprint` row lives in the REAL default schema (whichever
session `catch_up_on_worker_start` opens for itself, mirroring every other function in
this module) rather than a `blank_session` scratch schema, so cleanup is explicit here
- LESSONS: seed your own chain, never leave rows behind.
"""
from __future__ import annotations

from sqlalchemy import text

from app.database import SessionLocal

_FINGERPRINT_KEY = "_derived_rules_fingerprint"


def _clear_stored_fingerprint() -> None:
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM product_spec_search_policy WHERE policy_key = :key"),
            {"key": _FINGERPRINT_KEY},
        )
        db.commit()


def _stored_fingerprint() -> str | None:
    with SessionLocal() as db:
        return db.execute(
            text("SELECT help_text FROM product_spec_search_policy WHERE policy_key = :key"),
            {"key": _FINGERPRINT_KEY},
        ).scalar()


def test_ac_s3_5_a_differing_fingerprint_enqueues_exactly_one_catchup_and_the_job_stores_the_new_one(
    monkeypatch,
):
    from app.services import product_spec_rederive

    _clear_stored_fingerprint()
    try:
        calls: list[tuple] = []

        def _fake_enqueue(func, *args, **kwargs):
            calls.append((func, args, kwargs))
            return "job-1"

        monkeypatch.setattr(product_spec_rederive, "enqueue_job", _fake_enqueue, raising=False)

        result = product_spec_rederive.catch_up_on_worker_start()

        assert len(calls) == 1, "no stored fingerprint at all must count as differing, and enqueue once"
        func, args, kwargs = calls[0]
        assert kwargs.get("queue_name") == "imports" or "imports" in args, (
            "the catch-up re-read must be queued on the imports queue"
        )

        # Run the job the way the worker eventually would, so it stores the fingerprint
        # it ran against.
        func(*args, **{k: v for k, v in kwargs.items() if k != "queue_name"})

        assert _stored_fingerprint() is not None, "the job must store a fingerprint once it finishes"

        # Second call, same process state: the fingerprint just stored IS the current
        # running one by construction, so nothing should be queued this time.
        calls.clear()
        again = product_spec_rederive.catch_up_on_worker_start()
        assert calls == [], "a matching fingerprint must enqueue nothing"
    finally:
        _clear_stored_fingerprint()


def test_ac_s3_5_a_matching_fingerprint_enqueues_nothing(monkeypatch):
    from app.services import product_spec_rederive

    _clear_stored_fingerprint()
    try:
        calls: list[tuple] = []
        monkeypatch.setattr(
            product_spec_rederive,
            "enqueue_job",
            lambda func, *args, **kwargs: (calls.append((func, args, kwargs)), "job")[1],
            raising=False,
        )

        # First call always differs (nothing stored yet) - bootstrap the "matches" case
        # from it, exactly as the sibling test does.
        product_spec_rederive.catch_up_on_worker_start()
        assert len(calls) == 1
        func, args, kwargs = calls[0]
        func(*args, **{k: v for k, v in kwargs.items() if k != "queue_name"})

        calls.clear()
        product_spec_rederive.catch_up_on_worker_start()

        assert calls == [], "when the stored fingerprint already matches the running one, nothing is queued"
    finally:
        _clear_stored_fingerprint()
