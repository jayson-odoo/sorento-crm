"""LOOKUP-EMBED-CENTRAL review fix round 2, chatbot side (G-6): /lookup-words checks each permission once.
Run: SORENTO_ENV_FILE=.env.ci-tests PGGSSENCMODE=disable no_proxy='*' venv/bin/pytest tests/chatbot/test_lookup_embed_central_review2_chatbot.py -q -n 2
"""
from __future__ import annotations

import collections

import pytest

from tests.chatbot.test_lookup_embed_central_review1_chatbot import (  # noqa: F401  (fixtures)
    BASE, CUSTOMERS_VIEW, VIEW, _setting, allow, client, db, fresh, transport,
)


@pytest.fixture
def scope():
    return {"value": None}


@pytest.fixture
def calls(monkeypatch, client):  # noqa: F811
    from app.services.user_service import UserPermissionService

    inner = UserPermissionService.check_user_has_permission
    seen: collections.Counter = collections.Counter()

    def counting(self, uid, slug):
        seen[slug] += 1
        return inner(self, uid, slug)

    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", counting)
    return seen


@pytest.mark.parametrize("list_name, extra", [("category", None), ("customer", CUSTOMERS_VIEW)])
def test_g6_lookup_words_checks_each_permission_once(client, db, allow, calls, list_name, extra):  # noqa: F811
    _setting(db)
    allow.add(VIEW)
    if extra:
        allow.add(extra)
    assert client.get(BASE, params={"list": list_name}).status_code == 200
    assert calls[VIEW] == 1, dict(calls)
    if extra:
        assert calls[extra] == 1, dict(calls)
