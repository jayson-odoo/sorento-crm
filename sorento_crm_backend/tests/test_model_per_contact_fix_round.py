"""MODEL-PER-CONTACT fix round (review + security), red tests.

UAC AC-M-11 (route wiring of the code reader), AC-S-1 (contact PUT `llm` gate), AC-S-2 (tag `llm`
gate), AC-S-3 (model name pattern). The clarifier hand-off test (B1) lives in
`tests/chatbot/test_model_per_contact_runtime.py`. Same private-schema fixtures as the lane's tag
API tests; every row is seeded here. Postgres only.
"""
from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import text

from app.dependencies import get_external_api_user
from app.main import app
from app.services import contact_tag_settings as cts
from app.services import resolver_code_reader as reader_mod
from app.services.error_handler import AppException

from tests.test_contact_tags_s1 import (  # noqa: F401
    CONTACTS, EDIT, TAGS, VIEW, _contact, _tag, client, db, perms,
)
from tests.test_contact_tags_s2 import _holder, _stag  # noqa: F401

AI_EDIT = "system.ai_assistant_settings.edit"
RESOLVE = "/api/v1/system/references/resolve"
GEMINI = {"provider": "gemini", "model": "gemini-3.5-flash-lite"}
OPENAI = {"provider": "openai", "model": "gpt-4.1-mini"}

BAD_MODELS = ["../../tunedModels/x:generateContent", "a b", "x\ny", "x?y", "x#y", "/x", "-x", "x" * 101]
GOOD_MODELS = ["gpt-5.4-mini", "ft:gpt-4o-mini:org:abc", "gemini-3.5-flash-lite", "claude-haiku-4-5", "x" * 100]


@pytest.fixture
def no_ai(perms):
    perms["granted"] = {VIEW, EDIT}
    return perms


@pytest.fixture
def with_ai(perms):
    perms["granted"] = {VIEW, EDIT, AI_EDIT}
    return perms


def _put(client, cid, body):
    return client.put(f"{CONTACTS}/{cid}/chatbot", json=body)


def _stored(db, cid):
    db.expire_all()
    return tuple(db.execute(
        text("SELECT chatbot_llm_provider, chatbot_llm_model, chatbot_memory_level FROM respond_contacts WHERE id = :i"),
        {"i": cid}).one())


def _tag_settings(db, tag_id):
    db.expire_all()
    return db.execute(text("SELECT settings FROM contact_tags WHERE id = :i"), {"i": tag_id}).scalar()


# ---------------------------------------------------------------- B2 / B3 code reader wiring (AC-M-11)


@pytest.fixture
def resolve_client(client):
    app.dependency_overrides[get_external_api_user] = lambda: {"id": str(uuid.uuid4()), "email": "zzt@example.com"}
    return client


@pytest.fixture
def seen(monkeypatch):
    calls: list[dict] = []

    def fake_reader_for(db, **kwargs):
        calls.append(kwargs)
        return lambda missed: None

    monkeypatch.setattr(reader_mod, "reader_for", fake_reader_for)
    return calls


def _resolve(client, contact):
    return client.post(RESOLVE, json={"query": "zzt nothing", "semantic_fallback": True, "contact_id": contact.id})


def test_b2_the_resolve_route_hands_the_tagged_contacts_choice_to_the_code_reader(resolve_client, db, with_ai, seen):
    contact = _holder(resolve_client, db, [_stag(resolve_client, db, {"chatbot": {"llm": GEMINI}})])
    resp = _resolve(resolve_client, contact)
    assert resp.status_code == 200, resp.text
    assert len(seen) == 1, seen
    choice = seen[0].get("llm_choice")
    assert choice is not None, seen[0]
    assert (choice.provider, choice.model) == ("gemini", "gemini-3.5-flash-lite")


def test_b3_a_failing_tag_read_does_not_fail_the_route(resolve_client, db, with_ai, seen, monkeypatch):
    from app.services import contact_llm_choice as contact_model

    def boom(*a, **k):
        raise RuntimeError("zzt tag read broke")

    monkeypatch.setattr(contact_model, "contact_llm_choice", boom)
    contact = _holder(resolve_client, db, [_stag(resolve_client, db, {"chatbot": {"llm": GEMINI}})])
    resp = _resolve(resolve_client, contact)
    assert resp.status_code == 200, resp.text
    assert len(seen) == 1 and seen[0].get("llm_choice") is None, seen


# ---------------------------------------------------------------- B4 AC-S-1 contact PUT gate


@pytest.mark.parametrize("llm", [OPENAI, None])
def test_b4_llm_without_the_ai_slug_is_403_and_nothing_is_written(client, db, no_ai, llm):
    c = _contact(db)
    db.execute(text("UPDATE respond_contacts SET chatbot_llm_provider='gemini', chatbot_llm_model='m1', "
                    "chatbot_memory_level='off' WHERE id = :i"), {"i": c.id})
    db.flush()
    resp = _put(client, c.id, {"llm": llm, "memory_level": "full"})
    assert resp.status_code == 403, resp.text
    assert _stored(db, c.id) == ("gemini", "m1", "off")


def test_b4_a_body_without_llm_keeps_todays_gate(client, db, no_ai):
    c = _contact(db)
    resp = _put(client, c.id, {"memory_level": "full"})
    assert resp.status_code == 200, resp.text
    assert _stored(db, c.id)[2] == "full"


def test_b4_with_both_slugs_it_is_written(client, db, with_ai):
    c = _contact(db)
    resp = _put(client, c.id, {"llm": OPENAI, "memory_level": "full"})
    assert resp.status_code == 200, resp.text
    assert _stored(db, c.id) == ("openai", "gpt-4.1-mini", "full")


# ---------------------------------------------------------------- B5 AC-S-2 tag gate


def test_b5_create_with_llm_without_the_slug_is_403_and_writes_nothing(client, db, no_ai):
    name = f"ZZT gate {uuid.uuid4().hex[:6]}"
    resp = client.post(TAGS, json={"name": name, "settings": {"chatbot": {"llm": GEMINI}}})
    assert resp.status_code == 403, resp.text
    assert db.execute(text("SELECT count(*) FROM contact_tags WHERE name = :n"), {"n": name}).scalar() == 0


def test_b5_create_with_llm_with_the_slug_is_ok(client, db, with_ai):
    resp = client.post(TAGS, json={"name": f"ZZT gate {uuid.uuid4().hex[:6]}", "settings": {"chatbot": {"llm": GEMINI}}})
    assert resp.status_code == 201, resp.text


@pytest.mark.parametrize(
    "before,after",
    [
        ({"chatbot": {"chatbot_stock_allowed": True}}, {"chatbot": {"llm": GEMINI}}),  # add
        ({"chatbot": {"llm": GEMINI}}, {"chatbot": {"llm": OPENAI}}),  # change
        ({"chatbot": {"llm": GEMINI, "chatbot_stock_allowed": True}}, {"chatbot": {"chatbot_stock_allowed": True}}),  # remove
    ],
)
def test_b5_update_that_adds_changes_or_removes_llm_is_403_without_the_slug(client, db, no_ai, before, after):
    tag = _stag(client, db, before)
    resp = client.patch(f"{TAGS}/{tag['id']}", json={"settings": after})
    assert resp.status_code == 403, resp.text
    assert _tag_settings(db, tag["id"]) == before


def test_b5_update_that_leaves_llm_alone_passes_without_the_slug(client, db, no_ai):
    tag = _stag(client, db, {"chatbot": {"llm": GEMINI}})
    after = {"chatbot": {"llm": GEMINI, "chatbot_stock_allowed": False}}
    resp = client.patch(f"{TAGS}/{tag['id']}", json={"settings": after})
    assert resp.status_code == 200, resp.text
    assert _tag_settings(db, tag["id"]) == after


def test_b5_update_with_the_slug_is_written(client, db, with_ai):
    tag = _stag(client, db, {"chatbot": {"llm": GEMINI}})
    resp = client.patch(f"{TAGS}/{tag['id']}", json={"settings": {"chatbot": {"llm": OPENAI}}})
    assert resp.status_code == 200, resp.text
    assert _tag_settings(db, tag["id"]) == {"chatbot": {"llm": OPENAI}}


# ---------------------------------------------------------------- B6 AC-S-3 model pattern


@pytest.mark.parametrize("model", BAD_MODELS)
def test_b6_a_bad_model_is_422_on_the_contact_put(client, db, with_ai, model):
    c = _contact(db)
    resp = _put(client, c.id, {"llm": {"provider": "gemini", "model": model}})
    assert resp.status_code == 422, resp.text
    assert _stored(db, c.id)[:2] == (None, None)


@pytest.mark.parametrize("model", GOOD_MODELS)
def test_b6_a_good_model_is_accepted_on_the_contact_put(client, db, with_ai, model):
    c = _contact(db)
    resp = _put(client, c.id, {"llm": {"provider": "openai", "model": model}})
    assert resp.status_code == 200, resp.text
    assert _stored(db, c.id)[1] == model


@pytest.mark.parametrize("model", BAD_MODELS)
def test_b6_a_bad_model_is_422_in_the_tag_validator(db, model):
    with pytest.raises(AppException) as exc:
        cts.validate_settings(db, {"chatbot": {"llm": {"provider": "gemini", "model": model}}})
    assert exc.value.status_code == 422
    assert "llm" in str(exc.value.detail)


@pytest.mark.parametrize("model", GOOD_MODELS)
def test_b6_a_good_model_passes_the_tag_validator(db, model):
    llm = {"provider": "gemini", "model": model}
    assert cts.validate_settings(db, {"chatbot": {"llm": llm}}) == {"chatbot": {"llm": llm}}
