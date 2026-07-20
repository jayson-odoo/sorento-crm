"""Group integration failures into signatures so the dashboard can name a cause.

A failed count answers "did something break". It does not answer "what broke",
which is the only question worth asking at 2am. The raw `error_message` cannot
group them: it embeds record ids, retry timestamps and payload echoes, so one
recurring fault shows up as N distinct one-off errors and the pattern is lost.

`normalize` masks the tokens that demonstrably vary between instances of the same
fault — uuids, digit runs, ISO timestamps — and nothing else. Words are never
touched: over-normalising is the worse error, because it merges two real faults
into one line and the rarer one disappears entirely.

The signature is (status_code, normalised prose). Same words under a 401 and a
403 are different problems and stay apart.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

MAX_SAMPLE_CHARS = 300
DEFAULT_LIMIT = 3

_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE
)
_ISO_TS = re.compile(
    r"\d{4}-\d{2}-\d{2}[t ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?"
)  # input is already lowercased, hence `t` not `T`
# No `\b` anchors: a digit run butted against a unit ("30412ms") has no word
# boundary between the digit and the letter, so anchoring would skip it.
_DIGITS = re.compile(r"\d+")
_WHITESPACE = re.compile(r"\s+")

# httpx appends "For more information check: <mdn url>" to every raise_for_status
# message. It is identical on every row and consumed the whole display width,
# pushing the part that actually identifies the fault out of view.
_HTTPX_BOILERPLATE = re.compile(r"\s*For more information check:.*", re.IGNORECASE | re.DOTALL)


# Segments shorter than this are punctuation noise ("'", "/") and would not
# narrow anything. Kept low deliberately: short-but-decisive segments like
# "/message'" are exactly what separates two faults on the same endpoint family.
MIN_TERM_CHARS = 4
# Cap on how many terms travel in the drill-down URL.
MAX_FILTER_TERMS = 6


@dataclass
class FailureSignature:
    """One distinct fault, with a real message you can paste into a log search."""

    signature: str
    sample_message: str
    status_code: Optional[int]
    count: int
    # Literal substrings shared by every row in this group, AND-ed by the
    # drill-down filter. Deliberately NOT the sample message: that embeds a
    # contact id and would select the single row it came from.
    #
    # A LIST, not one substring: on live data the longest single run of the 401
    # fault stops at the url version digit ("…respond.io/v"), which also matches
    # a DIFFERENT fault against /conversation/status. One term returned 433 rows
    # for a group of 428. AND-ing every stable segment restores the boundary.
    filter_terms: list[str] = field(default_factory=list)


def normalize(message: Optional[str]) -> str:
    """Collapse a message to a stable grouping key.

    Order matters: uuids and timestamps are masked before the generic digit run,
    otherwise `_DIGITS` shreds them into unrecognisable fragments first.
    """
    text = (message or "").strip().lower()
    text = _UUID.sub("<id>", text)
    text = _ISO_TS.sub("<ts>", text)
    text = _DIGITS.sub("<n>", text)
    return _WHITESPACE.sub(" ", text).strip()


def _display(message: Optional[str]) -> str:
    """Trim a message to the part that identifies the fault.

    Only known-boilerplate suffixes are removed — never leading content, which
    is where the actual error lives.
    """
    original = (message or "").strip()
    trimmed = _HTTPX_BOILERPLATE.sub("", original).strip()
    # If the marker sat at position 0 the trim would blank the row entirely.
    # An ugly message beats an empty one — keep the original.
    return (trimmed or original)[:MAX_SAMPLE_CHARS]


def _filter_terms(message: Optional[str]) -> list[str]:
    """Every run of the message containing no volatile token, longest first.

    Operates on the ORIGINAL text (not `normalize`'s output) because each term is
    fed to a SQL LIKE and must appear verbatim in every row of the group.

    Returns them all rather than just the longest because the longest is not
    necessarily the distinguishing one — see `filter_terms` on the dataclass.
    Empty when nothing stable survives; an empty filter is honest, whereas a
    fragment that over-matches would report a count the group does not have.
    """
    text = _display(message)
    for pattern in (_UUID, _ISO_TS, _DIGITS):
        text = pattern.sub("\x00", text)

    segments = {seg.strip() for seg in text.split("\x00")}
    kept = [seg for seg in segments if len(seg) >= MIN_TERM_CHARS]
    kept.sort(key=len, reverse=True)
    return kept[:MAX_FILTER_TERMS]


def top_failures(
    rows: Iterable[Any], limit: int = DEFAULT_LIMIT
) -> list[FailureSignature]:
    """Aggregate pre-grouped rows into the worst `limit` distinct faults.

    Each row supplies `status_code`, `error_message` and `count` — the shape the
    health query already groups by, so this adds no extra database work.
    """
    buckets: dict[tuple[Optional[int], str], FailureSignature] = {}

    for row in rows:
        status_code = getattr(row, "status_code", None)
        message = getattr(row, "error_message", None)
        count = int(getattr(row, "count", 0) or 0)
        key = (status_code, normalize(message))

        existing = buckets.get(key)
        if existing is None:
            buckets[key] = FailureSignature(
                signature=key[1],
                sample_message=_display(message),
                status_code=status_code,
                count=count,
                filter_terms=_filter_terms(message),
            )
        else:
            existing.count += count

    return sorted(buckets.values(), key=lambda f: f.count, reverse=True)[:limit]
