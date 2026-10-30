"""AGENTIC-P1 round 5b: `crm_resolve` resolves brand, category and sales_agent from the bot's own
closed lists (`head/lookup_lists` rows scored by `head/list_resolver`), not through the entity
resolver, which has no probe for them. Red first.
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.models.product import Brand, ProductCategory
from app.models.sales_agent import SalesAgent
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_agent_contact

RESOLVE = "crm_resolve"
SLUGS = {
    "brand": "master_data.brands.view",
    "category": "master_data.product_categories.view",
    "sales_agent": "master_data.sales_agents.view",
    "product": "master_data.products.view",
}


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


class Resolver:
    def __init__(self):
        self.bodies = []

    def factory(self, db):
        def call(body):
            self.bodies.append(dict(body))
            return {"tokens": body["tokens"], "resolutions": [
                {"token": t, "resolved": False, "ambiguous": False, "matches": []} for t in body["tokens"]
            ]}

        return call


@pytest.fixture()
def resolver(monkeypatch):
    from app.services.chatbot.lanes.business import services

    r = Resolver()
    monkeypatch.setattr(services, "_resolve_entity", r.factory)
    return r


def _brand(db, name, code=None):
    row = Brand(id=str(uuid.uuid4()), brand_code=code or unique_code("BR")[:20], brand_name=name,
                company_id=DEFAULT_COMPANY_ID, is_active=True)
    db.add(row)
    db.flush()
    return row


def _category(db, name):
    row = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT")[:30], category_name=name,
                          company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.flush()
    return row


def _agent(db, code):
    row = SalesAgent(id=str(uuid.uuid4()), sales_agent=code, is_active=True, company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def world(db, monkeypatch):
    """A contact in the default company that may see the salesperson list, a user holding every
    kind slug, and a brand scope hook the tests can narrow."""
    from app.services import company_scope_resolver, contact_asker, contact_brand_scope

    monkeypatch.setattr(
        company_scope_resolver, "resolve_contact_company_scope", lambda *a, **k: frozenset({DEFAULT_COMPANY_ID})
    )
    monkeypatch.setattr(contact_asker, "may_ask_sales_ranking", lambda *a, **k: ("granted", None))
    state = {"brand_scope": None}
    monkeypatch.setattr(contact_brand_scope, "contact_brand_scope", lambda *a, **k: state["brand_scope"])
    held = set(SLUGS.values())
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in held)
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    state["held"] = held
    state["contact"] = seed_agent_contact(db, slugs=())
    return state


def _resolve(db, world, args):
    from app.services.chatbot.agent import tools
    from app.services.chatbot.agent.access import build_context

    ctx = build_context(db, world["contact"]["respond_id"])
    seen: set[str] = set()
    out = tools.dispatch(db, ctx, RESOLVE, args, call=lambda n, a: {}, catalog={}, timeout=5.0, seen_ids=seen)
    return out, seen


def _row(out, term):
    assert out.status == "ok", (out.status, out.message)
    return {r["term"]: r for r in out.data["results"]}[term]


def test_a_seeded_brand_resolves_to_its_id_without_the_entity_resolver(db, world, resolver):
    brand = _brand(db, "Kohler", "KOH")
    _brand(db, "Grohe", "GRO")
    out, seen = _resolve(db, world, {"terms": ["Kohler"], "kinds": ["brand"]})
    row = _row(out, "Kohler")
    assert row["status"] == "found"
    assert row["matches"][0]["id"] == str(brand.id)
    assert row["matches"][0]["kind"] == "brand"
    assert "Kohler" in (row["matches"][0]["name"] or "")
    assert str(brand.id) in seen
    assert resolver.bodies == []  # brand never goes to the entity resolver


def test_a_misspelt_brand_one_letter_off_resolves(db, world, resolver):
    brand = _brand(db, "Kohler", "KOH")
    _brand(db, "Grohe", "GRO")
    row = _row(_resolve(db, world, {"terms": ["Kohlar"], "kinds": ["brand"]})[0], "Kohlar")
    assert row["status"] == "found"
    assert row["matches"][0]["id"] == str(brand.id)


def test_two_brands_sharing_a_word_are_ambiguous(db, world, resolver):
    a = _brand(db, "Royal Ceramic", "RCE")
    b = _brand(db, "Royal Tiles", "RTI")
    _brand(db, "Grohe", "GRO")
    row = _row(_resolve(db, world, {"terms": ["Royal"], "kinds": ["brand"]})[0], "Royal")
    assert row["status"] == "ambiguous"
    assert {m["id"] for m in row["matches"]} == {str(a.id), str(b.id)}


def test_a_term_that_matches_no_brand_is_not_found(db, world, resolver):
    _brand(db, "Kohler", "KOH")
    row = _row(_resolve(db, world, {"terms": ["Zzyzx"], "kinds": ["brand"]})[0], "Zzyzx")
    assert row["status"] == "not_found" and row["matches"] == []


def test_a_brand_outside_the_contacts_brand_scope_is_not_found(db, world, resolver):
    mine = _brand(db, "Kohler", "KOH")
    other = _brand(db, "Grohe", "GRO")
    world["brand_scope"] = frozenset({str(mine.id)})
    out, seen = _resolve(db, world, {"terms": ["Kohler", "Grohe"], "kinds": ["brand"]})
    assert _row(out, "Kohler")["status"] == "found"
    assert _row(out, "Grohe")["status"] == "not_found"
    assert str(other.id) not in seen
    assert str(other.id) not in json.dumps(out.data)


def test_category_and_sales_agent_are_found_with_their_ids(db, world, resolver):
    cat = _category(db, "Water Closet")
    _category(db, "Basin Mixer")
    agent = _agent(db, "SEAN I")
    out, seen = _resolve(db, world, {"terms": ["Water Closet", "SEAN I"], "kinds": ["category", "sales_agent"]})
    c = _row(out, "Water Closet")
    a = _row(out, "SEAN I")
    assert c["status"] == "found" and c["matches"][0]["id"] == str(cat.id) and c["matches"][0]["kind"] == "category"
    assert a["status"] == "found" and a["matches"][0]["id"] == str(agent.id) and a["matches"][0]["kind"] == "sales_agent"
    assert {str(cat.id), str(agent.id)} <= seen
    assert resolver.bodies == []


def test_only_product_supplier_customer_go_to_the_entity_resolver(db, world, resolver):
    _brand(db, "Kohler", "KOH")
    out, _ = _resolve(db, world, {"terms": ["Kohler"], "kinds": ["product", "brand", "category"]})
    assert out.status == "ok"
    assert set(resolver.bodies[0]["allowed_entity_types"]) == {"product"}
    assert _row(out, "Kohler")["matches"][0]["kind"] == "brand"


def test_the_kind_gates_still_apply_to_the_list_kinds(db, world, resolver):
    _brand(db, "Kohler", "KOH")
    world["held"].discard(SLUGS["brand"])
    out, _ = _resolve(db, world, {"terms": ["Kohler"], "kinds": ["brand", "category"]})
    assert out.status == "ok"
    assert out.data["skipped_kinds"] == ["brand"]
    assert _row(out, "Kohler")["status"] == "not_found"


def test_a_contact_that_may_not_see_salespeople_cannot_resolve_sales_agents(db, world, resolver, monkeypatch):
    from app.services import contact_asker

    _agent(db, "SEAN I")
    monkeypatch.setattr(contact_asker, "may_ask_sales_ranking", lambda *a, **k: ("not_granted", None))
    out, seen = _resolve(db, world, {"terms": ["SEAN I"], "kinds": ["sales_agent", "category"]})
    assert out.status == "ok"
    assert out.data["skipped_kinds"] == ["sales_agent"]
    assert _row(out, "SEAN I")["status"] == "not_found"
    assert not seen
