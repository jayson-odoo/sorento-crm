"""AGENTIC-KNOWLEDGE P1 over HTTP (UAC AC-K2, K5, K6, K10, K11).

Routes live under `/api/v1/resource-management/` (see app/api/v1/__init__.py:160), NOT
`/api/v1/resources/`. The worker enqueue is stubbed at `knowledge_service._enqueue`; storage is
the in-process fake. Auth is the real permission layer over a real seeded user: the principal
is switched per request through `who["id"]`.
"""
from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves circular-import in app.modules.runtime.guards
from app.main import app  # noqa: E402
from app.models.resources import Attachment
from tests._fake_storage import patch_storage
from tests._knowledge_seed import (
    EXACT_VEC,
    seed_attachment,
    seed_chunk,
    seed_reader,
    seed_team,
    seed_type,
)
from tests._pg_fixture import blank_session

BASE = "/api/v1/resource-management"
TYPES = f"{BASE}/attachment-types"
FILES = f"{BASE}/attachments"
PDF = b"%PDF-1.4 minimal"


@pytest.fixture
def api(monkeypatch):
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.services import knowledge_service
    from app.services.contact_access_type_service import ContactAccessTypeService
    import app.api.v1.resources.attachments as attachments_module

    with blank_session() as db:
        patch_storage(monkeypatch)
        monkeypatch.setattr(attachments_module, "_create_and_send_webhook", lambda *a, **k: None)
        monkeypatch.setattr(ContactAccessTypeService, "get_default_access_levels", lambda self: ["dealer"])
        monkeypatch.setattr(
            ContactAccessTypeService, "validate_access_levels", lambda self, levels, field_name="access_levels": list(levels)
        )
        enqueued: list[str] = []
        monkeypatch.setattr(knowledge_service, "_enqueue", lambda attachment_id: enqueued.append(str(attachment_id)))

        manager = seed_reader(
            db,
            slugs=(
                "resource.attachments.view",
                "resource.attachments.upload",
                "resource.attachment_types.view",
            ),
        )
        plain = seed_reader(db, slugs=("resource.attachments.view",))
        who = {"id": manager}

        def _db():
            yield db

        def _user():
            return {"id": who["id"], "email": "k@test.com"}

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _user
        app.dependency_overrides[get_current_user_or_api_key] = _user
        try:
            with TestClient(app) as c:
                yield type("Api", (), {"c": c, "db": db, "enqueued": enqueued, "who": who, "manager": manager, "plain": plain})
        finally:
            app.dependency_overrides.clear()


def _type_body(name=None, **extra):
    return {"type_name": name or f"ZZTK Handbook {uuid.uuid4().hex[:6]}", "allowed_extensions": "pdf,docx", **extra}


def _upload(api, att_type, name="Employee Handbook 2026.pdf"):
    return api.c.post(
        f"{FILES}/",
        data={"attachment_type_id": str(att_type.id)},
        files={"file": (name, io.BytesIO(PDF), "application/pdf")},
    )


# ---------------------------------------------------------------- AC-K2 type API


def test_create_defaults_to_off_with_no_team(api):
    res = api.c.post(f"{TYPES}/", json=_type_body())

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["ai_audience"] == "off"
    assert body["ai_escalate_team_id"] is None
    assert body["ai_escalate_team_name"] is None


def test_create_accepts_audience_and_team_and_returns_the_team_name(api):
    team = seed_team(api.db, "ZZTK HR")

    res = api.c.post(f"{TYPES}/", json=_type_body(ai_audience="staff", ai_escalate_team_id=team))

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["ai_audience"] == "staff"
    assert body["ai_escalate_team_id"] == team
    assert body["ai_escalate_team_name"] == "ZZTK HR"


def test_get_one_and_list_return_the_ai_fields(api):
    team = seed_team(api.db, "ZZTK HR")
    created = api.c.post(f"{TYPES}/", json=_type_body(ai_audience="dealer", ai_escalate_team_id=team)).json()

    one = api.c.get(f"{TYPES}/{created['id']}").json()
    listed = api.c.get(f"{TYPES}/", params={"limit": 100}).json()["data"]
    row = next(r for r in listed if r["id"] == created["id"])

    for body in (one, row):
        assert body["ai_audience"] == "dealer"
        assert body["ai_escalate_team_id"] == team
        assert body["ai_escalate_team_name"] == "ZZTK HR"


def test_update_changes_audience_and_team_and_null_clears_the_team(api):
    team = seed_team(api.db, "ZZTK HR")
    created = api.c.post(f"{TYPES}/", json=_type_body()).json()

    res = api.c.put(f"{TYPES}/{created['id']}", json={"ai_audience": "public", "ai_escalate_team_id": team})
    assert res.status_code == 200, res.text
    assert (res.json()["ai_audience"], res.json()["ai_escalate_team_name"]) == ("public", "ZZTK HR")

    res = api.c.put(f"{TYPES}/{created['id']}", json={"ai_escalate_team_id": None})
    assert res.status_code == 200, res.text
    assert res.json()["ai_escalate_team_id"] is None
    assert res.json()["ai_escalate_team_name"] is None
    assert res.json()["ai_audience"] == "public", "an unsent field is left alone"


@pytest.mark.parametrize("bad", ["everyone", "STAFF", "", "admin"])
def test_create_rejects_any_other_audience_with_422(api, bad):
    res = api.c.post(f"{TYPES}/", json=_type_body(ai_audience=bad))

    assert res.status_code == 422, res.text


def test_update_rejects_any_other_audience_with_422(api):
    created = api.c.post(f"{TYPES}/", json=_type_body()).json()

    res = api.c.put(f"{TYPES}/{created['id']}", json={"ai_audience": "everyone"})

    assert res.status_code == 422, res.text
    assert api.c.get(f"{TYPES}/{created['id']}").json()["ai_audience"] == "off"


def test_the_type_routes_refuse_an_anonymous_caller(api):
    from app.dependencies import get_current_user, get_current_user_or_api_key

    created = api.c.post(f"{TYPES}/", json=_type_body()).json()
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_or_api_key, None)

    assert api.c.post(f"{TYPES}/", json=_type_body(ai_audience="staff")).status_code == 401
    assert api.c.put(f"{TYPES}/{created['id']}", json={"ai_audience": "staff"}).status_code == 401


# ---------------------------------------------------------------- AC-K6 re-queue on a type save


def _file(api, att_type, status, name):
    att = seed_attachment(api.db, att_type, name)
    att.ai_read_status = status
    api.db.flush()
    return att


def test_turning_a_type_on_queues_files_never_read_or_failed_and_no_others(api):
    att_type = seed_type(api.db, audience="off")
    never = _file(api, att_type, None, "never.pdf")
    failed = _file(api, att_type, "failed", "failed.pdf")
    done = _file(api, att_type, "done", "done.pdf")
    other_type_file = _file(api, seed_type(api.db, audience="off"), None, "elsewhere.pdf")

    res = api.c.put(f"{TYPES}/{att_type.id}", json={"ai_audience": "staff"})

    assert res.status_code == 200, res.text
    assert sorted(api.enqueued) == sorted([str(never.id), str(failed.id)])
    assert str(done.id) not in api.enqueued
    assert str(other_type_file.id) not in api.enqueued
    api.db.expire_all()
    statuses = {
        r.id: r.ai_read_status
        for r in api.db.query(Attachment).filter(Attachment.id.in_([never.id, failed.id, done.id]))
    }
    assert statuses == {never.id: "queued", failed.id: "queued", done.id: "done"}


def test_turning_a_type_off_queues_nothing_and_keeps_the_status(api):
    att_type = seed_type(api.db, audience="staff")
    done = _file(api, att_type, "done", "done.pdf")
    never = _file(api, att_type, None, "never.pdf")

    res = api.c.put(f"{TYPES}/{att_type.id}", json={"ai_audience": "off"})

    assert res.status_code == 200, res.text
    assert api.enqueued == []
    api.db.expire_all()
    assert api.db.get(Attachment, never.id).ai_read_status is None
    assert api.db.get(Attachment, done.id).ai_read_status == "done"


def test_a_save_that_leaves_the_audience_off_queues_nothing(api):
    att_type = seed_type(api.db, audience="off")
    _file(api, att_type, None, "never.pdf")

    res = api.c.put(f"{TYPES}/{att_type.id}", json={"description": "renamed only"})

    assert res.status_code == 200, res.text
    assert api.enqueued == []


def test_moving_between_readable_audiences_does_not_requeue(api):
    """AC-K6 queues on off -> anything else; staff -> dealer changes who may see, not what was read."""
    att_type = seed_type(api.db, audience="staff")
    _file(api, att_type, None, "never.pdf")

    res = api.c.put(f"{TYPES}/{att_type.id}", json={"ai_audience": "dealer"})

    assert res.status_code == 200, res.text
    assert api.enqueued == []


def test_a_type_save_queues_at_most_the_per_save_cap(api):
    from app.services.knowledge_service import MAX_REQUEUE_PER_SAVE

    assert MAX_REQUEUE_PER_SAVE == 500
    att_type = seed_type(api.db, audience="off")
    api.db.add_all(
        [
            Attachment(
                id=str(uuid.uuid4()),
                original_filename=f"bulk-{i}.pdf",
                stored_filename=f"bulk-{i}.pdf",
                file_path=f"https://cdn.test/bulk-{i}.pdf",
                attachment_type_id=str(att_type.id),
                is_deleted=False,
            )
            for i in range(MAX_REQUEUE_PER_SAVE + 3)
        ]
    )
    api.db.flush()

    res = api.c.put(f"{TYPES}/{att_type.id}", json={"ai_audience": "staff"})

    assert res.status_code == 200, res.text
    assert len(api.enqueued) == MAX_REQUEUE_PER_SAVE


# ---------------------------------------------------------------- AC-K5 upload


def test_uploading_to_an_ai_readable_type_queues_one_read(api):
    att_type = seed_type(api.db, audience="staff")

    res = _upload(api, att_type)

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["ai_read_status"] == "queued"
    assert api.enqueued == [body["id"]]
    api.db.expire_all()
    assert api.db.get(Attachment, body["id"]).ai_read_status == "queued"


def test_uploading_to_a_type_that_is_off_enqueues_nothing(api):
    att_type = seed_type(api.db, audience="off")

    res = _upload(api, att_type)

    assert res.status_code == 201, res.text
    assert res.json()["ai_read_status"] is None
    assert api.enqueued == []


# ---------------------------------------------------------------- AC-K11 attachment API


def test_the_attachment_detail_returns_every_ai_read_field(api):
    att = seed_attachment(api.db, seed_type(api.db, audience="staff"))
    att.ai_read_status = "failed"
    att.ai_read_pages = 42
    att.ai_read_ocr_pages = 3
    att.ai_read_cost_usd = "0.0120"
    att.ai_read_error = "The file could not be read."
    api.db.flush()

    res = api.c.get(f"{FILES}/{att.id}")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ai_read_status"] == "failed"
    assert body["ai_read_pages"] == 42
    assert body["ai_read_ocr_pages"] == 3
    assert float(body["ai_read_cost_usd"]) == pytest.approx(0.012)
    assert body["ai_read_error"] == "The file could not be read."
    assert body["ai_read_at"] is None or isinstance(body["ai_read_at"], str)


def test_an_unread_attachment_returns_the_fields_as_null(api):
    """`response_model` drops undeclared fields silently, so the keys themselves are asserted."""
    att = seed_attachment(api.db, seed_type(api.db, audience="off"))

    body = api.c.get(f"{FILES}/{att.id}").json()

    for key in ("ai_read_status", "ai_read_pages", "ai_read_ocr_pages", "ai_read_cost_usd", "ai_read_error", "ai_read_at"):
        assert key in body, key
        assert body[key] is None


# ---------------------------------------------------------------- AC-K11 Read again


def test_read_again_queues_the_file_and_answers_202(api):
    att = seed_attachment(api.db, seed_type(api.db, audience="staff"))
    att.ai_read_status = "failed"
    att.ai_read_error = "The file could not be read."
    api.db.flush()

    res = api.c.post(f"{FILES}/{att.id}/ai-read")

    assert res.status_code == 202, res.text
    assert api.enqueued == [str(att.id)]
    api.db.expire_all()
    assert api.db.get(Attachment, att.id).ai_read_status == "queued"
    assert api.c.get(f"{FILES}/{att.id}").json()["ai_read_status"] == "queued"


def test_read_again_needs_the_upload_permission(api):
    att = seed_attachment(api.db, seed_type(api.db, audience="staff"))
    api.who["id"] = api.plain

    res = api.c.post(f"{FILES}/{att.id}/ai-read")

    assert res.status_code == 403, res.text
    assert api.enqueued == []


def test_read_again_refuses_an_anonymous_caller(api):
    from app.dependencies import get_current_user, get_current_user_or_api_key

    att = seed_attachment(api.db, seed_type(api.db, audience="staff"))
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_or_api_key, None)

    assert api.c.post(f"{FILES}/{att.id}/ai-read").status_code == 401
    assert api.enqueued == []


def test_read_again_on_an_unknown_file_is_404(api):
    res = api.c.post(f"{FILES}/{uuid.uuid4()}/ai-read")

    assert res.status_code == 404, res.text
    assert api.enqueued == []


# ---------------------------------------------------------------- AC-K10 / K19 n8n RAG route


@pytest.mark.parametrize("source_type", [None, "attachment", "knowledge"])
def test_external_rag_search_never_returns_a_knowledge_chunk(api, monkeypatch, source_type):
    from app.dependencies import get_external_api_user
    from app.services.embedding_settings import records_search_model
    import app.api.v1.external.rag as rag

    model = records_search_model(api.db)
    att = seed_attachment(api.db, seed_type(api.db, audience="staff"))
    # Same vector and same model as the records search: only the source type tells them apart.
    seed_chunk(api.db, att, EXACT_VEC, text="HR handbook passage", source_type="knowledge", model_name=model)
    seed_chunk(api.db, att, EXACT_VEC, text="plain record row", source_type="attachment", model_name=model)
    monkeypatch.setattr(rag, "_embed_query", lambda query, model=None, db=None: EXACT_VEC)
    # An n8n caller: allowed semantic search, and (the strongest case) ALSO able to view files.
    n8n = seed_reader(api.db, slugs=("integration.semantic_search.use", "resource.attachments.view"))
    api.who["id"] = n8n
    # The seeded principal holds no company grant, so the request's scope resolver would stamp an
    # empty scope and the control record could never match. Keep the suite's Sorento scope instead.
    from app.services.company_scope_resolver import apply_company_scope

    app.dependency_overrides[apply_company_scope] = lambda: None
    app.dependency_overrides[get_external_api_user] = lambda: {"id": n8n, "email": "n8n@test.com"}

    res = api.c.post("/api/v1/external/rag/search", json={"query": "annual leave", "top_k": 20, **({"source_type": source_type} if source_type else {})})

    assert res.status_code == 200, res.text
    rows = res.json()["data"]
    assert all(r["source_type"] != "knowledge" for r in rows)
    assert all("HR handbook passage" not in r["chunk_text"] for r in rows)
    if source_type != "knowledge":
        assert any(r["chunk_text"] == "plain record row" for r in rows), "the control record is returned"
