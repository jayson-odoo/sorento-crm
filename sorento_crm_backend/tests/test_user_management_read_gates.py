"""GET-route permission gates on the user-management surface.

Context: `documentation/plans/security/PLAN-user-management-read-gates.md` +
`documentation/plans/security/user-management-read-gates-acceptance-criteria.md`.
Thirteen GETs across `teams.py` / `access_agents.py` / `contact_access_types.py`
were `Depends(get_current_user)` only - any authenticated session, regardless of
role, could read the contact directory, staff rosters, the agent-to-contact
access matrix and per-field ACL rows. They now require
`user_management.teams.view` or `user_management.access_agents.view` via
`Depends(require_permission(...))`.

Structure:

* Work item 3 (UAC1.1-1.3, 2.1-2.2, 3.1-3.2) - one 403 + one 200 per gated route,
  table-driven.
* UAC2.3 - the field-access 403 fires before any field-access row is read.
* Work item 4 (UAC4.1-4.3) - structural coverage: every GET in the seven
  user-management files carries a permission dependency or sits in a commented
  exception allowlist, so a route added tomorrow without a gate fails this test.
* Work item 5 (UAC3.3, 5.1, 5.2) - the three documented exceptions stay exactly
  as documented: the active-only contact-access-types catalog is NOT gated, the
  quick-access read is self-scoped, and the contacts/companies read is gated
  in the handler body rather than by dependency.

Dependency-override + `allow`-set monkeypatch pattern copied from
tests/test_user_respond_users_permission.py (PR #168).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.v1.user_management import router as user_management_router
from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models.access import AccessAgent, ContactAccessType, Team, TeamMember
from app.models.base import set_company_scope
from app.models.user import User, UserQuickAccess, UserStatus
from app.services.company_scope_resolver import apply_company_scope
from app.services.user_service import AccessAgentService
from tests._pg_fixture import blank_session, unique_code

TEAMS_VIEW = "user_management.teams.view"
ACCESS_AGENTS_VIEW = "user_management.access_agents.view"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _install_overrides(db, caller: dict):
    """Wire get_db / get_current_user / the company-scope resolver onto the SAME
    test session, for a raw (no bearer token) TestClient call.

    ``apply_company_scope`` is a router-level dependency on the whole /api/v1/*
    mount (app/main.py) that re-derives the principal from the request's own
    Authorization header - it does NOT read the `get_current_user` override, so
    without this a tokenless TestClient request resolves UNSET (fail-closed) and
    every CompanyScopedMixin table (e.g. `teams`) silently reads back zero rows,
    404-ing a route that a real gated + authenticated caller would see fine. This
    pins it open to "all companies" so seeded rows are visible, matching what the
    permission gate under test actually cares about.
    """

    def _override_db():
        yield db

    def _override_scope(_db=Depends(get_db)):
        set_company_scope(_db, None)
        return None

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[apply_company_scope] = _override_scope


def _clear_overrides():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(apply_company_scope, None)


@pytest.fixture
def api(db, monkeypatch):
    """A caller whose permission set is controlled by the returned `allow` set."""
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()
    caller = {"id": str(uuid.uuid4()), "email": "read-gates-caller@zzt.test"}

    _install_overrides(db, caller)
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client, allow, caller
    finally:
        _clear_overrides()


# --------------------------------------------------------------------- seeds


def _seed_team(db) -> str:
    team = Team(id=str(uuid.uuid4()), name=unique_code("team"))
    db.add(team)
    db.flush()
    return str(team.id)


def _seed_team_with_member(db) -> tuple[str, str]:
    team = Team(id=str(uuid.uuid4()), name=unique_code("team"))
    db.add(team)
    db.flush()
    user = User(
        id=unique_code("user"),
        email=f"{unique_code('member')}@zzt.test",
        name="ZZT Member",
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    db.flush()
    member = TeamMember(id=str(uuid.uuid4()), team_id=team.id, user_id=user.id, sort_order=0)
    db.add(member)
    db.flush()
    return str(team.id), str(user.id)


def _seed_access_agent(db) -> str:
    agent = AccessAgent(id=str(uuid.uuid4()), code=unique_code("agent"), name="ZZT Agent", is_active=True)
    db.add(agent)
    db.flush()
    return str(agent.id)


def _seed_contact_access_type(db) -> str:
    code = unique_code("cat").lower().replace("-", "_")
    row = ContactAccessType(code=code, name="ZZT Access Type", is_active=True)
    db.add(row)
    db.flush()
    return code


# --------------------------------------------------------------- work item 3


def _team_route_specs(db):
    team_id = _seed_team(db)
    team_id_with_member, member_user_id = _seed_team_with_member(db)
    return [
        ("GET /teams/",
            "/api/v1/user-management/teams/",
            TEAMS_VIEW,
            lambda r: isinstance(r.json(), list)),
        ("GET /teams/{id}",
            f"/api/v1/user-management/teams/{team_id}",
            TEAMS_VIEW,
            lambda r: r.json()["id"] == team_id),
        ("GET /teams/{id}/members",
            f"/api/v1/user-management/teams/{team_id_with_member}/members",
            TEAMS_VIEW,
            lambda r: {m["user_id"] for m in r.json()} == {member_user_id}),
        ("GET /teams/{id}/members/{uid}/market-segments",
            f"/api/v1/user-management/teams/{team_id_with_member}/members/{member_user_id}/market-segments",
            TEAMS_VIEW,
            lambda r: r.json()["codes"] == []),
    ]


def _access_agent_route_specs(db):
    agent_id = _seed_access_agent(db)
    return [
        ("GET /access-agents/",
            "/api/v1/user-management/access-agents/",
            ACCESS_AGENTS_VIEW,
            lambda r: "data" in r.json() and "pagination" in r.json()),
        ("GET /access-agents/contact-access",
            "/api/v1/user-management/access-agents/contact-access",
            ACCESS_AGENTS_VIEW,
            lambda r: "data" in r.json() and "pagination" in r.json()),
        ("GET /access-agents/neighbours",
            f"/api/v1/user-management/access-agents/neighbours?id={agent_id}",
            ACCESS_AGENTS_VIEW,
            lambda r: {"total", "index", "prev_id", "next_id"} <= set(r.json())),
        ("GET /access-agents/{id}",
            f"/api/v1/user-management/access-agents/{agent_id}",
            ACCESS_AGENTS_VIEW,
            lambda r: r.json()["id"] == agent_id),
        ("GET /access-agents/{id}/teams",
            f"/api/v1/user-management/access-agents/{agent_id}/teams",
            ACCESS_AGENTS_VIEW,
            lambda r: r.json() == {"assignments": []}),
        ("GET /access-agents/{id}/field-access",
            f"/api/v1/user-management/access-agents/{agent_id}/field-access",
            ACCESS_AGENTS_VIEW,
            lambda r: "fields" in r.json() and "overrides" in r.json()),
        ("GET /access-agents/{id}/contact-access",
            f"/api/v1/user-management/access-agents/{agent_id}/contact-access",
            ACCESS_AGENTS_VIEW,
            lambda r: r.json() == []),
    ]


def _contact_access_type_route_specs(db):
    code = _seed_contact_access_type(db)
    return [
        ("GET /contact-access-types/all",
            "/api/v1/user-management/contact-access-types/all",
            ACCESS_AGENTS_VIEW,
            lambda r: code in {row["code"] for row in r.json()}),
        ("GET /contact-access-types/{code}",
            f"/api/v1/user-management/contact-access-types/{code}",
            ACCESS_AGENTS_VIEW,
            lambda r: r.json()["code"] == code),
    ]


def _all_route_specs(db):
    return (
        _team_route_specs(db)
        + _access_agent_route_specs(db)
        + _contact_access_type_route_specs(db)
    )


class TestPerRouteGates:
    """UAC1.1-1.3, 2.1-2.2, 3.1-3.2: one 403 + one 200 per gated route."""

    @pytest.fixture(autouse=True)
    def _specs(self, db):
        self.specs = _all_route_specs(db)
        assert len(self.specs) == 13, "one entry per gated route named in the plan's audit table"

    def test_denied_without_permission(self, api):
        client, allow, _caller = api
        for label, url, slug, _check in self.specs:
            resp = client.get(url)
            assert resp.status_code == 403, f"{label}: expected 403, got {resp.status_code} ({resp.text})"
            assert slug in resp.json()["detail"], f"{label}: slug {slug!r} not named in detail {resp.json()!r}"

    def test_allowed_with_permission(self, api):
        client, allow, _caller = api
        for label, url, slug, check in self.specs:
            allow.clear()
            allow.add(slug)
            resp = client.get(url)
            assert resp.status_code == 200, f"{label}: expected 200, got {resp.status_code} ({resp.text})"
            assert check(resp), f"{label}: response shape unexpected: {resp.json()!r}"


def test_field_access_403_fires_before_any_field_access_row_is_read(api, monkeypatch, db):
    """UAC2.3 - a denied caller learns nothing about which fields exist.

    A sentinel that appends instead of raising: the route wraps its body in a
    try/except, so a raise inside the monkeypatched service method would be
    swallowed and read as an unrelated 500, not prove the point. Recording,
    then asserting the recording list stayed empty AFTER the response check,
    proves the permission dependency ran (and denied) before the handler body
    - and therefore before `AccessAgentService.list_field_access` - ever ran.
    """
    client, allow, _caller = api
    calls: list[tuple[str, str | None]] = []

    def _sentinel(self, agent_id, contact_id=None):
        calls.append((agent_id, contact_id))
        return {"agent_code": "should-not-be-reached", "fields": [], "overrides": []}

    monkeypatch.setattr(AccessAgentService, "list_field_access", _sentinel)

    agent_id = _seed_access_agent(db)
    resp = client.get(f"/api/v1/user-management/access-agents/{agent_id}/field-access")

    assert resp.status_code == 403
    assert ACCESS_AGENTS_VIEW in resp.json()["detail"]
    assert calls == [], "field-access rows were read despite the caller lacking the permission"


# --------------------------------------------------------------- work item 4

# Files in scope for the structural coverage sweep (PLAN row list + Q1-Q3).
_IN_SCOPE_MODULES = {
    "app.api.v1.user_management.contacts",
    "app.api.v1.user_management.teams",
    "app.api.v1.user_management.access_agents",
    "app.api.v1.user_management.contact_access_types",
    "app.api.v1.user_management.market_segments",
    "app.api.v1.user_management.quick_access",
    "app.api.v1.user_management.settings",
}

_PLAN_PATH = "documentation/plans/security/PLAN-user-management-read-gates.md"

# Every GET in the seven files that is deliberately NOT behind a permission
# dependency, keyed on the exact ROUTE PATH (not endpoint function name -
# `get_contact_access_agents` names two different handlers: the gated one at
# `/access-agents/{agent_id}/contact-access` and this deferred one at
# `/contacts/{contact_id}/access-agents`; a name-keyed map would conflate them).
_EXCEPTION_ALLOWLIST: dict[str, str] = {
    # --- Q1: no `user_management.contacts.view` slug exists yet; the screen is
    # reachable by all 125 assigned users via the topbar Apps dropdown with no
    # menu-level filter, so gating on any user_management.* slug would silently
    # narrow access rather than mechanically preserve it. See Q1, PLAN_PATH.
    "/api/v1/user-management/contacts/": "Q1 deferred - " + _PLAN_PATH,
    "/api/v1/user-management/contacts/cs-routing/candidates": "Q1 deferred - " + _PLAN_PATH,
    "/api/v1/user-management/contacts/cs-routing/fields": "Q1 deferred - " + _PLAN_PATH,
    "/api/v1/user-management/contacts/{contact_id}": "Q1 deferred - " + _PLAN_PATH,
    "/api/v1/user-management/contacts/{contact_id}/access-agents": "Q1 deferred - " + _PLAN_PATH,
    "/api/v1/user-management/contacts/{contact_id}/attachment-types": "Q1 deferred - " + _PLAN_PATH,
    "/api/v1/user-management/contacts/{contact_id}/cs-routing": "Q1 deferred - " + _PLAN_PATH,
    "/api/v1/user-management/contacts/{contact_id}/market-segments": "Q1 deferred - " + _PLAN_PATH,
    # --- Already gated, but in the handler body (`_require_superadmin`) rather
    # than a dependency - UAC5.2 asserts this still bites.
    "/api/v1/user-management/contacts/{contact_id}/companies": (
        "gated in-body via _require_superadmin, not a dependency - see UAC5.2"
    ),
    # --- Q2: leaks n8n webhook URLs, SMTP config, default-approver identities and
    # role ids, but is also read by procurement screens under a role with none of
    # the candidate user_management.* slugs - gating would be a silent narrowing,
    # not a pure fix. See Q2, PLAN_PATH.
    "/api/v1/user-management/settings/": "Q2 deferred - " + _PLAN_PATH,
    # --- Q3: cross-module reference catalogs consumed by ~10 marketing / forms /
    # resource-management / master-data screens under roles holding zero
    # user_management.* grants. See Q3, PLAN_PATH.
    "/api/v1/user-management/market-segments/": "Q3 deferred - " + _PLAN_PATH,
    "/api/v1/user-management/contact-access-types/": "Q3 deferred - " + _PLAN_PATH,
    # --- Self-scoped: filters on `user_id == current_user["id"]`, discloses
    # nothing about anyone else, and fires on every page load for every user
    # from the app shell (a gate would 403 users with no pin/unpin grant).
    "/api/v1/user-management/quick-access/": "self-scoped - see UAC5.1",
}


def _mounted_get_routes():
    """The real flattened GET APIRoute objects for the seven in-scope files.

    Mounted onto a throwaway app (rather than read off `app.main.app.routes`)
    for the same reasons as tests/test_external_permission_coverage.py: a
    half-initialised app.main under test ordering, and lazy _IncludedRouter
    wrappers on newer FastAPI. include_router() onto a fresh app forces the
    flatten deterministically either way.
    """
    probe = FastAPI()
    probe.include_router(user_management_router, prefix="/api/v1/user-management")
    return [
        r
        for r in probe.routes
        if hasattr(r, "path")
        and "GET" in getattr(r, "methods", set())
        and getattr(r.endpoint, "__module__", "") in _IN_SCOPE_MODULES
    ]


def _dependant_chain_names(route) -> list[str]:
    """Every dependency callable's qualname reachable from this route's Dependant
    tree - covers both `dependencies=[...]` entries and `Depends(...)` used as a
    parameter default (the shape `require_permission` is applied in), and any
    dependency nested under either.
    """
    names: list[str] = []
    seen: set[int] = set()

    def _walk(dependant):
        if id(dependant) in seen:
            return
        seen.add(id(dependant))
        call = getattr(dependant, "call", None)
        if call is not None:
            names.append(getattr(call, "__qualname__", "") or "")
        for sub in getattr(dependant, "dependencies", []) or []:
            _walk(sub)

    _walk(route.dependant)
    return names


def _is_gated(route) -> bool:
    names = _dependant_chain_names(route)
    return any("require_permission" in n or "require_any_permission" in n for n in names)


class TestStructuralCoverage:
    def test_there_are_user_management_get_routes_to_check(self):
        # UAC4.2's whole point breaks if this is vacuously empty. 26 is the real
        # count (13 gated + 13 exceptions) at the time this test was written.
        assert len(_mounted_get_routes()) >= 20

    def test_every_get_route_is_gated_or_explicitly_excepted(self):
        ungated_unexplained = []
        for route in _mounted_get_routes():
            if _is_gated(route):
                continue
            if route.path in _EXCEPTION_ALLOWLIST:
                continue
            ungated_unexplained.append(route.path)
        assert not ungated_unexplained, (
            "GET route(s) with neither a permission dependency nor an allowlist "
            f"entry - a new ungated route (UAC4.2): {ungated_unexplained}"
        )

    def test_gated_routes_match_the_thirteen_named_in_the_plan(self):
        gated_paths = {r.path for r in _mounted_get_routes() if _is_gated(r)}
        assert len(gated_paths) == 13
        assert gated_paths == {
            "/api/v1/user-management/teams/",
            "/api/v1/user-management/teams/{team_id}",
            "/api/v1/user-management/teams/{team_id}/members",
            "/api/v1/user-management/teams/{team_id}/members/{user_id}/market-segments",
            "/api/v1/user-management/access-agents/",
            "/api/v1/user-management/access-agents/contact-access",
            "/api/v1/user-management/access-agents/neighbours",
            "/api/v1/user-management/access-agents/{agent_id}",
            "/api/v1/user-management/access-agents/{agent_id}/teams",
            "/api/v1/user-management/access-agents/{agent_id}/field-access",
            "/api/v1/user-management/access-agents/{agent_id}/contact-access",
            "/api/v1/user-management/contact-access-types/all",
            "/api/v1/user-management/contact-access-types/{code}",
        }

    def test_allowlist_entries_all_carry_an_inline_reason(self):
        # UAC4.3 - short enough to read, and every entry says why.
        assert len(_EXCEPTION_ALLOWLIST) <= 15
        for path, reason in _EXCEPTION_ALLOWLIST.items():
            assert reason and reason.strip(), f"{path} has no reason on record"

    def test_allowlist_paths_are_actually_mounted_and_ungated(self):
        # Guards the allowlist itself from rotting into a list of stale/typo'd
        # paths that would silently widen coverage by never matching anything.
        mounted = {r.path: r for r in _mounted_get_routes()}
        for path in _EXCEPTION_ALLOWLIST:
            assert path in mounted, f"allowlisted path {path!r} is not a mounted GET route"
            assert not _is_gated(mounted[path]), (
                f"allowlisted path {path!r} actually carries a permission dependency - "
                "remove it from the allowlist instead"
            )


# --------------------------------------------------------------- work item 5


def test_contact_access_types_active_catalog_stays_ungated(api):
    """UAC3.3 (REG) - the active-only catalog answers 200 for a caller holding
    ZERO user_management.* permissions, pinning the documented exception so it
    cannot silently rot into a gate."""
    client, allow, _caller = api
    assert allow == set()

    resp = client.get("/api/v1/user-management/contact-access-types/")

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_quick_access_is_self_scoped(db):
    """UAC5.1 - user A's pins are not visible to user B."""
    user_a = User(
        id=unique_code("user-a"),
        email=f"{unique_code('a')}@zzt.test",
        name="ZZT User A",
        status=UserStatus.ACTIVE.value,
    )
    user_b = User(
        id=unique_code("user-b"),
        email=f"{unique_code('b')}@zzt.test",
        name="ZZT User B",
        status=UserStatus.ACTIVE.value,
    )
    db.add_all([user_a, user_b])
    db.flush()
    db.add_all(
        [
            UserQuickAccess(id=str(uuid.uuid4()), user_id=user_a.id, path="/a/pin-1", sort_order=0),
            UserQuickAccess(id=str(uuid.uuid4()), user_id=user_b.id, path="/b/pin-1", sort_order=0),
        ]
    )
    db.flush()

    _install_overrides(db, {"id": user_a.id, "email": user_a.email})
    try:
        client = TestClient(app)
        resp = client.get("/api/v1/user-management/quick-access/")
    finally:
        _clear_overrides()

    assert resp.status_code == 200
    paths = {row["path"] for row in resp.json()}
    assert paths == {"/a/pin-1"}


def test_contacts_companies_denies_non_superadmin(db):
    """UAC5.2 - the in-body `_require_superadmin` check still bites; a caller
    with no role grant at all (so no superadmin/admin role slug) is denied."""
    contact_id = unique_code("contact")
    caller = {"id": str(uuid.uuid4()), "email": "non-superadmin@zzt.test"}

    _install_overrides(db, caller)
    try:
        client = TestClient(app)
        resp = client.get(f"/api/v1/user-management/contacts/{contact_id}/companies")
    finally:
        _clear_overrides()

    assert resp.status_code == 403
    assert "Superadmin" in resp.text
