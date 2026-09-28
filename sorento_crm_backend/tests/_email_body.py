"""Scope an assertion to what a template authored, not the shared layout around it.

Since #1349 every rendered mail is a whole branded document (layout table, header,
footer), so a test that regexes every `<td>` or `<tr>` of `body_html` would also meet the
layout's own cells. The layout brackets each custom text block with
`<!--block:custom_text-->` ... `<!--/block:custom_text-->`; this returns what sits inside,
in order, which is exactly the body the template's author wrote.
"""
from __future__ import annotations

import re

_BLOCK_RE = re.compile(r"<!--block:custom_text-->(.*?)<!--/block:custom_text-->", re.S)


def authored_html(body_html: str) -> str:
    parts = _BLOCK_RE.findall(body_html or "")
    assert parts, "no custom text block in the rendered mail"
    return "\n".join(parts)
