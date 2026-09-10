"""Plain text out of the RTF AutoCount pushes on a sales-order note.

AutoCount's `internal_note` field is a rich-text control, so the ESB carries its
raw RTF wrapper (`{\\rtf1\\ansi...}`) rather than the words a user typed. Nothing
downstream - the SO detail page, `project_fulfilment_board_service`, SCM
services, MCP - wants the control codes, so this is cleaned once at the edge
(`CanonicalSalesOrder`'s validator) rather than by every reader re-deriving it.

A value that does not start with the RTF wrapper is passed through untouched
(besides a `.strip()`) - most of the book's notes are already plain text typed
straight into a field with no RTF control at all.
"""
from __future__ import annotations

import re
from typing import Optional

from striprtf.striprtf import rtf_to_text

_RTF_PREFIX = "{\\rtf"
_RUN_OF_BLANK_LINES = re.compile(r"\n{3,}")


def strip_rtf(value: Optional[str]) -> Optional[str]:
    """`None`/blank in, `None` out. RTF in, its plain text out. Anything else, stripped."""
    if not value:
        return None
    if not value.startswith(_RTF_PREFIX):
        stripped = value.strip()
        return stripped or None

    text = rtf_to_text(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    text = _RUN_OF_BLANK_LINES.sub("\n\n", text)
    return text or None
