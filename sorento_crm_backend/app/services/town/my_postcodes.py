"""Malaysian postcode -> state, for placing a dealer on the SORENTO-TOWN map.

Plan: documentation/plans/dashboard/PLAN-town-project-city-11nov.md ("Phase 2 contract").
Source: the Pos Malaysia postcode allocation by state, as commonly published (the first two
digits of a 5-digit postcode name the state or territory): 01-02 Perlis, 05-09 Kedah, 10-14 Pulau
Pinang, 15-18 Kelantan, 20-24 Terengganu, 25-28 Pahang (plus 39 Cameron Highlands, 49 and 69
Genting), 30-36 Perak, 40-48 Selangor (plus 63-64 Cyberjaya/Sepang and 68 Ampang/Gombak), 50-60
Kuala Lumpur, 62 Putrajaya, 70-73 Negeri Sembilan, 75-78 Melaka, 79-86 Johor, 87 Labuan, 88-91
Sabah, 93-98 Sarawak. A prefix outside every range (00, 03, 04, 19, 29, 37, 38, 61, 65-67, 74, 92,
99) gives None. The values are the `my_state` lookup spellings.
"""
from __future__ import annotations

import re
from typing import Optional

_POSTCODE_RE = re.compile(r"(?<!\d)\d{5}(?!\d)")

#: (first prefix, last prefix, state), inclusive, on the first two digits.
_RANGES = (
    (1, 2, "Perlis"),
    (5, 9, "Kedah"),
    (10, 14, "Pulau Pinang"),
    (15, 18, "Kelantan"),
    (20, 24, "Terengganu"),
    (25, 28, "Pahang"),
    (30, 36, "Perak"),
    (39, 39, "Pahang"),
    (40, 48, "Selangor"),
    (49, 49, "Pahang"),
    (50, 60, "Kuala Lumpur"),
    (62, 62, "Putrajaya"),
    (63, 64, "Selangor"),
    (68, 68, "Selangor"),
    (69, 69, "Pahang"),
    (70, 73, "Negeri Sembilan"),
    (75, 78, "Melaka"),
    (79, 86, "Johor"),
    (87, 87, "Labuan"),
    (88, 91, "Sabah"),
    (93, 98, "Sarawak"),
)

#: The `my_state` values, for matching a typed region or state to its canonical spelling.
MY_STATES = (
    "Johor", "Kedah", "Kelantan", "Melaka", "Negeri Sembilan", "Pahang", "Perak", "Perlis",
    "Pulau Pinang", "Sabah", "Sarawak", "Selangor", "Terengganu", "Kuala Lumpur", "Labuan", "Putrajaya",
)
_STATE_BY_LOWER = {name.lower(): name for name in MY_STATES}


def state_for_postcode(pc: str) -> Optional[str]:
    """The state of a 5-digit postcode, or None when it is not 5 digits or outside every range."""
    if not isinstance(pc, str) or not re.fullmatch(r"\d{5}", pc):
        return None
    prefix = int(pc[:2])
    for first, last, state in _RANGES:
        if first <= prefix <= last:
            return state
    return None


def last_postcode(address: Optional[str]) -> Optional[str]:
    """The LAST 5-digit group in an address (a street number of 5 digits earlier on is not it)."""
    found = _POSTCODE_RE.findall(address or "")
    return found[-1] if found else None


def canonical_state(value: Optional[str]) -> Optional[str]:
    """`value` (trimmed, case-insensitive) as its `my_state` spelling, or None when it is not one."""
    return _STATE_BY_LOWER.get((value or "").strip().lower())
