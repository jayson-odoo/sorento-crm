"""LOOKUP-EMBED-CENTRAL review fix round 1, chatbot side: F-3 (per-list view permissions on the lookup words list
and on /try) and F-11 (phrase length). Red before the fixes. Lives in tests/chatbot (it reaches chatbot code).
Run: SORENTO_ENV_FILE=.env.ci-tests PGGSSENCMODE=disable no_proxy='*' venv/bin/pytest tests/chatbot/test_lookup_embed_central_review1_chatbot.py -q -n 2
"""
from __future__ import annotations

import json
import uuid

import httpx
import pytest

import app.main  # noqa: F401  isort:skip
from app.services.chatbot.head import lookup_lists as ll
from tests._pg_fixture import TEST_PREFIX, blank_session

M3S = "text-embedding-3-small"
VIEW = "master_data.lookup_sets.view"
EDIT = "master_data.lookup_sets.edit"
BASE = "/api/v1/system/chatbot/lookup-words"
CUSTOMERS_VIEW = "order_management.customers.view"
AGENTS_VIEW = "master_data.sales_agents.view"
WAREHOUSES_VIEW = "inventory.warehouses.view"


def pad(*head):
    return [float(x) for x in head] + [0.0] * (1536 - len(head))


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def allow():
    return set()


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(ll, "_cache", {})
    monkeypatch.setattr(ll, "_matrices", {})
    monkeypatch.setattr(ll, "_pieces", {})


@pytest.fixture
def scope():
    """The company scope the request runs under: None (all companies) unless a test sets `scope["value"]`."""
    return {"value": None}


@pytest.fixture
def client(db, allow, scope, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.models.user import User
    from app.services.company_scope import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    user = User(
        id=str(uuid.uuid4()), email=f"{TEST_PREFIX}-s5l-{uuid.uuid4().hex[:6]}@zzt.test".lower(),
        name=f"{TEST_PREFIX} S5L", avatar_storage_provider="s3",
    )
    db.add(user)
    db.commit()
    who = {"id": user.id, "email": user.email}
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in allow)

    def _db():
        yield db

    def _scope():
        # The router-level resolver would reset a token-less test request to UNSET; pin the scope the test intends.
        set_company_scope(db, scope["value"])
        return scope["value"]

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: who
    app.dependency_overrides[get_current_user_or_api_key] = lambda: who
    app.dependency_overrides[apply_company_scope] = _scope
    try:
        yield TestClient(app)
    finally:
        for dep in (get_db, get_current_user, get_current_user_or_api_key, apply_company_scope):
            app.dependency_overrides.pop(dep, None)


class Transport:
    """Texts mentioning gizmo / widget share (words no built-in class row or product type uses) share axis 0 (the same meaning); anything else gets an axis of its own."""

    def __init__(self, fail=False):
        self.fail = fail
        self.requests: list[list[str]] = []

    def vec(self, t):
        low = t.lower()
        if "gizmo" in low or "widget" in low:
            return pad(1.0)
        v = [0.0] * 1536
        v[1 + int(abs(hash(low)) % 1500)] = 1.0
        return v

    def send(self, request):
        body = json.loads(request.content)
        texts = list(body["input"])
        self.requests.append(texts)
        if self.fail:
            return httpx.Response(500, json={"error": "zzt down"}, request=request)
        return httpx.Response(200, json={"data": [{"index": i, "embedding": self.vec(t)} for i, t in enumerate(texts)]}, request=request)


@pytest.fixture
def transport(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "zzt-openai", raising=False)

    def make(fail=False):
        t = Transport(fail)
        real_send = httpx.Client.send

        def send(self, request, **kw):
            # The TestClient is an httpx client too: only provider calls are stubbed.
            if request.url.host == "testserver":
                return real_send(self, request, **kw)
            return t.send(request)

        monkeypatch.setattr(httpx.Client, "send", send)
        return t

    return make


def _setting(db):
    from app.models.user import SystemSetting

    row = SystemSetting(
        id=str(uuid.uuid4()), name=f"{TEST_PREFIX} R1C Co", embedding_provider="openai", embedding_model=M3S,
        embedding_records_search_model=M3S,
    )
    db.add(row)
    db.flush()


def _customer(db, name="ZZT R1 Customer"):
    from app.models.order import Customer

    db.add(Customer(id=str(uuid.uuid4()), customer_code="ZZTR1C", customer_name=name, is_active=True))
    db.flush()


# ------------------------------------------------------------------ F-3: lists of people / customers / warehouses
@pytest.mark.parametrize(
    "list_name, extra",
    [("customer", CUSTOMERS_VIEW), ("salesperson", AGENTS_VIEW), ("location", WAREHOUSES_VIEW)],
)
def test_f3_a_list_of_customers_people_or_warehouses_needs_its_own_view_permission(client, db, allow, list_name, extra):
    _setting(db)
    allow.add(VIEW)
    assert client.get(BASE, params={"list": list_name}).status_code == 403
    allow.add(extra)
    assert client.get(BASE, params={"list": list_name}).status_code == 200


def test_f3_the_other_lists_still_need_only_the_lookup_sets_view_permission(client, db, allow):
    _setting(db)
    allow.add(VIEW)
    for name in ("category", "file_type", "brand", "sales_channel", "spec", "promotion_kind"):
        assert client.get(BASE, params={"list": name}).status_code == 200, name


def _candidate_lists(client, phrase):
    resp = client.post(f"{BASE}/try", json={"phrase": phrase})
    assert resp.status_code == 200, resp.text
    return {c["list"] for c in resp.json()["candidates"]}


def test_f3_try_offers_no_customer_candidate_to_a_user_who_cannot_view_customers(client, db, allow, transport):
    _setting(db)
    _customer(db)
    transport()
    allow.add(VIEW)
    assert "customer" not in _candidate_lists(client, "ZZT R1 Customer")
    allow.add(CUSTOMERS_VIEW)
    assert "customer" in _candidate_lists(client, "ZZT R1 Customer")


# ------------------------------------------------------------------ F-11: phrase length
def test_f11_a_phrase_over_200_characters_is_422(client, db, allow, transport):
    _setting(db)
    transport()
    allow.add(VIEW)
    assert client.post(f"{BASE}/try", json={"phrase": "a" * 201}).status_code == 422
    assert client.post(f"{BASE}/try", json={"phrase": "a" * 200}).status_code == 200
