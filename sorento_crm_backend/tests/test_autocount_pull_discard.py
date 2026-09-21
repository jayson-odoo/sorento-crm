"""RED tests for the AutoCount pull discard lane (AC-DS-1..8).

Plan: documentation/plans/autocount/PLAN-autocount-pull-discard.md
UAC:  documentation/plans/autocount/autocount-pull-discard-acceptance-criteria.md

Nothing under test here exists yet - `POST /api/v1/autocount/pulls/{job_id}/discard`,
`autocount_pull_service.discard_pull`, `PullNotDiscardable`, and the preview task's
"do not resurrect a discarded pull" guard are ALL the coder's deliverable for this slice.
`find_open_pull` skipping a `cancelled`-status job is the one other gap this file pins
(AC-DS-8's second half) - that function DOES exist today, it just does not yet check
`status == cancelled`, only `status == failed`.

Substrate reused BY IMPORT from `tests/test_autocount_pull_sr1.py` (`env`, `task_db`,
`_FakeFoundryX`, `_patch_foundryx`, `_seed_pull_job`, `_job_row`, `_job_count`,
`_prepare_preview`, `_run_preview`, `_fixture`, `PULLS_URL`) - the same technique
`test_autocount_pull_sr3.py` / `sr4.py` / `fixes.py` already use: importing a fixture NAME
into this module's globals is enough for pytest to discover it here too, and a plain
function is just as importable. Postgres only (`tests/_pg_fixture.py`); every test seeds
its own data chain - the CI database has no seed data of its own.

A route that does not exist yet answers a bare FastAPI 404 (`{"detail": "Not Found"}`, no
`code` key) for EVERY method/path combination under `/discard` - so several tests below
assert on `resp.json().get("code")` (not just the status code) specifically so a test whose
EXPECTED status happens to coincide with that bare 404 (AC-DS-6a: another user's pull is
*also* 404 once discard is real) still reds today, for the right reason, rather than passing
by accident.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards (repo convention, see test_ingest_deletions.py).
from app.main import app  # noqa: E402,F401

from app.models.job import ImportJob, JobStatus
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests.test_autocount_pull_sr1 import (  # noqa: F401 - env/task_db are fixtures
    PULLS_URL,
    _FakeFoundryX,
    _fixture,
    _job_count,
    _job_row,
    _patch_foundryx,
    _prepare_preview,
    _run_preview,
    _seed_pull_job,
    env,
    task_db,
)

MARKER = "ZZTAPDS"


def _post_discard(env, job_id):
    return env.client.post(f"{PULLS_URL}/{job_id}/discard")


def _completed_at(db, job_id):
    return db.execute(
        text("SELECT completed_at FROM import_jobs WHERE id = :id"), {"id": str(job_id)}
    ).scalar()


def _seed_review(env, *, user_id: str, phase: str = "review") -> str:
    return _seed_pull_job(
        env.db, job_type="autocount_products_pull", user_id=user_id,
        company_id=env.company_a, entity="products", company_code="SRT",
        snapshot_id=f"{MARKER}-{uuid.uuid4().hex[:8]}", phase=phase,
    )


# ======================================================================= DS-1/2/4 - happy path


class TestDiscardHappyPath:
    def test_ds_1_discard_review_sets_discarded_cancelled_and_completed_at(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        job_id = _seed_review(env, user_id=user["id"], phase="review")
        products_before = env.db.execute(text("SELECT count(*) FROM products")).scalar()

        resp = _post_discard(env, job_id)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["phase"] == "discarded"
        row = _job_row(env.db, job_id)
        assert row["status"] == "cancelled"
        assert _completed_at(env.db, job_id) is not None
        # No ingest ran - discard never touches products/stock.
        products_after = env.db.execute(text("SELECT count(*) FROM products")).scalar()
        assert products_after == products_before
        # No second `import_jobs` row (unlike Confirm, which creates an apply job).
        assert _job_count(env.db) == 1

    def test_ds_2a_discard_building_makes_no_foundryx_call(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        started = env.post_pull("products").json()
        env.fake.calls.clear()

        resp = _post_discard(env, started["job_id"])

        assert resp.status_code == 200, resp.text
        assert resp.json()["phase"] == "discarded"
        assert env.fake.calls == []

    def test_ds_2b_discard_previewing_makes_no_foundryx_call(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        job_id = _seed_review(env, user_id=user["id"], phase="previewing")
        assert env.fake.calls == []

        resp = _post_discard(env, job_id)

        assert resp.status_code == 200, resp.text
        assert resp.json()["phase"] == "discarded"
        assert env.fake.calls == []

    def test_ds_4_discard_twice_answers_200_both_times_with_the_same_body(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        job_id = _seed_review(env, user_id=user["id"], phase="review")

        first = _post_discard(env, job_id)
        second = _post_discard(env, job_id)

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json() == second.json()
        assert _job_count(env.db) == 1


# ======================================================================= DS-3 - pull again


class TestDiscardThenPullAgain:
    def test_ds_3_after_discard_current_is_404_and_a_new_start_builds_a_new_snapshot(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        first = env.post_pull("products").json()

        discard_resp = _post_discard(env, first["job_id"])
        assert discard_resp.status_code == 200, discard_resp.text

        current = env.get_current("products")
        assert current.status_code == 404, current.text

        env.fake.calls.clear()
        second = env.post_pull("products")

        assert second.status_code in (200, 201, 202), second.text
        assert second.json()["job_id"] != first["job_id"]
        assert len(env.fake.calls) == 1


# ======================================================================= DS-5 - refusals


class TestDiscardRefusals:
    @pytest.mark.parametrize("phase", ["confirmed", "failed", "expired"])
    def test_ds_5_discard_on_a_dead_or_confirmed_phase_is_409_not_discardable(self, env, phase):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        # `_seed_pull_job` always stamps `status=pending` regardless of `phase` (it bypasses
        # the route entirely) - fine here, since discard's refusal is keyed off the STORED
        # phase, never `import_jobs.status` directly.
        job_id = _seed_review(env, user_id=user["id"], phase=phase)
        before = _job_row(env.db, job_id)

        resp = _post_discard(env, job_id)

        assert resp.status_code == 409, resp.text
        assert resp.json().get("code") == "NOT_DISCARDABLE"
        after = _job_row(env.db, job_id)
        assert after["metadata"]["autocount_pull"]["phase"] == phase
        assert after["status"] == before["status"]

    def test_ds_6a_another_users_pull_is_404(self, env):
        owner = env.user("master_data.products.autocount_pull")
        env.as_user(owner)
        job_id = _seed_review(env, user_id=owner["id"], phase="review")

        other = env.user("master_data.products.autocount_pull")
        env.as_user(other)
        resp = _post_discard(env, job_id)

        assert resp.status_code == 404, resp.text
        assert resp.json().get("code") == "NOT_FOUND"
        row = _job_row(env.db, job_id)
        assert row["metadata"]["autocount_pull"]["phase"] == "review"

    def test_ds_6b_no_token_is_401(self, env):
        from app.dependencies import get_current_user

        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        job_id = _seed_review(env, user_id=user["id"], phase="review")

        saved = app.dependency_overrides.pop(get_current_user)
        try:
            resp = env.client.post(f"{PULLS_URL}/{job_id}/discard")
        finally:
            app.dependency_overrides[get_current_user] = saved

        assert resp.status_code == 401, resp.text

    def test_ds_7_confirm_on_a_discarded_pull_is_409_and_creates_no_apply_job(self, env):
        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        job_id = _seed_review(env, user_id=user["id"], phase="review")

        discard_resp = _post_discard(env, job_id)
        assert discard_resp.status_code == 200, discard_resp.text
        assert discard_resp.json()["phase"] == "discarded"

        confirm_resp = env.client.post(f"{PULLS_URL}/{job_id}/confirm")

        assert confirm_resp.status_code == 409, confirm_resp.text
        assert _job_count(env.db) == 1  # no second (apply) row was ever created
        row = _job_row(env.db, job_id)
        assert row["metadata"]["autocount_pull"].get("apply_job_id") is None


# ======================================================================= DS-8 - task + find_open_pull


class TestPreviewTaskRespectsDiscard:
    def test_ds_8a_preview_finishing_after_a_discard_leaves_the_phase_discarded(
        self, task_db, monkeypatch
    ):
        db, factory = task_db
        fake = _FakeFoundryX()
        _patch_foundryx(monkeypatch, fake, db)
        rows = _fixture("products-rows-page1.json")["rows"]
        job_id = _prepare_preview(db, fake, rows=rows)

        # Simulate a discard that landed WHILE the preview was in flight - a direct write,
        # not through the (not-yet-built) discard endpoint: this test's own claim is about
        # the TASK's behaviour on a row it re-reads, not about the route.
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        meta = dict(job.job_metadata or {})
        pull = dict(meta.get("autocount_pull") or {})
        pull["phase"] = "discarded"
        meta["autocount_pull"] = pull
        job.job_metadata = meta
        job.status = JobStatus.CANCELLED.value
        db.commit()

        _run_preview(monkeypatch, factory, job_id)

        row_after = _job_row(db, job_id)
        assert row_after["metadata"]["autocount_pull"]["phase"] == "discarded"
        assert row_after["status"] == "cancelled"

    def test_ds_8b_find_open_pull_skips_a_cancelled_job_even_if_its_phase_still_says_building(
        self, env
    ):
        from app.services import autocount_pull_service as pull_service

        user = env.user("master_data.products.autocount_pull")
        env.as_user(user)
        started = env.post_pull("products").json()

        # The generic Cancel button (`canCancel` = pending/queued/started on the job page) can
        # set `import_jobs.status = cancelled` on a pull still stored `building` - simulated
        # directly, since that button's own route is generic import-job machinery, not this
        # lane's own concern.
        job = env.db.query(ImportJob).filter(ImportJob.id == started["job_id"]).first()
        job.status = JobStatus.CANCELLED.value
        env.db.commit()

        open_pull = pull_service.find_open_pull(
            env.db, user_id=user["id"], company_id=env.company_a, entity="products"
        )

        assert open_pull is None
