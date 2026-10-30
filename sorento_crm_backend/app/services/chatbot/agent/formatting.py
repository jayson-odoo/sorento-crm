"""The agent's reply as WhatsApp markup (AGENTIC-P3 slice 6, V5).

Models write Markdown; chat mode and WhatsApp read `*bold*`, `_italic_` and `- ` bullets. Numbered
lists and line breaks are left as written.
"""
from __future__ import annotations

import re

_HEADING = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]+(.+?)[ \t]*$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"__(.+?)__")
_BULLET = re.compile(r"(?m)^([ \t]*)\*[ \t]+(?=\S)")


def to_whatsapp(text: str) -> str:
    text = _HEADING.sub(r"*\1*", text)
    text = _BOLD.sub(r"*\1*", text)
    text = _ITALIC.sub(r"_\1_", text)
    return _BULLET.sub(r"\1- ", text)
