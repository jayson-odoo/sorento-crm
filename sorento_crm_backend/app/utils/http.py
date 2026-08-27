"""HTTP header primitives shared by every route that hands bytes back.

One function lives here so far, and it exists because of a real 500: an
attachment named ``2026-7-27 库存明细.xlsx`` downloaded fine right up to the
point where the header was written, then failed with ``'latin-1' codec can't
encode characters in position 33-36``. Header values are latin-1 on the wire, so
a raw filename in ``Content-Disposition`` is a crash waiting for the first
customer who names a file in their own language.
"""
from __future__ import annotations

import re
from urllib.parse import quote

# Everything outside printable US-ASCII becomes "_" in the plain parameter. That
# covers CJK and accents, and it also covers CR/LF, which would otherwise let a
# filename inject a header of its own.
_NON_ASCII = re.compile(r"[^\x20-\x7e]")

_FALLBACK_NAME = "download"


def content_disposition(name: str, inline: bool = False) -> str:
    """A ``Content-Disposition`` value that survives any filename.

    Emits both forms RFC 6266 allows: a quoted ASCII ``filename`` an old client
    understands, and the RFC 5987 ``filename*=UTF-8''...`` a modern one prefers
    and uses in place of it. So a Chinese name reaches the browser intact while
    the header itself stays latin-1 clean.
    """
    disposition = "inline" if inline else "attachment"
    cleaned = (name or "").strip()
    if not cleaned:
        cleaned = _FALLBACK_NAME

    ascii_name = _NON_ASCII.sub("_", cleaned)
    # Backslash first: escaping the quote introduces backslashes of its own.
    ascii_name = ascii_name.replace("\\", "\\\\").replace('"', '\\"')

    return (
        f"{disposition}; filename=\"{ascii_name}\"; "
        f"filename*=UTF-8''{quote(cleaned, safe='')}"
    )
