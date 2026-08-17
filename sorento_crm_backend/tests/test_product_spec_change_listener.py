"""`rederive_codes` - the inline-vs-worker split, and reading the registry once per
batch, both earned by the phase 3 review pass (PR1-CONTRACT.md section 6b.1).

Contract: at or below `INLINE_REDERIVE_LIMIT` (50), derive inline; above it, hand the
batch to the worker (`app.tasks.product_spec_tasks.derive_product_specs` on the
`imports` queue); an unreachable queue falls back to inline and never raises; and the
hoisted `configured_rules` / `configured_scopes` reads happen ONCE per batch, not once
per code, with the SAME object handed to every `derive_for_code` call.

No product rows are seeded for most of these: codes that do not exist produce zero
rows in `derive_for_code`'s own query and it returns early without writing anything,
so a fake ZZT-prefixed code is safe to hand to the REAL `SessionLocal()` that
`_rederive_inline` opens internally (it is not swappable from the caller, unlike the
service-level tests that use `tests/_pg_fixture.blank_session`). `configured_rules`
and `configured_scopes` still do real, read-only queries against the live database in
that path - nothing here writes to it.
"""
from __future__ import annotations

import app.services.product_spec_change_listener as listener
import app.services.product_spec_derivation as derivation
from app.services import queue_service


def _codes(prefix: str, n: int) -> set[str]:
    return {f"ZZT-RC-{prefix}-{i}" for i in range(n)}


# --------------------------------------------------------------------------- #
# threshold split
# --------------------------------------------------------------------------- #
def test_above_the_threshold_enqueues_and_skips_inline_derivation(monkeypatch):
    enqueued: list[list[str]] = []
    inline_calls: list[list[str]] = []
    monkeypatch.setattr(
        listener, "_enqueue_rederive", lambda codes: (enqueued.append(sorted(codes)), True)[1]
    )
    monkeypatch.setattr(listener, "_rederive_inline", lambda codes: inline_calls.append(sorted(codes)))

    codes = _codes("ABOVE", listener.INLINE_REDERIVE_LIMIT + 1)
    listener.rederive_codes(codes)

    assert len(enqueued) == 1
    assert inline_calls == [], "above the threshold, a successful enqueue must skip inline derivation"


def test_at_the_threshold_derives_inline_without_enqueuing(monkeypatch):
    enqueue_calls: list[int] = []
    inline_calls: list[list[str]] = []
    monkeypatch.setattr(listener, "_enqueue_rederive", lambda codes: enqueue_calls.append(1) or True)
    monkeypatch.setattr(listener, "_rederive_inline", lambda codes: inline_calls.append(sorted(codes)))

    codes = _codes("AT", listener.INLINE_REDERIVE_LIMIT)
    listener.rederive_codes(codes)

    assert enqueue_calls == [], "exactly at the limit, the batch must derive inline, not enqueue"
    assert len(inline_calls) == 1


def test_below_the_threshold_derives_inline_without_enqueuing(monkeypatch):
    enqueue_calls: list[int] = []
    inline_calls: list[list[str]] = []
    monkeypatch.setattr(listener, "_enqueue_rederive", lambda codes: enqueue_calls.append(1) or True)
    monkeypatch.setattr(listener, "_rederive_inline", lambda codes: inline_calls.append(sorted(codes)))

    codes = _codes("BELOW", 1)
    listener.rederive_codes(codes)

    assert enqueue_calls == []
    assert len(inline_calls) == 1


def test_an_empty_batch_does_nothing(monkeypatch):
    enqueue_calls: list[int] = []
    inline_calls: list[int] = []
    monkeypatch.setattr(listener, "_enqueue_rederive", lambda codes: enqueue_calls.append(1) or True)
    monkeypatch.setattr(listener, "_rederive_inline", lambda codes: inline_calls.append(1))

    listener.rederive_codes(set())

    assert enqueue_calls == []
    assert inline_calls == []


# --------------------------------------------------------------------------- #
# an unreachable queue falls back to inline and never raises
# --------------------------------------------------------------------------- #
def test_enqueue_failure_falls_back_to_inline_and_never_raises(monkeypatch):
    inline_calls: list[list[str]] = []
    monkeypatch.setattr(listener, "_enqueue_rederive", lambda codes: False)
    monkeypatch.setattr(listener, "_rederive_inline", lambda codes: inline_calls.append(sorted(codes)))

    codes = _codes("FAIL", listener.INLINE_REDERIVE_LIMIT + 1)
    listener.rederive_codes(codes)  # must not raise

    assert len(inline_calls) == 1, "a failed enqueue above the threshold must still derive inline"


def test_enqueue_rederive_itself_returns_false_and_never_raises_when_the_queue_blows_up(monkeypatch):
    """The lower-level unit: `_enqueue_rederive` wraps `enqueue_job` in try/except and
    reports failure as a return value, never as an exception - Redis down included."""

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated queue failure")

    monkeypatch.setattr(queue_service, "enqueue_job", _boom)

    result = listener._enqueue_rederive({"ZZT-RC-BOOM-1"})

    assert result is False


# --------------------------------------------------------------------------- #
# the registry is read ONCE per batch, not once per code
# --------------------------------------------------------------------------- #
def test_inline_rederive_reads_the_registry_once_and_hands_the_same_object_to_every_code(monkeypatch):
    """`_rederive_inline` mirrors `derive_all`: read `configured_rules` /
    `configured_scopes` once, then pass the SAME dicts into every `derive_for_code`
    call. A per-code read would cost N registry round-trips for what should be one,
    and the review named it explicitly as "the point of the change" - a spy on call
    count is the honest way to pin it, per the tester brief."""
    rules_calls: list[int] = []
    scopes_calls: list[int] = []
    derive_calls: list[tuple] = []

    def _counting_rules(db):
        rules_calls.append(1)
        return {"material": []}

    def _counting_scopes(db):
        scopes_calls.append(1)
        return {}

    def _fake_derive_for_code(db, code, *, commit=False, rules_by_key=None, scopes_by_key=None):
        derive_calls.append((code, id(rules_by_key), id(scopes_by_key)))
        return {"written": 0, "skipped": 0, "exceptions": 0}

    monkeypatch.setattr(derivation, "configured_rules", _counting_rules)
    monkeypatch.setattr(derivation, "configured_scopes", _counting_scopes)
    monkeypatch.setattr(derivation, "derive_for_code", _fake_derive_for_code)

    codes = _codes("ONCE", 5)
    listener.rederive_codes(codes)

    assert len(rules_calls) == 1, "configured_rules must be read once per batch, not once per code"
    assert len(scopes_calls) == 1, "configured_scopes must be read once per batch, not once per code"
    assert len(derive_calls) == 5, "every code in the batch must still be derived"

    rules_object_ids = {rid for (_code, rid, _sid) in derive_calls}
    scopes_object_ids = {sid for (_code, _rid, sid) in derive_calls}
    assert len(rules_object_ids) == 1, "every call must receive the SAME hoisted rules object"
    assert len(scopes_object_ids) == 1, "every call must receive the SAME hoisted scopes object"
