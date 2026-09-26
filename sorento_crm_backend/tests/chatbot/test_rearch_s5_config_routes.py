"""S5 backend - domain/entity-kind CRUD routes, contact chatbot profile PUT, settings
GET/PUT for chatbot_tier_order/chatbot_memory, and the new manage permission's sweep
(AC-1561, PLAN-chatbot-turn-rearch.md "Phase 1 (frontend, mocked)": `GET/POST/PUT/
DELETE /api/v1/system/chatbot/domains`, `/entity-kinds`; `PUT /user-management/
contacts/{id}/chatbot`; settings gain `chatbot_tier_order`, `chatbot_memory`).

None of these routes exist yet - measured: no `domains` or `entity-kinds` path under
`app/api/v1/system/chatbot.py`, no `/chatbot` sub-route under
`app/api/v1/user_management/contacts.py`. Every CRUD test is RED on a 404 today - the
right reason, same posture `test_turns_admin_api.py` itself was written under
(see that file's own docstring).

Runs against the REAL migrated database (`pg_session`): `chatbot_domains` /
`chatbot_entity_kinds` are migration-seeded tables (S0), and the permission sweep test
reads real `user_roles` / `user_role_permissions` rows.

**Ambiguities flagged to the captain, not resolved here**:

1. The list response envelope. This repo has two established shapes for a paginated
   list: `ListResponse[T]` (`{data: [...], pagination: {total, page, limit}}`, e.g.
   `app/api/v1/order_management/order_statuses.py`) and a cursor shape
   (`{items: [...], next_cursor}`, e.g. `chatbot.turns`). This file assumes the
   `ListResponse` shape (domains/entity-kinds are small reference tables, not an
   ever-growing log) and reads `data`/`pagination.total`, falling back to `items` if
   present - the STRUCTURAL count assertions do not depend on which key wins.
2. The PUT `/chatbot` settings category. No existing route file has a `/chatbot`
   settings sub-route; this file PUTs `chatbot_tier_order` / `chatbot_memory` at
   `PUT /api/v1/user-management/settings/general`, the endpoint
   `SystemSettingUpdate` (which already carries `chatbot_business_lane_enabled` /
   `chatbot_ordering_enabled`) is wired to today - if the coder adds a dedicated
   `/chatbot` category instead, this file's PUT target needs a one-line change.
3. `chatbot_memory`'s four named sub-keys (`recall_default`, `episode_retention_days`,
   `profile_fields`, `focus_reset_events`) are asserted present on round-trip; their
   validation rules (if any) are not specified anywhere and are not tested here.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.main import app
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.access import McpTool
from app.services.user_service import UserPermissionService

from tests._pg_fixture import pg_session, unique_code

VIEW = "system.chat_history.view"
MANAGE = "system.chatbot_config.manage"
SETTINGS_VIEW = "user_management.settings.view"
SETTINGS_EDIT = "user_management.settings.edit"
# Coordinator fixture item, 16 Sep 2026: `PUT /contacts/{id}/chatbot` now requires
# this grant too (coder's just-merged permission gate on that route) - a fixture
# gap, not a route bug.
CONTACT_EDIT = "user_management.contacts.edit"
DOMAINS_BASE = "/api/v1/system/chatbot/domains"
ENTITY_KINDS_BASE = "/api/v1/system/chatbot/entity-kinds"
CONTACT_CHATBOT_BASE = "/api/v1/user-management/contacts"
SETTINGS_GET = "/api/v1/user-management/settings/"
SETTINGS_PUT_GENERAL = "/api/v1/user-management/settings/general"

NARROWING_VALUES = (
    "must_narrow_one",
    "narrow_to_code",
    "narrow_by_type",
    "narrow_by_tier",
    "optional_filter",
    "list_all",
    "not_applicable",
)

_GRANTS: set[str] = set()
_ACTOR: dict = {"id": None, "name": "ZZT Config Routes Tester"}


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    _GRANTS.clear()
    _GRANTS.add(VIEW)
    _GRANTS.add(MANAGE)
    _GRANTS.add(SETTINGS_VIEW)
    _GRANTS.add(SETTINGS_EDIT)
    _GRANTS.add(CONTACT_EDIT)
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in _GRANTS,
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield
    _GRANTS.clear()


@pytest.fixture()
def pg_db():
    with pg_session() as db:
        yield db


@pytest.fixture()
def client(pg_db):
    def _override_db():
        try:
            yield pg_db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    _ACTOR["id"] = str(uuid.uuid4())
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def real_tool_name(pg_db) -> str:
    row = pg_db.execute(McpTool.__table__.select().limit(1)).first()
    if row is not None:
        return row.tool_name
    from datetime import datetime, timezone

    name = unique_code("tool")
    pg_db.add(
        McpTool(
            tool_name=name,
            description="ZZT scratch tool",
            http_path="/api/v1/zzt/scratch",
            http_method="GET",
            is_active=True,
            last_seen_at=datetime.now(timezone.utc),
        )
    )
    pg_db.flush()
    return name


def _domain_body(name: str, *, tool: str, team: str = "purchasing", narrowing: str = "list_all") -> dict:
    return {
        "name": name,
        "label": f"ZZT {name}",
        "intents": ["zzt_check"],
        "tools": [tool],
        "primary_tool": tool,
        "escalation_team_code": team,
        "switch_words": ["zzt"],
        "narrowing": {"product": narrowing},
        "takes_date_filter": False,
        "reveal_key": None,
        "supported": True,
        "ladder": [],
        "sort_order": 999,
    }


def _kind_body(kind: str, *, default_narrowing: str = "optional_filter") -> dict:
    return {
        "kind": kind,
        "resolver_source": "zzt_source",
        "did_you_mean": True,
        "default_narrowing": default_narrowing,
        "family_grouping": None,
        "base_property_words": {},
    }


class TestDomainsCrudHappyPath:
    def test_list_accepts_datagrid_params(self, client) -> None:
        resp = client.get(DOMAINS_BASE, params={"page": 1, "limit": 20, "sort": "name", "dir": "asc", "query": ""})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "data" in body or "items" in body, body

    def test_post_then_get_one_then_put_then_delete(self, client, real_tool_name) -> None:
        name = unique_code("domain")
        create_resp = client.post(DOMAINS_BASE, json=_domain_body(name, tool=real_tool_name))
        assert create_resp.status_code in (200, 201), create_resp.text
        created = create_resp.json()
        domain_id = created.get("id") or created.get("name")

        get_resp = client.get(f"{DOMAINS_BASE}/{domain_id}")
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json().get("name") == name

        put_body = _domain_body(name, tool=real_tool_name)
        put_body["label"] = "ZZT updated label"
        put_resp = client.put(f"{DOMAINS_BASE}/{domain_id}", json=put_body)
        assert put_resp.status_code == 200, put_resp.text
        assert put_resp.json().get("label") == "ZZT updated label"

        delete_resp = client.delete(f"{DOMAINS_BASE}/{domain_id}")
        assert delete_resp.status_code in (200, 204), delete_resp.text

        after = client.get(f"{DOMAINS_BASE}/{domain_id}")
        assert after.status_code == 404


class TestEntityKindsCrudHappyPath:
    def test_list_accepts_datagrid_params(self, client) -> None:
        resp = client.get(ENTITY_KINDS_BASE, params={"page": 1, "limit": 20, "sort": "kind", "dir": "asc"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "data" in body or "items" in body, body

    def test_post_then_get_one_then_put_then_delete(self, client) -> None:
        kind = unique_code("kind")
        create_resp = client.post(ENTITY_KINDS_BASE, json=_kind_body(kind))
        assert create_resp.status_code in (200, 201), create_resp.text
        created = create_resp.json()
        kind_id = created.get("id") or created.get("kind")

        get_resp = client.get(f"{ENTITY_KINDS_BASE}/{kind_id}")
        assert get_resp.status_code == 200, get_resp.text

        put_body = _kind_body(kind)
        put_body["resolver_source"] = "zzt_updated_source"
        put_resp = client.put(f"{ENTITY_KINDS_BASE}/{kind_id}", json=put_body)
        assert put_resp.status_code == 200, put_resp.text
        assert put_resp.json().get("resolver_source") == "zzt_updated_source"

        delete_resp = client.delete(f"{ENTITY_KINDS_BASE}/{kind_id}")
        assert delete_resp.status_code in (200, 204), delete_resp.text


class TestAuthDenial:
    """GET needs `system.chat_history.view`; POST/PUT/DELETE need `system.
    chatbot_config.manage`."""

    def test_get_with_view_only_is_200(self, client) -> None:
        _GRANTS.discard(MANAGE)
        resp = client.get(DOMAINS_BASE)
        assert resp.status_code == 200, resp.text

    def test_post_without_manage_is_403(self, client, real_tool_name) -> None:
        _GRANTS.discard(MANAGE)
        resp = client.post(DOMAINS_BASE, json=_domain_body(unique_code("domain"), tool=real_tool_name))
        assert resp.status_code == 403, resp.text
        assert MANAGE in resp.text

    def test_put_without_manage_is_403(self, client, real_tool_name) -> None:
        _GRANTS.discard(MANAGE)
        resp = client.put(f"{DOMAINS_BASE}/inventory", json=_domain_body("inventory", tool=real_tool_name))
        assert resp.status_code == 403, resp.text

    def test_delete_without_manage_is_403(self, client) -> None:
        _GRANTS.discard(MANAGE)
        resp = client.delete(f"{DOMAINS_BASE}/inventory")
        assert resp.status_code == 403, resp.text

    def test_entity_kinds_post_without_manage_is_403(self, client) -> None:
        _GRANTS.discard(MANAGE)
        resp = client.post(ENTITY_KINDS_BASE, json=_kind_body(unique_code("kind")))
        assert resp.status_code == 403, resp.text


class TestValidation:
    def test_tool_not_in_mcp_tools_is_422(self, client) -> None:
        resp = client.post(
            DOMAINS_BASE, json=_domain_body(unique_code("domain"), tool="zzt-not-a-real-tool-name")
        )
        assert resp.status_code == 422, resp.text

    def test_escalation_team_not_in_suggested_teams_is_422(self, client, real_tool_name) -> None:
        resp = client.post(
            DOMAINS_BASE,
            json=_domain_body(unique_code("domain"), tool=real_tool_name, team="zzt-not-a-real-team"),
        )
        assert resp.status_code == 422, resp.text

    def test_narrowing_policy_outside_seven_values_is_422(self, client, real_tool_name) -> None:
        resp = client.post(
            DOMAINS_BASE,
            json=_domain_body(unique_code("domain"), tool=real_tool_name, narrowing="zzt-not-a-real-policy"),
        )
        assert resp.status_code == 422, resp.text

    def test_entity_kind_default_narrowing_outside_seven_values_is_422(self, client) -> None:
        resp = client.post(
            ENTITY_KINDS_BASE, json=_kind_body(unique_code("kind"), default_narrowing="zzt-bad-policy")
        )
        assert resp.status_code == 422, resp.text

    @pytest.mark.parametrize("policy", NARROWING_VALUES)
    def test_each_of_the_seven_narrowing_values_is_accepted(self, client, real_tool_name, policy) -> None:
        resp = client.post(
            DOMAINS_BASE,
            json=_domain_body(unique_code("domain"), tool=real_tool_name, narrowing=policy),
        )
        assert resp.status_code in (200, 201), (policy, resp.text)

    def test_duplicate_name_is_409_or_422(self, client, real_tool_name) -> None:
        name = unique_code("domain")
        first = client.post(DOMAINS_BASE, json=_domain_body(name, tool=real_tool_name))
        assert first.status_code in (200, 201), first.text

        second = client.post(DOMAINS_BASE, json=_domain_body(name, tool=real_tool_name))
        assert second.status_code in (409, 422), second.text


class TestContactChatbotProfilePut:
    def _seed_contact(self, pg_db) -> str:
        from sqlalchemy import text

        cid = unique_code("contact")
        pg_db.execute(
            text(
                "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
                "VALUES (gen_random_uuid()::text, :cid, :phone, CAST('{}' AS jsonb)) RETURNING id"
            ),
            {"cid": cid, "phone": f"+60{uuid.uuid4().int % 10**9}"},
        )
        pg_db.flush()
        row = pg_db.execute(
            text("SELECT id FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": cid}
        ).first()
        return row.id

    def test_put_chatbot_profile_and_memory_level(self, client, pg_db) -> None:
        """Superseded by chatbot memory lane A (contract section 5): the PUT body
        drops `chatbot_recall_enabled` and gains `chatbot_memory_level` - updated
        rather than dropped, so this route's happy path stays covered."""
        contact_id = self._seed_contact(pg_db)

        resp = client.put(
            f"{CONTACT_CHATBOT_BASE}/{contact_id}/chatbot",
            json={
                "chatbot_profile": {"tier": "dealer", "default_ledgers": []},
                "chatbot_memory_level": "full",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("chatbot_profile", {}).get("tier") == "dealer", body
        assert body.get("chatbot_memory_level") == "full", body


class TestSettingsCarryTierOrderAndMemory:
    @pytest.fixture(autouse=True)
    def _ensure_settings_row(self, pg_db):
        """The singleton `system_settings` row - this worktree's private DB has none
        (`SELECT count(*) FROM system_settings` measured 0), unlike the shared
        prod-copy dev DB every other settings test in this repo implicitly relies on.
        Get-or-create, same idiom as `tests/chatbot/conftest.py::set_chatbot_switches`.
        """
        from app.models.user import SystemSetting

        row = pg_db.query(SystemSetting).first()
        if row is None:
            row = SystemSetting()
            pg_db.add(row)
            pg_db.flush()
        return row

    def test_get_settings_includes_both_fields(self, client) -> None:
        resp = client.get(SETTINGS_GET)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        settings = body.get("settings") or body
        assert "chatbot_tier_order" in settings, settings.keys()
        assert "chatbot_memory" in settings, settings.keys()

    def test_put_round_trips_tier_order_and_memory_sub_keys(self, client) -> None:
        """`chatbot_memory`'s sub-keys are superseded by chatbot memory lane A
        (contract section 2/5): `enabled` + `default_level` replace the four dead
        keys this test used to round-trip. Updated rather than dropped, so the
        settings PUT's tier-order + memory round trip stays covered."""
        payload = {
            "chatbot_tier_order": ["dealer", "office", "end_user"],
            "chatbot_memory": {
                "enabled": True,
                "default_level": "past",
            },
        }
        resp = client.put(SETTINGS_PUT_GENERAL, json=payload)
        assert resp.status_code == 200, resp.text

        after = client.get(SETTINGS_GET)
        settings = after.json().get("settings") or after.json()
        assert settings.get("chatbot_tier_order") == payload["chatbot_tier_order"], settings
        memory = settings.get("chatbot_memory") or {}
        for key in payload["chatbot_memory"]:
            assert key in memory, (key, memory)


class TestPermissionRegistrationAndSweep:
    def test_chatbot_config_manage_present_in_registry(self) -> None:
        from app.rbac.permission_registry import PERMISSION_REGISTRY

        slugs = {p["slug"] for p in PERMISSION_REGISTRY}
        assert MANAGE in slugs, (
            f"{MANAGE!r} must be declared in app/rbac/permission_registry.py"
        )

    def test_sweep_grants_manage_to_every_role_holding_chat_history_view(self, pg_db) -> None:
        from sqlalchemy import text

        view_roles = {
            row[0]
            for row in pg_db.execute(
                text(
                    "SELECT r.id FROM user_roles r "
                    "JOIN user_role_permissions rp ON rp.role_id = r.id "
                    "JOIN user_permissions p ON p.id = rp.permission_id "
                    "WHERE p.slug = :slug"
                ),
                {"slug": VIEW},
            )
        }
        assert view_roles, f"no role holds {VIEW!r} today - cannot assert the sweep"

        manage_roles = {
            row[0]
            for row in pg_db.execute(
                text(
                    "SELECT r.id FROM user_roles r "
                    "JOIN user_role_permissions rp ON rp.role_id = r.id "
                    "JOIN user_permissions p ON p.id = rp.permission_id "
                    "WHERE p.slug = :slug"
                ),
                {"slug": MANAGE},
            )
        }

        missing = view_roles - manage_roles
        assert not missing, (
            f"every role holding {VIEW!r} must also hold {MANAGE!r} via the "
            f"provisioning sweep - {len(missing)} role(s) do not: {missing!r}"
        )

    def test_manage_is_held_only_by_superadmin_and_admin_after_s6c(self, pg_db) -> None:
        """`chatbot_rearch_s6c` (security review fix, AC-1561) took `MANAGE` back off
        every role but the two administrator ones - `chatbot_rearch_s5`'s own original
        sweep had derived the grant from `VIEW`, which on the production copy also
        includes `guest`, `integration_foundryx_esb` and `integration_n8n` (the
        migration's own docstring). The sibling test above only proves "nobody holding
        VIEW lost MANAGE"; it does not prove the narrower, corrected invariant s6c
        exists to enforce - a role holding MANAGE that is neither admin role would pass
        that test silently. Guard red until this DB's role seed genuinely narrows it."""
        from sqlalchemy import text

        manage_role_slugs = {
            row[0]
            for row in pg_db.execute(
                text(
                    "SELECT r.slug FROM user_roles r "
                    "JOIN user_role_permissions rp ON rp.role_id = r.id "
                    "JOIN user_permissions p ON p.id = rp.permission_id "
                    "WHERE p.slug = :slug"
                ),
                {"slug": MANAGE},
            )
        }
        extra = manage_role_slugs - {"superadmin", "admin"}
        assert not extra, (
            f"{MANAGE!r} must be held only by superadmin/admin after chatbot_rearch_s6c "
            f"- also held by: {extra!r}"
        )


class TestContactChatbotProfilePutDenial:
    """`PUT /contacts/{id}/chatbot` needs `user_management.contacts.edit` - the route's
    own added gate (coordinator fixture item, 16 Sep 2026, same session this file's own
    `CONTACT_EDIT` constant documents). `TestContactChatbotProfilePut.test_put_chatbot_
    profile_and_recall_toggle` only proves the grant WORKS; nothing in this file proved
    its ABSENCE is refused, so a coder who wired the dependency backwards (or dropped
    it) would pass every existing test in this file."""

    def _seed_contact(self, pg_db) -> str:
        from sqlalchemy import text

        cid = unique_code("contact")
        pg_db.execute(
            text(
                "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
                "VALUES (gen_random_uuid()::text, :cid, :phone, CAST('{}' AS jsonb))"
            ),
            {"cid": cid, "phone": f"+60{uuid.uuid4().int % 10**9}"},
        )
        pg_db.flush()
        row = pg_db.execute(
            text("SELECT id FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": cid}
        ).first()
        return row.id

    def test_put_without_contacts_edit_is_403(self, client, pg_db) -> None:
        contact_id = self._seed_contact(pg_db)
        _GRANTS.discard(CONTACT_EDIT)

        resp = client.put(
            f"{CONTACT_CHATBOT_BASE}/{contact_id}/chatbot",
            json={
                "chatbot_profile": {"tier": "dealer", "language": "en", "default_ledgers": []},
                "chatbot_recall_enabled": True,
            },
        )
        assert resp.status_code == 403, resp.text


class TestValidateDomainContentGuards:
    """`_clean_text` (`app/api/v1/system/chatbot_config.py`): control characters are
    STRIPPED (never rejected - an operator pasting from a spreadsheet meant the
    letters), the two policy-block markers are REJECTED (422 - no legitimate reason for
    either to appear in a domain field), and an over-long field is REJECTED (422, > 64
    chars on `label`/`name`, the default `_TEXT_MAX`)."""

    def test_control_characters_are_stripped_not_rejected(self, client, real_tool_name) -> None:
        name = unique_code("domain")
        body = _domain_body(name, tool=real_tool_name)
        body["label"] = "ZZT\x00Label\x07With\x1fControl\x0cChars"
        resp = client.post(DOMAINS_BASE, json=body)
        assert resp.status_code in (200, 201), resp.text
        assert resp.json().get("label") == "ZZTLabelWithControlChars", resp.json()

    def test_a_policy_block_marker_in_a_field_is_422(self, client, real_tool_name) -> None:
        from app.services.chatbot_parser_prompt import BLOCKS_BEGIN

        body = _domain_body(unique_code("domain"), tool=real_tool_name)
        body["label"] = f"ZZT {BLOCKS_BEGIN} escape"
        resp = client.post(DOMAINS_BASE, json=body)
        assert resp.status_code == 422, resp.text

    def test_a_field_over_the_length_ceiling_is_422(self, client, real_tool_name) -> None:
        # `label` gets its own 128-char ceiling (`_validate_domain`'s own
        # `max_chars=128` override); `name` stays on the default `_TEXT_MAX` (64).
        body = _domain_body(unique_code("domain"), tool=real_tool_name)
        body["name"] = "z" * 65
        resp = client.post(DOMAINS_BASE, json=body)
        assert resp.status_code == 422, resp.text

    def test_the_label_field_has_its_own_wider_ceiling(self, client, real_tool_name) -> None:
        body = _domain_body(unique_code("domain"), tool=real_tool_name)
        body["label"] = "Z" * 129
        resp = client.post(DOMAINS_BASE, json=body)
        assert resp.status_code == 422, resp.text
