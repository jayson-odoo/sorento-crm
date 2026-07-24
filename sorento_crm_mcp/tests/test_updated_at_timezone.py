"""Regression guard: `updated_at` must be emitted as NAIVE Malaysia wall-clock.

LESSONS-LEARNT: the backend serializes `updated_at` as naive UTC (no `Z`).
Converting it to an offset-aware `...+08:00` string is technically correct but
downstream consumers (n8n / luxon) re-convert an offset-aware timestamp back to
UTC for display — undoing the conversion, so 09:28 MYT rendered as 01:28.

The contract is therefore: convert to Asia/Kuala_Lumpur, then STRIP the offset.
An offset-aware output is the bug, not a stylistic difference.
"""
from __future__ import annotations

import pytest

from sorento_crm_mcp.server import _normalize_updated_at, _to_malaysia_iso


@pytest.mark.parametrize(
    "raw,expected",
    [
        # naive UTC (how the backend actually serializes it) -> +8h, no offset
        ("2026-06-12T01:28:56", "2026-06-12T09:28:56"),
        # explicit Z -> same
        ("2026-06-12T01:28:56Z", "2026-06-12T09:28:56"),
        # already offset-aware UTC -> same
        ("2026-06-12T01:28:56+00:00", "2026-06-12T09:28:56"),
        # already MYT-aware -> wall clock preserved, offset stripped
        ("2026-06-12T09:28:56+08:00", "2026-06-12T09:28:56"),
    ],
)
def test_updated_at_is_naive_malaysia_wall_clock(raw, expected):
    assert _to_malaysia_iso(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "2026-06-12T01:28:56",
        "2026-06-12T01:28:56Z",
        "2026-06-12T09:28:56+08:00",
    ],
)
def test_updated_at_never_carries_an_offset(raw):
    """The offset is what n8n/luxon uses to re-convert back to UTC."""
    out = _to_malaysia_iso(raw)

    assert "+" not in out, f"offset-aware output {out!r} will be re-rendered as UTC downstream"
    assert not out.endswith("Z"), f"UTC marker in {out!r} will be re-rendered as UTC downstream"


def test_non_timestamp_values_pass_through_untouched():
    """A malformed or non-string value must not raise or be mangled."""
    assert _to_malaysia_iso("not a date") == "not a date"
    assert _to_malaysia_iso("") == ""
    assert _to_malaysia_iso(None) is None
    assert _to_malaysia_iso(12345) == 12345


def test_normalization_reaches_nested_rows_and_skips_other_keys():
    """`_normalize_updated_at` recurses, and touches ONLY the `updated_at` key.

    Guards the "generic on the updated_at key" property — the fix was applied
    once centrally so every tool benefits; a narrowed implementation that only
    handled top-level rows would silently regress nested payloads.
    """
    payload = {
        "data": [
            {
                "product_code": "SRTWT107",
                "updated_at": "2026-06-12T01:28:56Z",
                "created_at": "2026-06-12T01:28:56Z",  # must NOT be rewritten
                "nested": {"updated_at": "2026-06-12T01:28:56Z"},
            }
        ]
    }

    out = _normalize_updated_at(payload)
    row = out["data"][0]

    assert row["updated_at"] == "2026-06-12T09:28:56"
    assert row["nested"]["updated_at"] == "2026-06-12T09:28:56"
    assert row["created_at"] == "2026-06-12T01:28:56Z", "only `updated_at` is in scope"
    assert row["product_code"] == "SRTWT107"
