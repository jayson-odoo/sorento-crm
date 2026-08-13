"""Parity net for generalising the allocator from cash to any scarce capacity.

`allocate_funding` is a proven money path with three callers and only four golden
assertions guarding it. That is far too thin a net to refactor against, so this module
builds the net first: a deterministic matrix of allocation scenarios, snapshotted from
the PRE-refactor implementation into `fixtures/golden_allocator.json`, and asserted
byte-for-byte afterwards.

Regenerate the snapshot ONLY when you intend to change cash behaviour:

    python -m tests.scm.test_capacity_allocator_parity --regenerate

A parity failure means the refactor is wrong, not that the snapshot is stale. That is
the same rule the M3 golden set carries, applied to the same class of change.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from app.services.scm import cash_ranking as cr

_FIXTURE = Path(__file__).parent / "fixtures" / "golden_allocator.json"


def _scenarios() -> list[dict]:
    """A deliberately awkward matrix: ties, overflow, pins past the budget, uncosted
    rows, rejects, zero and None budgets, and the full-budget inversion."""
    # (id, rank, cash_impact) triples reused across budget/pin/reject permutations.
    buy_sets = {
        "simple": [("a", 1, 100.0), ("b", 2, 200.0), ("c", 3, 300.0)],
        # b is cheaper than a but ranked lower: proves greedy-by-rank, not by cost.
        "rank_beats_cost": [("a", 1, 500.0), ("b", 2, 10.0), ("c", 3, 10.0)],
        # skip-overflow: a fits, b does not, c fits again in the remainder.
        "skip_overflow": [("a", 1, 60.0), ("b", 2, 500.0), ("c", 3, 30.0)],
        "with_uncosted": [("a", 1, 100.0), ("b", 2, None), ("c", 3, 50.0)],
        "all_uncosted": [("a", 1, None), ("b", 2, None)],
        "rank_none": [("a", None, 100.0), ("b", 1, 100.0)],
        "zero_cost": [("a", 1, 0.0), ("b", 2, 100.0)],
        "empty": [],
    }
    budgets = [None, 0.0, 90.0, 100.0, 250.0, 10_000.0]
    pin_sets = [(), ("a",), ("b",), ("a", "c")]
    reject_sets = [(), ("a",), ("b", "c")]

    out: list[dict] = []
    for set_name, triples in buy_sets.items():
        for budget in budgets:
            for pins in pin_sets:
                for rejects in reject_sets:
                    for full in (False, True):
                        out.append(
                            {
                                "buy_set": set_name,
                                "buys": [list(t) for t in triples],
                                "budget": budget,
                                "pinned_ids": list(pins),
                                "rejected_ids": list(rejects),
                                "full": full,
                            }
                        )
    return out


def _run(scn: dict) -> dict:
    buys = [cr.Buy(id=i, rank=r, cash_impact=c) for i, r, c in scn["buys"]]
    res = cr.allocate_funding(
        buys,
        scn["budget"],
        pinned_ids=scn["pinned_ids"],
        rejected_ids=scn["rejected_ids"],
        full=scn["full"],
    )
    d = asdict(res)
    # Sort the status map so JSON ordering can never make a passing test fail.
    d["status_by_id"] = dict(sorted(d["status_by_id"].items()))
    return d


def _key(scn: dict) -> str:
    return "|".join(
        [
            scn["buy_set"],
            "budget=" + repr(scn["budget"]),
            "pin=" + ",".join(scn["pinned_ids"]),
            "rej=" + ",".join(scn["rejected_ids"]),
            "full=" + str(scn["full"]),
        ]
    )


def _snapshot() -> dict[str, dict]:
    return {_key(s): _run(s) for s in _scenarios()}


def test_matrix_is_large_enough_to_be_a_real_net():
    """A snapshot of three cases would prove nothing. Guard the guard."""
    assert len(_scenarios()) >= 500


def test_allocator_parity_against_snapshot():
    assert _FIXTURE.exists(), (
        f"{_FIXTURE} missing. Generate it from the PRE-refactor implementation with "
        "`python -m tests.scm.test_capacity_allocator_parity --regenerate` before "
        "changing cash_ranking."
    )
    expected = json.loads(_FIXTURE.read_text())
    actual = _snapshot()

    assert set(actual) == set(expected), "scenario matrix changed; the net moved, not the code"

    drift = {k: {"expected": expected[k], "actual": actual[k]} for k in expected if actual[k] != expected[k]}
    assert not drift, (
        f"{len(drift)} of {len(expected)} allocator scenarios changed. Cash behaviour must "
        f"be byte-identical after generalisation. First 3: "
        f"{json.dumps(dict(list(drift.items())[:3]), indent=2, default=str)}"
    )


if __name__ == "__main__":  # pragma: no cover - snapshot generation only
    import sys

    if "--regenerate" not in sys.argv:
        print(__doc__)
        sys.exit(2)
    _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    snap = _snapshot()
    _FIXTURE.write_text(json.dumps(snap, indent=2, sort_keys=True, default=str) + "\n")
    print(f"wrote {len(snap)} scenarios to {_FIXTURE}")
