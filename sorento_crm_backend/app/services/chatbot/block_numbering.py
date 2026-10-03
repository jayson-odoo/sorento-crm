"""Block numbering for card replies: one 1..N run across every section of a reply."""
from __future__ import annotations

import re


BLOCK_START_RE = re.compile(r"^(?:\d+\. )?\*(?:Company|Product Code|Order Number):\*")


def renumber(groups: list[list[str]], start: int | None = None) -> list[list[str]]:
    """Number the block paragraphs across all `groups` when there is more than one, on from
    `start` (else the first block's own number, else 1, so a counted set's continuation page
    keeps its offset); a lone block, and every non-block paragraph, is left as it is."""
    if sum(1 for g in groups for p in g if BLOCK_START_RE.match(p)) < 2:
        return groups
    if start is None:
        first = next(p for g in groups for p in g if BLOCK_START_RE.match(p))
        found = re.match(r"^(\d+)\. ", first)
        start = int(found.group(1)) if found else 1
    n = start - 1
    out: list[list[str]] = []
    for g in groups:
        done: list[str] = []
        for p in g:
            if BLOCK_START_RE.match(p):
                n += 1
                p = f"{n}. " + re.sub(r"^\d+\. ", "", p)
            done.append(p)
        out.append(done)
    return out
