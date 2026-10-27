"""Per-SO remark rules (FULFIL-SO-REMARK): one pure module the board and the email share.

Card: documentation/plans/scm/CARD-fulfil-so-remark-25oct.md. The frontend mirrors only the
two-line decision (`default_remark`, `label_lines`) in `_shared/lib/soRemark.ts`.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

MOCKUP_WORD = "Mockup"
SPONSORSHIP = "Sponsorship"
PURCHASE_REQUEST = "Purchase Request"

_PR_NUMBER = re.compile(r"^\s*PR\d", re.IGNORECASE)


def _mock(text: Optional[str]) -> bool:
    return bool(text) and "MOCK" in text.upper()


def is_mockup_line(
    note: Optional[str], line_remark: Optional[str], section_heading: Optional[str]
) -> bool:
    """AC-3: the SO note, the line remark or the heading above the line says MOCK."""
    return _mock(note) or _mock(line_remark) or _mock(section_heading)


def remark_type(ship_info: Optional[str]) -> Optional[str]:
    """AC-4: Sponsorship beats Purchase Request; None for an ordinary SO."""
    text = (ship_info or "").upper()
    if "SPON" in text:
        return SPONSORSHIP
    if "PURCHASE REQ" in text or _PR_NUMBER.match(text):
        return PURCHASE_REQUEST
    return None


def default_remark(rtype: Optional[str], chosen_flags: Iterable[bool]) -> str:
    """AC-5: the remark type, else Mockup when any chosen line is a mockup line, else blank."""
    if rtype:
        return rtype
    return MOCKUP_WORD if any(chosen_flags) else ""


def label_lines(chosen_flags: Iterable[bool]) -> bool:
    """AC-6: label the mockup lines only when the chosen lines mix mockup and actual."""
    flags = list(chosen_flags)
    return any(flags) and not all(flags)
