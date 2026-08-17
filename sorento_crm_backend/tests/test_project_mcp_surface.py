"""S6 — the surface the AI / MCP layer reads projects through (UAC Group K).

Three things are being pinned, and none of them is "the endpoint returns rows":

1. **UUID-first filters.** The MCP contract (`test_no_freetext_query_on_data_list_tools`
   in the MCP package) forbids a fuzzy `query` param on an entity list tool, so the way an
   agent asks for "Damai Land's projects" is: resolve the name to a UUID, then filter by it.
   That means the list route needs `<entity>_ids` params shaped exactly like every other
   list route's, and a bad UUID must fail loudly rather than silently returning everything.

2. **Status by KEY.** Statuses are global rows with UUID ids, but `key` is the documented
   stable identity (grill finding G3). An agent asked "which projects are tendering" should
   not need a status-table round trip to answer, so `status_key` is a first-class filter.

3. **Name resolution exists at all.** `project` and `project_party` probes have to be
   registered with the entity resolver, or the coercion layer has nothing to substitute and
   every name-shaped argument reaches the backend as a 400.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-s6"
BASE = "/api/v1/project-sales"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _client(db, user_id: str):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "superadmin"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
    UserPermissionService.get_user_permission_slugs = lambda self, uid: [
        "projects.projects.view",
        "projects.projects.create",
        "projects.projects.edit",
    ]
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


@pytest.fixture()
def api():
    from app.models.projects import ProjectParty
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        ali = _user(db, f"{MARKER} Ali")
        siti = _user(db, f"{MARKER} Siti")

        developer = ProjectParty(
            id=_uid(),
            company_id=company_id,
            party_type="developer",
            name=f"{MARKER} Damai Land Sdn Bhd",
        )
        other_dev = ProjectParty(
            id=_uid(),
            company_id=company_id,
            party_type="developer",
            name=f"{MARKER} Mutiara Properties Bhd",
        )
        db.add_all([developer, other_dev])
        db.flush()

        first = register_project(
            db,
            company_id=company_id,
            actor_user_id=ali,
            developer_party_id=developer.id,
            title=f"{MARKER} Residensi Damai",
            owner_user_id=ali,
        )
        second = register_project(
            db,
            company_id=company_id,
            actor_user_id=siti,
            developer_party_id=other_dev.id,
            title=f"{MARKER} Bandar Mutiara Tower",
            owner_user_id=siti,
        )
        db.flush()

        client, originals = _client(db, ali)
        try:
            yield {
                "db": db,
                "client": client,
                "company_id": company_id,
                "ali": ali,
                "siti": siti,
                "developer": developer,
                "other_dev": other_dev,
                "first": first,
                "second": second,
            }
        finally:
            _restore(originals)


def _codes(payload) -> set[str]:
    return {row["project_code"] for row in payload["data"]}


# ------------------------------------------------------------------ UUID filters


def test_projects_filter_by_project_ids_csv(api):
    """CSV in one param, because that is how the MCP layer passes a resolved list."""
    response = api["client"].get(
        f"{BASE}/projects/", params={"project_ids": str(api["first"].id)}
    )
    assert response.status_code == 200, response.text
    assert _codes(response.json()) == {api["first"].project_code}


def test_projects_filter_by_developer_party_ids(api):
    response = api["client"].get(
        f"{BASE}/projects/", params={"developer_party_ids": str(api["other_dev"].id)}
    )
    assert response.status_code == 200, response.text
    assert _codes(response.json()) == {api["second"].project_code}


def test_projects_filter_by_owner_user_ids_is_my_pipeline(api):
    """AC-K1's "my pipeline" is this filter with the caller's own id -- MCP calls carry no
    user identity (AC-K4), so the owner is always passed explicitly rather than inferred."""
    response = api["client"].get(
        f"{BASE}/projects/", params={"owner_user_ids": api["siti"]}
    )
    assert response.status_code == 200, response.text
    assert _codes(response.json()) == {api["second"].project_code}


def test_a_malformed_uuid_is_a_400_not_a_silent_full_list(api):
    """Silently ignoring an unparseable filter is the worst outcome: the agent reports
    "Damai Land has 47 projects" when it actually listed every project in the company."""
    response = api["client"].get(
        f"{BASE}/projects/", params={"developer_party_ids": "Damai Land Sdn Bhd"}
    )
    assert response.status_code == 400, response.text


# ------------------------------------------------------------------ status by key


def test_projects_filter_by_status_key(api):
    """`key` is the stable identity per entity_type (G3), so an agent can ask for a rung by
    name without a status-table lookup first."""
    from app.models.status import Status

    db = api["db"]
    tendering = (
        db.query(Status)
        .filter(
            Status.entity_type == "project",
            Status.scope_id.is_(None),
            Status.key == "tendering",
        )
        .first()
    )
    api["second"].status_id = tendering.id
    db.flush()

    response = api["client"].get(f"{BASE}/projects/", params={"status_key": "tendering"})
    assert response.status_code == 200, response.text
    assert _codes(response.json()) == {api["second"].project_code}


def test_an_unknown_status_key_says_so_rather_than_returning_everything(api):
    response = api["client"].get(f"{BASE}/projects/", params={"status_key": "negotiating"})
    assert response.status_code == 422, response.text
    body = response.json()
    # The message has to name the valid keys, or the caller's only recourse is guessing.
    assert "tendering" in str(body)


# ------------------------------------------------------------------ name resolution


def test_the_resolver_finds_a_project_by_its_code_and_title(api):
    from app.services.entity_resolver import resolve_references

    db = api["db"]
    result = resolve_references(
        db,
        [api["first"].project_code, f"{MARKER} Residensi Damai"],
        allowed_entity_types=["project"],
        enable_embedding_fallback=False,
    )
    resolved_ids = {
        match.uuid for token in result.resolutions for match in token.matches
    }
    assert str(api["first"].id) in resolved_ids


def test_the_resolver_finds_a_developer_by_name(api):
    """"Damai Land's projects" is two steps: resolve the party, then filter by its id."""
    from app.services.entity_resolver import resolve_references

    result = resolve_references(
        api["db"],
        [f"{MARKER} Damai Land Sdn Bhd"],
        allowed_entity_types=["project_party"],
        enable_embedding_fallback=False,
    )
    resolved_ids = {
        match.uuid for token in result.resolutions for match in token.matches
    }
    assert str(api["developer"].id) in resolved_ids


def test_the_coercion_layer_knows_the_project_params():
    """Without these entries a resolved name never reaches the tool call, and the agent
    passes the literal name into a UUID param (the 400 this mapping exists to prevent)."""
    from app.services.ai_assistant_service import _UUID_PARAM_ENTITY_TYPES

    assert _UUID_PARAM_ENTITY_TYPES.get("project_ids") == "project"
    assert _UUID_PARAM_ENTITY_TYPES.get("project_id") == "project"
    assert _UUID_PARAM_ENTITY_TYPES.get("developer_party_ids") == "project_party"


# ------------------------------------------------------------------ tool bootstrap


def test_the_project_tools_are_enabled_for_the_assistant_without_an_admin():
    """AC-K1. The in-app assistant only considers tools listed in
    `AIAssistantConfig.enabled_tools`, so a shipped tool nobody enabled is invisible.

    NOTE ON THE AC: it says "agent_mcp_tools links are seeded by the startup hook". That
    table and the tool->agent ownership model were REMOVED when n8n took over agent routing
    (see the `McpTool` docstring). The equivalent today is this list, which is what
    `it_support_bootstrap` also maintains, so the requirement is met against the mechanism
    that actually exists.
    """
    from app.models.ai_assistant import AIAssistantConfig
    from app.services import project_mcp_bootstrap as bootstrap

    with blank_session() as db:
        db.add(AIAssistantConfig(id=_uid(), enabled_tools=["crm_master_products_list"]))
        db.flush()

        added = bootstrap.run(db)
        config = db.query(AIAssistantConfig).first()

        assert set(bootstrap.PROJECT_TOOLS).issubset(set(config.enabled_tools))
        # The tool somebody else enabled is still there.
        assert "crm_master_products_list" in config.enabled_tools
        assert added["tools_enabled"] == len(bootstrap.PROJECT_TOOLS)

        # Idempotent: a second boot changes nothing.
        assert bootstrap.run(db)["tools_enabled"] == 0


def test_the_bootstrap_is_silent_when_the_assistant_is_not_configured():
    """A fresh install has no AIAssistantConfig row. Boot must not raise -- the next boot
    picks it up once somebody configures the assistant."""
    from app.services import project_mcp_bootstrap as bootstrap

    with blank_session() as db:
        assert bootstrap.run(db)["tools_enabled"] == 0


# ------------------------------------------------------------------ API-key principal


def _api_key_client(db):
    """A client authenticating the way the MCP server does: X-API-Key only, NO JWT.

    Clears the fixture's JWT overrides first -- leaving them in place made an earlier version
    of these tests pass while proving nothing, because every request was still arriving as a
    logged-in superadmin.
    """
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[apply_company_scope] = lambda: None
    return TestClient(app)


def test_the_mcp_read_routes_accept_an_api_key(api):
    """Found by calling the tools for real: every project route used `require_permission`,
    which is JWT-only, so all four tools returned 401 "Authentication required".

    The MCP server has no JWT -- it presents `X-API-Key` plus an act-as user whose role
    supplies the permissions (the CLAUDE.md auth-boundary note). Read routes therefore need
    `require_permission_with_api_key`, which still enforces the permission against the
    resolved act-as user.
    """
    from app.config import settings
    from app.services.user_service import UserPermissionService

    db = api["db"]
    project_id = str(api["first"].id)

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
    UserPermissionService.get_user_permission_slugs = lambda self, uid: [
        "projects.projects.view"
    ]
    original_key = settings.external_api_key
    original_act_as = settings.external_api_key_act_as_user_id
    settings.external_api_key = "zzt-test-key"
    settings.external_api_key_act_as_user_id = api["ali"]
    # The key is authenticated against the `integrations` tables (hashed), not against the
    # env var directly -- the env value is only CARRIED OVER into an integration row at boot.
    # Seeding it here is what makes this test exercise the real auth path rather than a
    # simulation of it.
    from app.services.integration_seed import seed_integrations

    seed_integrations(db, "zzt-test-key", None)
    db.flush()

    try:
        client = _api_key_client(db)
        headers = {"X-API-Key": "zzt-test-key"}
        for path in (
            f"{BASE}/projects/",
            f"{BASE}/projects/{project_id}",
            f"{BASE}/projects/{project_id}/quotations",
            f"{BASE}/reports/forecast",
        ):
            response = client.get(path, headers=headers)
            assert response.status_code == 200, (
                f"{path} -> {response.status_code} {response.text[:200]}"
            )
    finally:
        settings.external_api_key = original_key
        settings.external_api_key_act_as_user_id = original_act_as
        UserPermissionService.check_user_has_permission = originals[0]
        UserPermissionService.get_user_permission_slugs = originals[1]


def test_a_write_route_still_refuses_an_api_key(api):
    """AC-K2 enforced at the ROUTE, not only in the tool catalog.

    Widening reads must not quietly widen writes: an API key that could POST a project would
    make "no write-capable project tools in v1" a statement about the catalog rather than
    about the system.
    """
    from app.config import settings

    db = api["db"]
    original_key = settings.external_api_key
    settings.external_api_key = "zzt-test-key"
    try:
        client = _api_key_client(db)
        response = client.post(
            f"{BASE}/projects/",
            headers={"X-API-Key": "zzt-test-key"},
            json={"title": f"{MARKER} written by a key"},
        )
        assert response.status_code in (401, 403), response.text
    finally:
        settings.external_api_key = original_key


def test_the_bootstrap_grants_the_read_permission_to_integration_roles():
    """Found by calling the tools against the real stack: 401 became 403.

    Integration principals (`sorento-mcp`, `n8n`, `foundryx-esb`) were seeded with the ADMIN
    permission set as it stood at seed time. `projects.projects.view` did not exist then and
    nothing back-fills it, so every project tool would 403 forever while looking perfectly
    configured -- the tool is in the catalog, enabled for the assistant, and the key
    authenticates.

    So the bootstrap grants exactly ONE permission, the module's read slug, to roles that an
    integration acts as. Deliberately narrow: read only, integration roles only, and only
    where missing. Widening an integration's rights is not something to do broadly on a boot.
    """
    from app.models.integration import Integration
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )
    from app.services import project_mcp_bootstrap as bootstrap

    with blank_session() as db:
        permission = UserPermission(
            id=_uid(), name="Projects view", slug=bootstrap.READ_PERMISSION
        )
        role = UserRole(id=_uid(), name="Integration MCP", slug="integration_sorento_mcp")
        principal = _user(db, f"{MARKER} mcp principal")
        db.add_all([permission, role])
        db.flush()
        db.add(UserRoleAssignment(id=_uid(), user_id=principal, role_id=role.id))
        db.add(
            Integration(
                id=_uid(),
                name="sorento-mcp",
                type="mcp",
                act_as_user_id=principal,
            )
        )
        db.flush()

        granted = bootstrap.run(db)["permissions_granted"]
        assert granted == 1

        held = (
            db.query(UserRolePermission)
            .filter(
                UserRolePermission.role_id == role.id,
                UserRolePermission.permission_id == permission.id,
            )
            .count()
        )
        assert held == 1
        # Idempotent, and a second boot does not re-report work.
        assert bootstrap.run(db)["permissions_granted"] == 0


def test_the_bootstrap_grants_nothing_to_a_human_role():
    """The grant is scoped to principals an INTEGRATION acts as. A salesperson's rights stay
    an admin's decision -- a boot that quietly hands out permissions to human roles is a
    security incident waiting to be discovered."""
    from app.models.user import (
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )
    from app.services import project_mcp_bootstrap as bootstrap

    with blank_session() as db:
        permission = UserPermission(
            id=_uid(), name="Projects view", slug=bootstrap.READ_PERMISSION
        )
        role = UserRole(id=_uid(), name="Salesperson", slug="salesperson")
        human = _user(db, f"{MARKER} human")
        db.add_all([permission, role])
        db.flush()
        db.add(UserRoleAssignment(id=_uid(), user_id=human, role_id=role.id))
        db.flush()

        assert bootstrap.run(db)["permissions_granted"] == 0
        assert (
            db.query(UserRolePermission)
            .filter(UserRolePermission.role_id == role.id)
            .count()
            == 0
        )
