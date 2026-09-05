"""Port of `build-ctx.js` (spine RS-2): the six-key hub every later stage reads.

n8n's version replaced five by-name producers with one. In the CRM the by-name hazard
does not exist at all, so this file is small - but the SHAPE has to survive, byte for
byte, because `route-turn` spreads `ctx.access` into its own output and n8n's downstream
nodes still read `$('build-ctx').first().json.ctx.<key>` during the migration (AC-110).

EVERY KEY IS ONE PRODUCER'S VALUE, VERBATIM. No reshaping, no defaults, no `|| {}`. A
reader that used to see `undefined` still sees a missing key. `media` is nullable on
purpose: the media lane runs on a minority of turns.
"""
from __future__ import annotations

from typing import Any


def build_ctx(
    *,
    contact: Any,
    text: Any,
    session: Any,
    parse: Any,
    access: Any,
    media: Any = None,
) -> list[dict[str, Any]]:
    """The `{ctx}` envelope, as one n8n item list.

    The item is `{ctx}`, NOT `{...input, ctx}`: `route-turn` spreads its input, so an
    extra key here would ride into `escalate-catalog` and on into what gets persisted.
    """
    ctx = {
        "contact": contact,
        "text": text,
        "session": session,
        "parse": parse,
        "access": access,
        "media": media,
    }
    return [{"json": {"ctx": ctx}}]
