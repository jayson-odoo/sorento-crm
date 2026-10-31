"""AGENTIC-KNOWLEDGE fix round 1 (SS4): `user_guides_read` serves only the configured guide collection.

A document id (or a search hit) that belongs to another Outline collection must come back as the
NO_MATCH-style refusal, never as a body. Outline is replaced by a fake `_outline_post`.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from sorento_crm_mcp import user_guides

GUIDE_COLLECTION = "col-guides"
OTHER_COLLECTION = "col-hr-private"
URL_ID = "6nHGiMmtcg"
SECRET = "ZZT PRIVATE HR BODY"


def _settings():
    return SimpleNamespace(
        outline_base_url="https://outline.test",
        outline_api_token="token",
        outline_collection_id=GUIDE_COLLECTION,
        request_timeout_seconds=5,
    )


def _doc(collection_id: str, *, text: str, doc_id: str = URL_ID) -> dict:
    return {"id": doc_id, "urlId": doc_id, "title": "A doc", "url": "/doc/a", "updatedAt": "2026-10-01", "text": text, "collectionId": collection_id}


def _fake(monkeypatch, *, info: dict, hits: list[dict]):
    calls: list[tuple[str, dict]] = []

    async def post(settings, path, payload):
        calls.append((path, payload))
        if path == "documents.info":
            return {"data": info}
        if path == "documents.search":
            return {"data": [{"document": h, "context": "snippet"} for h in hits]}
        raise AssertionError(path)

    monkeypatch.setattr(user_guides, "_outline_post", post)
    return calls


def test_a_direct_id_in_another_collection_is_refused(monkeypatch):
    _fake(monkeypatch, info=_doc(OTHER_COLLECTION, text=SECRET), hits=[])

    out = asyncio.run(user_guides.read_user_guide_impl(_settings(), URL_ID))

    assert SECRET not in out
    assert json.loads(out)["code"] == "NO_MATCH"


def test_a_search_hit_in_another_collection_is_refused(monkeypatch):
    foreign = _doc(OTHER_COLLECTION, text=SECRET, doc_id="doc-foreign")
    _fake(monkeypatch, info=foreign, hits=[foreign])

    out = asyncio.run(user_guides.read_user_guide_impl(_settings(), "how do I read the hr file"))

    assert SECRET not in out
    assert json.loads(out)["code"] == "NO_MATCH"


def test_a_document_in_the_guide_collection_is_still_served(monkeypatch):
    _fake(monkeypatch, info=_doc(GUIDE_COLLECTION, text="Step 1: open Orders."), hits=[])

    out = asyncio.run(user_guides.read_user_guide_impl(_settings(), URL_ID))

    assert "Step 1: open Orders." in out
    assert "code" not in json.loads(out)
