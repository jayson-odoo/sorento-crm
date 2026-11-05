"""AI-PROMPTS-STD-VIEWS: the prompts list on the standard DataGrid contract.

``GET /api/v1/system/ai-assistant/prompts/list`` pages, sorts (every column, server-side),
searches and multi-select filters the prompt keys, returning ``{data, empty, pagination}``
like every other list GET. Rows carry ``id = name`` so the detail page's pager can walk them.
"""
from __future__ import annotations

import pytest

from app.services.ai_prompt_registry import PROMPT_KEYS
from app.services.ai_prompt_service import AIPromptService

# Fixtures (db -> seeded -> api) are the prompt registry suite's own.
from tests.test_ai_prompt_registry import api, db, seeded  # noqa: F401

URL = "/api/v1/system/ai-assistant/prompts/list"
VIEW = "system.ai_assistant_settings.view"

SORTABLE = [
    "name",
    "role",
    "status",
    "model",
    "production_version",
    "latest_version",
    "updated_at",
    "updated_by_name",
]


def _get(client, **params):
    res = client.get(URL, params=params)
    assert res.status_code == 200, res.text
    return res.json()


def test_list_pages_with_the_standard_envelope(api):
    client, allow = api
    allow.add(VIEW)
    body = _get(client, page=1, limit=5)
    assert len(body["data"]) == 5
    assert body["pagination"]["total"] == len(PROMPT_KEYS)
    assert body["pagination"]["page"] == 1
    assert body["empty"] is False
    for row in body["data"]:
        assert row["id"] == row["name"]

    second = _get(client, page=2, limit=5)
    assert {r["name"] for r in second["data"]}.isdisjoint({r["name"] for r in body["data"]})


def test_list_denies_without_view_permission(api):
    client, _allow = api
    assert client.get(URL).status_code == 403


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sort_by_name(api, direction):
    client, allow = api
    allow.add(VIEW)
    names = [r["name"] for r in _get(client, limit=500, sort="name", dir=direction)["data"]]
    assert names == sorted(PROMPT_KEYS.keys(), reverse=direction == "desc")


@pytest.mark.parametrize("field", SORTABLE)
def test_every_column_sorts_server_side(api, field):
    client, allow = api
    allow.add(VIEW)
    AIPromptService(api_session(api)).set_agent_model(
        "spec_understanding", label="production", provider="openai", model="gpt-5.4-mini"
    )
    asc = _get(client, limit=500, sort=field, dir="asc")["data"]
    desc = _get(client, limit=500, sort=field, dir="desc")["data"]
    assert len(asc) == len(PROMPT_KEYS)

    def key(row):
        if field == "status":
            return 0 if row["active"] else 1
        return row[field]

    present_asc = [key(r) for r in asc if key(r) is not None]
    present_desc = [key(r) for r in desc if key(r) is not None]
    assert present_asc == sorted(present_asc)
    assert present_desc == sorted(present_desc, reverse=True)
    # Blanks sit at the end in both directions.
    for rows in (asc, desc):
        keys = [key(r) for r in rows]
        if None in keys:
            first_blank = keys.index(None)
            assert all(k is None for k in keys[first_blank:])


def test_status_filter_is_multi_select(api):
    client, allow = api
    allow.add(VIEW)
    dormant = _get(client, limit=500, status="dormant")["data"]
    assert dormant and all(not r["active"] for r in dormant)
    assert {r["name"] for r in dormant} == {n for n, s in PROMPT_KEYS.items() if not s.active}

    active = _get(client, limit=500, status="active")["data"]
    assert active and all(r["active"] for r in active)

    both = _get(client, limit=500, status="active,dormant")
    assert both["pagination"]["total"] == len(PROMPT_KEYS)


def test_model_filter_is_multi_select_with_a_default_bucket(api):
    client, allow = api
    allow.add(VIEW)
    svc = AIPromptService(api_session(api))
    svc.set_agent_model("spec_understanding", label="production", provider="openai", model="gpt-5.4-mini")
    svc.set_agent_model("semantic_parser", label="production", provider="openai", model="gpt-5.4")

    one = _get(client, limit=500, model="gpt-5.4-mini")["data"]
    assert [r["name"] for r in one] == ["spec_understanding"]

    two = _get(client, limit=500, model=["gpt-5.4-mini", "gpt-5.4"])["data"]
    assert {r["name"] for r in two} == {"spec_understanding", "semantic_parser"}

    default = _get(client, limit=500, model="default")["data"]
    assert default and all(r["model"] is None for r in default)
    assert len(default) == len(PROMPT_KEYS) - 2


def test_model_options_name_every_model_in_use(api):
    client, allow = api
    allow.add(VIEW)
    AIPromptService(api_session(api)).set_agent_model(
        "spec_understanding", label="production", provider="openai", model="gpt-5.4-mini"
    )
    body = _get(client, limit=5)
    assert body["model_options"] == ["gpt-5.4-mini"]


def test_search_matches_name_and_role_case_insensitively(api):
    client, allow = api
    allow.add(VIEW)
    by_name = _get(client, limit=500, query="SEMANTIC_parser")["data"]
    assert "semantic_parser" in {r["name"] for r in by_name}
    assert all("semantic_parser" in r["name"].lower() or "semantic_parser" in r["role"].lower() for r in by_name)

    role_word = PROMPT_KEYS["judge"].role.split()[0]
    by_role = _get(client, limit=500, query=role_word.upper())["data"]
    assert "judge" in {r["name"] for r in by_role}


def test_filters_and_search_count_the_narrowed_set(api):
    client, allow = api
    allow.add(VIEW)
    body = _get(client, limit=2, status="dormant")
    assert body["pagination"]["total"] == sum(1 for s in PROMPT_KEYS.values() if not s.active)
    assert len(body["data"]) == min(2, body["pagination"]["total"])


def test_an_unknown_sort_is_refused(api):
    client, allow = api
    allow.add(VIEW)
    assert client.get(URL, params={"sort": "nope"}).status_code == 422


def api_session(api_fixture):
    """The seeded session the api fixture's TestClient reads, via the dependency override."""
    import app.dependencies as deps
    from app.main import app

    return next(app.dependency_overrides[deps.get_db]())
