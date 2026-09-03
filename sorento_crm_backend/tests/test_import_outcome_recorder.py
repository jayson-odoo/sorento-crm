"""ImportOutcome recorder: the contract every importer now depends on.

Covers UAC AC-A2 (counters come only from the recorder), AC-A7 (best-effort),
AC-A8 (buffered bulk insert, never per-row), AC-A9 (counts stay exact when row
persistence is capped) and AC-B2/B3 (complete breakdown + top values).
"""
from __future__ import annotations

import uuid

import pytest

from app.services import import_outcome_codes as oc
from app.services.import_outcome import ImportOutcome


def _recorder(**kwargs) -> ImportOutcome:
    """Aggregation-only recorder (no DB), which is what most assertions need."""
    kwargs.setdefault("persist", False)
    return ImportOutcome(None, **kwargs)


def test_counters_reflect_every_recorded_row():
    out = _recorder()
    out.success(row=2, code=oc.CREATED)
    out.updated(row=3)
    out.unchanged(row=4)
    out.skip(row=5, code=oc.PRODUCT_NOT_FOUND, message="Product not found: A")
    out.fail(row=6, code=oc.ROW_ERROR, message="boom")

    assert out.successful == 3  # created + updated + unchanged
    assert out.skipped == 1
    assert out.failed == 1
    assert out.processed == 5


def test_completion_counts_feed_the_job_row():
    out = _recorder()
    out.success(row=1)
    out.skip(row=2, code=oc.DUPLICATE_LINE, message="dupe")

    counts = out.completion_counts(total_rows=10)
    assert counts == {
        "successful_rows": 1,
        "failed_rows": 0,
        "skipped_rows": 1,
        "processed_rows": 2,
        "total_rows": 10,
    }


def test_breakdown_is_complete_and_sorted_by_count():
    out = _recorder()
    for _ in range(5):
        out.skip(row=1, code=oc.DUPLICATE_LINE, message="dupe")
    out.skip(row=2, code=oc.PRODUCT_NOT_FOUND, message="missing", value="ABC")

    skipped = out.breakdown()["skipped"]
    assert [e["code"] for e in skipped] == [oc.DUPLICATE_LINE, oc.PRODUCT_NOT_FOUND]
    assert [e["count"] for e in skipped] == [5, 1]
    # Sum of the breakdown must equal the counter - no unattributed rows.
    assert sum(e["count"] for e in skipped) == out.skipped


def test_top_values_rank_the_offending_tokens():
    out = _recorder()
    for value, times in (("A-150", 4), ("A-P", 3), ("A-200", 2)):
        for _ in range(times):
            out.skip(row=1, code=oc.PRODUCT_NOT_FOUND, message="x", value=value)

    entry = out.breakdown()["skipped"][0]
    assert entry["top_values"][:3] == [
        {"value": "A-150", "count": 4},
        {"value": "A-P", "count": 3},
        {"value": "A-200", "count": 2},
    ]


def test_envelope_arithmetic_always_reconciles():
    out = _recorder()
    out.success(row=1)
    out.skip(row=2, code=oc.DUPLICATE_LINE, message="d")
    out.fail(row=3, code=oc.ROW_ERROR, message="e")

    env = out.finalize("done", total_rows=3)
    counts = env["counts"]
    assert counts["successful"] + counts["skipped"] + counts["failed"] == counts["processed"]
    for group in ("successful", "skipped", "failed"):
        assert sum(e["count"] for e in env["breakdown"][group]) == counts[group]


def test_extra_keys_ride_along_for_back_compat():
    out = _recorder()
    out.success(row=1)
    env = out.finalize("done", errors=[{"row": 1, "error": "legacy"}])
    assert env["errors"] == [{"row": 1, "error": "legacy"}]
    assert env["message"] == "done"


def test_counts_stay_exact_when_row_capture_is_capped():
    """AC-A9: the cap limits drill-down, never the numbers."""
    captured: list[list[dict]] = []

    class _FakeSession:
        def bulk_insert_mappings(self, _model, rows):
            captured.append(list(rows))

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    out = ImportOutcome(
        uuid.uuid4(), buffer_size=10, max_rows=25, session_factory=lambda: _FakeSession()
    )
    for i in range(100):
        out.skip(row=i, code=oc.DUPLICATE_LINE, message="dupe")
    out.flush()

    persisted = sum(len(batch) for batch in captured)
    assert persisted == 25, "row capture stops at the cap"
    assert out.rows_truncated is True
    assert out.skipped == 100, "counts are in-memory and stay exact past the cap"
    assert out.breakdown()["skipped"][0]["count"] == 100


def test_rows_are_written_in_batches_not_one_at_a_time():
    """AC-A8: buffered bulk insert. A per-row INSERT would be 50 calls, not 5."""
    batches: list[int] = []

    class _FakeSession:
        def bulk_insert_mappings(self, _model, rows):
            batches.append(len(list(rows)))

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    out = ImportOutcome(uuid.uuid4(), buffer_size=10, session_factory=lambda: _FakeSession())
    for i in range(50):
        out.success(row=i)
    out.flush()

    assert batches == [10, 10, 10, 10, 10]


def test_recorder_failure_never_breaks_the_import():
    """AC-A7: observability must not take the import down with it."""

    class _ExplodingSession:
        def bulk_insert_mappings(self, _model, _rows):
            raise RuntimeError("database on fire")

        def commit(self):
            raise RuntimeError("database on fire")

        def rollback(self):
            pass

        def close(self):
            pass

    out = ImportOutcome(uuid.uuid4(), buffer_size=2, session_factory=lambda: _ExplodingSession())
    for i in range(5):
        out.skip(row=i, code=oc.DUPLICATE_LINE, message="dupe")
    out.flush()  # must not raise

    # The numbers survive even though nothing could be written.
    assert out.skipped == 5


def test_flush_never_touches_import_jobs_when_bump_job_progress_is_off():
    """Review round 2, N3: `bump_job_progress` (S2) is the gate, not merely a caller's own
    `publish=True` - a recorder built without it must never even QUERY `import_jobs`, so a
    caller that forgets to opt in cannot accidentally race another importer's own explicit
    progress reporting."""
    touched = {"query": False}

    class _FakeSession:
        def bulk_insert_mappings(self, _model, _rows):
            pass

        def query(self, *_a, **_kw):
            touched["query"] = True
            raise AssertionError("import_jobs must not be queried")

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    # bump_job_progress left at its default (off).
    out = ImportOutcome(uuid.uuid4(), session_factory=lambda: _FakeSession())
    out.success(row=1)
    out.flush(publish=True)

    assert touched["query"] is False


def test_the_buffer_full_auto_flush_does_not_publish():
    """Review round 2, N3: the auto-flush inside `_record` (buffer_size reached) must never
    bump `processed_rows`, even with `bump_job_progress=True` on the recorder - only an
    explicit `flush(publish=True)` may, and `_record` never passes it. A worker killed right
    after this auto-flush must not have shown a count ahead of what is actually committed."""
    touched = {"query": False}

    class _FakeSession:
        def bulk_insert_mappings(self, _model, _rows):
            pass

        def query(self, *_a, **_kw):
            touched["query"] = True
            raise AssertionError("import_jobs must not be queried by an auto-flush")

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    out = ImportOutcome(uuid.uuid4(), buffer_size=3, session_factory=lambda: _FakeSession(),
                        bump_job_progress=True)
    for i in range(3):  # exactly buffer_size - triggers the auto-flush inside _record
        out.success(row=i)

    assert touched["query"] is False


def test_identity_is_flattened_and_bounded():
    """Identity is printed in the UI, so it stays flat, short and JSON-safe."""
    from app.services.import_outcome import _json_safe_identity

    safe = _json_safe_identity(
        {"doc_no": "DO-1", "qty": 3, "empty": "", "none": None, "nested": {"a": 1}}
    )
    assert safe["doc_no"] == "DO-1"
    assert safe["qty"] == 3
    assert "empty" not in safe and "none" not in safe
    assert isinstance(safe["nested"], str), "nested values are stringified, not embedded"
    assert len(_json_safe_identity({"long": "x" * 500})["long"]) == 255


def test_unknown_code_still_gets_a_readable_label():
    assert oc.label_for(oc.PRODUCT_NOT_FOUND) == "Product not found"
    assert oc.label_for("some_new_code") == "Some new code"
    assert oc.label_for("") == "Unspecified"


@pytest.mark.parametrize(
    "outcome_value,expected_group",
    [
        (oc.OUTCOME_CREATED, "successful"),
        (oc.OUTCOME_UPDATED, "successful"),
        (oc.OUTCOME_UNCHANGED, "successful"),
        (oc.OUTCOME_SKIPPED, "skipped"),
        (oc.OUTCOME_FAILED, "failed"),
    ],
)
def test_every_outcome_lands_in_exactly_one_group(outcome_value, expected_group):
    out = _recorder()
    if outcome_value == oc.OUTCOME_SKIPPED:
        out.skip(row=1, code="x", message="m")
    elif outcome_value == oc.OUTCOME_FAILED:
        out.fail(row=1, code="x", message="m")
    else:
        out.success(row=1, code="x", outcome=outcome_value)

    groups = out.breakdown()
    assert len(groups[expected_group]) == 1
    others = [g for g in groups if g != expected_group]
    assert all(groups[g] == [] for g in others)
