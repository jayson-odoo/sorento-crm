"""AGENTIC-P1 round 5e: the local `crm_products_find` tool, the prompt rules, the "may" nit
(red first)."""
from __future__ import annotations

import json
import re
import uuid

import pytest

from app.models.product import Brand, ProductCategory
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.user_service import UserPermissionService
from tests._mc_lookup_seed import product as seed_product, seed_mocha
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_agent_contact

FIND = "crm_products_find"
SLUG = "master_data.products.view"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def world(db, monkeypatch):
    from app.services import company_scope_resolver, contact_brand_scope

    monkeypatch.setattr(
        company_scope_resolver, "resolve_contact_company_scope", lambda *a, **k: frozenset({DEFAULT_COMPANY_ID})
    )
    state = {"brand_scope": None, "held": {SLUG}}
    monkeypatch.setattr(contact_brand_scope, "contact_brand_scope", lambda *a, **k: state["brand_scope"])
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in state["held"])
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    state["contact"] = seed_agent_contact(db, slugs=())
    return state


def _brand(db, name, company=DEFAULT_COMPANY_ID):
    row = Brand(id=str(uuid.uuid4()), brand_code=unique_code("BR")[:20], brand_name=name, company_id=company, is_active=True)
    db.add(row)
    db.flush()
    return row


def _category(db, name, parent=None, company=DEFAULT_COMPANY_ID):
    row = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT")[:30], category_name=name, company_id=company,
        parent_category_id=parent.id if parent else None,
    )
    db.add(row)
    db.flush()
    return row


def _product(db, *, code, name=None, brand=None, category=None, company=DEFAULT_COMPANY_ID, active=True):
    row = seed_product(db, company_id=company, code=code)
    row.product_name = name or code
    if brand is not None:
        row.brand_id = brand.id
    if category is not None:
        row.category_id = category.id
    row.is_active = active
    db.flush()
    return row


def _find(db, world, args, seen):
    from app.services.chatbot.agent import tools
    from app.services.chatbot.agent.access import build_context

    ctx = build_context(db, world["contact"]["respond_id"])
    return tools.dispatch(db, ctx, FIND, args, call=lambda n, a: {}, catalog={}, timeout=5.0, seen_ids=seen)


def _codes(out):
    assert out.status == "ok", (out.status, out.message)
    return [p["code"] for p in out.data["products"]]


# ------------------------------------------------------------------ registry


def test_the_registry_holds_the_find_tool_with_its_slug_and_no_contact_grant():
    from app.services.chatbot.agent.tools import REGISTRY, TOOL_LABELS

    assert len(REGISTRY) == 13
    assert REGISTRY[FIND].user_permission == SLUG
    assert REGISTRY[FIND].contact_grant is None
    assert REGISTRY[FIND].render is False
    assert FIND in TOOL_LABELS


# ------------------------------------------------------------------ the query


def test_brand_and_category_narrow_the_rows_and_return_names(db, world):
    kohler, grohe = _brand(db, "Kohler"), _brand(db, "Grohe")
    wc, basin = _category(db, "Water Closet"), _category(db, "Basin")
    a = _product(db, code="ZZT-A", name="Kohler closet", brand=kohler, category=wc)
    _product(db, code="ZZT-B", brand=kohler, category=basin)
    _product(db, code="ZZT-C", brand=grohe, category=wc)
    seen = {str(kohler.id), str(wc.id)}

    out = _find(db, world, {"brand_ids": [kohler.id], "category_ids": [wc.id]}, seen)

    assert _codes(out) == ["ZZT-A"]
    row = out.data["products"][0]
    assert row["id"] == str(a.id) and row["name"] == "Kohler closet"
    assert row["brand"] == "Kohler" and row["category"] == "Water Closet"
    assert out.data["more"] == 0
    assert str(a.id) in seen  # its product id is now known


def test_a_category_includes_its_children_one_level(db, world):
    parent = _category(db, "Sanitary")
    child = _category(db, "Closets", parent=parent)
    grandchild = _category(db, "Smart closets", parent=child)
    _product(db, code="ZZT-P", category=parent)
    _product(db, code="ZZT-K", category=child)
    _product(db, code="ZZT-G", category=grandchild)
    out = _find(db, world, {"category_ids": [parent.id]}, {str(parent.id)})
    assert sorted(_codes(out)) == ["ZZT-K", "ZZT-P"]


def test_query_matches_code_or_name_contains_and_ignores_wildcards(db, world):
    _product(db, code="ZZT-CLOSET-1", name="plain")
    _product(db, code="ZZT-X", name="Big Closet")
    _product(db, code="ZZT-Y", name="other")
    assert sorted(_codes(_find(db, world, {"query": "closet"}, set()))) == ["ZZT-CLOSET-1", "ZZT-X"]
    out = _find(db, world, {"query": "%"}, set())
    assert out.status == "empty"


def test_inactive_products_are_excluded_unless_asked_for(db, world):
    brand = _brand(db, "Kohler")
    _product(db, code="ZZT-ON", brand=brand)
    _product(db, code="ZZT-OFF", brand=brand, active=False)
    seen = {str(brand.id)}
    assert _codes(_find(db, world, {"brand_ids": [brand.id]}, set(seen))) == ["ZZT-ON"]
    both = _find(db, world, {"brand_ids": [brand.id], "active_only": False}, set(seen))
    assert sorted(_codes(both)) == ["ZZT-OFF", "ZZT-ON"]


def test_another_company_never_appears(db, world):
    seed_mocha(db)
    brand = _brand(db, "Kohler")
    _product(db, code="ZZT-MINE", brand=brand)
    other_company = _product(db, code="ZZT-THEIRS", brand=brand, company="00000000-0000-0000-0000-000000000002")
    out = _find(db, world, {"brand_ids": [brand.id]}, {str(brand.id)})
    assert _codes(out) == ["ZZT-MINE"]
    assert str(other_company.id) not in json.dumps(out.data)


def test_a_product_outside_the_brand_scope_never_appears(db, world):
    mine, other = _brand(db, "Kohler"), _brand(db, "Grohe")
    _product(db, code="ZZT-IN", brand=mine)
    hidden = _product(db, code="ZZT-OUT", brand=other)
    world["brand_scope"] = frozenset({str(mine.id)})
    seen = {str(mine.id), str(other.id)}
    out = _find(db, world, {"brand_ids": [mine.id, other.id]}, seen)
    assert _codes(out) == ["ZZT-IN"]
    assert str(hidden.id) not in seen


def test_the_cap_is_fifty_rows_and_more_counts_the_rest(db, world):
    brand = _brand(db, "Kohler")
    for i in range(53):
        _product(db, code=f"ZZT-{i:03d}", brand=brand)
    out = _find(db, world, {"brand_ids": [brand.id]}, {str(brand.id)})
    codes = _codes(out)
    assert len(codes) == 50 and codes == sorted(codes)
    assert out.data["more"] == 3


def test_no_rows_is_the_typed_empty(db, world):
    brand = _brand(db, "Kohler")
    out = _find(db, world, {"brand_ids": [brand.id]}, {str(brand.id)})
    assert out.status == "empty"
    assert "No rows matched" in out.message


# ------------------------------------------------------------------ the rules


def test_an_id_not_seen_this_turn_is_invalid(db, world):
    brand = _brand(db, "Kohler")
    out = _find(db, world, {"brand_ids": [brand.id]}, set())
    assert out.status == "invalid" and "Unknown id" in out.message
    out = _find(db, world, {"brand_ids": ["KOHLER"]}, set())
    assert out.status == "invalid" and "takes ids from crm_resolve" in out.message


@pytest.mark.parametrize("args", [{}, {"active_only": True}, {"brand_ids": []}, {"query": "  "}])
def test_at_least_one_filter_is_required(db, world, args):
    assert _find(db, world, args, set()).status == "invalid"


def test_the_slug_is_required_at_dispatch(db, world):
    world["held"].discard(SLUG)
    assert _find(db, world, {"query": "x"}, set()).status == "denied"


def test_unknown_arguments_and_bad_types_are_invalid(db, world):
    assert _find(db, world, {"query": "x", "drop": 1}, set()).status == "invalid"
    assert _find(db, world, {"query": "x", "active_only": "yes"}, set()).status == "invalid"
    assert _find(db, world, {"brand_ids": "not a list"}, set()).status == "invalid"


def test_the_tool_is_offered_to_the_model_with_a_local_schema(db, world):
    from app.services.chatbot.agent.access import build_context, permitted_tools
    from app.services.chatbot.agent.tools import tool_schemas

    ctx = build_context(db, world["contact"]["respond_id"])
    tools = permitted_tools(db, ctx)
    assert FIND in [t.name for t in tools]
    schema = next(s for s in tool_schemas(tools, {}) if s["function"]["name"] == FIND)
    assert set(schema["function"]["parameters"]["properties"]) == {"brand_ids", "category_ids", "query", "active_only"}


def test_a_found_product_id_passes_the_id_rule_for_the_next_tool(db, world):
    from app.services.chatbot.agent import tools

    brand = _brand(db, "Kohler")
    p = _product(db, code="ZZT-A", brand=brand)
    seen = {str(brand.id)}
    _find(db, world, {"brand_ids": [brand.id]}, seen)
    assert tools._check_ids({"product_ids": [str(p.id)]}, seen) is None


# ------------------------------------------------------------------ the prompt


def test_the_prompt_teaches_the_find_chain_the_unavailable_answer_and_the_language():
    from app.services.ai_prompt_registry import _chatbot_agent_fallback

    text = _chatbot_agent_fallback()
    low = text.lower()
    assert "crm_products_find" in text
    assert re.search(r"brand[^.]{0,120}crm_resolve[^.]{0,200}crm_products_find", text, re.S) or (
        "crm_resolve" in text and "crm_products_find" in text
    )
    assert "not available" in low
    assert "supplier" in low
    assert "language" in low and "this message" in low
    assert not re.search("[" + chr(0x2013) + chr(0x2014) + "]", text)


# ------------------------------------------------------------------ the "may" nit


def test_a_lowercase_may_is_not_a_month_but_May_with_a_year_or_capital_is():
    from app.services.chatbot.agent.loop import unsupported_figures

    assert unsupported_figures("Only 5 may arrive", []) == ["5"]
    assert unsupported_figures("It arrives on 5 May", []) == []
    assert unsupported_figures("It arrives on 5 may 2026", []) == []
    assert unsupported_figures("It arrives on 5 May 2026", []) == []
    assert unsupported_figures("It arrives on 15 Nov", []) == []
