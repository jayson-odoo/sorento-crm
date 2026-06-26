"""Guard the DataGrid list-endpoint pagination cap (PLAN-unified-list-toolbar Phase 0).

Root cause of the "per-page 500 -> empty grid" bug: list endpoints capped the
`limit` query param below the page sizes the frontend offers, so a large page
size 422'd and the grid rendered empty. Fix: a shared MAX_PAGE_LIMIT (1000) used
as the `le=` on every ListResponse list endpoint. These tests stop that cap from
silently drifting back down.
"""
import ast
import re
from pathlib import Path

import pytest

from app.schemas.common import MAX_PAGE_LIMIT

API_V1 = Path(__file__).resolve().parent.parent / "app" / "api" / "v1"

# `limit: int = Query(...)` — capture the full arg list so we can read `le=` and
# skip non-grid caps (those carry a `description=`, e.g. dashboard "top N" sizes).
_LIMIT_QUERY = re.compile(r"limit:\s*int\s*=\s*Query\((?P<args>[^)]*)\)", re.S)
_LE = re.compile(r"\ble=(\d+)")


def test_max_page_limit_matches_frontend_ceiling():
    # FE `data-grid-pagination.tsx` offers up to 1000 rows/page; keep them in lockstep.
    assert MAX_PAGE_LIMIT == 1000


def _list_response_files():
    for path in API_V1.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "response_model=ListResponse[" in text:
            yield path, text


def test_no_listresponse_endpoint_caps_limit_below_max_page_limit():
    """Every DataGrid list endpoint must allow at least MAX_PAGE_LIMIT rows.

    Numeric `le=<n>` caps below 1000 on a `limit` param in a file that serves a
    `ListResponse[...]` are the exact regression we fixed — they should read
    `le=MAX_PAGE_LIMIT` instead.
    """
    offenders: list[str] = []
    for path, text in _list_response_files():
        for m in _LIMIT_QUERY.finditer(text):
            args = m.group("args")
            # Skip non-grid caps — they carry an explicit description (e.g. the
            # stock dashboard "Cap on list sizes (top warehouses...)").
            if "description=" in args:
                continue
            le = _LE.search(args)
            if le and int(le.group(1)) < MAX_PAGE_LIMIT:
                line = text[: m.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(API_V1)}:{line} le={le.group(1)}")
    assert not offenders, (
        "List endpoints cap `limit` below MAX_PAGE_LIMIT (use le=MAX_PAGE_LIMIT):\n"
        + "\n".join(offenders)
    )
