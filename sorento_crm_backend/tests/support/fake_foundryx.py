"""A small, in-memory fake of the FoundryX AutoCount pull gateway, for the AutoCount
pull + review lane's browser pass ONLY (PLAN-autocount-pull-review.md "Local stack for
the browser pass"). Never imported by a unit test that patches `FoundryxAutocountClient.
TRANSPORT` directly - those keep using `_FakeFoundryX` in `tests/test_autocount_pull_
sr1.py`. This is a real ASGI app, started as its own process:

    venv/bin/python -m uvicorn tests.support.fake_foundryx:app --port 8009

Env:
    FAKE_FOUNDRYX_BUILD_SECONDS  - seconds a snapshot stays `building` before flipping
                                    `ready` (default 20).
    FAKE_FOUNDRYX_DATA           - a directory holding `<companyCode>-products.json` /
                                    `<companyCode>-stock_balances.json` (a JSON list of
                                    canonical rows each, see `scripts/build_fake_
                                    foundryx_data.py`). Unset -> the committed fixture
                                    rows (`tests/fixtures/autocount_pull/products-rows-
                                    page1.json` / `stock-rows-page1.json`) for ANY
                                    company code - served verbatim, never mutated.

Endpoints (the same three `FoundryxAutocountClient` calls, same shapes as the committed
fixtures): `POST /api/v1/autocount/snapshots`, `GET .../snapshots/{id}`,
`GET .../snapshots/{id}/rows?page&pageSize`. No auth beyond requiring an `X-API-Key`
header to be PRESENT (its value is never checked) - this is a rehearsal double, not a
security boundary.

Every error body is TOP-LEVEL `{"code", "message", ...}` - the same shape
`FoundryxAutocountClient._parse` reads off a real FoundryX error - never nested under
FastAPI's default `{"detail": ...}` wrapper (the custom exception handler below flattens
it), or `FoundryxPullError.code` would silently read "UNKNOWN" against this fake.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

# Reused, not re-implemented (the A5 rule this fake's `contentHash` must satisfy for
# `fetch_verified_snapshot`'s own warning check to stay clean).
from app.tasks.autocount_pull_tasks import _content_hash
from app.models.integration import Integration
from app.services.integration_admin_service import IntegrationAdminService

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "autocount_pull"

#: Read once per process at import time - a uvicorn restart is how a browser-pass
#: operator changes it, same as any other env-driven server setting.
BUILD_SECONDS = float(os.environ.get("FAKE_FOUNDRYX_BUILD_SECONDS", "20") or "20")

_MAX_PAGE_SIZE = 1000
_PROGRESS_STAGES = ("lookup:category", "lookup:brand", "lookup:uom", "assemble")
_PROGRESS_PAGES_TOTAL = 4

app = FastAPI(title="Fake FoundryX (browser pass only, never production)")

# snapshot_id -> {"snapshot_id", "company_code", "entity", "rows", "started_at"}.
# `started_at` is `time.monotonic()`, not wall-clock - immune to the system clock
# moving, which a wall-clock "started_at" is not.
_snapshots: dict[str, dict[str, Any]] = {}
# (companyCode, entity) -> the snapshot_id of its still-building attempt, so a second
# POST for the SAME pair while it is still building returns the SAME id (real FoundryX
# behaviour). Once ready, a later POST starts a genuinely new build.
_in_flight: dict[tuple[str, str], str] = {}

#: The `X-API-Key` header value of the most recent request this fake served, whatever
#: it was (this fake never validates the value, only its presence - see
#: `_require_api_key`). SR6's connection tests read this to prove
#: `FoundryxAutocountClient` actually sent the row's decrypted key, without the fake
#: needing to grow a real auth check of its own.
LAST_API_KEY: Optional[str] = None


@app.exception_handler(HTTPException)
async def _flatten_error(_request: Request, exc: HTTPException) -> JSONResponse:
    body = exc.detail if isinstance(exc.detail, dict) else {"code": "ERROR", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=body)


def _require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> None:
    global LAST_API_KEY
    LAST_API_KEY = x_api_key
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "INVALID_API_KEY",
                "message": "Missing, malformed, unknown or revoked key.",
            },
        )


def _unknown_snapshot() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "UNKNOWN_SNAPSHOT", "message": "No snapshot with that id."},
    )


def _load_rows(company_code: str, entity: str) -> list[dict]:
    data_dir = os.environ.get("FAKE_FOUNDRYX_DATA")
    if data_dir:
        path = Path(data_dir) / f"{company_code}-{entity}.json"
        if not path.exists():
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "NO_FAKE_DATA",
                    "message": f"FAKE_FOUNDRYX_DATA is set but {path} does not exist.",
                },
            )
        return json.loads(path.read_text())

    fixture_name = "products-rows-page1.json" if entity == "products" else "stock-rows-page1.json"
    return json.loads((FIXTURE_DIR / fixture_name).read_text())["rows"]


def _elapsed(record: dict) -> float:
    return time.monotonic() - record["started_at"]


def _is_ready(record: dict) -> bool:
    return _elapsed(record) >= BUILD_SECONDS


def _building_body(record: dict) -> dict:
    fraction = min(1.0, _elapsed(record) / BUILD_SECONDS) if BUILD_SECONDS > 0 else 1.0
    pages_done = min(_PROGRESS_PAGES_TOTAL, int(fraction * _PROGRESS_PAGES_TOTAL) + 1)
    stage_idx = min(len(_PROGRESS_STAGES) - 1, int(fraction * len(_PROGRESS_STAGES)))
    return {
        "snapshotId": record["snapshot_id"],
        "status": "building",
        "entity": record["entity"],
        "companyCode": record["company_code"],
        "progress": {
            "pagesDone": pages_done,
            "pagesTotal": _PROGRESS_PAGES_TOTAL,
            "stage": _PROGRESS_STAGES[stage_idx],
        },
    }


def _is_zero_price(value: Any) -> bool:
    try:
        return float(value) == 0
    except (TypeError, ValueError):
        return False


def _ready_header(record: dict) -> dict:
    rows = record["rows"]
    now = datetime.now(timezone.utc)
    header = {
        "snapshotId": record["snapshot_id"],
        "entity": record["entity"],
        "companyCode": record["company_code"],
        "status": "ready",
        "extractedAt": now.isoformat().replace("+00:00", "Z"),
        "expiresAt": (now + timedelta(hours=24)).isoformat().replace("+00:00", "Z"),
        "recordCount": len(rows),
        "complete": True,
        "contentHash": _content_hash(rows),
        "sourcePageSize": _MAX_PAGE_SIZE,
        "enrichMissCount": 0,
        "excludedCount": 0,
        "excludedRows": [],
    }
    if record["entity"] == "products":
        # Rows already carry FoundryX's own clamped price (a negative source value
        # is reported as "0.0", same as the committed fixture) - the two counters
        # cannot be told apart from clamped data alone, so every zero-priced row
        # counts as "zero", never "negative" (a fake-only simplification; nothing
        # asserts an exact split here).
        header["zeroListPriceCount"] = sum(1 for r in rows if _is_zero_price(r.get("list_price")))
        header["negativeListPriceCount"] = 0
    else:
        header["zeroPairs"] = 0
        header["negativePairs"] = 0
        header["fractionalPairs"] = 0
        header["negativePairList"] = []
        header["excludedNonzeroCount"] = 0
    return header


class SnapshotBuildBody(BaseModel):
    companyCode: str
    entity: str


@app.post("/api/v1/autocount/snapshots", status_code=202)
def build_snapshot(body: SnapshotBuildBody, _auth: None = Depends(_require_api_key)) -> dict:
    key = (body.companyCode, body.entity)
    existing_id = _in_flight.get(key)
    if existing_id is not None:
        existing = _snapshots.get(existing_id)
        if existing is not None and not _is_ready(existing):
            return _building_body(existing)

    snapshot_id = str(uuid.uuid4())
    record = {
        "snapshot_id": snapshot_id,
        "company_code": body.companyCode,
        "entity": body.entity,
        "rows": _load_rows(body.companyCode, body.entity),
        "started_at": time.monotonic(),
    }
    _snapshots[snapshot_id] = record
    _in_flight[key] = snapshot_id
    return _building_body(record)


@app.get("/api/v1/autocount/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: str, _auth: None = Depends(_require_api_key)) -> dict:
    record = _snapshots.get(snapshot_id)
    if record is None:
        raise _unknown_snapshot()
    if not _is_ready(record):
        return _building_body(record)
    return _ready_header(record)


@app.get("/api/v1/autocount/snapshots/{snapshot_id}/rows")
def get_rows(
    snapshot_id: str,
    page: int = Query(1, ge=1),
    pageSize: int = Query(_MAX_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),  # noqa: N803 - FoundryX's own casing
    _auth: None = Depends(_require_api_key),
) -> dict:
    record = _snapshots.get(snapshot_id)
    if record is None:
        raise _unknown_snapshot()

    rows = record["rows"]
    total_pages = max(1, -(-len(rows) // pageSize))  # ceil division
    if page > total_pages:
        raise HTTPException(
            status_code=404, detail={"code": "UNKNOWN_PAGE", "message": "No such page."}
        )
    start = (page - 1) * pageSize
    return {
        "snapshotId": snapshot_id,
        "page": page,
        "pageSize": pageSize,
        "totalPages": total_pages,
        "recordCount": len(rows),
        "rows": rows[start:start + pageSize],
    }


# ======================================================= SR6 connection UI seam


def seed_foundryx_connection(
    db: Session, *, base_url: str, api_key: str, active: bool = True
) -> Integration:
    """Create or update the ``foundryx-esb`` integration row through
    ``IntegrationAdminService``, so the stored credential is real Fernet ciphertext -
    never a hand-built row with a plaintext ``credentials_json`` column, which is not
    what ``FoundryxAutocountClient`` (SR6) will decrypt against.

    Used by ``tests/test_foundryx_connection_ui.py`` in place of the settings
    monkeypatch SR1-4 used - SR6 retires ``settings.foundryx_base_url`` /
    ``foundryx_api_key`` entirely, so the row is the only way left to configure a
    client under test.
    """
    service = IntegrationAdminService(db)
    row = db.query(Integration).filter(Integration.name == "foundryx-esb").first()
    if row is None:
        row = service.create(
            name="foundryx-esb",
            type_="autocount_esb",
            config_json={"base_url": base_url},
            credentials_json={"api_key": api_key},
            is_active=active,
        )
    else:
        service.update(
            row,
            config_json={"base_url": base_url},
            credentials_json={"api_key": api_key},
            is_active=active,
        )
    db.flush()
    return row
