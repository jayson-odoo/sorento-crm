"""AGENTIC-P1 round 5 (crew eval 30 Oct: FAIL, 0/15 strict): red tests for items 1 to 8 of the
"Round 5 contract" in PLAN-agentic-p1-29oct.md.

Decisions the contract left open, made here (the coder may push back through the captain):
* The resolver seam is patched as the module attribute `lanes.business.services._resolve_entity`
  (a factory taking the session), so `crm_resolve` must look it up at call time.
* `crm_resolve` answers `ToolResult(status="ok")` with `data = {"results": [{term, status, matches:
  [{id, kind, code, name}]}], "skipped_kinds": [...]}`.
* The "ids seen this turn" rule and the answer verifier are exercised through `run_agent_turn`
  (scripted provider), so they do not depend on how `dispatch` carries its per-turn state.
* A `not_found` entry cites the term in `what` and the model's tool call id in `call_id`.
* A figure whose number is only in the user's own message is not tested (contract is silent).
"""
from __future__ import annotations

import copy
import json
import re
import uuid
from pathlib import Path

import pytest

from app.models.base import get_company_scope
from app.models.user import SystemSetting
from app.services.chatbot.lanes.business import services as business_services
from app.services.llm_provider import ChatResult
from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_agent_contact

STOCK = "crm_inventory_stock_balance_list"
GRN = "crm_procurement_grn_summary"
RESOLVE = "crm_resolve"
ANSWER = "answer"

UUID_A = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
UUID_B = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb"

KIND_SLUGS = {
    "product": "master_data.products.view",
    "supplier": "procurement.suppliers.view",
    "brand": "master_data.brands.view",
    "customer": "order_management.customers.view",
    "category": "master_data.product_categories.view",
    "sales_agent": "master_data.sales_agents.view",
}

_PROPS = {
    "contact_id": {"type": "string"},
    "space_id": {"type": "string"},
    "query": {"type": "string"},
    "view": {"type": "string"},
    "product_ids": {"type": "array", "items": {"type": "string"}},
    "brand_id": {"type": "string"},
}
CATALOG = {
    n: {"description": n, "inputSchema": {"type": "object", "properties": dict(_PROPS), "required": ["contact_id"]}}
    for n in (STOCK, GRN, "crm_report_ask")
}

_HELD: set[str] = set()


@pytest.fixture()
def held(monkeypatch):
    _HELD.clear()
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in _HELD
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield _HELD
    _HELD.clear()


def _ctx(grants=()):
    from app.services.chatbot.agent.access import AgentContext

    return AgentContext(
        contact_pk="pk-1", contact_respond_id="ZZT-R5-1", space_id="364817", user_id="user-1",
        user_name="ZZT User", grants=frozenset(grants),
    )


class Rec:
    def __init__(self, result=None, exc=None):
        self.result = {"items": [{"qty": 1}], "has_result": True} if result is None else result
        self.exc = exc
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        if self.exc is not None:
            raise self.exc
        return self.result


def _dispatch(name, args, rec, ctx=None, db=None):
    from app.services.chatbot.agent import tools

    return tools.dispatch(db, ctx or _ctx(), name, args, call=rec, catalog=CATALOG, timeout=5.0)


# ------------------------------------------------------------------ resolver stub


def hit(kind, code, id_, name=None):
    return {
        "entity_type": kind, "canonical_code": code, "uuid": id_, "display": {"name": name or code},
    }


def resolution(term, matches, *, resolved=None, ambiguous=None):
    return {
        "token": term,
        "resolved": len(matches) == 1 if resolved is None else resolved,
        "ambiguous": len(matches) > 1 if ambiguous is None else ambiguous,
        "matches": matches,
    }


class Resolver:
    """Stands in for `services._resolve_entity(db)`; records every body and the company scope the
    session carried when it ran."""

    def __init__(self, table=None):
        self.table = table or {}  # term -> list of match dicts or a ready resolution dict
        self.bodies: list[dict] = []
        self.scopes: list = []
        self.db = None

    def factory(self, db):
        self.db = db

        def call(body):
            self.bodies.append(copy.deepcopy(body))
            self.scopes.append(get_company_scope(db))
            out = []
            for term in body["tokens"]:
                entry = self.table.get(term, [])
                out.append(entry if isinstance(entry, dict) else resolution(term, entry))
            return {
                "tokens": list(body["tokens"]),
                "resolutions": out,
                "unresolved_tokens": [r["token"] for r in out if not r["matches"]],
            }

        return call


@pytest.fixture()
def resolver(monkeypatch):
    r = Resolver()
    monkeypatch.setattr(business_services, "_resolve_entity", r.factory)
    return r


def _results(out):
    assert out.status == "ok", (out.status, out.message)
    return {r["term"]: r for r in out.data["results"]}


# ------------------------------------------------------------------ 1. crm_resolve


def test_registry_has_crm_resolve_and_no_longer_crm_lookup_resolve():
    from app.services.chatbot.agent.tools import REGISTRY

    assert RESOLVE in REGISTRY
    assert "crm_lookup_resolve" not in REGISTRY
    assert len(REGISTRY) == 10


def test_found_ambiguous_and_not_found_per_term_and_the_body_sent(held, resolver):
    held.update({KIND_SLUGS["product"], KIND_SLUGS["brand"]})
    resolver.table = {
        "SRTWT7445": [hit("product", "SRTWT7445", UUID_A, "Water closet")],
        "KOHLER": [hit("brand", "KOHLER", UUID_A), hit("product", "KOHLER-1", UUID_B)],
        "ZZTNOPE": [],
    }
    terms = ["SRTWT7445", "KOHLER", "ZZTNOPE"]

    out = _dispatch(RESOLVE, {"terms": terms, "kinds": ["product", "brand"]}, Rec())

    by_term = _results(out)
    assert by_term["SRTWT7445"]["status"] == "found"
    assert by_term["SRTWT7445"]["matches"][0]["id"] == UUID_A
    assert by_term["SRTWT7445"]["matches"][0]["kind"] == "product"
    assert by_term["SRTWT7445"]["matches"][0]["code"] == "SRTWT7445"
    assert "name" in by_term["SRTWT7445"]["matches"][0]
    assert by_term["KOHLER"]["status"] == "ambiguous"
    assert len(by_term["KOHLER"]["matches"]) == 2
    assert by_term["ZZTNOPE"]["status"] == "not_found"
    assert by_term["ZZTNOPE"]["matches"] == []

    body = resolver.bodies[0]
    assert body["tokens"] == terms
    assert body["raw_tokens"] == terms
    assert set(body["allowed_entity_types"]) == {"product", "brand"}
    assert body["dry_run"] is True


def test_a_top_match_the_resolver_marks_unambiguous_is_found(held, resolver):
    held.add(KIND_SLUGS["product"])
    resolver.table = {
        "SRTWT7445": resolution(
            "SRTWT7445",
            [hit("product", "SRTWT7445", UUID_A), hit("product", "SRTWT7445-B", UUID_B)],
            resolved=True, ambiguous=False,
        )
    }
    out = _dispatch(RESOLVE, {"terms": ["SRTWT7445"]}, Rec())
    row = _results(out)["SRTWT7445"]
    assert row["status"] == "found"
    assert row["matches"][0]["id"] == UUID_A


def test_at_most_five_matches_are_returned(held, resolver):
    held.add(KIND_SLUGS["product"])
    resolver.table = {"BASIN": [hit("product", f"BASIN-{i}", str(uuid.uuid4())) for i in range(8)]}
    row = _results(_dispatch(RESOLVE, {"terms": ["BASIN"]}, Rec()))["BASIN"]
    assert row["status"] == "ambiguous"
    assert len(row["matches"]) == 5


@pytest.mark.parametrize("terms", [[], ["t"] * 11])
def test_terms_must_be_one_to_ten(held, resolver, terms):
    held.add(KIND_SLUGS["product"])
    out = _dispatch(RESOLVE, {"terms": terms}, Rec())
    assert out.status == "invalid"
    assert resolver.bodies == []


def test_kinds_the_user_lacks_the_slug_for_are_not_searched_and_are_listed(held, resolver):
    held.update({KIND_SLUGS["product"], KIND_SLUGS["brand"]})  # not suppliers, not customers
    out = _dispatch(
        RESOLVE, {"terms": ["X"], "kinds": ["product", "supplier", "brand", "customer"]}, Rec()
    )
    assert out.status == "ok"
    assert set(resolver.bodies[0]["allowed_entity_types"]) == {"product", "brand"}
    assert sorted(out.data["skipped_kinds"]) == ["customer", "supplier"]


def test_supplier_needs_the_contacts_reveal_as_well_as_the_slug(held, resolver):
    held.update({KIND_SLUGS["product"], KIND_SLUGS["supplier"]})
    out = _dispatch(RESOLVE, {"terms": ["X"], "kinds": ["product", "supplier"]}, Rec(), ctx=_ctx())
    assert set(resolver.bodies[-1]["allowed_entity_types"]) == {"product"}
    assert out.data["skipped_kinds"] == ["supplier"]

    out = _dispatch(
        RESOLVE, {"terms": ["X"], "kinds": ["product", "supplier"]}, Rec(),
        ctx=_ctx({"purchase_orders.supplier"}),
    )
    assert set(resolver.bodies[-1]["allowed_entity_types"]) == {"product", "supplier"}
    assert out.data["skipped_kinds"] == []


def test_when_no_kind_may_be_searched_the_resolver_is_not_called(held, resolver):
    out = _dispatch(RESOLVE, {"terms": ["X"], "kinds": ["supplier"]}, Rec())
    assert resolver.bodies == []
    assert "supplier" in json.dumps(out.__dict__, default=str)


def test_default_kinds_are_all_the_user_may_search(held, resolver):
    held.update({KIND_SLUGS["product"], KIND_SLUGS["category"]})
    _dispatch(RESOLVE, {"terms": ["X"]}, Rec())
    assert set(resolver.bodies[0]["allowed_entity_types"]) == {"product", "category"}


def test_the_slug_is_checked_at_dispatch_time(held, resolver):
    held.add(KIND_SLUGS["product"])
    first = _dispatch(RESOLVE, {"terms": ["X"], "kinds": ["product"]}, Rec())
    assert first.status == "ok"  # exposed and callable while the user holds the slug
    assert len(resolver.bodies) == 1

    held.discard(KIND_SLUGS["product"])  # revoked between exposure and the next call
    out = _dispatch(RESOLVE, {"terms": ["X"], "kinds": ["product"]}, Rec())

    assert len(resolver.bodies) == 1  # the resolver was not asked again
    assert out.status == "denied" or out.data["skipped_kinds"] == ["product"]


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def test_build_context_stamps_the_contacts_company_scope(db, monkeypatch):
    from app.services import company_scope_resolver
    from app.services.chatbot.agent.access import build_context

    company = str(uuid.uuid4())
    monkeypatch.setattr(
        company_scope_resolver, "resolve_contact_company_scope", lambda *a, **k: frozenset({company})
    )
    contact = seed_agent_contact(db)

    build_context(db, contact["respond_id"])

    assert get_company_scope(db) == frozenset({company})


def test_a_failed_company_scope_lookup_fails_closed_to_an_empty_set(db, monkeypatch):
    from app.services import company_scope_resolver
    from app.services.chatbot.agent.access import build_context

    def boom(*a, **k):
        raise RuntimeError("scope lookup down")

    monkeypatch.setattr(company_scope_resolver, "resolve_contact_company_scope", boom)
    contact = seed_agent_contact(db)

    build_context(db, contact["respond_id"])

    assert get_company_scope(db) == frozenset()


def test_the_resolver_runs_under_the_stamped_company_scope(db, monkeypatch, resolver):
    from app.services import company_scope_resolver
    from app.services.chatbot.agent.access import build_context
    from app.services.chatbot.agent import tools

    company = str(uuid.uuid4())
    monkeypatch.setattr(
        company_scope_resolver, "resolve_contact_company_scope", lambda *a, **k: frozenset({company})
    )
    contact = seed_agent_contact(db, slugs=(KIND_SLUGS["product"],))
    ctx = build_context(db, contact["respond_id"])

    out = tools.dispatch(db, ctx, RESOLVE, {"terms": ["X"]}, call=Rec(), catalog=CATALOG, timeout=5.0)

    assert out.status == "ok", out.message
    assert resolver.scopes == [frozenset({company})]


def _customer_world(db, monkeypatch, *, enforced_ids=None):
    from app.services import company_scope_resolver
    from app.services.chatbot.agent.access import build_context
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._mc_lookup_seed import customer, seed_mocha

    mocha = seed_mocha(db)
    mine = customer(db, company_id=DEFAULT_COMPANY_ID)
    mine2 = customer(db, company_id=DEFAULT_COMPANY_ID)
    other = customer(db, company_id=mocha.id)
    monkeypatch.setattr(
        company_scope_resolver, "resolve_contact_company_scope",
        lambda *a, **k: frozenset({DEFAULT_COMPANY_ID}),
    )
    scope = None if enforced_ids is None else {
        "enforced": True, "ids": [enforced_ids(mine, mine2)], "names": [], "linked": [], "staff": False,
    }
    monkeypatch.setattr(business_services, "customer_scope", lambda *a, **k: scope)
    contact = seed_agent_contact(db, slugs=(KIND_SLUGS["customer"],))
    return build_context(db, contact["respond_id"]), mine, mine2, other


def test_customer_matches_in_another_company_are_dropped(db, monkeypatch, resolver):
    from app.services.chatbot.agent import tools

    ctx, mine, _mine2, other = _customer_world(db, monkeypatch)
    resolver.table = {
        "ACME": [hit("customer", "C1", str(mine.id)), hit("customer", "C2", str(other.id))]
    }

    out = tools.dispatch(
        db, ctx, RESOLVE, {"terms": ["ACME"], "kinds": ["customer"]}, call=Rec(), catalog=CATALOG, timeout=5.0
    )

    row = _results(out)["ACME"]
    assert [m["id"] for m in row["matches"]] == [str(mine.id)]
    assert row["status"] == "found"


def test_a_customer_only_in_another_company_reads_not_found(db, monkeypatch, resolver):
    from app.services.chatbot.agent import tools

    ctx, _mine, _mine2, other = _customer_world(db, monkeypatch)
    resolver.table = {"ACME": [hit("customer", "C2", str(other.id))]}

    out = tools.dispatch(
        db, ctx, RESOLVE, {"terms": ["ACME"], "kinds": ["customer"]}, call=Rec(), catalog=CATALOG, timeout=5.0
    )

    row = _results(out)["ACME"]
    assert row["status"] == "not_found" and row["matches"] == []


def test_an_enforced_customer_link_narrows_the_matches(db, monkeypatch, resolver):
    from app.services.chatbot.agent import tools

    ctx, mine, mine2, _other = _customer_world(db, monkeypatch, enforced_ids=lambda a, b: str(a.id))
    resolver.table = {
        "ACME": [hit("customer", "C1", str(mine.id)), hit("customer", "C3", str(mine2.id))]
    }

    out = tools.dispatch(
        db, ctx, RESOLVE, {"terms": ["ACME"], "kinds": ["customer"]}, call=Rec(), catalog=CATALOG, timeout=5.0
    )

    assert [m["id"] for m in _results(out)["ACME"]["matches"]] == [str(mine.id)]


# ------------------------------------------------------------------ 3. typed empty


@pytest.mark.parametrize(
    "envelope",
    [
        {"items": [], "has_result": False},
        {"items": [], "has_result": True},
        {"has_result": False, "result_type": "stock"},
        {"items": [], "answers": [], "has_result": True},
    ],
)
def test_an_envelope_with_no_rows_is_empty(held, envelope):
    held.add("inventory.stock.view")
    out = _dispatch(STOCK, {"query": "ZZT-FILTER-VALUE"}, Rec(result=envelope))
    assert out.status == "empty"
    assert out.message == "No rows matched these filters."
    assert "ZZT-FILTER-VALUE" in json.dumps(out.data, default=str)  # the applied filters


@pytest.mark.parametrize(
    "envelope",
    [
        {"items": [{"qty": 3}], "has_result": True},
        {"answers": [{"text": "x"}], "has_result": True},
    ],
)
def test_an_envelope_with_rows_is_still_ok(held, envelope):
    held.add("inventory.stock.view")
    assert _dispatch(STOCK, {"query": "x"}, Rec(result=envelope)).status == "ok"


# ------------------------------------------------------------------ 4. clear errors


def test_a_returned_route_4xx_body_is_invalid_with_the_routes_detail(held):
    held.add("procurement.grn.view")
    body = {
        "detail": "product_ids must be valid UUIDs",
        "status_code": 422,
        "error": "GET /api/v1/procurement/grn returned HTTP 422: product_ids must be valid UUIDs",
        "http_error": "GET /api/v1/procurement/grn returned HTTP 422: product_ids must be valid UUIDs",
    }
    out = _dispatch(GRN, {"query": "x"}, Rec(result=body), ctx=_ctx({"purchase_orders.placed"}))
    assert out.status == "invalid"
    assert "product_ids must be valid UUIDs" in out.message


def test_a_raised_4xx_tool_error_is_invalid_with_urls_and_hosts_stripped(held):
    from app.services.ai_assistant_service import MCPToolCallError

    held.add("inventory.stock.view")
    long_tail = "x" * 400
    exc = MCPToolCallError(
        "Error executing tool crm_inventory_stock_balance_list: GET /api/v1/inventory/stock returned "
        f"HTTP 422: brand_id must be a valid UUID, see http://10.1.2.3:8000/api/v1/inventory/stock "
        f"on host backend.internal.example.com {long_tail}"
    )
    out = _dispatch(STOCK, {"query": "x"}, Rec(exc=exc))
    assert out.status == "invalid"
    assert "brand_id must be a valid UUID" in out.message
    assert "http://" not in out.message and "10.1.2.3" not in out.message
    assert "backend.internal.example.com" not in out.message
    assert len(out.message) <= 200


def test_a_5xx_or_any_other_failure_is_the_fixed_sentence(held):
    held.add("inventory.stock.view")
    for exc in (
        RuntimeError("connection refused to http://10.1.2.3:8000"),
        ValueError("boom"),
        __import__("app.services.ai_assistant_service", fromlist=["MCPToolCallError"]).MCPToolCallError(
            "Error executing tool x: GET /api/v1/y returned HTTP 500: Internal Server Error"
        ),
    ):
        out = _dispatch(STOCK, {"query": "x"}, Rec(exc=exc))
        assert out.status == "error"
        assert out.message == "The tool failed."


# ------------------------------------------------------------------ loop-level helpers


def call(name, args=None, cid="c1"):
    return {"id": cid, "name": name, "arguments": {} if args is None else args}


def asks(*calls, prompt=100, completion=10):
    return ChatResult(
        content="", prompt_tokens=prompt, completion_tokens=completion,
        total_tokens=prompt + completion, tool_calls=list(calls),
    )


def answer_call(text, *, figures=(), not_found=(), not_checked=(), cid="a1", prompt=100):
    return asks(
        call(
            ANSWER,
            {
                "text": text,
                "figures": [dict(f) for f in figures],
                "not_found": [dict(n) for n in not_found],
                "not_checked": list(not_checked),
            },
            cid,
        ),
        prompt=prompt,
    )


def plain(text):
    return ChatResult(content=text, prompt_tokens=100, completion_tokens=10, total_tokens=110)


class Provider:
    def __init__(self, script, on_call=None):
        self.script = list(script)
        self.seen: list[dict] = []
        self.on_call = on_call

    def chat(self, messages, *, tools=None, reasoning_effort=None, **kw):
        self.seen.append({"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)})
        if self.on_call:
            self.on_call(len(self.seen))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _names(tools):
    return [t["function"]["name"] for t in tools or []]


def _tool_msgs(messages):
    return [m for m in messages if m.get("role") == "tool"]


def _payload(msg):
    return json.loads(msg["content"])


@pytest.fixture()
def contact(db):
    return seed_agent_contact(
        db, slugs=("inventory.stock.view", "order_management.orders.view", KIND_SLUGS["product"])
    )


def run(db, contact, provider, mcp=None, text="stock of SRTWT7445?", **kw):
    from app.services.chatbot.agent.loop import run_agent_turn

    return run_agent_turn(
        db, contact_respond_id=contact["respond_id"], text=text, provider=provider,
        mcp_call=mcp or Rec(), catalog=CATALOG, **kw,
    )


def _budget(db, **cols):
    row = db.query(SystemSetting).first() or SystemSetting()
    db.add(row)
    for k, v in cols.items():
        setattr(row, k, v)
    db.flush()


# ------------------------------------------------------------------ the tool surface


def test_the_model_is_offered_crm_resolve_and_the_answer_tool(db, contact, resolver):
    provider = Provider([answer_call("Hello.")])
    run(db, contact, provider)
    names = _names(provider.seen[0]["tools"])
    assert RESOLVE in names and ANSWER in names
    assert "crm_lookup_resolve" not in names
    answer_schema = next(t for t in provider.seen[0]["tools"] if t["function"]["name"] == ANSWER)
    props = answer_schema["function"]["parameters"]["properties"]
    assert set(props) >= {"text", "figures", "not_found", "not_checked"}


# ------------------------------------------------------------------ 2. ids come from results


def test_a_code_in_an_id_argument_is_invalid_and_never_reaches_mcp(db, contact, resolver):
    mcp = Rec()
    provider = Provider(
        [asks(call(STOCK, {"product_ids": ["SRTWT7445"]})), answer_call("Could not read it.")]
    )
    run(db, contact, provider, mcp)

    msg = _payload(_tool_msgs(provider.seen[1]["messages"])[0])
    assert msg["status"] == "invalid"
    assert "takes ids from crm_resolve, not codes or names" in msg["message"]
    assert "product_ids" in msg["message"] and "SRTWT7445" in msg["message"]
    assert mcp.calls == []


def test_an_unknown_uuid_in_an_id_argument_is_invalid(db, contact, resolver):
    mcp = Rec()
    stranger = str(uuid.uuid4())
    provider = Provider([asks(call(STOCK, {"brand_id": stranger})), answer_call("Could not read it.")])
    run(db, contact, provider, mcp)

    msg = _payload(_tool_msgs(provider.seen[1]["messages"])[0])
    assert msg["status"] == "invalid"
    assert "Unknown id in" in msg["message"] and "brand_id" in msg["message"]
    assert "get ids from crm_resolve first" in msg["message"]
    assert mcp.calls == []


def test_a_uuid_from_an_earlier_crm_resolve_in_the_same_turn_passes(db, contact, resolver):
    resolver.table = {"SRTWT7445": [hit("product", "SRTWT7445", UUID_A)]}
    mcp = Rec()
    provider = Provider(
        [
            asks(call(RESOLVE, {"terms": ["SRTWT7445"]}, "r1")),
            asks(call(STOCK, {"product_ids": [UUID_A]}, "c2")),
            answer_call("Found it."),
        ]
    )
    run(db, contact, provider, mcp)

    resolved = _payload(_tool_msgs(provider.seen[1]["messages"])[0])
    assert resolved["status"] == "ok"
    assert resolved["data"]["results"][0]["matches"][0]["id"] == UUID_A
    assert [c[0] for c in mcp.calls] == [STOCK]
    assert mcp.calls[0][1]["product_ids"] == [UUID_A]


def test_an_id_from_a_resolve_in_a_previous_turn_is_not_remembered(db, contact, resolver):
    resolver.table = {"SRTWT7445": [hit("product", "SRTWT7445", UUID_A)]}
    run(db, contact, Provider([asks(call(RESOLVE, {"terms": ["SRTWT7445"]}, "r1")), answer_call("Done.")]))

    mcp = Rec()
    provider = Provider([asks(call(STOCK, {"product_ids": [UUID_A]})), answer_call("Could not read it.")])
    run(db, contact, provider, mcp)

    assert _payload(_tool_msgs(provider.seen[1]["messages"])[0])["status"] == "invalid"
    assert mcp.calls == []


def test_contact_and_space_are_not_subject_to_the_id_rule(held):
    held.add("inventory.stock.view")
    rec = Rec()
    out = _dispatch(STOCK, {"query": "x", "contact_id": "ZZT-EVIL", "space_id": "EVIL"}, rec)
    assert out.status == "ok"
    assert rec.calls[0][1]["contact_id"] == "ZZT-R5-1"
    assert rec.calls[0][1]["space_id"] == "364817"


# ------------------------------------------------------------------ 5. the answer tool verifier


def test_a_backed_figure_passes_and_ends_the_turn(db, contact, resolver):
    provider = Provider(
        [
            asks(call(STOCK, {"query": "SRTWT7445"}, "c1")),
            answer_call("There are 12 units.", figures=[{"value": "12", "call_id": "c1"}]),
        ]
    )
    mcp = Rec(result={"items": [{"qty": 12}], "has_result": True})

    result = run(db, contact, provider, mcp)

    assert result.status == "answered"
    assert result.reply_text == "There are 12 units."
    assert len(provider.seen) == 2


def test_a_figure_backed_by_a_numeric_string_value_passes(db, contact, resolver):
    provider = Provider(
        [
            asks(call(STOCK, {"query": "x"}, "c1")),
            answer_call("There are 12 units.", figures=[{"value": "12", "call_id": "c1"}]),
        ]
    )
    result = run(db, contact, provider, Rec(result={"items": [{"qty": "12"}], "has_result": True}))
    assert result.reply_text == "There are 12 units."


def test_thousands_separators_in_the_text_match_the_number_in_the_result(db, contact, resolver):
    provider = Provider(
        [
            asks(call(STOCK, {"query": "x"}, "c1")),
            answer_call("There are 1,200 units.", figures=[{"value": "1,200", "call_id": "c1"}]),
        ]
    )
    result = run(db, contact, provider, Rec(result={"items": [{"qty": 1200}], "has_result": True}))
    assert result.reply_text == "There are 1,200 units."
    assert len(provider.seen) == 2


def test_a_sum_the_model_made_is_sent_back_once_then_marked_not_verified(db, contact, resolver):
    bad = answer_call("Total is 12 units.", figures=[{"value": "12", "call_id": "c1"}])
    again = answer_call("Total is 12 units.", figures=[{"value": "12", "call_id": "c1"}], cid="a2")
    provider = Provider([asks(call(STOCK, {"query": "x"}, "c1")), bad, again])
    mcp = Rec(result={"items": [{"qty": 5}, {"qty": 7}], "has_result": True})

    result = run(db, contact, provider, mcp)

    assert len(provider.seen) == 3  # one repair round only
    verdict = _payload(_tool_msgs(provider.seen[2]["messages"])[-1])
    assert verdict["status"] == "invalid"
    assert "12" in verdict["message"]
    assert "(not verified)" in result.reply_text
    assert "12" not in result.reply_text


def test_a_repair_that_cites_the_real_rows_is_accepted(db, contact, resolver):
    provider = Provider(
        [
            asks(call(STOCK, {"query": "x"}, "c1")),
            answer_call("Total is 12 units.", figures=[{"value": "12", "call_id": "c1"}]),
            answer_call(
                "Two rows: 5 and 7 units.",
                figures=[{"value": "5", "call_id": "c1"}, {"value": "7", "call_id": "c1"}],
                cid="a2",
            ),
        ]
    )
    result = run(db, contact, provider, Rec(result={"items": [{"qty": 5}, {"qty": 7}], "has_result": True}))
    assert result.reply_text == "Two rows: 5 and 7 units."
    assert "(not verified)" not in result.reply_text


def test_a_number_missing_from_figures_is_a_violation(db, contact, resolver):
    provider = Provider(
        [
            asks(call(STOCK, {"query": "x"}, "c1")),
            answer_call("There are 12 units."),
            answer_call("There are 12 units.", cid="a2"),
        ]
    )
    result = run(db, contact, provider, Rec(result={"items": [{"qty": 12}], "has_result": True}))
    assert "(not verified)" in result.reply_text


def test_a_figure_citing_a_call_that_did_not_succeed_is_a_violation(db, contact, resolver):
    bad = lambda cid: answer_call(  # noqa: E731
        "There are 12 units.", figures=[{"value": "12", "call_id": "nope"}], cid=cid
    )
    provider = Provider([asks(call(STOCK, {"query": "x"}, "c1")), bad("a1"), bad("a2")])
    result = run(db, contact, provider, Rec(result={"items": [{"qty": 12}], "has_result": True}))
    assert "(not verified)" in result.reply_text


@pytest.mark.parametrize(
    "number, row",
    [
        ("12", {"12": "label"}),  # only a JSON key
        ("1234", {"id": "aaaa1234-0000-4000-8000-000000000000"}),  # only inside a UUID
        ("12", {"shipped": "2026-10-12"}),  # only inside a date
    ],
)
def test_a_number_that_only_appears_in_a_key_a_uuid_or_a_date_does_not_count(db, contact, resolver, number, row):
    text = f"There are {number} units."
    figures = [{"value": number, "call_id": "c1"}]
    provider = Provider(
        [
            asks(call(STOCK, {"query": "x"}, "c1")),
            answer_call(text, figures=figures),
            answer_call(text, figures=figures, cid="a2"),
        ]
    )
    result = run(db, contact, provider, Rec(result={"items": [row], "has_result": True}))
    assert "(not verified)" in result.reply_text
    assert number not in result.reply_text


def test_not_found_citing_a_crm_resolve_not_found_term_passes(db, contact, resolver):
    resolver.table = {"ZZTNOPE": []}
    provider = Provider(
        [
            asks(call(RESOLVE, {"terms": ["ZZTNOPE"]}, "r1")),
            answer_call(
                "I could not find ZZTNOPE.", not_found=[{"what": "ZZTNOPE", "call_id": "r1"}]
            ),
        ]
    )
    result = run(db, contact, provider)
    assert result.reply_text == "I could not find ZZTNOPE."
    assert len(provider.seen) == 2


def test_not_found_citing_an_empty_call_whose_ids_came_from_a_found_match_passes(db, contact, resolver):
    resolver.table = {"SRTWT7445": [hit("product", "SRTWT7445", UUID_A)]}
    provider = Provider(
        [
            asks(call(RESOLVE, {"terms": ["SRTWT7445"]}, "r1")),
            asks(call(STOCK, {"product_ids": [UUID_A]}, "c2")),
            answer_call(
                "No stock rows for SRTWT7445.", not_found=[{"what": "stock for SRTWT7445", "call_id": "c2"}]
            ),
        ]
    )
    result = run(db, contact, provider, Rec(result={"items": [], "has_result": False}))
    assert result.reply_text == "No stock rows for SRTWT7445."
    assert len(provider.seen) == 3


def test_not_found_citing_an_empty_call_with_unresolved_ids_gets_the_prefix(db, contact, resolver):
    cite = [{"what": "stock for SRTWT7445", "call_id": "c1"}]
    provider = Provider(
        [
            asks(call(STOCK, {"query": "SRTWT7445"}, "c1")),
            answer_call("There is no stock.", not_found=cite),
            answer_call("There is no stock.", not_found=cite, cid="a2"),
        ]
    )
    result = run(db, contact, provider, Rec(result={"items": [], "has_result": False}))

    assert len(provider.seen) == 3
    verdict = _payload(_tool_msgs(provider.seen[2]["messages"])[-1])
    assert verdict["status"] == "invalid"
    assert "stock for SRTWT7445" in verdict["message"]
    assert "I could not confirm that nothing exists for: stock for SRTWT7445." in result.reply_text
    assert "There is no stock." in result.reply_text


def test_not_found_citing_a_resolve_term_that_was_found_is_a_violation(db, contact, resolver):
    resolver.table = {"SRTWT7445": [hit("product", "SRTWT7445", UUID_A)]}
    cite = [{"what": "SRTWT7445", "call_id": "r1"}]
    provider = Provider(
        [
            asks(call(RESOLVE, {"terms": ["SRTWT7445"]}, "r1")),
            answer_call("It does not exist.", not_found=cite),
            answer_call("It does not exist.", not_found=cite, cid="a2"),
        ]
    )
    result = run(db, contact, provider)
    assert "I could not confirm that nothing exists for: SRTWT7445." in result.reply_text


def test_a_plain_text_reply_with_no_answer_call_gets_a_repair_round_asking_for_the_tool(db, contact, resolver):
    provider = Provider([plain("Here are the rows."), answer_call("Here are the rows.")])

    result = run(db, contact, provider)

    assert len(provider.seen) == 2
    nudge = json.dumps(provider.seen[1]["messages"][-1]).lower()
    assert "answer" in nudge
    assert result.reply_text == "Here are the rows."
    assert result.status == "answered"


def test_a_plain_text_reply_with_a_number_stays_unverified_if_the_tool_is_never_used(db, contact, resolver):
    provider = Provider([plain("There are 12 units."), plain("There are 12 units.")])
    result = run(db, contact, provider)
    assert len(provider.seen) == 2
    nudge = provider.seen[1]["messages"][-1]["content"].lower()
    assert any(p in nudge for p in ("answer tool", "`answer`", "'answer'", '"answer"', "answer function"))
    assert "(not verified)" in result.reply_text
    assert "12" not in result.reply_text


# ------------------------------------------------------------------ 6. the limit path


def _names_in_last_call(provider):
    return _names(provider.seen[-1]["tools"])


def test_the_final_call_offers_only_the_answer_tool(db, contact, resolver):
    _budget(db, chatbot_agent_max_rounds=1)
    provider = Provider([asks(call(STOCK, {"query": "x"}, "c1")), answer_call("Partial result.")])

    result = run(db, contact, provider)

    assert result.status == "limited" and result.limit_hit == "rounds"
    assert _names_in_last_call(provider) == [ANSWER]


def test_empty_not_checked_gets_the_fixed_sentence_naming_the_rest_of_the_question(db, contact, resolver):
    _budget(db, chatbot_agent_max_rounds=1)
    provider = Provider([asks(call(STOCK, {"query": "x"}, "c1")), answer_call("Partial result.")])

    result = run(db, contact, provider)

    assert "Partial result." in result.reply_text
    assert "I stopped at the rounds limit before finishing, so I did not check:" in result.reply_text
    assert "the rest of your question" in result.reply_text


def test_the_sentence_names_a_refused_tool_by_a_plain_label(db, contact, resolver):
    _budget(db, chatbot_agent_max_rounds=1)
    provider = Provider([asks(call(GRN, {"query": "x"}, "c1")), answer_call("Partial result.")])

    result = run(db, contact, provider)  # the user does not hold procurement.grn.view

    assert _payload(_tool_msgs(provider.seen[1]["messages"])[0])["status"] == "denied"
    assert "I stopped at the rounds limit before finishing, so I did not check:" in result.reply_text
    assert "the rest of your question" not in result.reply_text
    assert GRN not in result.reply_text


def test_a_failed_tool_is_named_in_the_sentence(db, contact, resolver):
    _budget(db, chatbot_agent_max_rounds=1)
    provider = Provider([asks(call(STOCK, {"query": "x"}, "c1")), answer_call("Partial result.")])

    result = run(db, contact, provider, Rec(exc=RuntimeError("down")))

    assert "I did not check:" in result.reply_text
    assert "the rest of your question" not in result.reply_text
    assert STOCK not in result.reply_text


def test_the_model_stating_not_checked_is_not_overwritten(db, contact, resolver):
    _budget(db, chatbot_agent_max_rounds=1)
    provider = Provider(
        [
            asks(call(STOCK, {"query": "x"}, "c1")),
            answer_call("Partial result.", not_checked=["incoming shipments"]),
        ]
    )
    result = run(db, contact, provider)
    assert "I stopped at the" not in result.reply_text
    assert "incoming shipments" in result.reply_text


def test_the_time_limit_is_named_time(db, contact, resolver):
    clock = {"t": 0.0}
    provider = Provider(
        [asks(call(STOCK, {"query": "x"}, "c1")), answer_call("Partial result.")],
        on_call=lambda n: clock.__setitem__("t", clock["t"] + 100.0) if n == 1 else None,
    )
    result = run(db, contact, provider, clock=lambda: clock["t"])
    assert result.limit_hit == "seconds"
    assert "I stopped at the time limit before finishing, so I did not check:" in result.reply_text


def test_the_input_token_limit_is_named_token(db, contact, resolver):
    _budget(db, chatbot_agent_max_input_tokens=10_000)
    provider = Provider(
        [asks(call(STOCK, {"query": "x"}, "c1"), prompt=10_001), answer_call("Partial result.")]
    )
    result = run(db, contact, provider)
    assert result.limit_hit == "input_tokens"
    assert "I stopped at the token limit before finishing, so I did not check:" in result.reply_text


# ------------------------------------------------------------------ 7. the fallback prompt


def test_the_fallback_system_prompt_carries_the_round_5_rules():
    from app.services.ai_prompt_registry import _chatbot_agent_fallback

    text = _chatbot_agent_fallback()
    low = text.lower()
    assert "crm_resolve" in text
    assert "crm_lookup_resolve" not in text
    assert "answer tool" in low
    assert "crm_report_ask" in text
    assert re.search(r"(never|not|don't)[^.]{0,80}\b(add|adding|sum|summing)\b", low)
    assert "empty" in low
    assert "not_found" in low or "not found" in low
    assert "ambiguous" in low
    assert not re.search("[" + chr(0x2013) + chr(0x2014) + "]", text)


# ------------------------------------------------------------------ 8. the migration


def test_the_agent_migration_has_no_create_schema_statement():
    versions = Path(__file__).resolve().parents[3] / "alembic" / "versions"
    import ast

    tree = ast.parse((versions / "agp1_0001_agent_foundation.py").read_text())
    docstring = ast.get_docstring(tree, clean=False)
    strings = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != docstring
    ]
    # Comments may explain the omission; no executed statement may contain it.
    assert [s for s in strings if "create schema" in s.lower()] == []
