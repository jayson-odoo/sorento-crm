"""The agent's reply as WhatsApp markup (AGENTIC-P3 slice 6, V5).

Models write Markdown; chat mode and WhatsApp read `*bold*`, `_italic_` and `- ` bullets. Numbered
lists and line breaks are left as written.
"""
from __future__ import annotations

import re

_HEADING = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]+(.+?)[ \t]*$")
# A marker pair counts only when nothing word-like touches it on the outside, so a product code
# (`A**B`, `HX__200__B`) or an attribute (`obj.__init__`) is left alone.
_BOLD = re.compile(r"(?<![\w*.])\*\*(?=\S)(.+?)(?<=\S)\*\*(?![\w*])")
_ITALIC = re.compile(r"(?<![\w_.])__(?=\S)(.+?)(?<=\S)__(?![\w_])")
_BULLET = re.compile(r"(?m)^([ \t]*)\*[ \t]+(?=\S)")


def to_whatsapp(text: str) -> str:
    text = _HEADING.sub(lambda m: "*" + m.group(1).replace("**", "") + "*", text)
    text = _BOLD.sub(r"*\1*", text)
    text = _ITALIC.sub(r"_\1_", text)
    return _BULLET.sub(r"\1- ", text)
