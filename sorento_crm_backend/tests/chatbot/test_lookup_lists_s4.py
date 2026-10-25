"""CHAT-SLIM-INDEX S4, red tests: customers (list "customer"), one-span-one-list, visibility, long warm-up.

Contract: PLAN-chat-lookup-lists-25oct.md "S4 code contract" + "Access scoping". Sources cited for the coder:
- rows = active customers (customers_select.py:51-53 `_customers_select`, is_active filter; label `customer_name`,
  customers_select.py:84), company scoped by the session.
- a customer-scoped (dealer) contact: `contact_customer_scope.contact_customer_scope(...).enforced`
  (services/contact_customer_scope.py:52-54: linked customers and no active office access type) may only see its own
  customers (`_contact_scope.enforce_customer_scope`, api/v1/order_management/_contact_scope.py:32-77: any other id or
  name is refused 403 `customer_not_permitted`). Pinned here: a dealer's Customer block lists only its linked customers.
- staff: an active office access type ("Sorento Office", contact_customer_scope.py:21) is not enforced, sees every active customer.
Assumed: `load_rows(db, *, include_customers: bool = False)`; the engine passes it (and restricts a dealer to its own links).
Postgres only, fake names (Zz prefix).
"""
from __future__ import annotations

import json
import threading
import time
import types
import uuid

import app.main  # noqa: F401  isort:skip
from app.models.base import set_company_scope
from app.models.order import Customer
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import customer as seed_customer
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_customer_scope_lane import _give_access_type, _link_customers, _other_customer
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access  # noqa: F401
from tests.chatbot.test_lookup_lists_engine import _fresh_caches, _quiet, _seed_prompt  # noqa: F401
from tests.chatbot.test_lookup_lists_s2 import scoped

HDR = "Customer candidates (pick one only if the message means it):"
QUARTZ, MARBLE = "Zzquartz Trading", "Zzmarble Holdings"


def _row(label: str, *extra: str) -> ll.LookupRow:
    return ll.LookupRow("customer", label, label, (label, *extra))


def labels(hits: dict, name: str) -> list[str]:
    return [h.row.label for h in hits.get(name, [])]


def _cos_embed(cosine: float):
    import math

    def embed(texts):
        out = []
        for t in texts:
            v = [0.0] * 4096
            if t.casefold().strip() == "anchor":
                v[0] = 1.0
            elif t.casefold().strip() == "target":
                v[0], v[1] = cosine, math.sqrt(1 - cosine * cosine)
            else:
                v[2 + sum(map(ord, t)) % 4000] = 1.0
            out.append(v)
        return out

    return embed


# ------------------------------------------------------------------ constants, floors, render


def test_customer_constants():
    assert ll.HEADER_NOUN["customer"] == "Customer" and ll.TOP_K["customer"] == 5
    assert ll.header("customer") == HDR
    assert ll.FLOOR_MEANING_BY_LIST["customer"] == 0.53 and ll.FLOOR_SPELLING == 0.5


def test_customer_meaning_floor_is_053():
    row = ll.LookupRow("customer", "k", "Target Row", ("target",))
    assert ll.shortlist("anchor", [row], _cos_embed(0.52)).get("customer", []) == []
    assert [h.row.label for h in ll.shortlist("anchor", [row], _cos_embed(0.54))["customer"]] == ["Target Row"]


def test_customer_top_k_is_five():
    rows = [ll.LookupRow("customer", f"c{i}", f"Zzcust {i}", ("zzcust",)) for i in range(8)]
    assert len(ll.shortlist("zzcust", rows, None)["customer"]) == 5


def test_render_order_ends_with_customer():
    names = ("customer", "sales_channel", "location", "salesperson", "promotion_kind", "brand", "file_type", "spec", "category")
    hit = lambda n: ll.Hit(ll.LookupRow(n, n, f"{n} one", (n,)), "x", 1.0, 0.0)  # noqa: E731
    out = ll.render({n: [hit(n)] for n in names})
    heads = [ln for ln in out if not ln.startswith("- ")]
    assert heads[-1] == HDR and heads[-2] == ll.header("sales_channel"), heads


# ------------------------------------------------------------------ one span, one list


def test_a_category_channel_location_or_brand_word_feeds_no_customer_row():
    cust = [_row("Tiles"), _row("Dealer"), _row("ZZBRW"), _row("Zzsrt"), _row("Zztilesmith Supplies")]
    other = [
        ll.LookupRow("category", "c", "Tiles", ("Tiles",)),
        ll.LookupRow("sales_channel", "dealer", "dealer", ("dealer",)),
        ll.LookupRow("location", "w", "ZZ Bravo (ZZBRW)", ("ZZ Bravo", "ZZBRW")),
        ll.LookupRow("brand", "b", "Zzsorento (Zzsrt)", ("Zzsorento", "Zzsrt")),
    ]
    rows = [*cust, *other]
    for word in ("tiles", "dealer", "zzbrw"):
        assert ll.shortlist(word, rows, None).get("customer", []) == [], word
    assert ll.shortlist("zzsrt", rows, None, brand_words=frozenset({"zzsrt"})).get("customer", []) == []
    # control: a word that is no other list's word still reaches its customer
    assert labels(ll.shortlist("zztilesmith", rows, None), "customer") == ["Zztilesmith Supplies"]


# ------------------------------------------------------------------ load_rows


def _seed_customers(session_factory):
    db = session_factory()
    seed_customer(db, company_id=DEFAULT_COMPANY_ID, name=QUARTZ)
    seed_customer(db, company_id=DEFAULT_COMPANY_ID, name=MARBLE)
    gone = seed_customer(db, company_id=DEFAULT_COMPANY_ID, name="Zzinactive Ltd")
    gone.is_active = False
    db.commit()


def test_customer_rows_are_off_by_default_and_active_only_when_asked(session_factory):
    _seed_customers(session_factory)
    db = scoped(session_factory)
    assert not [r for r in ll.load_rows(db) if r.list_name == "customer"]
    on = {r.label for r in ll.load_rows(db, include_customers=True) if r.list_name == "customer"}
    assert on == {QUARTZ, MARBLE}, on


def test_customer_rows_follow_the_session_company_scope(session_factory):
    _seed_customers(session_factory)
    db = session_factory()
    set_company_scope(db, frozenset({str(uuid.uuid4())}))
    assert not [r for r in ll.load_rows(db, include_customers=True) if r.list_name == "customer"]


def test_a_customer_name_typo_is_offered(session_factory):
    _seed_customers(session_factory)
    rows = ll.load_rows(scoped(session_factory), include_customers=True)
    assert labels(ll.shortlist("zzquartz tradin", rows, None), "customer") == [QUARTZ]


# ------------------------------------------------------------------ engine: visibility


def _turn(session_factory, stub_access, monkeypatch, *, role: str) -> list[str]:
    _seed_prompt(session_factory, monkeypatch, marker=True)
    _seed_customers(session_factory)
    if role == "dealer":
        _link_customers(session_factory, QUARTZ)
    elif role == "unlinked":
        pass  # no linked customer, no office access type
    else:
        _give_access_type(session_factory, "Sorento Office")
    monkeypatch.setattr(ll, "EMBED", None, raising=False)
    seen: list[str] = []

    def parse(config, user_block):
        seen.append(str(user_block))
        return _quiet()

    monkeypatch.setattr(parser_mod, "parse", parse)
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    stub_access()
    message = {"event_type": "message.received", "contact": {"id": CONTACT_ID}, "message": {
        "messageId": f"ZZT-s4-{uuid.uuid4().hex[:6]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
        "traffic": "incoming", "message": {"type": "text", "text": f"{QUARTZ} and {MARBLE}".lower()}}}
    engine_mod.run_turn(_envelope(message=message), session_factory=session_factory)
    return seen[-1].splitlines()


def test_staff_contact_gets_a_customer_block_with_both_names(session_factory, seeded, stub_access, monkeypatch):
    lines = _turn(session_factory, stub_access, monkeypatch, role="staff")
    assert HDR in lines and f"- {QUARTZ}" in lines and f"- {MARBLE}" in lines, lines


def test_dealer_contact_is_offered_only_its_own_customer(session_factory, seeded, stub_access, monkeypatch):
    lines = _turn(session_factory, stub_access, monkeypatch, role="dealer")
    assert HDR in lines and f"- {QUARTZ}" in lines, lines
    assert f"- {MARBLE}" not in lines and not any(MARBLE in ln for ln in lines if ln.startswith("- ")), lines


def test_contact_with_no_link_and_no_office_access_gets_no_customer_block(session_factory, seeded, stub_access, monkeypatch):
    lines = _turn(session_factory, stub_access, monkeypatch, role="unlinked")
    assert HDR not in lines, lines
    assert not any(ln.startswith("- ") and (QUARTZ in ln or MARBLE in ln) for ln in lines), lines


# ------------------------------------------------------------------ long warm-up


def test_a_warm_up_longer_than_the_turn_budget_still_completes_and_turns_never_wait(monkeypatch):
    from app.services import llm_provider

    monkeypatch.setattr(ll, "EMBED_CHUNK", 50)
    ll._cache.clear()
    calls: list[int] = []

    class _Embeddings:
        def create(self, *, model, input):
            calls.append(len(input))
            time.sleep(0.9)
            return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[1.0, 0.0]) for _ in input])

    client = types.SimpleNamespace(embeddings=_Embeddings())
    monkeypatch.setattr(llm_provider.OpenAIProvider, "_client", lambda self, **kw: client)
    rows = [ll.LookupRow("customer", f"c{i}", f"Zzcust {i}", (f"zzcust {i}",)) for i in range(300)]
    embed = ll.provider_embedder("sk-test")

    t0 = time.monotonic()
    ll.warm(rows, embed)
    assert time.monotonic() - t0 < 0.5, "warm must return at once"
    assert ll.usable_embedder(rows, embed) is None, "a turn during warm-up is spelling only"
    assert time.monotonic() - t0 < 0.5, "a turn never waits on the warm-up"
    deadline = time.monotonic() + 14
    while time.monotonic() < deadline and not embed.is_cached(ll.row_texts(rows)):
        time.sleep(0.2)
    assert embed.is_cached(ll.row_texts(rows)), f"warm-up died at the per-call budget after {len(calls)} chunk(s)"
    assert ll.usable_embedder(rows, embed) is embed
