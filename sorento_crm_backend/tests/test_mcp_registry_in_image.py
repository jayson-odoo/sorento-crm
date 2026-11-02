"""MCP-REGISTRY-IMAGE: the `mcp_tools` registry syncs inside the deployed backend image.

`sync_catalog` imported `sorento_crm_mcp`, which the backend image does not contain (it is built
with `context: ./sorento_crm_backend`, and `requirements.txt` never named the package). The boot
hook in `app/main.py` swallowed the ImportError, so production's `mcp_tools` table has never been
synced since the hook landed on 1 May 2026. Dev and CI run in the monorepo, where the import
works, which is why no test saw it. The image-layout tests below make the package unimportable,
exactly as in the container.

Production also boots 4 gunicorn workers (`gunicorn.conf.py`), and each runs `startup_event`, so
four syncs start together. The concurrency test pins that they queue instead of colliding on the
`tool_name` unique index.
"""
from __future__ import annotations

import sys
import threading
import time
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine
from app.models.access import McpTool
from app.services import mcp_catalog_copy
from app.services import mcp_tool_registry_service as registry
from tests._pg_fixture import blank_session, pg_empty_schema


@pytest.fixture
def image_layout(monkeypatch):
    """The backend as the production container sees it: the MCP package cannot be imported."""
    for name in ("sorento_crm_mcp", "sorento_crm_mcp.catalog", "sorento_crm_mcp.module_loader"):
        monkeypatch.setitem(sys.modules, name, None)
    yield


def test_registry_specs_are_the_backend_catalog_copy():
    """Pins the source: the backend's verbatim copy, which `test_mcp_catalog_in_image.py` keeps
    byte-identical to the MCP package's catalog."""
    assert tuple(registry._load_specs()) == mcp_catalog_copy.CATALOG


def test_sync_catalog_writes_every_catalog_tool_in_the_image_layout(image_layout):
    with blank_session() as db:
        report = registry.sync_catalog(db)
        db.flush()

        rows = {r.tool_name: r for r in db.query(McpTool).all()}

    expected = {spec.name: spec for spec in mcp_catalog_copy.CATALOG}
    assert set(rows) == set(expected)
    assert report.added == len(expected)
    assert all(r.is_active for r in rows.values())
    restricted = [s for s in expected.values() if s.restricted_fields]
    assert restricted, "the catalog declares restricted fields; the sync must carry them"
    for spec in restricted:
        assert rows[spec.name].restricted_fields == [
            {"key": key, "label": label} for key, label in spec.restricted_fields
        ]


@dataclass(frozen=True)
class _Spec:
    name: str
    description: str
    path: str
    method: str = "GET"
    module: str = ""
    restricted_fields: tuple = ()


def _wait_until_blocked_on_a_lock(pid: int, timeout: float = 10.0) -> None:
    with engine.connect() as probe:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            waiting = probe.execute(
                text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"), {"pid": pid}
            ).scalar()
            if waiting == "Lock":
                return
            probe.rollback()
            time.sleep(0.05)
    raise AssertionError(f"the second sync (pid {pid}) never waited on the first one")


def test_two_boot_syncs_at_once_both_succeed(monkeypatch):
    """Two workers booting together: the second sync waits for the first to commit, then
    updates the rows the first inserted, instead of failing on the unique `tool_name`."""
    stem = f"zzt_registry_{uuid.uuid4().hex[:8]}"
    specs = tuple(_Spec(f"{stem}_{i}", f"tool {i}", f"/api/v1/{stem}/{i}") for i in range(3))
    monkeypatch.setattr(registry, "_load_specs", lambda: specs)

    with pg_empty_schema([McpTool.__table__]) as first:
        translate = first.bind.get_execution_options()["schema_translate_map"]
        second_engine = engine.execution_options(schema_translate_map=translate)
        outcome: dict = {}

        def second_worker():
            with Session(bind=second_engine) as second:
                outcome["pid"] = second.execute(text("SELECT pg_backend_pid()")).scalar()
                # A broken lock (one commit does not release) then fails as
                # LockNotAvailable instead of hanging the run.
                second.execute(text("SET LOCAL lock_timeout = '20s'"))
                try:
                    outcome["report"] = registry.sync_catalog(second)
                    second.commit()
                except Exception as exc:  # noqa: BLE001 - the assertion below names it
                    second.rollback()
                    outcome["error"] = exc

        registry.sync_catalog(first)  # holds its transaction open, as a booting worker does
        worker = threading.Thread(target=second_worker, daemon=True)
        worker.start()
        while "pid" not in outcome and worker.is_alive():
            time.sleep(0.01)
        try:
            _wait_until_blocked_on_a_lock(outcome["pid"])
        finally:
            first.commit()
            worker.join(timeout=30)

        assert not worker.is_alive(), "the second sync never finished"
        assert "error" not in outcome, f"the second sync failed: {outcome.get('error')!r}"
        assert outcome["report"].added == 0
        assert outcome["report"].updated == len(specs)

        first.expire_all()
        rows = first.query(McpTool).all()
        assert sorted(r.tool_name for r in rows) == sorted(s.name for s in specs)
        assert all(r.is_active for r in rows)
