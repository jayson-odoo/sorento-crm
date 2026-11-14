"""SPARE-PART-OR-B (slice 2 of #2381), Phase 2. R5 History meaning, U5.1 only.

Contract: documentation/plans/purchasing/spare-part-or-b-14nov-acceptance-criteria.md.
Owner answered Q2 (14 Nov): History shows the WHOLE life on both the OR and the OI page, so
U5.2 - U5.5 (a `scope` query) are dropped. This file is the guard that
`GET /order-inquiry-headers/{id}/history` keeps reading the whole life of a spare part
request through the slice: created, edited, submitted, line changed (old -> new), approved,
revised, raised (every raise). It is expected to pass before and after the coder's work.

The flow is the UAC's example E2: the approver changes 10 -> 8, approves (raise 1), the
requester revises and changes 8 -> 20, submits, and it is approved again (raise 2).

Postgres only (`blank_session` via the shared world); every row seeded here.
"""
from __future__ import annotations

import json
import re

from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    HEADERS,
    approve,
    body,
    line,
    reload,
    row_for,
    sent,
    staged,
    submitted,
    svc,
    world,
)

ARROW = r"\s*(->|→)\s*"


def _e2(w):
    inquiry = submitted(w)
    row_a = row_for(w.db, inquiry, w.product_a)
    row_b = row_for(w.db, inquiry, w.product_b)
    svc().edit_line(w.db, inquiry, row_a.id, w.stage1.tier1, qty="8")
    w.db.commit()
    inquiry = approve(w, reload(w.db, inquiry), w.stage1.tier1)
    svc().revise(w.db, inquiry, w.requester)
    w.db.commit()
    lines = [
        {**line(w.product_a, w.loc_a, qty="20", unit_price="25.00"), "id": str(row_a.id)},
        {**line(w.product_b, w.loc_b, qty="4", unit_price="12.50"), "id": str(row_b.id)},
    ]
    svc().update(w.db, reload(w.db, inquiry), body(w, lines=lines), w.requester)
    w.db.commit()
    svc().submit(w.db, reload(w.db, inquiry), w.requester)
    w.db.commit()
    return approve(w, reload(w.db, inquiry), w.stage1.tier1)


def _events(w, inquiry, **params) -> list:
    res = w.as_user(w.admin).get(f"{HEADERS}/{inquiry.id}/history", params=params)
    assert res.status_code == 200, res.text
    return res.json()["events"]


def test_U5_1_default_history_reads_the_whole_life(staged):
    w = staged
    inquiry = _e2(w)
    assert inquiry.state == "raised", "precondition: approved twice"
    events = _events(w, inquiry)
    kinds = [e["kind"] for e in events]
    for kind in ("created", "submitted", "changed", "approved", "revised", "edited"):
        assert kind in kinds, f"{kind} is on History: {kinds}"
    assert kinds.count("raised") == 2, f"both raises: {kinds}"
    text = json.dumps(events, ensure_ascii=False)
    assert re.search(rf"\b10(\.0+)?{ARROW}8(\.0+)?\b", text), "the approver's 10 -> 8"
    assert re.search(rf"\b8(\.0+)?{ARROW}20(\.0+)?\b", text), "the requester's 8 -> 20"


def test_U5_1_history_is_newest_first(staged):
    w = staged
    events = _events(w, _e2(w))
    stamps = [e["at"] for e in events if e.get("at")]
    assert stamps == sorted(stamps, reverse=True)
