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


def _size(chars: int) -> int:
    return round(chars / 4)


CLOSED_TEMPLATE = (
    "Opening words before any heading. " * 20 + "\n== PRICE TERMINOLOGY ==\n" + "alpha text " * 60 + "\n== CLOSED LISTS ==\n"
    "SPECS-BEGIN {{specs}} SPECS-END\nFILES-BEGIN {{attachment_types}} FILES-END\n"
    "CERTS-BEGIN {{certification_types}} CERTS-END\n"
)
EXAMPLES = '  - "check stock x" -> true\n  - "price of y" -> false\n'
RULES_A = "Read the message and answer in strict JSON. " * 30
RULES_B = "A price word means the sell price unless the message says cost. " * 25
REALISTIC = (
    "You read one customer message.\n"
    f"== PRICE TERMINOLOGY ==\n{RULES_A}\n"
    "== TODAY ==\nToday is {{current_date}}.\n"
    "== BRANDS ==\nKnown brands: {{brands}}\n"
    f"== EXAMPLES ==\n{EXAMPLES}"
    f"== SELF_REFERENCE ==\n{RULES_B}\nSpec words: {{{{specs}}}}\n"
    "== CLOSED LISTS ==\nFiles: {{attachment_types}}\nCertificates: {{certification_types}}\n"
)
GROUPS = ["Rules", "Examples", "Product lists", "Lists from other settings"]
HEADINGS = ("PRICE TERMINOLOGY", "SELF_REFERENCE", "CLOSED LISTS", "EXAMPLES", "TODAY", "BRANDS")


def _groups(body: dict) -> dict[str, dict]:
    return {g["name"]: g for g in body["groups"]}


# --------------------------------------------------------------------------- #
# Shape and groups
# --------------------------------------------------------------------------- #


def test_shape_of_the_response(client, pg_db):
    _mode(pg_db, "index")
    number = _version(pg_db, CLOSED_TEMPLATE)
    res = _get(client, number)
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) >= {"version", "mode", "uses_closed_lists", "total_size", "groups", "lists"}, body
    assert "sections" not in body and "total_tokens" not in body
    assert body["version"] == number
    assert body["mode"] == "index"
    assert body["uses_closed_lists"] is True
    for group in body["groups"]:
        assert set(group) == {"name", "size", "share"}, group
        assert group["size"] > 0 and 0 < group["share"] <= 1
    assert body["total_size"] == sum(g["size"] for g in body["groups"])
    assert [item["key"] for item in body["lists"]] == [*LISTS, "warehouses"]
    for item in body["lists"]:
        assert {"key", "name", "source", "href", "how", "entries", "sent_each_message_size", "full_list_size"} <= set(item)
        assert not ({"sent_each_message_tokens", "full_list_tokens"} & set(item))


def test_groups_are_at_most_the_four_in_order_and_zero_size_ones_are_left_out(client, pg_db):
    _mode(pg_db, "block")
    body = _get(client, _version(pg_db, "== ONLY ==\n" + "plain rule text. " * 40 + "\n")).json()
    assert [g["name"] for g in body["groups"]] == ["Rules"]
    assert body["groups"][0]["share"] == pytest.approx(1.0)


def test_realistic_template_groups(client, pg_db):
    _mode(pg_db, "index")
    body = _get(client, _version(pg_db, REALISTIC)).json()
    groups = _groups(body)
    names = [g["name"] for g in body["groups"]]
    assert names == [n for n in GROUPS if n in groups]
    assert {"Rules", "Examples", "Product lists"} <= set(names), names
    # No heading text, section list or token word anywhere in the response.
    for heading in HEADINGS:
        assert heading not in str(body), heading
    # Examples: whole lines holding a quoted phrase then `->`.
    assert groups["Examples"]["size"] == pytest.approx(_size(len(EXAMPLES)), abs=2)
    # Rules: the template's own text, variables removed, examples out, the date counted here.
    own = REALISTIC.replace(EXAMPLES, "")
    import re as _re

    own = _re.sub(r"\{\{\w+\}\}", "", own)
    assert groups["Rules"]["size"] == pytest.approx(_size(len(own) + len(date.today().strftime("%A, %d %B %Y"))), abs=3)
    # Product lists: `{{specs}}` under a heading that is NOT the closed lists one still counts here,
    # and in index mode on a version carrying the section it is the fixed pointer line.
    blanks = sum(len(cli.SYSTEM_BLANKS[k]) for k in LISTS)
    assert groups["Product lists"]["size"] == pytest.approx(_size(blanks), abs=2)
    brands = pv.render_value(pg_db, "brands")
    if _size(len(brands)):
        assert groups["Lists from other settings"]["size"] == pytest.approx(_size(len(brands)), abs=1)
    else:
        assert "Lists from other settings" not in groups
    assert body["total_size"] == sum(g["size"] for g in body["groups"])
    assert sum(g["share"] for g in body["groups"]) == pytest.approx(1.0, abs=0.01)


def test_index_vs_block_changes_only_the_product_lists_group(client, pg_db):
    number = _version(pg_db, REALISTIC)
    _mode(pg_db, "index")
    idx = _groups(_get(client, number).json())
    _mode(pg_db, "block")
    blk = _groups(_get(client, number).json())
    for name in GROUPS:
        if name == "Product lists":
            continue
        assert (idx.get(name) or {}).get("size") == (blk.get(name) or {}).get("size"), name
    full = sum(len(pv.render_value(pg_db, k)) for k in LISTS)
    assert blk["Product lists"]["size"] == pytest.approx(_size(full), abs=2)
    assert blk["Product lists"]["size"] > idx["Product lists"]["size"]


def test_current_date_counts_under_rules(client, pg_db):
    _mode(pg_db, "block")
    padded = "x" * 400
    body = _get(client, _version(pg_db, "== DATED ==\n{{current_date}}" + padded + "\n")).json()
    [rules] = body["groups"]
    assert rules["name"] == "Rules"
    assert rules["size"] * 4 >= len(padded) + len(date.today().strftime("%Y"))


# --------------------------------------------------------------------------- #
# Index vs block
# --------------------------------------------------------------------------- #


def test_index_mode_lists_report_the_blank_line_as_what_is_sent(client, pg_db):
    _mode(pg_db, "index")
    body = _get(client, _version(pg_db, CLOSED_TEMPLATE)).json()
    assert body["mode"] == "index" and body["uses_closed_lists"] is True
    lists = {item["key"]: item for item in body["lists"]}
    names = {"specs": "Specifications", "attachment_types": "File types", "certification_types": "Certificates"}
    for key in LISTS:
        item = lists[key]
        variable = pv.VARIABLES[key]
        assert item["name"] == names[key]
        assert item["source"] == variable.source
        assert item["href"] == variable.href
        assert item["sent_each_message_size"] == _size(len(cli.SYSTEM_BLANKS[key])), item
        assert item["full_list_size"] == _size(len(pv.render_value(pg_db, key))), item
        assert not item.get("checked_only")


def test_block_mode_sends_the_full_lists(client, pg_db):
    _mode(pg_db, "block")
    body = _get(client, _version(pg_db, CLOSED_TEMPLATE)).json()
    assert body["mode"] == "block" and body["uses_closed_lists"] is True
    for item in body["lists"]:
        if item["key"] in LISTS:
            assert item["sent_each_message_size"] == item["full_list_size"], item


def test_a_template_without_the_closed_lists_section_sends_the_lists_whole_even_in_index_mode(client, pg_db):
    _mode(pg_db, "index")
    template = "== PRICE ==\nplain\n== SPECS ==\n{{specs}}\n"
    body = _get(client, _version(pg_db, template)).json()
    assert body["mode"] == "index"
    assert body["uses_closed_lists"] is False
    for item in body["lists"]:
        if item["key"] in LISTS:
            assert item["sent_each_message_size"] == item["full_list_size"] == _size(len(pv.render_value(pg_db, item["key"])))
    assert _groups(body)["Product lists"]["size"] == pytest.approx(_size(len(pv.render_value(pg_db, "specs"))), abs=2)


def test_how_a_message_is_matched_is_one_plain_sentence_per_list(client, pg_db):
    _mode(pg_db, "index")
    lists = {item["key"]: item for item in _get(client, _version(pg_db, CLOSED_TEMPLATE)).json()["lists"]}
    assert lists["specs"]["how"] == (
        "A word of the message matches a value, its name or a synonym from Product Specifications, "
        "or a code ending like -FRG; close spellings count too."
    )
    assert lists["attachment_types"]["how"] == (
        "A word matches a file type's code, name, its words or an alias keyword; close spellings count too."
    )
    assert lists["certification_types"]["how"] == (
        "A word matches a certificate kind or a certificate scheme by its name or words; close spellings count too."
    )
    assert lists["warehouses"]["how"] == (
        "Not sent to the bot; a warehouse the bot reads is checked against the warehouse list "
        "(the exact code, or the part after the last dash)."
    )


def test_no_internal_word_or_snake_case_in_any_text_field(client, pg_db):
    import re as _re

    _mode(pg_db, "index")
    body = _get(client, _version(pg_db, REALISTIC)).json()
    texts = [g["name"] for g in body["groups"]]
    for item in body["lists"]:
        texts += [item["name"], item["source"], item["how"]]
    blob = " ".join(texts)
    assert not _re.search(r"[A-Za-z]_[A-Za-z]", blob), blob
    for word in ("parser", "token", "grounding"):
        assert word not in blob.lower(), word


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
    assert wh["sent_each_message_size"] == 0 and wh["full_list_size"] == 0
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
