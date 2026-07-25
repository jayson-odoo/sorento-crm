"""Endpoint tests for POST /api/v1/marketing/promotions/export/pdf (compile PDF).

Covers: 202 + download_id happy path (enqueues generate_promotions_pdf and
creates a UserDownload row); empty ids -> 400; unknown id -> 404; auth denial
(no principal) -> 401/403; enqueue failure (Redis down) -> the UserDownload row
is marked failed.

Blank Postgres schema + dependency overrides (auth pattern from
test_upload_activity_endpoint.py). enqueue_job is monkeypatched so no Redis is hit.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app  # noqa: E402
from tests._pg_fixture import blank_session


_USER_ID = "130c548f-048f-53b2-97a6-3a54676bea77"


@pytest.fixture
def ctx(monkeypatch):
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db,
    )
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:

        def _override_get_db():
            yield db

        def _override_user():
            return {"id": _USER_ID, "email": "u@test.com"}

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[get_current_user_or_api_key] = _override_user
        # No auth header on the test request -> the router-level scope resolver would
        # compute UNSET (fail-closed) and hide the seeded Sorento promotions. No-op it
        # so the session keeps the conftest ``after_begin`` Sorento default.
        app.dependency_overrides[apply_company_scope] = lambda: None

        # Capture enqueue calls; never touch Redis.
        calls: list = []
        import app.services.queue_service as qs

        monkeypatch.setattr(qs, "enqueue_job", lambda *a, **kw: calls.append((a, kw)))

        try:
            with TestClient(app) as client:
                yield client, db, calls
        finally:
            app.dependency_overrides.clear()


def _mk_promo(db) -> str:
    from app.models.marketing import Promotion

    pid = str(uuid.uuid4())
    db.add(
        Promotion(
            id=pid,
            description=f"Promo {uuid.uuid4().hex[:6]}",
            access_levels=["dealer"],
            is_active=True,
        )
    )
    db.commit()
    return pid


def test_compile_happy_path_202_and_enqueues(ctx):
    from app.models.download import UserDownload

    client, db, calls = ctx
    pid_a = _mk_promo(db)
    pid_b = _mk_promo(db)

    res = client.post(
        "/api/v1/marketing/promotions/export/pdf",
        json={"promotion_ids": [pid_a, pid_b]},
    )
    assert res.status_code == 202, res.text
    download_id = res.json()["download_id"]
    assert download_id

    # A UserDownload row was created for this user with kind promotions_pdf.
    row = db.query(UserDownload).filter(UserDownload.id == download_id).first()
    assert row is not None
    assert row.kind == "promotions_pdf"
    assert str(row.user_id) == _USER_ID

    # The generation job was enqueued with the ids in the caller's order.
    assert len(calls) == 1
    args, kwargs = calls[0]
    # positional: (fn, download_id, promotion_ids, user_id)
    assert args[1] == download_id
    assert list(args[2]) == [pid_a, pid_b]
    assert kwargs.get("queue_name") == "imports"


def test_compile_empty_ids_400(ctx):
    client, _db, _calls = ctx
    res = client.post(
        "/api/v1/marketing/promotions/export/pdf", json={"promotion_ids": []}
    )
    assert res.status_code == 400, res.text


def test_compile_unknown_id_404(ctx):
    client, db, _calls = ctx
    known = _mk_promo(db)
    missing = str(uuid.uuid4())
    res = client.post(
        "/api/v1/marketing/promotions/export/pdf",
        json={"promotion_ids": [known, missing]},
    )
    assert res.status_code == 404, res.text


def test_compile_requires_auth():
    # No override, no principal -> auth rejection.
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/marketing/promotions/export/pdf",
            json={"promotion_ids": [str(uuid.uuid4())]},
        )
    assert res.status_code in (401, 403), res.text


def test_compile_enqueue_failure_marks_download_failed(ctx, monkeypatch):
    from app.models.download import UserDownload

    client, db, _calls = ctx
    pid = _mk_promo(db)

    import app.services.queue_service as qs

    def _boom(*a, **kw):
        raise RuntimeError("redis down")

    monkeypatch.setattr(qs, "enqueue_job", _boom)

    res = client.post(
        "/api/v1/marketing/promotions/export/pdf",
        json={"promotion_ids": [pid]},
    )
    # Enqueue failed -> internal error surfaced; the row must be marked failed.
    assert res.status_code >= 400
    rows = db.query(UserDownload).filter(UserDownload.kind == "promotions_pdf").all()
    assert len(rows) == 1
    status_val = getattr(rows[0].status, "value", rows[0].status)
    assert status_val == "failed"
    assert rows[0].error
