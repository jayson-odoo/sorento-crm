"""LOOKUP-EMBED-CENTRAL slice 5 red tests, core API (AC-LEC-19, 22, 24): overview, records backfill start/stop,
alias targets and the orphaned flag on alias-set options. The lookup-word endpoints (list, try, embed-missing) live on
the chatbot doorway and are tested in tests/chatbot/test_lookup_embed_central_slice5_lookup_api.py.

Postgres only (blank_session); all rows seeded here; Redis and the job queue are patched; no network.
Run: SORENTO_ENV_FILE=.env.ci-tests PGGSSENCMODE=disable no_proxy='*' venv/bin/pytest tests/test_lookup_embed_central_slice5_api.py -q -n 2
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from tests._pg_fixture import TEST_PREFIX, blank_session

M3S = "text-embedding-3-small"
GEM = "gemini-embedding-001"
VIEW = "master_data.lookup_sets.view"
EDIT = "master_data.lookup_sets.edit"
KEEP = {"attachment", "promotion", "certificate", "form", "product_spec", "project"}
OVERVIEW = "/api/v1/system/embeddings/overview"
BACKFILL = "/api/v1/system/embeddings/records-backfill"
SETS = "/api/v1/master-data/lookup-sets"


def pad(*head):
    return [float(x) for x in head] + [0.0] * (1536 - len(head))


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def allow():
    return set()


@pytest.fixture
def client(db, allow, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.models.user import User
    from app.services.user_service import UserPermissionService

    user = User(
        id=str(uuid.uuid4()), email=f"{TEST_PREFIX}-s5-{uuid.uuid4().hex[:6]}@zzt.test".lower(),
        name=f"{TEST_PREFIX} S5", avatar_storage_provider="s3",
    )
    db.add(user)
    db.commit()
    who = {"id": user.id, "email": user.email}
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in allow)

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: who
    app.dependency_overrides[get_current_user_or_api_key] = lambda: who
    try:
        yield TestClient(app)
    finally:
        for dep in (get_db, get_current_user, get_current_user_or_api_key):
            app.dependency_overrides.pop(dep, None)


def _setting(db, **cols):
    from app.models.user import SystemSetting

    base = dict(embedding_provider="gemini", embedding_model=GEM, embedding_records_search_model=M3S, embedding_backfill_rpm=20)
    base.update(cols)
    row = SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} S5 Co", **base)
    db.add(row)
    db.flush()
    return row


def _doc(db, source_type, n, *, body="zzt body", failures=None, active=True):
    from app.models.embeddings import EmbeddingDocument

    d = EmbeddingDocument(
        id=str(uuid.uuid4()), source_type=source_type, source_id=f"zzt-s5-{source_type}-{n}", source_key=f"K{n}",
        title=f"T{n}", body_text=body, metadata_json={"embed_failures": failures} if failures else {},
        source_hash="h", is_active=active,
    )
    db.add(d)
    db.flush()
    return d


def _chunk(db, doc, model, text="zzt", index=0):
    from app.models.embeddings import EmbeddingChunk

    c = EmbeddingChunk(
        id=str(uuid.uuid4()), document_id=doc.id, source_type=doc.source_type, source_id=doc.source_id,
        chunk_index=index, chunk_text=text, chunk_hash="h", embedding=pad(1.0), model_name=model, model_version="1",
        embedding_provider="gemini" if model == GEM else "openai", source_hash="h", is_current=True,
    )
    db.add(c)
    db.flush()
    return c


# ------------------------------------------------------------------ AC-LEC-19 overview
def test_ac_lec_19_overview_needs_the_view_permission(client, allow):
    assert client.get(OVERVIEW).status_code == 403
    allow.add(EDIT)
    assert client.get(OVERVIEW).status_code == 403  # edit alone is not view
    allow.add(VIEW)
    assert client.get(OVERVIEW).status_code == 200


def test_ac_lec_19_overview_admin_bypass(client, db, monkeypatch):
    from app.services.user_service import UserPermissionService

    monkeypatch.undo()  # drop the allow-set patch: use the real check with only the role lookup pinned
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"admin"})
    _setting(db)
    assert client.get(OVERVIEW).status_code == 200


def test_ac_lec_19_overview_shape(client, db, allow):
    allow.add(VIEW)
    _setting(db)  # setting gemini, search model 3-small
    p1, p2, p3 = (_doc(db, "promotion", n) for n in (1, 2, 3))
    _chunk(db, p1, M3S)
    _chunk(db, p2, M3S)
    _chunk(db, p1, GEM)  # p1 has the target model; p2 lacks it; p3 failed for it
    p3.metadata_json = {"embed_failures": {GEM: 3}}
    db.flush()
    _chunk(db, _doc(db, "order", 1), M3S)  # not a record source any more
    lk = _doc(db, "lookup_word", 1, body="t1\nt2\nt3")
    for i, t in enumerate(("t1", "t2", "t3")):
        _chunk(db, lk, GEM, text=t, index=i)
    for i, t in enumerate(("t1", "t2")):
        _chunk(db, lk, M3S, text=t, index=10 + i)

    body = client.get(OVERVIEW).json()

    assert body["setting"] == {"provider": "gemini", "model": GEM, "backfill_rpm": 20}
    assert body["records_search_model"] == M3S
    assert body["lookup"] == {"texts_total": 3, "texts_with_vector": 3}  # for the setting's model (gemini)
    records = {r["source_type"]: r for r in body["records"]}
    assert set(records) <= KEEP and "order" not in records and "lookup_word" not in records
    assert records["promotion"]["documents"] == 3
    assert records["promotion"]["chunks_by_model"] == {M3S: 2, GEM: 1}
    assert body["guard"] == {"target_model": GEM, "ready": False, "remaining": 1, "failed": 1}


def test_ac_lec_19_overview_has_a_row_for_every_keep_set_source(client, db, allow):
    allow.add(VIEW)
    _setting(db)
    body = client.get(OVERVIEW).json()
    assert {r["source_type"] for r in body["records"]} == KEEP


# ------------------------------------------------------------------ AC-LEC-22 records backfill
@pytest.fixture
def jobs(monkeypatch):
    from app.services import queue_service

    calls: list = []

    class _Job:
        id = "zzt-job-1"

    monkeypatch.setattr(queue_service, "enqueue_job", lambda func, *a, **k: calls.append((func, a, k)) or _Job())
    redis = MagicMock()
    monkeypatch.setattr(queue_service, "redis_conn", redis)
    return calls, redis


def test_ac_lec_22_records_backfill_needs_the_edit_permission(client, allow, jobs):
    allow.add(VIEW)
    assert client.post(BACKFILL, json={"action": "start"}).status_code == 403
    calls, _ = jobs
    assert calls == []


def test_ac_lec_22_start_enqueues_run_records_backfill_and_returns_at_once(client, allow, jobs):
    from app.tasks.embedding_backfill import run_records_backfill

    allow.add(EDIT)
    calls, _redis = jobs
    resp = client.post(BACKFILL, json={"action": "start"})
    assert resp.status_code == 202, resp.text
    assert len(calls) == 1 and calls[0][0] is run_records_backfill
    assert calls[0][2].get("queue_name", "imports") == "imports"


def test_ac_lec_22_stop_sets_the_stop_flag_and_enqueues_nothing(client, allow, jobs):
    allow.add(EDIT)
    calls, redis = jobs
    resp = client.post(BACKFILL, json={"action": "stop"})
    assert resp.status_code == 202, resp.text
    assert calls == []
    assert redis.set.called and redis.set.call_args.args[0] == "lec:records_backfill:stop"


def test_ac_lec_22_an_unknown_action_is_422(client, allow, jobs):
    allow.add(EDIT)
    assert client.post(BACKFILL, json={"action": "restart"}).status_code == 422


# ------------------------------------------------------------------ AC-LEC-24 alias targets + orphaned
def _alias_set(db, set_key):
    from app.models.lookup import LookupSet

    s = LookupSet(id=str(uuid.uuid4()), set_key=set_key, name=f"ZZT {set_key}", is_active=True)
    db.add(s)
    db.flush()
    return s


def _targets(client, s):
    return client.get(f"{SETS}/{s.id}/alias-targets")


def test_ac_lec_24_attachment_type_alias_targets_are_the_attachment_types(client, db, allow):
    from app.models.resources import AttachmentType

    allow.add(VIEW)
    db.add(AttachmentType(id=str(uuid.uuid4()), code="ZZT5-PH", type_name="ZZT5 Photo", allowed_extensions="jpg"))
    db.flush()
    resp = _targets(client, _alias_set(db, "attachment_type_alias"))
    assert resp.status_code == 200, resp.text
    assert {"value": "ZZT5 Photo", "label": "ZZT5 Photo"} in [{k: t[k] for k in ("value", "label")} for t in resp.json()]


def test_ac_lec_24_brand_alias_targets_are_brand_codes(client, db, allow):
    from app.models.product import Brand

    allow.add(VIEW)
    db.add(Brand(id=str(uuid.uuid4()), brand_code="ZZT5-BR", brand_name="ZZT5 Brand"))
    db.flush()
    resp = _targets(client, _alias_set(db, "brand_alias"))
    assert resp.status_code == 200, resp.text
    assert "ZZT5-BR" in [t["value"] for t in resp.json()]


def test_ac_lec_24_sales_channel_alias_targets_are_the_channel_values(client, db, allow):
    allow.add(VIEW)
    resp = _targets(client, _alias_set(db, "sales_channel_alias"))
    assert resp.status_code == 200, resp.text
    assert {"dealer", "project"} <= {t["value"] for t in resp.json()}


def test_ac_lec_24_a_set_that_is_not_an_alias_set_is_404(client, db, allow):
    allow.add(VIEW)
    assert _targets(client, _alias_set(db, "zzt5_plain_set")).status_code == 404


def test_ac_lec_24_alias_targets_need_the_view_permission(client, db):
    assert _targets(client, _alias_set(db, "brand_alias")).status_code == 403


def test_ac_lec_24_options_of_an_alias_set_carry_orphaned(client, db, allow):
    from app.models.lookup import LookupOption
    from app.models.resources import AttachmentType

    allow.add(VIEW)
    db.add(AttachmentType(id=str(uuid.uuid4()), code="ZZT5-OK", type_name="ZZT5 Present", allowed_extensions="jpg"))
    s = _alias_set(db, "attachment_type_alias")
    for value in ("ZZT5 Present", "ZZT5 Deleted Type"):
        db.add(LookupOption(id=str(uuid.uuid4()), set_id=s.id, value=value, label=value, is_active=True))
    db.flush()
    resp = client.get(f"{SETS}/{s.id}/options")
    assert resp.status_code == 200, resp.text
    flags = {o["value"]: o.get("orphaned") for o in resp.json()["data"]}
    assert flags == {"ZZT5 Present": False, "ZZT5 Deleted Type": True}
