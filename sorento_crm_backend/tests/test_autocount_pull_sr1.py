"""RED tests for SR1 of the AutoCount pull + review lane (issue #1045).

Covers: AC-PL-2..7, AC-BD-1..5, AC-BD-7, AC-PP-1..6, AC-PM-1..2, AC-T-2.
Plan: documentation/plans/autocount/PLAN-autocount-pull-review.md
UAC:  documentation/plans/autocount/autocount-pull-review-acceptance-criteria.md

Nothing under test exists yet - the settings fields, the FoundryX client module, the pull
service, the pull router, the preview task and the two permission slugs are ALL the coder's
SR1 deliverable. Every one of those names is therefore imported (or, for `settings`, assigned)
INSIDE a fixture or a test body, never at module import time, so a missing piece fails only the
test/fixture that needs it - never the whole file at collection.

Two substrates, for two different reasons:

* `env` (`tests._pg_fixture.blank_session`) drives the HTTP routes through a real `TestClient`,
  exactly the `_Env` shape `test_ingest_deletions.py` uses. Nothing here runs a background task,
  so the ordinary "one session inside one rolled-back transaction" fixture is enough.
* `task_db` drives `preview_autocount_pull(db_job_id)` directly, synchronously, the way
  `test_import_outcome_attribution.py` drives `process_delivery_order_detail_import`. That task
  opens its OWN `SessionLocal()` (module convention: `from app.database import SessionLocal` at
  the top of `app/tasks/*.py`, confirmed in `import_tasks.py`) and `MasterIngestService.ingest`'s
  dry run calls `self.db.rollback()` on ITS session, not the caller's - so a *second*, real
  Postgres connection would either write for real to the shared scratch schema (leaking into
  later tests, the exact failure `test_import_outcome_attribution.py`'s docstring warns about)
  or roll back somewhere the seeding fixture cannot see. Instead `task_db` hands out a
  `sessionmaker` bound to the SAME `Connection` `env`-style fixtures use, under
  `join_transaction_mode="create_savepoint"` - proven empirically (spiked before this file was
  written) that two `Session` objects sharing one connection see each other's commits and that
  nothing survives a later, unrelated `blank_session()` once the outer transaction rolls back.
  `app.tasks.autocount_pull_tasks.SessionLocal` AND `app.database.SessionLocal` are both patched
  to it: the task's own top-level import needs the first, `ImportOutcome`'s own late
  `from app.database import SessionLocal as factory` (inside `flush()`) needs the second.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards (repo convention, see test_ingest_deletions.py).
from app.main import app  # noqa: E402

from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import _BLANK, blank_schema_engine, blank_session, unique_code

MARKER = "ZZTAP1"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "autocount_pull"
BASE_URL = "http://foundryx.test"
API_KEY = "fxa_test_SECRETKEY123"
PULLS_URL = "/api/v1/autocount/pulls"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


# ============================================================== fake FoundryX


class _FakeFoundryX:
    """An httpx handler standing in for the FoundryX gateway.

    Dispatch is on method + path shape only (never on a persisted snapshot store) -
    good enough for a contract test, and it lets each test point `status` / `rows`
    at exactly the fixture it wants to prove a decision against.
    """

    def __init__(self):
        self.calls: list[dict] = []
        self.build = (
            202,
            {
                "snapshotId": str(uuid.uuid4()),
                "status": "building",
                "entity": "products",
                "companyCode": "SRT",
            },
        )
        self.raise_on_build: Exception | None = None
        self.status = (200, _fixture("products-header-building.json"))
        self.rows: dict[int, tuple[int, dict]] = {1: (200, _fixture("products-rows-page1.json"))}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "url": str(request.url),
                "headers": {k.lower(): v for k, v in request.headers.items()},
                "params": dict(request.url.params),
                "json": json.loads(request.content) if request.content else None,
            }
        )
        path = request.url.path
        if request.method == "POST" and path.endswith("/api/v1/autocount/snapshots"):
            if self.raise_on_build is not None:
                raise self.raise_on_build
            status_code, body = self.build
            return httpx.Response(status_code, json=body)
        if request.method == "GET" and path.endswith("/rows"):
            page = int(request.url.params.get("page", "1"))
            status_code, body = self.rows.get(page, (404, {"code": "UNKNOWN_PAGE"}))
            return httpx.Response(status_code, json=body)
        if request.method == "GET" and "/snapshots/" in path:
            status_code, body = self.status
            return httpx.Response(status_code, json=body)
        return httpx.Response(404, json={"code": "UNKNOWN_ROUTE"})


def _patch_foundryx(monkeypatch, fake: _FakeFoundryX) -> None:
    """Point Settings + the client's shared TRANSPORT at the fake.

    Every one of these three attributes is the CONTRACT the coder builds - none exists
    today, so this raises (ValueError on the Settings assignment, ModuleNotFoundError on
    the client import) until SR1 lands. That is the correct red for every test that calls
    this helper.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "foundryx_base_url", BASE_URL, raising=False)
    monkeypatch.setattr(settings, "foundryx_api_key", API_KEY, raising=False)

    import app.services.foundryx_autocount_client as client_mod

    monkeypatch.setattr(client_mod, "TRANSPORT", httpx.MockTransport(fake.handler), raising=False)


# ==================================================================== rows


def _canonical_row(code: str, **overrides) -> dict:
    row = {
        "source_ref": f"{MARKER}:{code}",
        "code": code,
        "name": f"{MARKER} {code}",
        "description": f"{MARKER} {code}",
        "category_code": f"{MARKER}CAT",
        "brand_code": f"{MARKER}BRAND",
        "list_price": "10.0",
        "is_active": True,
    }
    row.update(overrides)
    return row


def _header(*, record_count: int, company_code: str = "SRT", complete: bool = True,
            content_hash: str = "deadbeef" * 8, zero_list_price_count: int = 0,
            negative_list_price_count: int = 0, excluded_count: int = 0,
            excluded_rows: list | None = None) -> dict:
    header = {
        "entity": "products",
        "companyCode": company_code,
        "status": "ready",
        "recordCount": record_count,
        "complete": complete,
        "contentHash": content_hash,
        "sourcePageSize": 1000,
        "zeroListPriceCount": zero_list_price_count,
        "negativeListPriceCount": negative_list_price_count,
        "enrichMissCount": 0,
        "excludedCount": excluded_count,
    }
    if excluded_rows is not None:
        header["excludedRows"] = excluded_rows
    return header


# ============================================================== job seeding


def _seed_pull_job(db, *, job_type: str, user_id: str, company_id: str, entity: str,
                    company_code: str, snapshot_id: str, phase: str,
                    header: dict | None = None, created_at: datetime | None = None,
                    extra: dict | None = None):
    """Creates + commits an `import_jobs` row directly, bypassing the route.

    Returns the ORM `id` (a `uuid.UUID`), the shape `preview_autocount_pull` and
    `JobService.get_job_by_db_id` both expect.
    """
    from app.models.job import ImportJob, JobStatus

    meta = {
        "autocount_pull": {
            "entity": entity,
            "company_code": company_code,
            "snapshot_id": snapshot_id,
            "phase": phase,
            "progress": None,
            "header": header,
            "counts": {},
            "confirm_blocked_reason": None,
            "compare": None,
            "apply_job_id": None,
        }
    }
    if extra:
        meta["autocount_pull"].update(extra)
    job = ImportJob(
        id=uuid.uuid4(),
        job_id=str(uuid.uuid4()),
        job_type=job_type,
        status=JobStatus.PENDING.value,
        user_id=user_id,
        company_id=company_id,
        job_metadata=meta,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    return job.id


def _job_row(db, job_id) -> dict | None:
    """A raw read, without the ORM company-scope filter - job-tracking rows are
    never company-partitioned, same reasoning as test_ingest_deletions.py's `row()`."""
    row = db.execute(
        text(
            "SELECT id, job_type, status, company_id, user_id, metadata, error, "
            "created_at FROM import_jobs WHERE id = :id"
        ),
        {"id": str(job_id)},
    ).mappings().first()
    return dict(row) if row else None


def _job_count(db) -> int:
    return db.execute(text("SELECT count(*) FROM import_jobs")).scalar()


def _job_rows(db, job_id) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT outcome, code, message, value, identity FROM import_job_rows "
            "WHERE import_job_id = :id"
        ),
        {"id": str(job_id)},
    ).mappings().all()
    return [dict(r) for r in rows]


# ========================================================== HTTP-route env


class _Env:
    def __init__(self, db, fake: _FakeFoundryX):
        self.db = db
        self.fake = fake
        self.company_a = DEFAULT_COMPANY_ID
        self.company_a_code = "SRT"

        from app.models.company import Company

        suffix = uuid.uuid4().hex[:8]
        other = Company(id=str(uuid.uuid4()), name=f"{MARKER} B {suffix}", code=f"ZL{suffix}")
        db.add(other)
        db.flush()
        self.company_b = str(other.id)

        self.client: TestClient | None = None
        self.principal: dict | None = None
        self.scope = frozenset({self.company_a})

    def user(self, *perm_slugs: str) -> dict:
        """A user holding EXACTLY the given permission slugs - never superadmin."""
        from app.models.user import (
            User,
            UserPermission,
            UserRole,
            UserRoleAssignment,
            UserRolePermission,
        )

        uid = str(uuid.uuid4())
        role_id = str(uuid.uuid4())
        self.db.add(
            UserRole(
                id=role_id, slug=f"{MARKER.lower()}-role-{uid[:8]}",
                name=f"{MARKER} role {uid[:8]}",
                description="", is_protected=False, is_default=False,
            )
        )
        self.db.add(
            User(id=uid, email=f"{MARKER.lower()}-{uid[:8]}@test.com", name="U", status="ACTIVE")
        )
        self.db.flush()
        self.db.add(UserRoleAssignment(user_id=uid, role_id=role_id))
        for slug in perm_slugs:
            perm = self.db.query(UserPermission).filter_by(slug=slug).one_or_none()
            if perm is None:
                perm = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
                self.db.add(perm)
                self.db.flush()
            self.db.add(
                UserRolePermission(id=str(uuid.uuid4()), role_id=role_id, permission_id=perm.id)
            )
        self.db.commit()
        return {"id": uid, "email": f"{MARKER.lower()}-{uid[:8]}@test.com"}

    def as_user(self, principal: dict, *, scope=None) -> None:
        self.principal = principal
        self.scope = scope if scope is not None else frozenset({self.company_a})

    # ------------------------------------------------------------- calls
    def post_pull(self, entity: str):
        return self.client.post(PULLS_URL, json={"entity": entity})

    def get_pull(self, job_id):
        return self.client.get(f"{PULLS_URL}/{job_id}")

    def get_current(self, entity: str):
        return self.client.get(f"{PULLS_URL}/current", params={"entity": entity})


@pytest.fixture
def env(monkeypatch):
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    fake = _FakeFoundryX()
    _patch_foundryx(monkeypatch, fake)

    with blank_session() as db:
        e = _Env(db, fake)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: e.principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: e.principal

        async def _override_scope():
            set_company_scope(db, e.scope)
            return e.scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        e.client = TestClient(app)
        try:
            yield e
        finally:
            app.dependency_overrides.clear()


# =============================================================== task_db


@pytest.fixture
def task_db(monkeypatch):
    """A sessionmaker bound to ONE connection over the shared blank schema.

    See the module docstring for why this exists instead of `blank_session()` +
    `patch.object(task_module, "SessionLocal", ...)` on a private per-test schema
    (`test_import_outcome_attribution.py`'s pattern): reusing the shared blank schema's
    Connection under `create_savepoint` gets the same "nothing survives teardown, nothing
    leaks to a sibling test" guarantee with none of the per-test DDL cost, and it was
    spiked empirically (two Session objects on one Connection: the second's commit is
    visible to the first; a rollback on either leaves nothing for a later, independent
    `blank_session()` to see).
    """
    engine = blank_schema_engine()
    connection = engine.connect()
    transaction = connection.begin()
    name = _BLANK["name"]
    connection.exec_driver_sql(
        f'SET LOCAL search_path TO "{name}", "{name}_scm", "{name}_dealer_kit", '
        f'"{name}_chatbot", "{name}_projects"'
    )
    factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint", autoflush=False)
    db = factory()

    # Covers ImportOutcome's own late `from app.database import SessionLocal as factory`.
    monkeypatch.setattr("app.database.SessionLocal", factory)
    try:
        yield db, factory
    finally:
        db.close()
        transaction.rollback()
        connection.close()


def _run_preview(monkeypatch, factory, job_id):
    monkeypatch.setattr("app.tasks.autocount_pull_tasks.SessionLocal", factory, raising=False)
    from app.tasks.autocount_pull_tasks import preview_autocount_pull

    preview_autocount_pull(job_id)


# ======================================================================= PL


class TestPullStart:
    def test_pl_2a_no_permission_is_403_with_no_job_and_no_outbound_call(self, env):
        env.as_user(env.user())
        resp = env.post_pull("products")
        assert resp.status_code == 403, resp.text
        assert _job_count(env.db) == 0
        assert env.fake.calls == []

    def test_pl_2b_multi_company_scope_is_400_with_no_job_and_no_outbound_call(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user, scope=frozenset({env.company_a, env.company_b}))
        resp = env.post_pull("products")
        assert resp.status_code == 400, resp.text
        assert "single company" in resp.text
        assert _job_count(env.db) == 0
        assert env.fake.calls == []

    @pytest.mark.parametrize(
        "entity,perm,job_type",
        [
            ("products", "master_data.products.autocount_pull", "autocount_products_pull"),
            ("stock_balances", "inventory.stock.autocount_pull", "autocount_stock_pull"),
        ],
    )
    def test_pl_3_success_calls_foundryx_and_creates_one_pending_job(
        self, env, entity, perm, job_type
    ):
        user = env.user(perm)
        env.as_user(user)

        resp = env.post_pull(entity)

        assert resp.status_code in (200, 201, 202), resp.text
        body = resp.json()
        assert body["job_id"]
        assert body.get("phase") == "building"

        assert len(env.fake.calls) == 1
        call = env.fake.calls[0]
        assert call["method"] == "POST"
        assert call["path"].endswith("/api/v1/autocount/snapshots")
        assert call["json"] == {"companyCode": "SRT", "entity": entity}
        assert call["headers"].get("x-api-key") == API_KEY

        assert _job_count(env.db) == 1
        row = _job_row(env.db, body["job_id"])
        assert row is not None
        assert row["job_type"] == job_type
        assert row["status"] == "pending"
        assert str(row["company_id"]) == env.company_a
        assert row["user_id"] == user["id"]
        meta = row["metadata"]["autocount_pull"]
        assert meta["entity"] == entity
        assert meta["company_code"] == "SRT"
        assert meta["phase"] == "building"
        assert meta["snapshot_id"]

    def test_pl_4a_second_start_returns_the_same_job_and_makes_no_second_call(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)

        first = env.post_pull("products").json()
        second = env.post_pull("products").json()

        assert second["job_id"] == first["job_id"]
        assert len(env.fake.calls) == 1
        assert _job_count(env.db) == 1

    def test_pl_4b_get_current_returns_the_open_pull_else_404(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        started = env.post_pull("products").json()

        resp = env.get_current("products")
        assert resp.status_code == 200, resp.text
        assert resp.json()["job_id"] == started["job_id"]

        none_yet = env.get_current("stock_balances")
        assert none_yet.status_code == 404

    def test_pl_4b_current_excludes_another_users_open_pull(self, env):
        owner = env.user("master_data.products.autocount_pull")
        env.as_user(owner)
        env.post_pull("products")

        other = env.user("master_data.products.autocount_pull")
        env.as_user(other)
        resp = env.get_current("products")
        assert resp.status_code == 404

    def test_pl_4b_current_excludes_another_companys_open_pull(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user, scope=frozenset({env.company_a}))
        env.post_pull("products")

        env.as_user(user, scope=frozenset({env.company_b}))
        resp = env.get_current("products")
        assert resp.status_code == 404


class TestPullStartErrorLadder:
    @pytest.mark.parametrize(
        "fixture_name,http_status,expected_status,expected_code",
        [
            ("error-409-pull-not-enabled.json", 409, 409, "PULL_NOT_ENABLED"),
            ("error-409-push-active.json", 409, 409, "PUSH_ACTIVE"),
            ("error-429-too-many-builds.json", 429, 429, "TOO_MANY_BUILDS"),
            ("error-401-invalid-api-key.json", 401, 502, "NOT_CONFIGURED"),
            ("error-404-unknown-company.json", 404, 502, "NOT_CONFIGURED"),
        ],
        ids=["pull_not_enabled", "push_active", "too_many_builds", "invalid_key_401", "unknown_company_404"],
    )
    def test_pl_6_foundryx_error_ladder_on_start(
        self, env, fixture_name, http_status, expected_status, expected_code
    ):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        env.fake.build = (http_status, _fixture(fixture_name))

        resp = env.post_pull("products")

        assert resp.status_code == expected_status, resp.text
        assert resp.json()["code"] == expected_code
        assert API_KEY not in resp.text
        assert _job_count(env.db) == 0

    def test_pl_6_foundryx_403_maps_to_not_configured(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        env.fake.build = (
            403,
            {"code": "FORBIDDEN", "message": "no", "companyCode": "SRT", "entity": "products"},
        )

        resp = env.post_pull("products")

        assert resp.status_code == 502, resp.text
        assert resp.json()["code"] == "NOT_CONFIGURED"
        assert _job_count(env.db) == 0

    def test_pl_6_transport_failure_maps_to_unreachable(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        env.fake.raise_on_build = httpx.ConnectError("boom")

        resp = env.post_pull("products")

        assert resp.status_code == 502, resp.text
        assert resp.json()["code"] == "UNREACHABLE"
        assert _job_count(env.db) == 0

    def test_pl_6_timeout_maps_to_unreachable(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        env.fake.raise_on_build = httpx.TimeoutException("slow")

        resp = env.post_pull("products")

        assert resp.status_code == 502, resp.text
        assert resp.json()["code"] == "UNREACHABLE"
        assert _job_count(env.db) == 0

    def test_pl_7_settings_unset_refuses_with_zero_outbound_calls(self, env, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "foundryx_base_url", "", raising=False)
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)

        resp = env.post_pull("products")

        assert resp.status_code == 503, resp.text
        assert resp.json()["code"] == "NOT_CONFIGURED"
        assert env.fake.calls == []
        assert _job_count(env.db) == 0


# ======================================================================= BD


class TestBuilding:
    def test_bd_1_get_on_building_pull_returns_phase_and_progress_no_enqueue(self, env, monkeypatch):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        started = env.post_pull("products").json()
        env.fake.status = (200, _fixture("products-header-building.json"))

        captured = []
        monkeypatch.setattr(
            "app.services.autocount_pull_service.enqueue_job",
            lambda *a, **k: captured.append((a, k)) or MagicMock(id=str(uuid.uuid4())),
        )

        resp = env.get_pull(started["job_id"])

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["phase"] == "building"
        assert body["progress"] == {"pagesDone": 2, "pagesTotal": 4, "stage": "lookup:uom"}
        assert captured == []

    def test_bd_2a_ready_stores_header_and_enqueues_preview_exactly_once(self, env, monkeypatch):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        started = env.post_pull("products").json()
        env.fake.status = (200, _fixture("products-header-ready.json"))

        captured = []

        def _enqueue(func, *a, **k):
            captured.append({"func": func, "args": a, "kwargs": k})
            return MagicMock(id=str(uuid.uuid4()))

        monkeypatch.setattr("app.services.autocount_pull_service.enqueue_job", _enqueue)

        resp = env.get_pull(started["job_id"])

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["phase"] == "previewing"
        assert len(captured) == 1
        assert captured[0]["kwargs"].get("queue_name", "imports") == "imports"
        assert getattr(captured[0]["func"], "__name__", "") == "preview_autocount_pull"

        row = _job_row(env.db, started["job_id"])
        header = row["metadata"]["autocount_pull"]["header"]
        assert header is not None
        assert "excludedRows" not in header
        assert header["recordCount"] == 10

    def test_bd_2b_further_gets_enqueue_nothing_more(self, env, monkeypatch):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        started = env.post_pull("products").json()
        env.fake.status = (200, _fixture("products-header-ready.json"))

        captured = []
        monkeypatch.setattr(
            "app.services.autocount_pull_service.enqueue_job",
            lambda *a, **k: captured.append(1) or MagicMock(id=str(uuid.uuid4())),
        )

        env.get_pull(started["job_id"])
        env.get_pull(started["job_id"])
        resp = env.get_pull(started["job_id"])

        assert resp.status_code == 200, resp.text
        assert len(captured) == 1

    def test_bd_3_foundryx_failed_status_fails_the_job(self, env, monkeypatch):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        started = env.post_pull("products").json()
        env.fake.status = (200, _fixture("snapshot-failed.json"))
        monkeypatch.setattr(
            "app.services.autocount_pull_service.enqueue_job", lambda *a, **k: None
        )

        resp = env.get_pull(started["job_id"])

        assert resp.status_code == 200, resp.text
        assert resp.json()["phase"] == "failed"
        row = _job_row(env.db, started["job_id"])
        assert row["status"] == "failed"
        blob = json.dumps(row["metadata"]) + (row["error"] or "")
        assert "SOURCE_PAGE_FAILED" in blob

    def test_bd_4_building_past_60_minutes_expires_without_calling_foundryx(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        started = env.post_pull("products").json()
        assert len(env.fake.calls) == 1

        env.db.execute(
            text("UPDATE import_jobs SET created_at = :t WHERE id = :id"),
            {"t": datetime.utcnow() - timedelta(minutes=61), "id": started["job_id"]},
        )
        env.db.commit()
        env.fake.calls.clear()

        resp = env.get_pull(started["job_id"])

        assert resp.status_code == 200, resp.text
        assert resp.json()["phase"] == "expired"
        row = _job_row(env.db, started["job_id"])
        assert row["status"] == "failed"
        assert env.fake.calls == []

    def test_bd_5_pending_pull_untouched_by_the_orphan_sweep(self, env):
        from app.scheduler.task_scheduler import _reconcile_orphan_import_jobs

        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        started = env.post_pull("products").json()
        env.db.execute(
            text("UPDATE import_jobs SET created_at = :t WHERE id = :id"),
            {"t": datetime.utcnow() - timedelta(minutes=10), "id": started["job_id"]},
        )
        env.db.commit()

        settled = _reconcile_orphan_import_jobs(env.db)

        assert settled == 0
        row = _job_row(env.db, started["job_id"])
        assert row["status"] == "pending"

    def test_bd_7_another_permitted_user_gets_404(self, env):
        owner = env.user("master_data.products.autocount_pull")
        env.as_user(owner)
        started = env.post_pull("products").json()

        other = env.user("master_data.products.autocount_pull")
        env.as_user(other)
        resp = env.get_pull(started["job_id"])
        assert resp.status_code == 404


# ======================================================================= PM


class TestPermissionsAndMigration:
    def test_pm_1a_registry_contains_both_slugs(self):
        from app.rbac.permission_registry import PERMISSION_REGISTRY

        slugs = {p["slug"] for p in PERMISSION_REGISTRY}
        assert "master_data.products.autocount_pull" in slugs
        assert "inventory.stock.autocount_pull" in slugs

    def test_pm_1b_migration_file_has_the_pinned_revision_ids(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "alembic" / "versions" / "522_autocount_pull_perms.py"
        )
        assert path.exists(), f"missing {path}"
        module = _load_migration_module(path)
        assert module.revision == "522_autocount_pull_perms"
        assert len(module.revision) <= 32
        assert module.down_revision == "521_sales_report_month_fix"

    def test_pm_1b_upgrade_sweeps_the_sibling_import_permission_idempotently(self, env):
        from app.models.user import UserPermission, UserRole, UserRolePermission

        def _perm(slug: str) -> str:
            row = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
            env.db.add(row)
            env.db.flush()
            return row.id

        def _role(slug: str) -> str:
            row = UserRole(
                id=str(uuid.uuid4()), slug=slug, name=slug, description="",
                is_protected=False, is_default=False,
            )
            env.db.add(row)
            env.db.flush()
            return row.id

        import_perm_id = _perm("master_data.products.import")
        holder_role = _role(f"{MARKER.lower()}-director")
        env.db.add(
            UserRolePermission(id=str(uuid.uuid4()), role_id=holder_role, permission_id=import_perm_id)
        )
        integration_role = _role("integration_zzt")
        env.db.add(
            UserRolePermission(id=str(uuid.uuid4()), role_id=integration_role, permission_id=import_perm_id)
        )
        env.db.commit()

        path = (
            Path(__file__).resolve().parents[1]
            / "alembic" / "versions" / "522_autocount_pull_perms.py"
        )
        module = _load_migration_module(path)

        def _run():
            from alembic.migration import MigrationContext
            from alembic.operations import Operations

            context = MigrationContext.configure(connection=env.db.connection())
            with Operations.context(context):
                module.upgrade()

        _run()
        _run()  # idempotent - a second run must not raise or duplicate a grant

        def _slugs(role_id: str) -> set[str]:
            rows = env.db.execute(
                text(
                    "SELECT p.slug FROM user_role_permissions rp "
                    "JOIN user_permissions p ON p.id = rp.permission_id "
                    "WHERE rp.role_id = :r"
                ),
                {"r": role_id},
            ).all()
            return {r[0] for r in rows}

        assert "master_data.products.autocount_pull" in _slugs(holder_role)
        assert "master_data.products.autocount_pull" not in _slugs(integration_role)

        dup = env.db.execute(
            text(
                "SELECT count(*) FROM user_role_permissions rp "
                "JOIN user_permissions p ON p.id = rp.permission_id "
                "WHERE rp.role_id = :r AND p.slug = 'master_data.products.autocount_pull'"
            ),
            {"r": holder_role},
        ).scalar()
        assert dup == 1

    def test_pm_2_products_only_user_cannot_start_a_stock_pull(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)

        resp = env.post_pull("stock_balances")

        assert resp.status_code == 403, resp.text
        assert _job_count(env.db) == 0

    def test_pm_2_products_only_user_is_refused_on_a_stock_pull_they_own(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        job_id = _seed_pull_job(
            env.db, job_type="autocount_stock_pull", user_id=user["id"],
            company_id=env.company_a, entity="stock_balances", company_code="SRT",
            snapshot_id=str(uuid.uuid4()), phase="review",
        )

        resp = env.get_pull(job_id)

        assert resp.status_code == 403, resp.text


def _load_migration_module(path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("zzt_migration_522", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ======================================================================= PP


class TestProductsPreview:
    def test_pp_1a_pages_through_every_snapshot_page(self, task_db, monkeypatch):
        db, factory = task_db
        fake = _FakeFoundryX()
        _patch_foundryx(monkeypatch, fake)

        snapshot_id = f"{MARKER}-snap-pages"
        row1 = _canonical_row(f"{MARKER}-PG1")
        row2 = _canonical_row(f"{MARKER}-PG2")
        fake.rows = {
            1: (200, {"snapshotId": snapshot_id, "page": 1, "pageSize": 1, "totalPages": 2,
                      "recordCount": 2, "rows": [row1]}),
            2: (200, {"snapshotId": snapshot_id, "page": 2, "pageSize": 1, "totalPages": 2,
                      "recordCount": 2, "rows": [row2]}),
        }
        job_id = _seed_pull_job(
            db, job_type="autocount_products_pull", user_id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID, entity="products", company_code="SRT",
            snapshot_id=snapshot_id, phase="previewing", header=_header(record_count=2),
        )

        _run_preview(monkeypatch, factory, job_id)

        rows_calls = [c for c in fake.calls if c["path"].endswith("/rows")]
        assert {c["params"].get("page") for c in rows_calls} == {"1", "2"}

    def test_pp_1b_incomplete_snapshot_fails_the_job(self, task_db, monkeypatch):
        db, factory = task_db
        fake = _FakeFoundryX()
        _patch_foundryx(monkeypatch, fake)
        snapshot_id = f"{MARKER}-snap-incomplete"
        row = _canonical_row(f"{MARKER}-INC")
        fake.rows = {1: (200, {"snapshotId": snapshot_id, "page": 1, "pageSize": 1000,
                                "totalPages": 1, "recordCount": 1, "rows": [row]})}
        job_id = _seed_pull_job(
            db, job_type="autocount_products_pull", user_id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID, entity="products", company_code="SRT",
            snapshot_id=snapshot_id, phase="previewing",
            header=_header(record_count=1, complete=False),
        )

        _run_preview(monkeypatch, factory, job_id)

        row_after = _job_row(db, job_id)
        assert row_after["status"] == "failed"

    def test_pp_1c_assembled_row_count_mismatch_fails_the_job(self, task_db, monkeypatch):
        db, factory = task_db
        fake = _FakeFoundryX()
        _patch_foundryx(monkeypatch, fake)
        snapshot_id = f"{MARKER}-snap-countmismatch"
        row = _canonical_row(f"{MARKER}-CM")
        fake.rows = {1: (200, {"snapshotId": snapshot_id, "page": 1, "pageSize": 1000,
                                "totalPages": 1, "recordCount": 1, "rows": [row]})}
        job_id = _seed_pull_job(
            db, job_type="autocount_products_pull", user_id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID, entity="products", company_code="SRT",
            snapshot_id=snapshot_id, phase="previewing",
            # header claims 3 records, only 1 is actually delivered
            header=_header(record_count=3),
        )

        _run_preview(monkeypatch, factory, job_id)

        row_after = _job_row(db, job_id)
        assert row_after["status"] == "failed"

    def test_pp_1d_company_code_mismatch_fails_the_job(self, task_db, monkeypatch):
        db, factory = task_db
        fake = _FakeFoundryX()
        _patch_foundryx(monkeypatch, fake)
        snapshot_id = f"{MARKER}-snap-companymismatch"
        row = _canonical_row(f"{MARKER}-CC")
        fake.rows = {1: (200, {"snapshotId": snapshot_id, "page": 1, "pageSize": 1000,
                                "totalPages": 1, "recordCount": 1, "rows": [row]})}
        job_id = _seed_pull_job(
            db, job_type="autocount_products_pull", user_id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID, entity="products", company_code="SRT",
            snapshot_id=snapshot_id, phase="previewing",
            # header echoes a DIFFERENT companyCode than the job's own
            header=_header(record_count=1, company_code="MCH"),
        )

        _run_preview(monkeypatch, factory, job_id)

        row_after = _job_row(db, job_id)
        assert row_after["status"] == "failed"

    def test_pp_2_dry_run_persists_nothing(self, task_db, monkeypatch):
        from app.models.embeddings import EmbeddingQueue
        from app.models.integration_reference import IntegrationReference
        from app.models.product import Product, ProductCategory, UnitOfMeasure

        db, factory = task_db
        fake = _FakeFoundryX()
        _patch_foundryx(monkeypatch, fake)

        category = ProductCategory(category_code=unique_code(MARKER), category_name="cat")
        uom = UnitOfMeasure(uom_code=unique_code(MARKER)[:20], uom_name="unit")
        db.add_all([category, uom])
        db.flush()
        code = f"{MARKER}-PP2"
        existing = Product(
            product_code=code, product_name="X", category_id=category.id, base_uom_id=uom.id,
            list_price=Decimal("50.00"), company_id=DEFAULT_COMPANY_ID,
        )
        db.add(existing)
        db.commit()

        def _count(model) -> int:
            return db.query(model).count()

        products_before, refs_before, embed_before = (
            _count(Product), _count(IntegrationReference), _count(EmbeddingQueue)
        )

        snapshot_id = f"{MARKER}-snap-dryrun"
        row = _canonical_row(code, list_price="99.00")
        fake.rows = {1: (200, {"snapshotId": snapshot_id, "page": 1, "pageSize": 1000,
                                "totalPages": 1, "recordCount": 1, "rows": [row]})}
        job_id = _seed_pull_job(
            db, job_type="autocount_products_pull", user_id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID, entity="products", company_code="SRT",
            snapshot_id=snapshot_id, phase="previewing", header=_header(record_count=1),
        )

        _run_preview(monkeypatch, factory, job_id)

        db.expire_all()
        assert _count(Product) == products_before
        assert _count(IntegrationReference) == refs_before
        assert _count(EmbeddingQueue) == embed_before
        db.refresh(existing)
        assert existing.list_price == Decimal("50.00")

    def test_pp_3_created_updated_unchanged_and_excluded_rows(self, task_db, monkeypatch):
        from app.models.product import Product, ProductCategory, UnitOfMeasure

        db, factory = task_db
        fake = _FakeFoundryX()
        _patch_foundryx(monkeypatch, fake)

        # "updated": stored at a different list_price than the fixture row (SRTW1000, 81.0).
        cat1 = ProductCategory(category_code=unique_code(MARKER), category_name="cat1")
        uom1 = UnitOfMeasure(uom_code=unique_code(MARKER)[:20], uom_name="unit1")
        db.add_all([cat1, uom1])
        db.flush()
        db.add(
            Product(
                product_code="SRTW1000", product_name="SRTW1000", category_id=cat1.id,
                base_uom_id=uom1.id, list_price=Decimal("50.00"), company_id=DEFAULT_COMPANY_ID,
            )
        )

        # "unchanged": stored with every mapped column already equal to the fixture row
        # (A611: category SRT-SH, brand SORENTO, list_price 130.0, is_active True, description
        # == name, no dimensions in the description).
        cat2 = ProductCategory(category_code="SRT-SH", category_name="cat2")
        uom2 = UnitOfMeasure(uom_code=unique_code(MARKER)[:20], uom_name="unit2")
        from app.models.product import Brand

        brand = Brand(brand_code="SORENTO", brand_name="Sorento")
        db.add_all([cat2, uom2, brand])
        db.flush()
        db.add(
            Product(
                product_code="A611", product_name="A611",
                description="SORENTO SHOWER ARM (SQUARE) A611",
                category_id=cat2.id, base_uom_id=uom2.id, brand_id=brand.id,
                list_price=Decimal("130.00"), is_active=True, is_discontinued=False,
                company_id=DEFAULT_COMPANY_ID,
            )
        )
        db.commit()

        rows = _fixture("products-rows-page1.json")["rows"]
        snapshot_id = f"{MARKER}-snap-pp3"
        excluded_entry = {
            "source_ref": f"{MARKER}:EXCLUDED-1", "code": f"{MARKER}-EXCLUDED-1",
            "reason": "mapping_failed", "message": "name: this field is required",
        }
        header = _header(
            record_count=len(rows), excluded_count=1, excluded_rows=[excluded_entry],
        )
        fake.rows = {1: (200, {"snapshotId": snapshot_id, "page": 1, "pageSize": 1000,
                                "totalPages": 1, "recordCount": len(rows), "rows": rows})}
        # Defensive: the header stored on the job (BD-2) is documented as "minus
        # excludedRows", so the preview task may instead re-fetch the full status to
        # learn about excluded rows. Both are covered.
        fake.status = (200, {**header, "snapshotId": snapshot_id, "status": "ready"})

        job_id = _seed_pull_job(
            db, job_type="autocount_products_pull", user_id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID, entity="products", company_code="SRT",
            snapshot_id=snapshot_id, phase="previewing", header=header,
        )

        _run_preview(monkeypatch, factory, job_id)

        rows_written = _job_rows(db, job_id)
        by_outcome: dict[str, list[dict]] = {}
        for r in rows_written:
            by_outcome.setdefault(r["outcome"], []).append(r)

        assert len(by_outcome.get("created", [])) == 8, rows_written
        assert "unchanged" not in by_outcome or by_outcome["unchanged"] == []

        updated = by_outcome.get("updated", [])
        assert len(updated) == 1, rows_written
        blob = " ".join(
            str(v) for r in updated for v in (r["message"], r["value"], r["identity"]) if v
        )
        assert "list_price" in blob
        assert "50" in blob
        assert "81" in blob

        skipped = by_outcome.get("skipped", [])
        excluded = [r for r in skipped if r["code"] == "AUTOCOUNT_EXCLUDED"]
        assert len(excluded) == 1, rows_written

    def test_pp_4_metadata_counts_and_header_price_counters(self, task_db, monkeypatch):
        from app.models.product import Product, ProductCategory, UnitOfMeasure

        db, factory = task_db
        fake = _FakeFoundryX()
        _patch_foundryx(monkeypatch, fake)

        # ACC-SRT9013 (row 5): fixture list_price is "0.0" (clamped from -1.0). Seeded
        # non-zero, so this becomes the price_to_zero record.
        cat = ProductCategory(category_code=unique_code(MARKER), category_name="cat")
        uom = UnitOfMeasure(uom_code=unique_code(MARKER)[:20], uom_name="unit")
        db.add_all([cat, uom])
        db.flush()
        db.add(
            Product(
                product_code="ACC-SRT9013", product_name="ACC-SRT9013", category_id=cat.id,
                base_uom_id=uom.id, list_price=Decimal("63.00"), company_id=DEFAULT_COMPANY_ID,
            )
        )
        db.commit()

        rows = _fixture("products-rows-page1.json")["rows"]
        snapshot_id = f"{MARKER}-snap-pp4"
        header = _header(
            record_count=len(rows), zero_list_price_count=3, negative_list_price_count=1,
        )
        fake.rows = {1: (200, {"snapshotId": snapshot_id, "page": 1, "pageSize": 1000,
                                "totalPages": 1, "recordCount": len(rows), "rows": rows})}
        job_id = _seed_pull_job(
            db, job_type="autocount_products_pull", user_id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID, entity="products", company_code="SRT",
            snapshot_id=snapshot_id, phase="previewing", header=header,
        )

        _run_preview(monkeypatch, factory, job_id)

        row_after = _job_row(db, job_id)
        meta = row_after["metadata"]["autocount_pull"]
        counts = meta["counts"]
        assert counts["received"] == 10
        assert counts["new"] == 9
        assert counts["changed"] == 1
        assert counts["unchanged"] == 0
        assert counts["failed"] == 0
        assert counts["left_out"] == 0
        assert counts["price_to_zero"] == 1
        assert meta["header"]["zeroListPriceCount"] == 3
        assert meta["header"]["negativeListPriceCount"] == 1

    def test_pp_5_ten_fixture_rows_against_an_empty_company_all_create(self, task_db, monkeypatch):
        db, factory = task_db
        fake = _FakeFoundryX()
        _patch_foundryx(monkeypatch, fake)

        rows = _fixture("products-rows-page1.json")["rows"]
        snapshot_id = f"{MARKER}-snap-pp5"
        fake.rows = {1: (200, {"snapshotId": snapshot_id, "page": 1, "pageSize": 1000,
                                "totalPages": 1, "recordCount": len(rows), "rows": rows})}
        job_id = _seed_pull_job(
            db, job_type="autocount_products_pull", user_id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID, entity="products", company_code="SRT",
            snapshot_id=snapshot_id, phase="previewing", header=_header(record_count=len(rows)),
        )

        _run_preview(monkeypatch, factory, job_id)

        rows_written = _job_rows(db, job_id)
        created = [r for r in rows_written if r["outcome"] == "created"]
        failed = [r for r in rows_written if r["outcome"] == "failed"]
        assert len(created) == 10, rows_written
        assert len(failed) == 0, rows_written

        mch_row = db.execute(
            text(
                "SELECT p.id, p.brand_id FROM products p WHERE p.product_code = 'MWT2800-N/H' "
                "AND p.company_id = :cid"
            ),
            {"cid": DEFAULT_COMPANY_ID},
        ).mappings().first()
        assert mch_row is not None, "the Mocha row (no brand_code key) was not created"
        assert mch_row["brand_id"] is None

    def test_pp_6_success_leaves_the_job_finished_in_review_phase(self, task_db, monkeypatch):
        db, factory = task_db
        fake = _FakeFoundryX()
        _patch_foundryx(monkeypatch, fake)

        rows = _fixture("products-rows-page1.json")["rows"]
        snapshot_id = f"{MARKER}-snap-pp6"
        fake.rows = {1: (200, {"snapshotId": snapshot_id, "page": 1, "pageSize": 1000,
                                "totalPages": 1, "recordCount": len(rows), "rows": rows})}
        job_id = _seed_pull_job(
            db, job_type="autocount_products_pull", user_id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID, entity="products", company_code="SRT",
            snapshot_id=snapshot_id, phase="previewing", header=_header(record_count=len(rows)),
        )

        _run_preview(monkeypatch, factory, job_id)

        row_after = _job_row(db, job_id)
        assert row_after["status"] == "finished"
        assert row_after["metadata"]["autocount_pull"]["phase"] == "review"


# ======================================================================== T


class TestKeyHygiene:
    def test_t_2_api_key_never_appears_in_responses_or_logs(self, env, monkeypatch, caplog):
        caplog.set_level(logging.DEBUG)
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        monkeypatch.setattr(
            "app.services.autocount_pull_service.enqueue_job",
            lambda *a, **k: MagicMock(id=str(uuid.uuid4())),
        )

        r1 = env.post_pull("products")
        env.fake.status = (200, _fixture("products-header-ready.json"))
        job_id = r1.json()["job_id"]
        r2 = env.get_pull(job_id)
        r3 = env.get_current("products")

        for resp in (r1, r2, r3):
            assert API_KEY not in resp.text
        assert API_KEY not in caplog.text

        assert env.fake.calls, "no outbound call was recorded"
        for call in env.fake.calls:
            assert call["url"].startswith(BASE_URL)
            assert call["headers"].get("x-api-key") == API_KEY
