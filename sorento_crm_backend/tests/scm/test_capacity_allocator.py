"""The scarce-capacity allocator, and specifically the divisible path cash never uses.

Cash behaviour is guarded by the 1,152-scenario snapshot in
`test_capacity_allocator_parity.py`. This module covers what is NEW: part-filling a
divisible item, which is the container-loading case, plus the shared rules that a second
caller must be able to rely on.

The container figures come from the real 2026-07-31 pre-load list so the arithmetic is
checkable against a document rather than invented.
"""
from __future__ import annotations

import pytest

from app.services.scm.cash_ranking import (
    ALLOCATED,
    DEFERRED,
    PARTIAL,
    UNMEASURED,
    CapacityItem,
    allocate_capacity,
)


# 2 x 40HQ. The real pre-load list's three largest lines, in PO-document order, which is
# the seeded priority rule.
_CBM_CAPACITY = 134.0
_LINES = [
    CapacityItem(id="PO-2026/05-0031", rank=1, demand=69.36, divisible=True),  # 408 u @ 0.17
    CapacityItem(id="PO-2026/06-0044", rank=2, demand=67.68, divisible=True),  # 376 u @ 0.18
    CapacityItem(id="PO-2026/06-0051", rank=3, demand=6.00, divisible=True),   # 200 u @ 0.03
]


def test_container_loading_part_fills_the_line_that_straddles_the_cut():
    res = allocate_capacity(_LINES, _CBM_CAPACITY)

    assert res.status_by_id["PO-2026/05-0031"] == ALLOCATED
    assert res.granted_by_id["PO-2026/05-0031"] == 69.36

    # 134.00 - 69.36 = 64.64 left, and the line wants 67.68. A container can be
    # part-loaded, so it takes the remainder instead of being skipped whole.
    assert res.status_by_id["PO-2026/06-0044"] == PARTIAL
    assert res.granted_by_id["PO-2026/06-0044"] == 64.64

    # Capacity is now exactly gone, so the last line defers even though it is tiny. This is
    # the case that would look like a bug to a user, which is why the deferral reason has to
    # be shown on screen.
    assert res.status_by_id["PO-2026/06-0051"] == DEFERRED
    assert res.granted_by_id["PO-2026/06-0051"] == 0.0

    assert res.granted_total == pytest.approx(134.0, abs=0.01)
    assert res.deferred_total == pytest.approx((67.68 - 64.64) + 6.00, abs=0.01)
    assert (res.granted_count, res.partial_count, res.deferred_count) == (1, 1, 1)


def test_granted_never_exceeds_capacity_when_nothing_is_pinned():
    res = allocate_capacity(_LINES, _CBM_CAPACITY)
    assert res.granted_total <= _CBM_CAPACITY + 1e-9


def test_indivisible_item_is_skipped_not_part_filled():
    """The MOQ rule. An indivisible item that does not fit is skipped, and a smaller
    lower-ranked item can still be granted from the remainder."""
    items = [
        CapacityItem(id="big", rank=1, demand=500.0, divisible=False),
        CapacityItem(id="small", rank=2, demand=30.0, divisible=False),
    ]
    res = allocate_capacity(items, 100.0)
    assert res.status_by_id == {"big": DEFERRED, "small": ALLOCATED}
    assert res.granted_total == 30.0


def test_divisible_and_indivisible_mix_independently():
    items = [
        CapacityItem(id="moq", rank=1, demand=500.0, divisible=False),
        CapacityItem(id="loadable", rank=2, demand=500.0, divisible=True),
    ]
    res = allocate_capacity(items, 100.0)
    assert res.status_by_id["moq"] == DEFERRED
    assert res.status_by_id["loadable"] == PARTIAL
    assert res.granted_by_id["loadable"] == 100.0


def test_unmeasured_item_is_parked_and_draws_nothing():
    """A shipment line with no volume on file cannot be ranked against a volume cap, so it
    is parked rather than guessed at. Same rule as an uncosted buy."""
    items = [
        CapacityItem(id="no-cbm", rank=1, demand=None, divisible=True),
        CapacityItem(id="known", rank=2, demand=50.0, divisible=True),
    ]
    res = allocate_capacity(items, 100.0)
    assert res.status_by_id["no-cbm"] == UNMEASURED
    assert "no-cbm" not in res.granted_by_id
    assert res.granted_by_id["known"] == 50.0
    assert res.granted_total == 50.0


def test_a_pin_wins_past_the_capacity_and_never_part_fills():
    """Ms Tee insisting a line ships is a decision, not a suggestion. It is granted whole
    even when it blows the cap, which is what makes the over-capacity figure honest."""
    items = [
        CapacityItem(id="cheap", rank=1, demand=10.0, divisible=True),
        CapacityItem(id="must-ship", rank=9, demand=200.0, divisible=True),
    ]
    res = allocate_capacity(items, 100.0, pinned_ids=["must-ship"])
    assert res.status_by_id["must-ship"] == ALLOCATED
    assert res.granted_by_id["must-ship"] == 200.0
    # Pins consume first and can exhaust the cap, so the cheap line loses.
    assert res.status_by_id["cheap"] == DEFERRED
    assert res.granted_total == 200.0


def test_excluded_item_is_absent_entirely():
    items = [
        CapacityItem(id="dropped", rank=1, demand=50.0, divisible=True),
        CapacityItem(id="kept", rank=2, demand=50.0, divisible=True),
    ]
    res = allocate_capacity(items, 100.0, excluded_ids=["dropped"])
    assert "dropped" not in res.status_by_id
    assert "dropped" not in res.granted_by_id
    assert res.granted_total == 50.0


def test_uncapped_grants_everything_measured():
    res = allocate_capacity(_LINES, None)
    assert set(res.status_by_id.values()) == {ALLOCATED}
    assert res.granted_total == pytest.approx(143.04, abs=0.01)
    assert res.deferred_total == 0.0


def test_zero_capacity_defers_everything_without_crashing():
    res = allocate_capacity(_LINES, 0.0)
    assert set(res.status_by_id.values()) == {DEFERRED}
    assert res.granted_total == 0.0


def test_rank_order_decides_not_size():
    """Proves the allocator is greedy by RANK, not by what packs best. A cbm-optimal
    packer would load the small line first; the priority policy says otherwise, and the
    policy wins because fairness to the customer outranks container utilisation."""
    items = [
        CapacityItem(id="urgent-big", rank=1, demand=90.0, divisible=True),
        CapacityItem(id="idle-small", rank=2, demand=20.0, divisible=True),
    ]
    res = allocate_capacity(items, 100.0)
    assert res.granted_by_id["urgent-big"] == 90.0
    assert res.status_by_id["idle-small"] == PARTIAL
    assert res.granted_by_id["idle-small"] == 10.0


def test_empty_input_is_not_an_error():
    res = allocate_capacity([], 100.0)
    assert res.status_by_id == {}
    assert res.granted_total == 0.0
    assert res.deferred_total == 0.0
