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

import logging
import re
from typing import Optional

from striprtf.striprtf import rtf_to_text

logger = logging.getLogger(__name__)

_RTF_PREFIX = "{\\rtf"
_RUN_OF_BLANK_LINES = re.compile(r"\n{3,}")


def strip_rtf(value: Optional[str]) -> Optional[str]:
    """`None`/blank in, `None` out. RTF in, its plain text out. Anything else, stripped."""
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if not stripped.startswith(_RTF_PREFIX):
        return stripped

    try:
        text = rtf_to_text(stripped)
    except Exception:
        # striprtf 0.0.33 raises (e.g. TypeError on a truncated \uc control word)
        # on malformed RTF that is real AutoCount data, not a bad payload someone
        # can retry - the push must not fail the whole sales order over a note,
        # and the backfill migration must not halt a deploy on one bad row.
        logger.warning("strip_rtf: rtf_to_text failed on %r", value[:40])
        return value

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    text = _RUN_OF_BLANK_LINES.sub("\n\n", text)
    return text or None
