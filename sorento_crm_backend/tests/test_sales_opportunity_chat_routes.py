"""Phase 2 RED tests - the two API-key routes behind logging a sales opportunity in chat,
UAC O1, O2, O3 (and O3-7, the source check constraint) of lane SALES-TARGET-CHAT, slice 2.

Contract: `documentation/plans/sales/PLAN-sales-opportunity-chat-25oct.md`, "Design (fixed for the
tests)". Both routes are driven over HTTP as the integration principal (`get_external_api_user`
overridden to a seeded act-as user; the gate is per contact, there is no permission slug).
No implementation symbol is imported at module level: a missing route fails each test on its own
(404). Postgres only (`blank_session`); every row is seeded here, CI has none.
"Today" is pinned to 25 Oct 2026.
"""
from __future__ import annotations

import re
import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db, get_external_api_user
from app.models.base import set_company_scope
from app.models.price_tag import ContactPortalFormOverride
from app.models.sales import SalesOpportunity
from app.models.user import User
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope

from tests._pg_fixture import blank_session, unique_code
from tests.test_sales_target_progress import (
    TODAY,
    UUID_RE,
    _agent,
    _contact,
    _customer,
    _linked_user,
    _opportunity,
    _target,
    _walk,
)
from tests.test_top_selling_report import _access, _link

OPTIONS = "/api/v1/external/sales-opportunities/customer-options"
CREATE = "/api/v1/external/sales-opportunities"
FORM = "sales_opportunity"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _pin_today(monkeypatch):
    from app.services.sales import target_service, team_service

    monkeypatch.setattr(team_service, "_today", lambda: TODAY)
    monkeypatch.setattr(target_service, "_today", lambda: TODAY)


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        from app.services.sales import sales_seed_service

        sales_seed_service.run(s)
        s.flush()
        yield s


def _principal(db) -> dict:
    user = User(id=_uid(), email=f"{unique_code('A')}@integrations.local", name="Act as", status="ACTIVE")
    db.add(user)
    db.flush()
    return {"id": user.id, "email": user.email}


@contextmanager
def make_client(db, *, api_key_principal=True, slug_granted=True):
    from unittest.mock import patch

    principal = _principal(db)

    def _override_db():
        yield db

    async def _scope():
        scope = frozenset({DEFAULT_COMPANY_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[apply_company_scope] = _scope
    if api_key_principal:
        app.dependency_overrides[get_external_api_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    try:
        # The real `require_external_permission` runs; only the lookup answer is stated here.
        with patch("app.api.v1.external.permissions.UserPermissionService") as service:
            service.return_value.check_user_has_permission.side_effect = (
                lambda uid, slug: slug_granted
            )
            service.slug_checks = service.return_value.check_user_has_permission
            yield TestClient(app, headers={"X-API-Key": "k"} if api_key_principal else {})
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client(db):
    with make_client(db) as c:
        yield c


def _enable_form(db, contact) -> None:
    db.add(ContactPortalFormOverride(id=_uid(), contact_id=contact.id, form_type=FORM, is_enabled=True))
    db.flush()


def _salesperson(db, code="SP", *, form=True):
    """A contact linked to one active sales agent, with the portal form enabled."""
    contact = _contact(db)
    agent = _agent(db, code, contact=contact)
    if form:
        _enable_form(db, contact)
    return contact, agent


def _me(contact) -> dict:
    return {"contact_id": contact.id, "space_id": "zzt-space"}


def _body(contact, **kw) -> dict:
    body = {
        **_me(contact), "customer_id": None, "prospect_name": "ZZT Prospect Co", "title": "ZZT condo job",
        "expected_amount": 40000, "expected_close_date": "2026-12-15", "dry_run": False,
    }
    body.update(kw)
    return body


def _code(resp) -> str | None:
    return resp.json().get("code")


def _count(db) -> int:
    return db.query(SalesOpportunity).count()


# ===================================================================================== O1


@pytest.mark.parametrize("blank", ["", "  "])
@pytest.mark.parametrize("field", ["contact_id", "space_id"])
def test_opp_routes_need_contact_and_space(client, db, field, blank):
    """O1-1."""
    contact, _agent_row = _salesperson(db)
    ids = {**_me(contact), field: blank}
    got = client.get(OPTIONS, params={**ids, "q": "x"})
    assert got.status_code == 422, got.text
    assert _code(got) == "contact_identity_required", got.text
    post = client.post(CREATE, json=_body(contact, **{field: blank}))
    assert post.status_code == 422, post.text
    assert _code(post) == "contact_identity_required", post.text


def test_opp_routes_refuse_non_salespeople(client, db):
    """O1-2: dealer, staff, unclassified, unknown, and a salesperson whose user is inactive or trashed."""
    dealer = _contact(db)
    _link(db, dealer, _customer(db, "ZZT GATE DEALER", 1))
    _enable_form(db, dealer)
    staff = _contact(db)
    _access(db, staff, "Sorento Office")
    _enable_form(db, staff)
    nobody = _contact(db)
    _enable_form(db, nobody)
    refused = [dealer, staff, nobody]
    for status, trashed in (("INACTIVE", False), ("ACTIVE", True)):
        sp, _row = _salesperson(db)
        _linked_user(db, sp, status=status, trashed=trashed)
        refused.append(sp)
    unknown = {"contact_id": _uid(), "space_id": "zzt-space"}
    before = _count(db)
    for ids in [_me(c) for c in refused] + [unknown]:
        got = client.get(OPTIONS, params={**ids, "q": "x"})
        assert got.status_code == 403, (ids, got.text)
        assert _code(got) == "not_a_salesperson", got.text
        post = client.post(CREATE, json={**_body(refused[0]), **ids})
        assert post.status_code == 403, (ids, post.text)
        assert _code(post) == "not_a_salesperson", post.text
    assert _count(db) == before


def test_opp_routes_need_the_portal_form(client, db):
    """O1-3: a salesperson whose contact may not see the portal sales_opportunity form."""
    contact, _agent_row = _salesperson(db, form=False)
    got = client.get(OPTIONS, params={**_me(contact), "q": "x"})
    assert got.status_code == 403, got.text
    assert _code(got) == "opportunity_not_enabled", got.text
    post = client.post(CREATE, json=_body(contact))
    assert post.status_code == 403, post.text
    assert _code(post) == "opportunity_not_enabled", post.text
    assert _count(db) == 0


def test_opp_routes_need_the_integration_slug(db):
    """O1-4: both routes carry `require_external_permission("integration.sales_opportunity.log")`."""
    from app.api.v1.external.permissions import EXTERNAL_ENDPOINT_PERMISSIONS
    from app.rbac import PERMISSION_REGISTRY

    slug = "integration.sales_opportunity.log"
    assert EXTERNAL_ENDPOINT_PERMISSIONS["sales-opportunities"] == slug
    assert slug in {row["slug"] for row in PERMISSION_REGISTRY}

    contact, _agent_row = _salesperson(db)
    with make_client(db, slug_granted=False) as denied:
        got = denied.get(OPTIONS, params={**_me(contact), "q": "x"})
        assert got.status_code == 403, got.text
        post = denied.post(CREATE, json=_body(contact))
        assert post.status_code == 403, post.text
    with make_client(db) as granted:
        got = granted.get(OPTIONS, params={**_me(contact), "q": "x"})
        assert got.status_code == 200, got.text
        post = granted.post(CREATE, json=_body(contact, dry_run=True))
        assert post.status_code == 201, post.text
    with make_client(db, api_key_principal=False) as bearer:
        headers = {"Authorization": "Bearer staff-session-token"}
        got = bearer.get(OPTIONS, params={**_me(contact), "q": "x"}, headers=headers)
        assert got.status_code in (401, 403), got.text
        post = bearer.post(CREATE, json=_body(contact), headers=headers)
        assert post.status_code in (401, 403), post.text
    assert _count(db) == 0


# ===================================================================================== O2


def test_options_own_customers_only(client, db):
    """O2-1."""
    contact, agent = _salesperson(db)
    other = _agent(db, "OTHER")
    mine = _customer(db, "ZZT BKIN ELECTRICAL SDN BHD", 1, agent=agent)
    theirs = _customer(db, "ZZT BKIN RIVAL SDN BHD", 1, agent=other)
    unowned = _customer(db, "ZZT BKIN ORPHAN SDN BHD", 1)
    resp = client.get(OPTIONS, params={**_me(contact), "q": "ZZT BKIN"})
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [i["customer_id"] for i in items] == [mine.id]
    assert items[0]["code"] == mine.customer_code
    assert items[0]["name"] == mine.customer_name
    assert items[0]["label"]
    for row in (theirs, unowned):
        assert row.customer_name not in resp.text and row.id not in resp.text


def test_options_returns_every_own_account(client, db):
    """O2-2: A/C I and A/C III of one dealer are both returned, labelled."""
    contact, agent = _salesperson(db)
    first = _customer(db, "ZZT TWIN DEALER SDN BHD", 1, agent=agent)
    third = _customer(db, "ZZT TWIN DEALER SDN BHD", 3, agent=agent)
    resp = client.get(OPTIONS, params={**_me(contact), "q": "ZZT TWIN DEALER"})
    assert resp.status_code == 200, resp.text
    items = {i["customer_id"]: i for i in resp.json()["items"]}
    assert set(items) == {first.id, third.id}
    assert "I" in items[first.id]["label"] and "III" in items[third.id]["label"]
    assert items[first.id]["label"] != items[third.id]["label"]


def test_options_blocked_and_prospect(client, db):
    """O2-3."""
    contact, _agent_row = _salesperson(db)
    other = _agent(db, "RIVAL")
    _customer(db, "ZZT SERI INDAH SDN BHD", 1, agent=other)
    blocked = client.get(OPTIONS, params={**_me(contact), "q": "ZZT SERI INDAH SDN BHD"})
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["items"] == [] and blocked.json()["blocked"] is True
    unknown = client.get(OPTIONS, params={**_me(contact), "q": "ZZT NOBODY HAS THIS NAME"})
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["items"] == [] and unknown.json()["prospect"] is True
    assert unknown.json()["blocked"] is False


# ===================================================================================== O3


def test_create_saves_with_source_chat_and_owner_agent(client, db):
    """O3-1: owner = the agent owning the customer, not the contact's first agent by code."""
    from app.services import status_service

    contact = _contact(db)
    first = _agent(db, "AAA", contact=contact)
    second = _agent(db, "ZZZ", contact=contact)
    _enable_form(db, contact)
    cust = _customer(db, "ZZT OWNED BY SECOND", 1, agent=second)
    resp = client.post(CREATE, json=_body(contact, customer_id=cust.id, prospect_name=None))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert re.fullmatch(r"OPP-\d{6}", body["opportunity_no"]), body
    assert body["customer"]["code"] == cust.customer_code and body["customer"]["name"] == cust.customer_name
    assert body["customer"]["label"]
    assert body["title"] == "ZZT condo job" and body["dry_run"] is False
    assert Decimal(str(body["expected_amount"])) == Decimal("40000")
    assert str(body["expected_close_date"]) == "2026-12-15" and "stage" in body
    row = db.query(SalesOpportunity).filter(SalesOpportunity.opportunity_no == body["opportunity_no"]).one()
    assert row.source == "chat" and row.outcome == "open"
    assert row.sales_agent_id == second.id != first.id
    assert row.created_by_contact_id == contact.id
    assert row.customer_id == cust.id
    assert row.status_id == status_service.initial_status(db, "sales_opportunity").id


def test_create_prospect_goes_to_first_agent(client, db):
    """O3-2: default_portal_agent, first of the contact's agents by code."""
    contact = _contact(db)
    late = _agent(db, "ZZZ", contact=contact)
    early = _agent(db, "AAA", contact=contact)
    _enable_form(db, contact)
    first_by_code = min((late, early), key=lambda a: a.sales_agent)
    resp = client.post(CREATE, json=_body(contact))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["customer"] is None and body["prospect_name"] == "ZZT Prospect Co"
    row = db.query(SalesOpportunity).filter(SalesOpportunity.opportunity_no == body["opportunity_no"]).one()
    assert row.sales_agent_id == first_by_code.id and row.customer_id is None


def test_create_refuses_other_agents_customer(client, db):
    """O3-3."""
    contact, _agent_row = _salesperson(db)
    theirs = _customer(db, "ZZT NOT MINE", 1, agent=_agent(db, "RIVAL"))
    resp = client.post(CREATE, json=_body(contact, customer_id=theirs.id, prospect_name=None))
    assert resp.status_code == 422, resp.text
    assert _code(resp) == "CUSTOMER_NOT_YOURS", resp.text
    assert _count(db) == 0


@pytest.mark.parametrize("amount", ["missing", 0, -5])
def test_create_requires_positive_amount(client, db, amount):
    """O3-4."""
    contact, _agent_row = _salesperson(db)
    body = _body(contact)
    if amount == "missing":
        body.pop("expected_amount")
    else:
        body["expected_amount"] = amount
    resp = client.post(CREATE, json=body)
    assert resp.status_code == 422, resp.text
    assert _code(resp) == "amount_required", resp.text
    assert _count(db) == 0


def test_create_dry_run_saves_nothing(client, db):
    """O3-5: every check runs, nothing inserted, no number consumed, opportunity_no null."""
    contact, _agent_row = _salesperson(db)
    other = _customer(db, "ZZT DRY NOT MINE", 1, agent=_agent(db, "RIVAL"))
    refused = client.post(CREATE, json=_body(contact, customer_id=other.id, prospect_name=None, dry_run=True))
    assert refused.status_code == 422 and _code(refused) == "CUSTOMER_NOT_YOURS", refused.text

    first = client.post(CREATE, json=_body(contact))
    assert first.status_code == 201, first.text
    before = _count(db)
    dry = client.post(CREATE, json=_body(contact, dry_run=True))
    assert dry.status_code == 201, dry.text
    assert dry.json()["dry_run"] is True and dry.json()["opportunity_no"] is None
    assert _count(db) == before
    second = client.post(CREATE, json=_body(contact))
    assert second.status_code == 201, second.text
    n1 = int(first.json()["opportunity_no"].split("-")[1])
    n2 = int(second.json()["opportunity_no"].split("-")[1])
    assert n2 == n1 + 1


def test_create_returns_pipeline(client, db):
    """O3-6: the owning agent's current target end date and open pipeline including this one."""
    contact, agent = _salesperson(db)
    cust = _customer(db, "ZZT PIPE DEALER", 1, agent=agent)
    _target(db, "agent", agent=agent, start=date(2026, 10, 1), end=date(2026, 12, 31))
    _opportunity(db, agent, 10000, date(2026, 11, 30))
    _opportunity(db, agent, 99999, date(2027, 2, 1))  # closes after the target ends: not counted
    resp = client.post(CREATE, json=_body(contact, customer_id=cust.id, prospect_name=None))
    assert resp.status_code == 201, resp.text
    pipeline = resp.json()["pipeline"]
    assert str(pipeline["target_end_date"]) == "2026-12-31"
    assert Decimal(str(pipeline["pipeline_value"])) == Decimal("50000")

    bare, bare_agent = _salesperson(db, "BARE")
    none = client.post(CREATE, json=_body(bare))
    assert none.status_code == 201, none.text
    assert none.json()["pipeline"] is None


def test_opportunity_source_accepts_chat(db):
    """O3-7: the check constraint takes 'chat' and still takes 'portal' / 'crm', and nothing else."""
    from sqlalchemy.exc import IntegrityError

    agent = _agent(db, "SRC")
    for source in ("chat", "portal", "crm"):
        row = _opportunity(db, agent, 1, date(2026, 12, 1))
        row.source = source
        db.flush()
        assert row.source == source
    row = _opportunity(db, agent, 1, date(2026, 12, 1))
    with db.begin_nested():
        row.source = "fax"
        with pytest.raises(IntegrityError):
            db.flush()
    db.expire_all()


def test_opp_responses_carry_no_other_ids(client, db):
    """O3-8: only the options route's own customer_id is a UUID; nothing else in any response."""
    contact, agent = _salesperson(db)
    cust = _customer(db, "ZZT NOID DEALER", 1, agent=agent)
    options = client.get(OPTIONS, params={**_me(contact), "q": "ZZT NOID"})
    assert options.status_code == 200, options.text
    options_payload = options.json()
    for item in options_payload["items"]:
        item.pop("customer_id")
    created = client.post(CREATE, json=_body(contact, customer_id=cust.id, prospect_name=None))
    assert created.status_code == 201, created.text
    for payload in (options_payload, created.json()):
        for key, value in _walk(payload):
            assert not (isinstance(value, str) and UUID_RE.search(value)), (key, value)


# ===================================================================================== review round


def test_opp_routes_need_the_sales_module(db, monkeypatch):
    """O1-5: `sales` off under strict mode is refused like the portal (MODULE_NOT_ENABLED)."""
    from app.config import settings
    from app.models.app_modules import AppModuleCatalog, TenantModule
    from app.modules.runtime.installer import DEFAULT_TENANT_ID

    monkeypatch.setattr(settings, "module_guard_strict", True)
    contact, _agent_row = _salesperson(db)
    other_key = f"zzt_other_{_uid()[:6]}"
    db.add(AppModuleCatalog(id=_uid(), module_key=other_key, display_name="ZZT Other", dependencies=[]))
    db.flush()
    db.add(TenantModule(id=_uid(), tenant_id=DEFAULT_TENANT_ID, module_key=other_key, enabled=True))
    db.flush()
    with make_client(db) as c:
        got = c.get(OPTIONS, params={**_me(contact), "q": "x"})
        post = c.post(CREATE, json=_body(contact))
    for resp in (got, post):
        assert resp.status_code == 403, resp.text
        assert "module not enabled" in resp.text.lower() or "MODULE_NOT_ENABLED" in resp.text, resp.text
    assert _count(db) == 0


def test_opp_audit_actor_keeps_integration_fields(db):
    """O1-8: the contact actor stamped by the gate keeps the integration actor's user_id,
    ip_address, user_agent and tool_name."""
    from app.audit_context import AuditActor, get_actor, stamp_actor

    contact, _agent_row = _salesperson(db)
    principal = _principal(db)
    integration = AuditActor(
        actor_type="integration", user_id=principal["id"], real_user_id=principal["id"],
        auth_method="api_key", integration_id=_uid(), ip_address="203.0.113.7",
        user_agent="zzt-agent/1.0", tool_name="crm_sales_opportunity_log",
    )

    async def _stamping_user():
        stamp_actor(integration, db=db)
        return principal

    with make_client(db) as c:
        app.dependency_overrides[get_external_api_user] = _stamping_user
        resp = c.get(OPTIONS, params={**_me(contact), "q": "x"})
    assert resp.status_code == 200, resp.text
    actor = get_actor(db)
    assert actor.actor_type == "contact" and actor.contact_id == contact.id
    assert actor.user_id == integration.user_id
    assert actor.integration_id == integration.integration_id
    assert actor.ip_address == "203.0.113.7"
    assert actor.user_agent == "zzt-agent/1.0"
    assert actor.tool_name == "crm_sales_opportunity_log"


def test_opp_slug_granted_to_chatbot_roles_only(db):
    """O1-7: stc_0003's grant reaches admin, integration_sorento_mcp, integration_n8n only."""
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from app.models.user import UserPermission, UserRole, UserRolePermission

    roles = {}
    for slug in ("admin", "integration_sorento_mcp", "integration_n8n", "integration_foundryx_esb",
                 "integration_other", "sales_manager"):
        row = db.query(UserRole).filter(UserRole.slug == slug).first()
        if row is None:
            row = UserRole(id=_uid(), slug=slug, name=f"ZZT {slug} {_uid()[:6]}")
            db.add(row)
        roles[slug] = row
    db.flush()

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "stc_0003_opp_log_slug.py"
    spec = importlib.util.spec_from_file_location("stc_0003_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(db.connection())):
        module.upgrade()
    db.flush()

    perm = db.query(UserPermission).filter(UserPermission.slug == "integration.sales_opportunity.log").one()
    granted = {
        r.slug
        for r in db.query(UserRole)
        .join(UserRolePermission, UserRolePermission.role_id == UserRole.id)
        .filter(UserRolePermission.permission_id == perm.id)
    }
    assert {"admin", "integration_sorento_mcp", "integration_n8n"} <= granted
    assert not granted & {"integration_foundryx_esb", "integration_other", "sales_manager"}


def test_create_refuses_too_large_amount(client, db):
    """O3-9: above numeric(15,2) is 422 amount_too_large, never a 500."""
    contact, _agent_row = _salesperson(db)
    resp = client.post(CREATE, json=_body(contact, expected_amount=10**13))
    assert resp.status_code == 422, resp.text
    assert _code(resp) == "amount_too_large", resp.text
    assert _count(db) == 0


def test_assistant_log_tool_needs_opportunities_add(db, monkeypatch):
    """O4-3: the in-app assistant maps the log tool to sales.opportunities.add and refuses
    the confirm for a user without it."""
    import app.services.ai_assistant_service as m
    import app.services.user_service as us
    from app.models.ai_assistant import AIAssistantConversation
    from app.services.ai_assistant_service import AIAssistantChatService

    assert AIAssistantChatService._WRITE_TOOL_PERMISSIONS["crm_sales_opportunity_log"] == "sales.opportunities.add"

    calls = []

    class _FakeMCP:
        def __init__(self, *a, **k):
            pass

        def call_tool(self, tool_name, args):
            calls.append((tool_name, args))
            return "{}"

    monkeypatch.setattr(m, "MCPRuntimeClient", _FakeMCP)
    monkeypatch.setattr(us.UserPermissionService, "check_user_has_permission", lambda self, uid, slug: False)
    user = User(id=_uid(), email=f"{unique_code('U')}@zzt.test", name="ZZT Staff", status="ACTIVE")
    db.add(user)
    db.flush()
    conv = AIAssistantConversation(user_id=user.id, title="t")
    db.add(conv)
    db.commit()
    svc = AIAssistantChatService(db)
    svc._turn_trace = None
    svc._turn_prompt_versions = []
    svc._parse_token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    import types

    cfg = types.SimpleNamespace(model="gpt-x", provider="openai")
    pending = {
        "tool_name": "crm_sales_opportunity_log",
        "args": {"contact_id": "c", "space_id": "s", "title": "t"},
        "summary": "log a sales opportunity",
    }
    svc._serve_pending_confirmation(conv=conv, config=cfg, pending=pending, request_started=0.0)
    loaded = svc._load_pending_confirmation(conv.id)
    _c, msg = svc._resolve_pending_confirmation(
        conv=conv, user_id=user.id, config=cfg, pending=loaded, action="confirm", request_started=0.0,
    )
    assert calls == []
    assert msg.metadata_json["pending_confirmation"]["status"] == "denied"


def test_options_partial_name_of_other_agents_customer_is_blocked(client, db):
    """O2-3 (crew a43805183): a partial name of another agent's customer is blocked, not a prospect."""
    contact, _agent_row = _salesperson(db)
    _customer(db, "4 SMART PLUS SDN BHD", 1, agent=_agent(db, "RIVAL"))
    part = client.get(OPTIONS, params={**_me(contact), "q": "4 SMART PLUS"})
    assert part.status_code == 200, part.text
    assert part.json()["items"] == []
    assert part.json()["blocked"] is True and part.json()["prospect"] is False
    none = client.get(OPTIONS, params={**_me(contact), "q": "ZZT NOBODY TRADING"})
    assert none.status_code == 200, none.text
    assert none.json()["prospect"] is True and none.json()["blocked"] is False


def test_create_refuses_prospect_that_is_another_agents_customer(client, db):
    """O3-10 (crew a43805183): the route refuses a prospect name matching another agent's customer."""
    contact, _agent_row = _salesperson(db)
    _customer(db, "4 SMART PLUS SDN BHD", 1, agent=_agent(db, "RIVAL"))
    refused = client.post(CREATE, json=_body(contact, prospect_name="4 SMART PLUS"))
    assert refused.status_code == 422, refused.text
    assert _code(refused) == "CUSTOMER_NOT_YOURS", refused.text
    assert _count(db) == 0
    ok = client.post(CREATE, json=_body(contact, prospect_name="ZZT NOBODY TRADING"))
    assert ok.status_code == 201, ok.text
    assert _count(db) == 1


def test_unassigned_customer_is_not_yours_in_chat(client, db):
    """O2-4: a company customer with no sales agent is not the salesperson's: blocked, never a prospect."""
    contact, _agent_row = _salesperson(db)
    _customer(db, "ZZT UNASSIGNED HARDWARE SDN BHD", 1)
    for q in ("ZZT UNASSIGNED HARDWARE SDN BHD", "ZZT UNASSIGNED HARDWARE"):
        resp = client.get(OPTIONS, params={**_me(contact), "q": q})
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"] == []
        assert resp.json()["blocked"] is True and resp.json()["prospect"] is False, (q, resp.text)
    refused = client.post(CREATE, json=_body(contact, prospect_name="ZZT UNASSIGNED HARDWARE"))
    assert refused.status_code == 422, refused.text
    assert _code(refused) == "CUSTOMER_NOT_YOURS", refused.text
    assert _count(db) == 0
