"""RED tests for the server-side AutoCount pull advance tick (D27, small fix track,
owner go 23 Sep 2026).

Plan: documentation/plans/autocount/PLAN-autocount-pull-server-advance.md
UAC:  documentation/plans/autocount/autocount-pull-server-advance-acceptance-criteria.md

`advance_building_pulls` and the `autocount_pull_advance` scheduler job are BOTH the
coder's deliverable here - neither exists yet, so every reference to either lives inside
a test body (never at module import time), matching `tests/test_scheduled_task_company_
scope.py`'s and `tests/test_spo_container_relink_sweep.py`'s own convention for a tick
that does not exist yet.

No HTTP route is involved - `advance_building_pulls` is called directly against a
`blank_session()`, the same substrate the two files above already use for a scheduler
tick, rather than `test_autocount_pull_sr1.py`'s `env` (`TestClient`) fixture, which this
lane has no need of. FoundryX is faked the same shape `test_autocount_pull_sr1.py`'s own
`_FakeFoundryX` uses (dispatch on method + path, `X-API-Key` header, `calls` recorded) -
copied here rather than imported, since dispatch here is keyed off the snapshot id in the
path (one fake serves several jobs' snapshots per test) rather than one fixed response.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import text

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards (repo convention, see test_ingest_deletions.py).
from app.main import app  # noqa: E402,F401

from app.services.company_scope import DEFAULT_COMPANY_ID

import tests.support.fake_foundryx as fake_foundryx
from tests._pg_fixture import blank_session

MARKER = "ZZTAPADV"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "autocount_pull"
BASE_URL = "http://foundryx.test"
API_KEY = "fxa_test_SECRETKEY123"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


# ============================================================== fake FoundryX


class _FakeFoundryX:
    """An httpx handler standing in for the FoundryX gateway, dispatching the status
    read on the snapshot id embedded in the path - several jobs, several snapshot ids,
    one fake per test."""

    def __init__(self):
        self.calls: list[dict] = []
        self.default_status = (200, _fixture("products-header-building.json"))
        self.status_by_snapshot: dict[str, tuple[int, dict]] = {}
        self.raise_for_snapshot: dict[str, Exception] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(
            {
                "method": request.method,
                "path": path,
                "headers": {k.lower(): v for k, v in request.headers.items()},
            }
        )
        if request.method == "GET" and "/snapshots/" in path:
            snapshot_id = path.rsplit("/", 1)[-1]
            if snapshot_id in self.raise_for_snapshot:
                raise self.raise_for_snapshot[snapshot_id]
            status_code, body = self.status_by_snapshot.get(snapshot_id, self.default_status)
            return httpx.Response(status_code, json=body)
        return httpx.Response(404, json={"code": "UNKNOWN_ROUTE"})


def _patch_foundryx(monkeypatch, fake: _FakeFoundryX, db) -> None:
    """Seed the ``foundryx-esb`` row (see `test_autocount_pull_sr1.py`'s own helper of
    the same name) and point the client's shared TRANSPORT at the fake."""
    fake_foundryx.seed_foundryx_connection(db, base_url=BASE_URL, api_key=API_KEY)

    import app.services.foundryx_autocount_client as client_mod

    monkeypatch.setattr(client_mod, "TRANSPORT", httpx.MockTransport(fake.handler), raising=False)


# ============================================================== job seeding


def _seed_pull(
    db,
    *,
    job_type: str = "autocount_products_pull",
    entity: str = "products",
    phase: str = "building",
    status: str = "pending",
    snapshot_id: str | None = None,
    created_at: datetime | None = None,
):
    from app.models.job import ImportJob

    snapshot_id = snapshot_id or f"{MARKER}-snap-{uuid.uuid4().hex[:8]}"
    meta = {
        "autocount_pull": {
            "entity": entity,
            "company_code": "SRT",
            "snapshot_id": snapshot_id,
            "phase": phase,
            "progress": None,
            "header": None,
            "counts": {},
            "confirm_blocked_reason": None,
            "compare": None,
            "apply_job_id": None,
            "warnings": [],
        }
    }
    job = ImportJob(
        id=uuid.uuid4(),
        job_id=str(uuid.uuid4()),
        job_type=job_type,
        status=status,
        user_id=str(uuid.uuid4()),
        company_id=DEFAULT_COMPANY_ID,
        job_metadata=meta,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    return job


def _job_row(db, job_id) -> dict:
    row = db.execute(
        text("SELECT id, job_type, status, metadata, error FROM import_jobs WHERE id = :id"),
        {"id": str(job_id)},
    ).mappings().first()
    return dict(row)


def _patch_enqueue(monkeypatch):
    captured: list[dict] = []

    def _enqueue(func, *a, **k):
        captured.append({"func": func, "args": a, "kwargs": k})
        return MagicMock(id=str(uuid.uuid4()))

    monkeypatch.setattr("app.services.autocount_pull_service.enqueue_job", _enqueue)
    return captured


# ======================================================================= SA


class TestAdvanceBuildingPulls:
    def test_t1_ready_pull_is_advanced_to_previewing_and_enqueues_preview_once(self, monkeypatch):
        with blank_session() as db:
            fake = _FakeFoundryX()
            _patch_foundryx(monkeypatch, fake, db)
            job = _seed_pull(db)
            snap = job.job_metadata["autocount_pull"]["snapshot_id"]
            fake.status_by_snapshot[snap] = (200, _fixture("products-header-ready.json"))
            captured = _patch_enqueue(monkeypatch)

            from app.services.autocount_pull_service import advance_building_pulls

            count = advance_building_pulls(db)

            assert count == 1
            row = _job_row(db, job.id)
            assert row["status"] == "queued"
            assert row["metadata"]["autocount_pull"]["phase"] == "previewing"
            assert len(captured) == 1
            assert getattr(captured[0]["func"], "__name__", "") == "preview_autocount_pull"
            assert captured[0]["args"][0] == str(job.id)

    def test_t2_still_building_with_progress_stores_progress_and_enqueues_nothing(self, monkeypatch):
        with blank_session() as db:
            fake = _FakeFoundryX()
            _patch_foundryx(monkeypatch, fake, db)
            job = _seed_pull(db)
            snap = job.job_metadata["autocount_pull"]["snapshot_id"]
            fake.status_by_snapshot[snap] = (200, _fixture("products-header-building.json"))
            captured = _patch_enqueue(monkeypatch)

            from app.services.autocount_pull_service import advance_building_pulls

            count = advance_building_pulls(db)

            assert count == 1
            assert captured == []
            row = _job_row(db, job.id)
            assert row["status"] == "pending"
            pull = row["metadata"]["autocount_pull"]
            assert pull["phase"] == "building"
            assert pull["progress"] == {"pagesDone": 2, "pagesTotal": 4, "stage": "lookup:uom"}

    def test_t3_no_building_pulls_returns_zero_and_builds_no_foundryx_client(self, monkeypatch):
        with blank_session() as db:
            client_cls = MagicMock(
                side_effect=AssertionError("FoundryxAutocountClient must not be constructed")
            )
            monkeypatch.setattr(
                "app.services.autocount_pull_service.FoundryxAutocountClient", client_cls
            )

            from app.services.autocount_pull_service import advance_building_pulls

            count = advance_building_pulls(db)

            assert count == 0
            client_cls.assert_not_called()

    def test_t4_a_second_tick_after_ready_enqueues_preview_only_once_in_total(self, monkeypatch):
        with blank_session() as db:
            fake = _FakeFoundryX()
            _patch_foundryx(monkeypatch, fake, db)
            job = _seed_pull(db)
            snap = job.job_metadata["autocount_pull"]["snapshot_id"]
            fake.status_by_snapshot[snap] = (200, _fixture("products-header-ready.json"))
            captured = _patch_enqueue(monkeypatch)

            from app.services.autocount_pull_service import advance_building_pulls

            first = advance_building_pulls(db)
            second = advance_building_pulls(db)

            assert first == 1
            assert second == 0  # the job is `queued`/`previewing` now, no longer selected
            assert len(captured) == 1

    def test_t5_one_pulls_foundryx_error_never_stops_the_other_and_never_escapes(self, monkeypatch):
        with blank_session() as db:
            fake = _FakeFoundryX()
            _patch_foundryx(monkeypatch, fake, db)
            job_bad = _seed_pull(db, created_at=datetime.utcnow() - timedelta(minutes=5))
            job_good = _seed_pull(db, created_at=datetime.utcnow() - timedelta(minutes=1))
            bad_snap = job_bad.job_metadata["autocount_pull"]["snapshot_id"]
            good_snap = job_good.job_metadata["autocount_pull"]["snapshot_id"]
            fake.raise_for_snapshot[bad_snap] = httpx.ConnectError("boom")
            fake.status_by_snapshot[good_snap] = (200, _fixture("products-header-ready.json"))
            captured = _patch_enqueue(monkeypatch)

            from app.services.autocount_pull_service import advance_building_pulls

            count = advance_building_pulls(db)  # must not raise

            assert count == 2
            row_bad = _job_row(db, job_bad.id)
            assert row_bad["status"] == "pending"
            assert row_bad["metadata"]["autocount_pull"]["phase"] == "building"
            row_good = _job_row(db, job_good.id)
            assert row_good["status"] == "queued"
            assert row_good["metadata"]["autocount_pull"]["phase"] == "previewing"
            assert len(captured) == 1

    def test_t6_expired_building_pull_is_marked_expired_with_no_foundryx_call(self, monkeypatch):
        with blank_session() as db:
            fake = _FakeFoundryX()
            _patch_foundryx(monkeypatch, fake, db)
            job = _seed_pull(db, created_at=datetime.utcnow() - timedelta(minutes=61))

            from app.services.autocount_pull_service import advance_building_pulls

            count = advance_building_pulls(db)

            assert count == 1
            row = _job_row(db, job.id)
            assert row["status"] == "failed"
            assert row["metadata"]["autocount_pull"]["phase"] == "expired"
            assert fake.calls == []

    @pytest.mark.parametrize(
        "phase,status",
        [
            ("previewing", "queued"),
            ("review", "finished"),
            ("confirmed", "finished"),
            ("discarded", "cancelled"),
            # S2 (opus review fix round): `status` alone (`pending`) would still match a
            # `previewing` row - only the JSONB phase predicate excludes it. A row this
            # shape is not one the real lifecycle produces (previewing always flips
            # status to queued in the same UPDATE), but the predicate must not rely on
            # that coincidence to stay correct.
            ("previewing", "pending"),
        ],
    )
    def test_t7_non_building_phases_are_never_selected(self, monkeypatch, phase, status):
        with blank_session() as db:
            fake = _FakeFoundryX()
            _patch_foundryx(monkeypatch, fake, db)
            job = _seed_pull(db, phase=phase, status=status)

            from app.services.autocount_pull_service import advance_building_pulls

            count = advance_building_pulls(db)

            assert count == 0
            assert fake.calls == []
            row = _job_row(db, job.id)
            assert row["metadata"]["autocount_pull"]["phase"] == phase
            assert row["status"] == status


# ======================================================================= S1 (AC-SA-8 guard)


class TestClaimAndEnqueuePreviewGuard:
    """S1 (opus review fix round): `_claim_and_enqueue_preview`'s own conditional UPDATE
    (`status == PENDING`) is what AC-SA-8 leans on for "a browser poll and the tick
    racing enqueue ONE preview" - covered end-to-end in `test_autocount_pull_sr1.py`, but
    never against the tick's own call site directly. These two prove the guard itself,
    calling `_claim_and_enqueue_preview` the way `advance_building_pulls` does."""

    def test_s1a_a_half_claimed_row_is_never_enqueued_and_stays_unchanged(self, monkeypatch):
        """`status` already flipped to `queued` (a poll that raced ahead of this call)
        while the stored `phase` is still `building` - the shape a losing caller would
        see mid-race. The UPDATE's own WHERE (`status == PENDING`) must refuse it."""
        with blank_session() as db:
            from app.services.autocount_pull_service import _claim_and_enqueue_preview, _pull_meta

            job = _seed_pull(db, phase="building", status="queued")
            pull = _pull_meta(job)
            captured = _patch_enqueue(monkeypatch)

            _claim_and_enqueue_preview(db, job, pull, _fixture("products-header-ready.json"))

            assert captured == []
            row = _job_row(db, job.id)
            assert row["status"] == "queued"
            assert row["metadata"]["autocount_pull"]["phase"] == "building"

    def test_s1b_calling_it_twice_on_the_same_row_enqueues_preview_exactly_once(self, monkeypatch):
        with blank_session() as db:
            from app.services.autocount_pull_service import _claim_and_enqueue_preview, _pull_meta

            job = _seed_pull(db, phase="building", status="pending")
            captured = _patch_enqueue(monkeypatch)
            header = _fixture("products-header-ready.json")

            _claim_and_enqueue_preview(db, job, _pull_meta(job), header)
            db.refresh(job)
            _claim_and_enqueue_preview(db, job, _pull_meta(job), header)

            assert len(captured) == 1
            row = _job_row(db, job.id)
            assert row["status"] == "queued"
            assert row["metadata"]["autocount_pull"]["phase"] == "previewing"


# ======================================================================= scheduler wiring


class TestSchedulerRegistersTheAdvanceTick:
    def test_t8_start_scheduler_registers_autocount_pull_advance_every_30s(self, monkeypatch):
        import app.scheduler.task_scheduler as scheduler_mod

        mock_scheduler = MagicMock()
        monkeypatch.setattr(
            scheduler_mod, "BackgroundScheduler", MagicMock(return_value=mock_scheduler)
        )

        scheduler_mod.start_scheduler()

        matching = [
            call
            for call in mock_scheduler.add_job.call_args_list
            if call.kwargs.get("id") == "autocount_pull_advance"
        ]
        assert len(matching) == 1, mock_scheduler.add_job.call_args_list
        trigger = matching[0].kwargs.get("trigger")
        assert trigger is not None
        assert trigger.interval_length == 30
        mock_scheduler.start.assert_called_once()
