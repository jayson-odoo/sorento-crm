"""AGENTIC-UNIFY PR 3, slice 1 (red): the staff principal and the rollout switch.

UAC: documentation/plans/chatbot/agentic-unify-panel-acceptance-criteria.md
AC-1, AC-2, AC-26 (rollout), AC-4 (principal key, no contact row, never sendable),
AC-10 (the reserved `panel` ingress).

Also holds the shared fixtures `test_panel_live_turn.py` imports: a seeded staff member
with two company grants, a permission switch, and a recorder that fakes ONLY the LLM
boundary (parser), the MCP client and the HTTP / queue seams.

Contract assumptions the coder must meet (or tell the captain to change here):
- `app.services.chatbot.panel_service` exposes a module-level `SessionLocal` that
  `run_panel_turn` uses as the engine's session factory (like `console_service.SessionLocal`).
- `run_panel_turn(db, *, user: dict, conversation, text, page_snapshot=None,
  message_id=None)`. `message_id` is the one addition: the dedup key, so a retry of the
  same message can be tested.
- the endpoint calls `panel_service.run_panel_turn(...)` as a module attribute.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.main import app
from app.models.ai_assistant import AIAssistantConversation, AIAssistantMessage
from app.models.company import Company, UserCompany
from app.models.user import User
from app.rbac.permission_registry import PERMISSION_REGISTRY
from app.services.company_scope import register_company_scope_listeners
from app.services.ai_assistant_service import AIAssistantChatService, MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import INGRESS_KINDS
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot.head.parser import OPPORTUNITY_LINE
from app.services.user_service import UserPermissionService
from tests._pg_fixture import unique_code
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import _envelope, _parser_output  # noqa: F401

AGENT = "system.ai_assistant_chat.agent"
USE = "system.ai_assistant_chat.use"
CHAT_URL = "/api/v1/system/ai-assistant/chat"
TURN_URL = "/api/v1/external/chat/turn"
VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"

NO_PANEL_ROW = "no respond_contacts row may be created for a panel principal"


# --------------------------------------------------------------------------- #
# Shared seeding and fakes (imported by test_panel_live_turn.py)
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@dataclass
class Staff:
    user_id: str
    conv_id: str
    company_a: str
    company_b: str
    phone: str


def seed_staff(session_factory, *, active: str = "a") -> Staff:
    """A real chain: two companies, a staff user granted both, one panel conversation."""
    db = session_factory()
    a = Company(id=str(uuid.uuid4()), name="ZZT Panel Co A", code=unique_code("PNA")[:30])
    b = Company(id=str(uuid.uuid4()), name="ZZT Panel Co B", code=unique_code("PNB")[:30])
    db.add_all([a, b])
    db.flush()
    phone = "+60" + str(uuid.uuid4().int)[:9]
    user = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('panel').lower()}@example.invalid",
        name="ZZT Panel Staff",
        status="ACTIVE",
        contact_number=phone,
        last_active_company_id=a.id if active == "a" else b.id,
    )
    db.add(user)
    db.flush()
    db.add_all([UserCompany(user_id=user.id, company_id=a.id), UserCompany(user_id=user.id, company_id=b.id)])
    conv = AIAssistantConversation(user_id=user.id, title="ZZT panel thread")
    db.add(conv)
    db.commit()
    return Staff(user.id, str(conv.id), a.id, b.id, phone)


def switch_active_company(session_factory, staff: Staff, to: str) -> None:
    db = session_factory()
    db.query(User).filter(User.id == staff.user_id).update(
        {"last_active_company_id": staff.company_a if to == "a" else staff.company_b}
    )
    db.commit()


@pytest.fixture()
def grants(monkeypatch) -> set[str]:
    """The slugs the staff member holds. The tests edit this set."""
    held: set[str] = {USE}
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in held
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    return held


@pytest.fixture()
def staff(session_factory) -> Staff:
    return seed_staff(session_factory)


def respond_contact_count(session_factory) -> int:
    from app.models.access import RespondContact

    return session_factory().query(RespondContact).count()


@dataclass
class World:
    """What the faked boundaries saw."""

    blocks: list[str] = field(default_factory=list)  # parser user blocks
    mcp: list[dict[str, Any]] = field(default_factory=list)
    http: list[str] = field(default_factory=list)
    jobs: list[str] = field(default_factory=list)
    respond_sends: list[str] = field(default_factory=list)
    scopes: list[Any] = field(default_factory=list)  # company scopes stamped on sessions
    brand_scopes: list[Any] = field(default_factory=list)
    parser_output: dict[str, Any] = field(default_factory=_parser_output)
    lookup_lists: bool = False
    #: A live label carries the LOG OPPORTUNITY line, so the parser offers the `opportunity` key.
    opportunity: bool = False

    def stock_product_ids(self) -> set[str]:
        return {
            pid
            for call in self.mcp
            if call["name"] == "crm_inventory_stock_balance_list"
            for pid in (call["args"].get("product_ids") or [])
        }


def stock_output(code: str) -> dict[str, Any]:
    return _parser_output(
        intent_hint="check_stock",
        domain_hint="inventory",
        user_goal="stock",
        entities=[{"raw": code, "hint": "product", "canonical_code": code, "current_message": True, "confident": True}],
    )


@pytest.fixture()
def world(monkeypatch) -> World:
    """Fake ONLY the provider boundary (parser), the MCP client, HTTP, queue and Respond sender."""
    w = World()

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub\n" + (OPPORTUNITY_LINE + "\n" if w.opportunity else ""),
            prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
            closed_lists=True, lookup_lists=w.lookup_lists, opportunity=w.opportunity,
        )

    def fake_parse(config, user_block):
        w.blocks.append(user_block)
        return w.parser_output

    def fake_call_tool(self, name, arguments):
        w.mcp.append(
            {
                "name": name,
                "args": dict(arguments or {}),
                "staff": self.staff,
                "staff_user_id": self.staff_user_id,
                "headers": self._headers(),
            }
        )
        return json.dumps({"ok": True, "items": []})

    real_send = httpx.Client.send

    def fake_send(self, request, **kwargs):
        if request.url.host == "testserver":  # the TestClient's own in-process call
            return real_send(self, request, **kwargs)
        w.http.append(str(request.url))
        return httpx.Response(200, json={}, request=request)

    def fake_enqueue(func, *args, **kwargs):
        w.jobs.append(getattr(func, "__name__", str(func)))
        return SimpleNamespace(id="zzt-job")

    real_scope = engine_mod.set_company_scope
    real_brand = engine_mod.set_brand_scope

    def spy_scope(db, scope):
        w.scopes.append(scope)
        return real_scope(db, scope)

    def spy_brand(db, scope):
        w.brand_scopes.append(scope)
        return real_brand(db, scope)

    from app.services import queue_service
    from app.services.integration_service import RespondClient

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", fake_parse)
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", fake_call_tool)
    monkeypatch.setattr(httpx.Client, "send", fake_send)
    monkeypatch.setattr(queue_service, "enqueue_job", fake_enqueue)
    monkeypatch.setattr(engine_mod, "enqueue_job", fake_enqueue)
    monkeypatch.setattr(
        RespondClient, "_post_contact_message", lambda self, ident, payload, **kw: w.respond_sends.append(ident) or {}
    )
    monkeypatch.setattr(engine_mod, "set_company_scope", spy_scope)
    monkeypatch.setattr(engine_mod, "set_brand_scope", spy_brand)
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, *, agent_code, contact_id, space_id: {
            "allowed": True, "decision": "allow", "agent_name": "General Enquiries",
            "attributes": None, "all_attributes_allowed": None,
        },
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")
    return w


def run_panel(session_factory, monkeypatch, staff: Staff, text: str, **extra):
    """One live panel turn through `panel_service.run_panel_turn`, the engine on the test DB."""
    from app.services.chatbot import panel_service

    monkeypatch.setattr(panel_service, "SessionLocal", session_factory)
    db = session_factory()
    conv = db.get(AIAssistantConversation, staff.conv_id)
    return panel_service.run_panel_turn(
        db, user={"id": staff.user_id, "name": "ZZT Panel Staff"}, conversation=conv, text=text, **extra
    )


def turn_row(session_factory, turn_id: str):
    from app.models.chatbot_turn import ChatbotTurn

    return session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()


# --------------------------------------------------------------------------- #
# AC-1: the permission exists and no migration hands it to a role
# --------------------------------------------------------------------------- #


def test_the_agent_slug_is_registered():
    assert AGENT in {entry["slug"] for entry in PERMISSION_REGISTRY}


def test_one_migration_seeds_the_slug_and_grants_it_to_no_role():
    files = [p for p in VERSIONS.glob("*.py") if AGENT in p.read_text()]
    assert len(files) == 1, f"expected exactly one migration naming {AGENT}, found {[p.name for p in files]}"
    body = files[0].read_text()
    assert "user_role_permissions" not in body, "the rollout permission must be granted to nobody"


# --------------------------------------------------------------------------- #
# AC-1, AC-2, AC-26: routing on the slug
# --------------------------------------------------------------------------- #


@pytest.fixture()
def panel_client(session_factory, staff, grants):
    def _db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: {"id": staff.user_id, "name": "ZZT Panel Staff"}
    app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": staff.user_id, "name": "ZZT Panel Staff"}
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def routes(monkeypatch, session_factory, staff):
    """Spies: the old `respond()`, and the brain (`engine.run_turn`)."""
    calls = SimpleNamespace(respond=[], brain=[])

    def fake_respond(self, **kwargs):
        calls.respond.append(kwargs)
        return session_factory().get(AIAssistantConversation, staff.conv_id), None

    def boom(*args, **kwargs):
        calls.brain.append(kwargs)
        raise AssertionError("the brain ran for a panel turn that does not hold the agent permission")

    monkeypatch.setattr(AIAssistantChatService, "respond", fake_respond)
    monkeypatch.setattr(engine_mod, "run_turn", boom)
    return calls


def _post(client, staff, **extra):
    return client.post(CHAT_URL, json={"conversation_id": staff.conv_id, "message": "ZZT how much stock", **extra})


def test_without_the_slug_respond_runs_and_the_brain_does_not(panel_client, routes, staff, grants):
    resp = _post(panel_client, staff)  # AC-1, AC-26

    assert resp.status_code == 200, resp.text
    assert len(routes.respond) == 1, "today's respond() must answer a user without the agent slug"
    assert routes.respond[0]["user_id"] == staff.user_id
    assert routes.respond[0]["message"] == "ZZT how much stock"
    assert routes.brain == []


def test_with_the_slug_run_panel_turn_answers_and_respond_does_not(
    panel_client, routes, staff, grants, monkeypatch
):
    grants.add(AGENT)
    seen: list[dict[str, Any]] = []

    def fake_run_panel_turn(db, **kwargs):
        seen.append(kwargs)
        return SimpleNamespace(
            reply_text="ZZT stub reply", attachments=[], quick_replies=[], route="chat",
            turn_id=str(uuid.uuid4()), status="done",
        )

    monkeypatch.setattr("app.services.chatbot.panel_service.run_panel_turn", fake_run_panel_turn)

    resp = _post(panel_client, staff)  # AC-2: same route, same gate, identity from the session

    assert resp.status_code == 200, resp.text
    assert routes.respond == [], "respond() must not answer when the user holds the agent slug"
    assert len(seen) == 1
    assert seen[0]["user"]["id"] == staff.user_id
    assert seen[0]["text"] == "ZZT how much stock"
    assert str(seen[0]["conversation"].id) == staff.conv_id


def test_the_use_gate_still_guards_the_route(panel_client, routes, staff, grants):
    grants.discard(USE)
    grants.add(AGENT)

    resp = _post(panel_client, staff)

    assert resp.status_code == 403, resp.text
    assert routes.respond == []


def test_a_confirm_waiting_from_the_old_path_is_finished_by_the_old_path(
    panel_client, routes, staff, grants, session_factory, monkeypatch
):
    grants.add(AGENT)
    db = session_factory()
    db.add(
        AIAssistantMessage(
            conversation_id=staff.conv_id, role="assistant", content="ZZT confirm this write?",
            metadata_json={"pending_confirmation": {"tool": "zzt_tool", "args": {}}},
        )
    )
    db.commit()

    def boom(*args, **kwargs):
        raise AssertionError("a Confirm waiting from the old path went to the new path")

    monkeypatch.setattr("app.services.chatbot.panel_service.run_panel_turn", boom)

    resp = _post(panel_client, staff, confirm_action="confirm")  # AC-2

    assert resp.status_code == 200, resp.text
    assert len(routes.respond) == 1
    assert routes.respond[0]["confirm_action"] == "confirm"


# --------------------------------------------------------------------------- #
# AC-4: the principal, its key, and "can never be sent to"
# --------------------------------------------------------------------------- #


def test_the_principal_key_is_panel_dash_conversation_id_without_a_colon():
    from app.services.chatbot.principal import StaffPrincipal

    conv = str(uuid.uuid4())
    p = StaffPrincipal(user_id=str(uuid.uuid4()), conversation_id=conv, active_company_id=str(uuid.uuid4()))

    assert p.key == f"panel-{conv}"
    assert ":" not in p.key
    assert len(p.key) <= 64, "chatbot.turns.contact_respond_id is String(64)"


def test_two_threads_of_one_user_have_two_keys():
    from app.services.chatbot.principal import StaffPrincipal

    user, company = str(uuid.uuid4()), str(uuid.uuid4())
    one = StaffPrincipal(user, str(uuid.uuid4()), company)
    two = StaffPrincipal(user, str(uuid.uuid4()), company)
    assert one.key != two.key


def test_a_panel_turn_creates_no_respond_contact_row(session_factory, monkeypatch, staff, grants, world):
    before = respond_contact_count(session_factory)
    world.parser_output = stock_output("ZZTNOROW")

    result = run_panel(session_factory, monkeypatch, staff, "stock ZZTNOROW")

    assert result.turn_id
    row = turn_row(session_factory, result.turn_id)
    assert row is not None and row.contact_respond_id == f"panel-{staff.conv_id}"  # present
    assert respond_contact_count(session_factory) == before, NO_PANEL_ROW


def test_the_outbound_path_refuses_a_panel_key(session_factory, monkeypatch):
    """`assert_outbound_enabled` fails OPEN for an identifier it cannot resolve
    (respond_outbound_service.py:42-46); a panel key must be refused instead."""
    from app.services.integration_service import RespondClient

    posted: list[str] = []

    def fake_send(self, request, **kwargs):
        posted.append(str(request.url))
        return httpx.Response(200, json={}, request=request)

    monkeypatch.setattr(httpx.Client, "send", fake_send)
    monkeypatch.setattr("app.database.SessionLocal", session_factory)
    key = f"panel-{uuid.uuid4()}"

    try:
        RespondClient(api_key="zzt-fake-key").send_message(key, "ZZT hello")
    except Exception:  # noqa: BLE001 - raising is one of the two allowed outcomes
        pass

    assert posted == [], f"a message to {key} left the process: {posted}"


# --------------------------------------------------------------------------- #
# AC-10 (first half): the ingress literal is reserved
# --------------------------------------------------------------------------- #


def test_panel_is_a_declared_ingress_kind():
    assert "panel" in INGRESS_KINDS


def test_an_api_key_caller_cannot_claim_the_panel_ingress(session_factory, monkeypatch):
    # The same real key the endpoint tests issue (role holding only integration.chat_turn.submit).
    from app.models.integration import Integration
    from app.models.user import UserPermission, UserRole, UserRoleAssignment, UserRolePermission
    from app.services.integration_key_service import IntegrationKeyService

    db = session_factory()
    user = User(email=f"{unique_code('k').lower()}@integrations.local", name="ZZT panel key", status="ACTIVE", is_integration=True)
    db.add(user)
    db.flush()
    role = UserRole(slug=unique_code("role").lower(), name="ZZT role")
    db.add(role)
    db.flush()
    db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    perm = UserPermission(slug="integration.chat_turn.submit", name="Submit chatbot turns")
    db.add(perm)
    db.flush()
    db.add(UserRolePermission(role_id=role.id, permission_id=perm.id))
    integration = Integration(name=unique_code("int"), type="n8n", act_as_user_id=user.id, is_active=True)
    db.add(integration)
    db.flush()
    issued = IntegrationKeyService(db).issue_key(integration)
    db.commit()
    monkeypatch.setattr("app.api.v1.external.chat.SessionLocal", session_factory)

    def _db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    try:
        envelope = json.loads(_envelope().model_dump_json())
        envelope["ingress"] = "panel"
        resp = TestClient(app, raise_server_exceptions=False).post(
            TURN_URL, json={"envelope": envelope}, headers={"X-API-Key": issued}
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 422, resp.text
    assert re.search(r"reserved", resp.text, re.I), f"refused, but not as a reserved ingress: {resp.text[:300]}"
