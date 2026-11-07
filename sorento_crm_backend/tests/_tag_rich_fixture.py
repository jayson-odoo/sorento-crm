"""Shared fixture text for the PRICETAG-COMBO-FORMAT backend suites (not a test module).

E1 is the real-case combo description (SRTBF11416) written as the editor would emit it:
twelve paragraphs, six bold item codes, grey dimension lines. The codes are labels only.
"""
from __future__ import annotations

GREY = '<span style="color: #6b7280">{}</span>'

E1_LINES = [
    "SRTBF11416 (CABINET)",
    "L400xW345xH390mm",
    "SRTWB248 (BASIN)",
    "L480xW380xH130mm",
    "MIRROR",
    "L500xW20xH700mm",
    "SHELF",
    "L400xW150xH20mm",
    "SRTWT5837 (TAP)",
    "H180mm",
    "SRTW2600 (WASTE)",
    "D32mm",
]

_BOLD = {"SRTBF11416", "SRTWB248", "MIRROR", "SHELF", "SRTWT5837", "SRTW2600"}


def _paragraph(line: str) -> str:
    head, _, tail = line.partition(" ")
    if head in _BOLD:
        return f"<p><strong>{head}</strong>{(' ' + tail) if tail else ''}</p>"
    return f"<p>{GREY.format(line)}</p>"


E1_HTML = "".join(_paragraph(line) for line in E1_LINES)
