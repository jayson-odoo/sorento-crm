"""CHAT-SLIM-INDEX review round, red tests: spec coverage (B3), code-like categories (B4), CPU caps (C1, C2),
cache (C3), label sanitising (C4), fail-closed DB errors (C5). Postgres only, fake data (Zz prefix).

B3 sources: the registry stores units mm (many keys), L `capacity_litre`, hp `power_hp`, oz `capacity_oz`
(app/services/product_spec_registry.py:539-1053); a boolean key stores {"true": [phrases]} and grounding binds
`stored = str(value).strip().lower() in {"true","yes","1"}` (head/grounding.py:171) and accepts a bool spec_value
(grounding.py:715); a numeric key with word synonyms ("2": ["double bowl"]) is registry.py:1188-1193
(grounding reads a numeric spec_value as `float(str(value).split()[0])`, grounding.py:703-709).
"""
from __future__ import annotations

import json
import time
import types
import uuid

import numpy as np

import app.main  # noqa: F401  isort:skip
from sqlalchemy import text

from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services import contact_field_reveal_service
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot._attach_world import World
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access  # noqa: F401
from tests.chatbot.test_lookup_lists_engine import _fresh_caches, _quiet, _seed_prompt  # noqa: F401
from tests.chatbot.test_lookup_lists_s2 import scoped
from tests.chatbot.test_lookup_lists_s3 import HDR, seed_world3


def _reg(key, label, dt, **kw):
    return ProductSpecRegistry(id=str(uuid.uuid4()), spec_key=key, label=label, data_type=dt, **kw)


def _seed_coverage(session_factory) -> None:
    db = session_factory()
    db.add_all([
        _reg("zz_rimless", "ZZ Rimless", "boolean", allowed_values=[], synonyms={"true": ["rimless", "zz rimless"]}, value_labels={}),
        _reg("zz_bowls", "ZZ Bowls", "numeric", synonyms={"_self": ["bowl", "bowls"], "1": ["single bowl"], "2": ["double bowl", "twin bowl"]}),
        _reg("zz_capacity", "ZZ Capacity", "numeric", unit="L", synonyms={"_self": ["litre", "liter"]}),
        _reg("zz_power", "ZZ Power", "numeric", unit="hp", synonyms={"_self": ["horsepower", "hp"]}),
        _reg("zz_oz", "ZZ Cup", "numeric", unit="oz", synonyms={"_self": ["oz", "ounce"]}),
    ])
    db.commit()
    w = World(session_factory)
    p = w.product("ZZREV1")
    w.db.add(ProductSpecifications(id=str(uuid.uuid4()), product_id=p.id, values={
        "zz_rimless": {"value": True}, "zz_bowls": {"value": 2}, "zz_capacity": {"value": 10},
        "zz_power": {"value": 2}, "zz_oz": {"value": 16},
    }))
    w.commit()


def _spec_lines(session_factory, message: str) -> list[str]:
    db = scoped(session_factory)
    rows = ll.load_rows(db)
    hits = ll.shortlist(message, rows, None)
    numbers = ll.number_hits(message, db)
    out = [h.row.label for h in numbers] + [h.row.label for h in hits.get("spec", [])]
    return out


# ------------------------------------------------------------------ B3


def test_a_yes_no_key_word_gets_a_spec_line_with_its_key_and_true(session_factory):
    _seed_coverage(session_factory)
    lines = _spec_lines(session_factory, "any rimless water closet")
    assert any(ln.startswith("ZZ Rimless") and ln.endswith("(zz_rimless: true)") for ln in lines), lines


def test_a_numeric_key_spelled_in_words_gets_a_spec_line_with_the_number(session_factory):
    _seed_coverage(session_factory)
    lines = _spec_lines(session_factory, "double bowl kitchen sink")
    assert any(ln.startswith("ZZ Bowls") and ln.endswith("(zz_bowls: 2)") for ln in lines), lines
    assert not any(ln.endswith("(zz_bowls: 1)") for ln in lines), lines


def test_numbers_in_litre_hp_and_oz_get_spec_lines_in_the_keys_own_unit(session_factory):
    _seed_coverage(session_factory)
    for message, tail in (
        ("a 10 litre bin", "(zz_capacity: 10)"), ("a 10L bin", "(zz_capacity: 10)"),
        ("a 2 hp pump", "(zz_power: 2)"), ("a 2hp pump", "(zz_power: 2)"), ("a 16 oz cup", "(zz_oz: 16)"),
    ):
        assert any(ln.endswith(tail) for ln in _spec_lines(session_factory, message)), (message, tail)


def test_a_litre_hp_or_oz_number_no_product_holds_offers_nothing(session_factory):
    _seed_coverage(session_factory)
    assert not [ln for ln in _spec_lines(session_factory, "a 99 litre bin and 7 hp and 3 oz") if "zz_" in ln]


# ------------------------------------------------------------------ B4


def test_a_category_whose_code_spells_near_a_product_code_is_not_offered_for_that_code():
    row = ll.LookupRow("category", "k", "SRTWC Water Closets", ("SRTWC Water Closets", "SRTWC"))
    assert ll.shortlist("stock SRTWC286", [row], None).get("category", []) == []
    assert ll.shortlist("stock SRTWC286-SH", [row], None).get("category", []) == []


# ------------------------------------------------------------------ C1, C2


def _word(i: int) -> str:
    return "w" + chr(97 + i % 26) + chr(97 + (i // 26) % 26) + chr(97 + i // 676)


def test_pieces_come_from_the_first_forty_words_only():
    words = [_word(i) for i in range(600)]
    out = ll.pieces(" ".join(words))
    assert len(out) <= 40 + 39 + 38 + 37, len(out)
    joined = " ".join(out).split()
    assert words[39] in joined and words[40] not in joined and words[599] not in joined


def test_number_hits_read_at_most_three_distinct_lengths(session_factory):
    db = session_factory()
    db.add(_reg("zz_tl", "ZZ Tl", "numeric", unit="mm"))
    db.commit()
    w = World(session_factory)
    for i in range(1, 11):
        p = w.product(f"ZZLEN{i}")
        w.db.add(ProductSpecifications(id=str(uuid.uuid4()), product_id=p.id, values={"zz_tl": {"value": i * 10}}))
    w.commit()
    message = " ".join(f"{i * 10}mm" for i in range(1, 11)) + " 10 mm"
    got = ll.number_hits(message, scoped(session_factory))
    # DIMENSION-ANY: each of the three lengths also leads with its any-dimension size line.
    assert sorted(h.row.label for h in got) == sorted(
        [*(f"ZZ Tl {i * 10}mm (zz_tl: {i * 10})" for i in (1, 2, 3)), *(f"Size {i * 10}mm, any dimension (size: {i * 10})" for i in (1, 2, 3))]
    ), got


# ------------------------------------------------------------------ C3


from tests.chatbot._embed_http import patch_openai_embeddings


def _fake_client(calls: list[list[str]]):
    class _Emb:
        def create(self, *, model, input):
            calls.append(list(input))
            return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[1.0] + [0.0] * 1535) for _ in input])

    return types.SimpleNamespace(embeddings=_Emb())


def test_row_vectors_are_cached_as_float32(monkeypatch):
    from app.services import llm_provider

    ll._cache.clear()
    calls: list[list[str]] = []
    patch_openai_embeddings(monkeypatch, _fake_client(calls).embeddings.create)
    embed = ll.provider_embedder("sk-test")
    embed(["zzrow one", "zzrow two"])
    assert ll._cache, "nothing was cached"
    for vec in ll._cache.values():
        arr = np.asarray(vec)
        assert isinstance(vec, np.ndarray) and vec.dtype == np.float32, type(vec)
        assert arr.nbytes <= 1536 * 4 + 64, arr.nbytes


def test_message_pieces_never_evict_or_replace_the_row_vectors(monkeypatch):
    from app.services import llm_provider

    ll._cache.clear()
    calls: list[list[str]] = []
    patch_openai_embeddings(monkeypatch, _fake_client(calls).embeddings.create)
    monkeypatch.setattr(ll, "_CACHE_CAP", 300)
    rows = [ll.LookupRow("customer", f"c{i}", f"Zzrow {i}", (f"zzrow {i}",)) for i in range(100)]
    embed = ll.provider_embedder("sk-test")
    embed(ll.row_texts(rows))
    warmed = len(calls)
    row_set = set(ll.row_texts(rows))
    for n in range(50):
        message = " ".join(_word(1000 + n * 40 + i) for i in range(40))  # plain words: code-like ones never reach the embedder
        ll.shortlist(message, rows, embed)
    assert embed.is_cached(ll.row_texts(rows)), "a row vector was evicted by message pieces"
    again = [t for batch in calls[warmed:] for t in batch if t in row_set]
    assert again == [], f"{len(again)} row texts were embedded again"


# ------------------------------------------------------------------ C4


def _hit(label: str) -> ll.Hit:
    return ll.Hit(ll.LookupRow("brand", label, label, (label,)), "x", 1.0, 0.0)


def test_render_collapses_whitespace_in_a_label_to_one_line():
    out = ll.render({"brand": [_hit("Zz\nBrand\r\nName\twith\ttabs  and   gaps")]})
    assert out[1] == "- Zz Brand Name with tabs and gaps", out
    assert len(out) == 2 and all("\n" not in ln and "\r" not in ln and "\t" not in ln for ln in out)


def test_render_caps_a_label_at_120_characters():
    out = ll.render({"brand": [_hit("Zz" + "x" * 400)]})
    assert 0 < len(out[1]) - 2 <= 120, len(out[1])


# ------------------------------------------------------------------ C5


def _turn(session_factory, stub_access, monkeypatch, text_body: str) -> tuple[list[str], object]:
    _seed_prompt(session_factory, monkeypatch, marker=True)
    seed_world3(session_factory)
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
        "messageId": f"ZZT-rv-{uuid.uuid4().hex[:6]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
        "traffic": "incoming", "message": {"type": "text", "text": text_body}}}
    result = engine_mod.run_turn(_envelope(message=message), session_factory=session_factory)
    return seen[-1].splitlines(), result


def test_a_db_error_in_the_salesperson_check_leaves_the_turn_answering_with_no_block(session_factory, seeded, stub_access, monkeypatch):
    def broken(db, contact):
        db.execute(text("SELECT * FROM zz_no_such_table_sales"))

    monkeypatch.setattr(contact_field_reveal_service, "granted_keys", broken)
    lines, result = _turn(session_factory, stub_access, monkeypatch, "zzsrt zz sean i")
    assert HDR["salesperson"] not in lines, lines
    assert HDR["brand"] in lines, ("the transaction was left aborted", lines)
    assert (result.reply or {}).get("text"), result


def test_a_db_error_in_the_customer_check_leaves_the_turn_answering_with_no_block(session_factory, seeded, stub_access, monkeypatch):
    from app.services import contact_customer_scope

    def broken(db, contact):
        db.execute(text("SELECT * FROM zz_no_such_table_customers"))

    monkeypatch.setattr(contact_customer_scope, "contact_customer_scope", broken)
    lines, result = _turn(session_factory, stub_access, monkeypatch, "zzsrt zz sean i")
    assert "Customer candidates (pick one only if the message means it):" not in lines, lines
    assert HDR["brand"] in lines, ("the transaction was left aborted", lines)
    assert (result.reply or {}).get("text"), result
