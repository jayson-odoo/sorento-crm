"""CHAT-INDEX-VIZ BE-3: `GET /system/ai-assistant/prompts/{name}/versions/{version}/architecture`.

Contract: documentation/plans/chatbot/chat-index-viz-20oct-contract.md ("BE-3"). Written before
the route and `app/services/chatbot/prompt_architecture.py` exist: each test fails on a 404
(route not mounted) until the coder adds them. Postgres only; every test seeds its own prompt
version and system setting inside a rolled-back transaction.
"""
from __future__ import annotations

import random
import uuid
from datetime import date

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.main import app
from app.models.ai_prompt import AIPromptVersion
from app.models.inventory import Warehouse
from app.models.user import SystemSetting
from app.services import ai_prompt_registry, chatbot_prompt_vars as pv
from app.services.chatbot.head import closed_lists_index as cli
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.user_service import UserPermissionService
from tests._pg_fixture import pg_session

VIEW = "system.ai_assistant_settings.view"
KEY = "chatbot_semantic_parser"
BASE = "/api/v1/system/ai-assistant/prompts"
LISTS = ("specs", "attachment_types", "certification_types")

_GRANTS: set[str] = set()


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    _GRANTS.clear()
    _GRANTS.add(VIEW)
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in _GRANTS
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    pv.clear_cache()
    ai_prompt_registry.bust_cache()
    yield
    pv.clear_cache()
    ai_prompt_registry.bust_cache()


@pytest.fixture()
def pg_db():
    with pg_session() as db:
        yield db


@pytest.fixture()
def client(pg_db):
    def _override_db():
        yield pg_db

    actor = {"id": str(uuid.uuid4()), "name": "ZZT Architecture Tester"}
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def _mode(db, mode: str) -> None:
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting()
        db.add(row)
    row.chatbot_closed_lists_mode = mode
    db.flush()


def _version(db, template: str, name: str = KEY) -> int:
    number = random.randint(80000, 99998)
    db.add(AIPromptVersion(id=str(uuid.uuid4()), name=name, version=number, type="text", template=template,
                           commit_message="zzt architecture", variables=[]))
    db.flush()
    pv.clear_cache()
    return number


def _get(client, version: int, name: str = KEY):
    return client.get(f"{BASE}/{name}/versions/{version}/architecture")


def _tokens(text: str) -> int:
    return round(len(text) / 4)


# Section text that is long enough for the heading line and a trailing newline to be rounding noise.
BODY_A = "alpha text " * 60
BODY_B = "bravo text " * 120
HEAD = "Opening words before any heading. " * 20
TEMPLATE = (
    f"{HEAD}\n== PRICE TERMINOLOGY ==\n{BODY_A}\n== ACCESS LEVELS ==\n{BODY_B}\n"
    "== TODAY ==\nToday is {{current_date}}. " + "pad " * 80 + "\n"
)
CLOSED_TEMPLATE = (
    f"{HEAD}\n== PRICE TERMINOLOGY ==\n{BODY_A}\n== CLOSED LISTS ==\n"
    "SPECS-BEGIN {{specs}} SPECS-END\nFILES-BEGIN {{attachment_types}} FILES-END\n"
    "CERTS-BEGIN {{certification_types}} CERTS-END\n"
)


# --------------------------------------------------------------------------- #
# Shape and sections
# --------------------------------------------------------------------------- #


def test_shape_of_the_response(client, pg_db):
    _mode(pg_db, "index")
    number = _version(pg_db, CLOSED_TEMPLATE)
    res = _get(client, number)
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) >= {"version", "mode", "uses_closed_lists", "total_tokens", "sections", "lists"}, body
    assert body["version"] == number
    assert body["mode"] == "index"
    assert body["uses_closed_lists"] is True
    for section in body["sections"]:
        assert set(section) == {"title", "tokens", "kind"}, section
    assert body["total_tokens"] == sum(s["tokens"] for s in body["sections"])
    assert [item["key"] for item in body["lists"]] == [*LISTS, "warehouses"]
    for item in body["lists"]:
        assert {"key", "name", "source", "href", "entries", "sent_each_message_tokens", "full_list_tokens"} <= set(item)


def test_sections_split_at_headings_with_an_opening_section(client, pg_db):
    _mode(pg_db, "block")
    number = _version(pg_db, TEMPLATE)
    body = _get(client, number).json()
    titles = [s["title"] for s in body["sections"]]
    assert titles == ["Opening", "PRICE TERMINOLOGY", "ACCESS LEVELS", "TODAY"], titles
    by_title = {s["title"]: s for s in body["sections"]}
    # tokens = round(len(rendered) / 4); the heading line and newlines are rounding noise here.
    assert by_title["Opening"]["tokens"] == pytest.approx(_tokens(HEAD), abs=4)
    assert by_title["PRICE TERMINOLOGY"]["tokens"] == pytest.approx(_tokens(BODY_A), abs=6)
    assert by_title["ACCESS LEVELS"]["tokens"] == pytest.approx(_tokens(BODY_B), abs=6)


def test_kinds(client, pg_db):
    _mode(pg_db, "block")
    template = TEMPLATE + "== CLOSED LISTS ==\n{{specs}}\n"
    body = _get(client, _version(pg_db, template)).json()
    kinds = {s["title"]: s["kind"] for s in body["sections"]}
    assert kinds["PRICE TERMINOLOGY"] == "text"
    assert kinds["TODAY"] == "filled_from_data"
    assert kinds["CLOSED LISTS"] == "closed_lists"


def test_a_closed_lists_variable_in_any_section_makes_it_closed_lists_kind(client, pg_db):
    _mode(pg_db, "block")
    template = "== ONE ==\n{{attachment_types}}\n== TWO ==\n{{certification_types}}\n== THREE ==\nplain\n"
    kinds = {s["title"]: s["kind"] for s in _get(client, _version(pg_db, template)).json()["sections"]}
    assert kinds == {"ONE": "closed_lists", "TWO": "closed_lists", "THREE": "text"}


def test_opening_is_omitted_when_blank(client, pg_db):
    _mode(pg_db, "block")
    body = _get(client, _version(pg_db, "\n\n== ONLY ==\nbody text here\n")).json()
    assert [s["title"] for s in body["sections"]] == ["ONLY"]


def test_current_date_is_substituted_before_counting(client, pg_db):
    _mode(pg_db, "block")
    padded = "x" * 400
    raw_template = "== DATED ==\n{{current_date}}" + padded + "\n"
    body = _get(client, _version(pg_db, raw_template)).json()
    [section] = body["sections"]
    rendered_len = len(date.today().strftime("%Y")) + len(padded)  # the date text is longer than the token
    assert section["kind"] == "filled_from_data"
    assert section["tokens"] >= _tokens(padded) - 2, section
    assert section["tokens"] * 4 >= rendered_len


# --------------------------------------------------------------------------- #
# Index vs block
# --------------------------------------------------------------------------- #


def test_index_mode_lists_report_the_blank_line_as_what_is_sent(client, pg_db):
    _mode(pg_db, "index")
    body = _get(client, _version(pg_db, CLOSED_TEMPLATE)).json()
    assert body["mode"] == "index" and body["uses_closed_lists"] is True
    lists = {item["key"]: item for item in body["lists"]}
    for key in LISTS:
        item = lists[key]
        variable = pv.VARIABLES[key]
        assert item["name"] == variable.label
        assert item["source"] == variable.source
        assert item["href"] == variable.href
        assert item["sent_each_message_tokens"] == _tokens(cli.SYSTEM_BLANKS[key]), item
        assert item["full_list_tokens"] == _tokens(pv.render_value(pg_db, key)), item
        assert not item.get("checked_only")


def test_index_mode_closed_lists_section_counts_the_blanks_not_the_full_lists(client, pg_db):
    _mode(pg_db, "index")
    body = _get(client, _version(pg_db, "== CLOSED LISTS ==\n{{specs}}\n{{attachment_types}}\n{{certification_types}}\n")).json()
    [section] = body["sections"]
    blanks = sum(len(cli.SYSTEM_BLANKS[k]) for k in LISTS)
    assert section["kind"] == "closed_lists"
    assert section["tokens"] == pytest.approx(_tokens("x" * blanks), abs=8)


def test_block_mode_sends_the_full_lists(client, pg_db):
    _mode(pg_db, "block")
    body = _get(client, _version(pg_db, CLOSED_TEMPLATE)).json()
    assert body["mode"] == "block" and body["uses_closed_lists"] is True
    for item in body["lists"]:
        if item["key"] in LISTS:
            assert item["sent_each_message_tokens"] == item["full_list_tokens"], item


def test_block_mode_closed_lists_section_counts_the_full_lists(client, pg_db):
    _mode(pg_db, "block")
    full = sum(len(pv.render_value(pg_db, k)) for k in LISTS)
    body = _get(client, _version(pg_db, "== CLOSED LISTS ==\n{{specs}}\n{{attachment_types}}\n{{certification_types}}\n")).json()
    [section] = body["sections"]
    assert section["tokens"] == pytest.approx(_tokens("x" * full), abs=8)


def test_a_template_without_the_closed_lists_section_sends_the_lists_whole_even_in_index_mode(client, pg_db):
    _mode(pg_db, "index")
    template = "== PRICE ==\nplain\n== SPECS ==\n{{specs}}\n"
    body = _get(client, _version(pg_db, template)).json()
    assert body["mode"] == "index"
    assert body["uses_closed_lists"] is False
    for item in body["lists"]:
        if item["key"] in LISTS:
            assert item["sent_each_message_tokens"] == item["full_list_tokens"] == _tokens(pv.render_value(pg_db, item["key"]))
    [_, specs] = body["sections"]
    assert specs["tokens"] == pytest.approx(_tokens(pv.render_value(pg_db, "specs")), abs=8)


def test_warehouses_are_checked_only(client, pg_db):
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    # A real request scopes its session to the caller's companies (`apply_company_scope`);
    # warehouses is a scoped table, so an unscoped session sees no rows at all (fail closed).
    scope = frozenset({DEFAULT_COMPANY_ID})

    def _scoped(_db=Depends(get_db)):
        set_company_scope(_db, scope)

    app.dependency_overrides[apply_company_scope] = _scoped
    set_company_scope(pg_db, scope)
    _mode(pg_db, "index")
    for code in ("ZZARCH-1", "ZZARCH-2"):
        pg_db.add(Warehouse(id=str(uuid.uuid4()), warehouse_code=code, warehouse_name=f"ZZ {code}", company_id=DEFAULT_COMPANY_ID))
    pg_db.flush()
    body = _get(client, _version(pg_db, CLOSED_TEMPLATE)).json()
    [wh] = [item for item in body["lists"] if item["key"] == "warehouses"]
    assert wh["name"] == "Warehouses" and wh["source"] == "Warehouses"
    assert wh["href"] == "/inventory-management/warehouses"
    assert wh["checked_only"] is True
    assert wh["sent_each_message_tokens"] == 0 and wh["full_list_tokens"] == 0
    assert wh["entries"] == pg_db.query(Warehouse).count() and wh["entries"] >= 2


# --------------------------------------------------------------------------- #
# Errors and permission
# --------------------------------------------------------------------------- #


def test_unknown_prompt_key_is_404(client, pg_db):
    assert _get(client, 1, name="zzt_not_a_key").status_code == 404


def test_unknown_version_is_404(client, pg_db):
    res = _get(client, 7_000_000)
    assert res.status_code == 404, res.text


def test_a_key_other_than_the_parser_is_404_with_the_reason(client, pg_db):
    number = _version(pg_db, "plain template", name="router")
    res = _get(client, number, name="router")
    assert res.status_code == 404, res.text
    assert "No architecture view for this prompt" in res.text


def test_denied_without_the_view_permission(client, pg_db):
    number = _version(pg_db, CLOSED_TEMPLATE)
    _GRANTS.clear()
    assert _get(client, number).status_code == 403
