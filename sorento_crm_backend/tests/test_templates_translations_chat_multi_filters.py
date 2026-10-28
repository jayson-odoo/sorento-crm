"""FILTER-MULTISELECT PR2: WhatsApp templates Status, Translations Language and Chat history Direction
take several values (OR within the filter). Language and Direction were validated against a fixed set
before, so an unknown value stays a 422. Red first; Postgres only; rows seeded here.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.models.chat_history import ChatHistory
from app.models.respond_template import RespondChannel, RespondMessageTemplate
from app.models.respond_workspace import RespondWorkspace
from app.models.translation_memory import TranslationMemory
from tests._multi_filter_client import get, ok_ids, open_client
from tests._pg_fixture import blank_session, unique_code

TEMPLATES = "/api/v1/integrations/respond/templates"
TRANSLATIONS = "/api/v1/system/translations"
CHAT = "/api/v1/system/chat-history"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


# ---- WhatsApp templates ------------------------------------------------------------------------------

def _template(db, channel, n, status):
    row = RespondMessageTemplate(id=str(uuid.uuid4()), channel_id=channel.id, respond_template_id=n,
                                 name=unique_code("tpl"), status=status, body_text="hi", components=[])
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def templates(db):
    ws = RespondWorkspace(id=str(uuid.uuid4()), space_id=unique_code("sp"), name="ZZT ws",
                          api_key_ciphertext="x", is_active=True, is_default=True)
    db.add(ws)
    db.flush()
    ch = RespondChannel(id=str(uuid.uuid4()), workspace_id=ws.id, respond_channel_id=1, name="WA")
    db.add(ch)
    db.flush()
    return dict(a=_template(db, ch, 1, "approved"), r=_template(db, ch, 2, "rejected"),
                p=_template(db, ch, 3, "pending"), a2=_template(db, ch, 4, "approved"))


def test_template_status_union(client, templates):
    s = templates
    assert ok_ids(get(client, TEMPLATES, [("limit", 200), ("status", "rejected,pending")])) == {s["r"].id, s["p"].id}


def test_template_status_single_and_repeated(client, templates):
    s = templates
    assert ok_ids(get(client, TEMPLATES, [("limit", 200), ("status", "approved")])) == {s["a"].id, s["a2"].id}
    got = ok_ids(get(client, TEMPLATES, [("limit", 200), ("status", "rejected"), ("status", "pending")]))
    assert got == {s["r"].id, s["p"].id}


def test_template_all_sentinel_still_means_no_filter(client, templates):
    s = templates
    assert ok_ids(get(client, TEMPLATES, [("limit", 200), ("status", "all")])) >= {s["a"].id, s["r"].id, s["p"].id}


# ---- Translations -----------------------------------------------------------------------------------

def _memory(db, lang):
    row = TranslationMemory(id=str(uuid.uuid4()), source_text=unique_code("src"), source_lang="zh",
                            target_lang=lang, target_text="x", source="manual")
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def memories(db):
    return dict(en=_memory(db, "en"), ms=_memory(db, "ms"), zh=_memory(db, "zh"), ms2=_memory(db, "ms"))


def test_language_union(client, memories):
    s = memories
    got = ok_ids(get(client, TRANSLATIONS, [("limit", 200), ("target_lang", "en,zh")]))
    assert got == {s["en"].id, s["zh"].id}


def test_language_single_and_repeated(client, memories):
    s = memories
    assert ok_ids(get(client, TRANSLATIONS, [("limit", 200), ("target_lang", "ms")])) == {s["ms"].id, s["ms2"].id}
    got = ok_ids(get(client, TRANSLATIONS, [("limit", 200), ("target_lang", "en"), ("target_lang", "zh")]))
    assert got == {s["en"].id, s["zh"].id}


def test_unknown_language_is_422(client, memories):
    assert get(client, TRANSLATIONS, [("target_lang", "fr")]).status_code == 422
    assert get(client, TRANSLATIONS, [("target_lang", "en,fr")]).status_code == 422


# ---- Chat history -----------------------------------------------------------------------------------

def _msg(db, tag, direction):
    row = ChatHistory(channel="whatsapp", contact_id="900000063", phone_number="+60160000517",
                      message=f"{tag} {direction}", sent_at=datetime.utcnow(), type=direction)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def chat(db):
    tag = unique_code("C", alpha=True)
    return dict(tag=tag, i=_msg(db, tag, "incoming"), o=_msg(db, tag, "outgoing"))


def _chat(client, s, pairs):
    resp = get(client, CHAT, [("limit", 200), ("query", s["tag"]), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


def test_direction_both_values_return_both_rows(client, chat):
    s = chat
    assert _chat(client, s, [("direction", "incoming,outgoing")]) == {s["i"].id, s["o"].id}


def test_direction_single_and_repeated(client, chat):
    s = chat
    assert _chat(client, s, [("direction", "incoming")]) == {s["i"].id}
    assert _chat(client, s, [("direction", "outgoing")]) == {s["o"].id}
    assert _chat(client, s, [("direction", "incoming"), ("direction", "outgoing")]) == {s["i"].id, s["o"].id}


def test_unknown_direction_is_422(client, chat):
    assert get(client, CHAT, [("direction", "sideways")]).status_code == 422
    assert get(client, CHAT, [("direction", "incoming,sideways")]).status_code == 422
