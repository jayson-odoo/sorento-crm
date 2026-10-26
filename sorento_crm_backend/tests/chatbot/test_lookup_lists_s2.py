"""CHAT-SLIM-INDEX S2, red tests: spec words, spec numbers, file types, prompt translations as data.

Contract: PLAN-chat-lookup-lists-25oct.md, "S2 code contract". Covers AC-6, AC-7, AC-8 and AC-4
("tandas" / "马桶" now through PROMPT_SYNONYMS with NO embedder). Postgres only (blank schema
fixture), own seed chain, stub embedder, fake names (ZZ prefix).
Assumed beyond the contract: `number_hits(message, db)` takes a session; `load_rows(db)` returns the
spec and file_type rows too, with PROMPT_SYNONYMS merged into the row texts.
"""
from __future__ import annotations

import uuid

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.base import set_company_scope
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.chatbot.head import lookup_lists as ll
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot._attach_world import World
from tests.chatbot.conftest import session_factory  # noqa: F401

HDR_SPEC = "Spec candidates (pick one only if the message means it):"
HDR_FILE = "File type candidates (pick one only if the message means it):"
HDR_CAT = "Category candidates (pick one only if the message means it):"
HDR_CHAN = "Sales channel candidates (pick one only if the message means it):"


def seed_world(session_factory) -> None:
    """Registry word + number keys, one product holding them, categories, a photo / drawing / certificate type."""
    db = session_factory()
    reg = lambda key, label, dt, **kw: ProductSpecRegistry(id=str(uuid.uuid4()), spec_key=key, label=label, data_type=dt, **kw)  # noqa: E731
    db.add_all([
        reg("zz_finish", "ZZ Finish", "enum", allowed_values=["gunmetal", "matt black"], synonyms={"gunmetal": ["gun metal"]}),
        reg("zz_trap_len", "ZZ Trap Length", "numeric", unit="mm"),
        reg("zz_width", "ZZ Width", "numeric", unit="mm"),
        reg("zz_depth", "ZZ Depth", "numeric", unit="mm"),
    ])
    db.commit()
    w = World(session_factory)
    w.category("Water Closet")
    w.type("Photo", code="photo")
    w.type("Drawing", code="drawing")
    w.type("Certificate", cert=True, code="certificate")
    p = w.product("ZZS2P1")
    w.db.add(ProductSpecifications(id=str(uuid.uuid4()), product_id=p.id, values={
        "zz_finish": {"value": "gunmetal"}, "zz_trap_len": {"value": 200}, "zz_width": {"value": 200}, "zz_depth": {"value": 350},
    }))
    w.commit()


def scoped(session_factory):
    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    return db


def labels(hits: dict, name: str) -> list[str]:
    return [h.row.label.casefold() for h in hits.get(name, [])]


DIM = 64


def meaning_embed(group: set[str]):
    """Strings in `group` share axis 0; every other string a stable axis of its own."""
    import hashlib

    def embed(texts):
        out = []
        for t in texts:
            v = [0.0] * 4096
            v[0 if t.casefold().strip() in group else int(hashlib.md5(t.encode()).hexdigest(), 16) % 4095 + 1] = 1.0
            out.append(v)
        return out

    return embed


# ------------------------------------------------------------------ constants, data, render


def test_s2_constants_and_headers():
    assert ll.HEADER_NOUN["spec"] == "Spec" and ll.HEADER_NOUN["file_type"] == "File type"
    assert ll.TOP_K["spec"] == 10 and ll.TOP_K["file_type"] == 5
    assert ll.header("spec") == HDR_SPEC and ll.header("file_type") == HDR_FILE


def test_prompt_synonyms_hold_the_v63_translations_as_data():
    ps = ll.PROMPT_SYNONYMS

    def texts(list_name: str, label: str) -> set[str]:
        rows = {k.casefold(): v for k, v in ps[list_name].items()}
        return {t.casefold() for t in rows[label]}

    assert {"tandas", "mangkuk tandas", "马桶"} <= texts("category", "water closet")
    assert {"paip air", "水龙头"} <= texts("category", "water tap")
    assert {"sinki dapur", "厨房水槽"} <= texts("category", "kitchen sink")
    assert {"gambar", "foto"} <= texts("file_type", "photo")
    assert "lukisan" in texts("file_type", "drawing")
    assert any("sijil" in {t.casefold() for t in v} for v in ps["file_type"].values())


def _hit(list_name: str, label: str) -> ll.Hit:
    return ll.Hit(ll.LookupRow(list_name, label, label, (label,)), "x", 1.0, 0.0)


def test_render_default_order_is_category_spec_file_type_sales_channel():
    hits = {n: [_hit(n, f"{n} one")] for n in ("sales_channel", "file_type", "spec", "category")}
    assert ll.render(hits) == [
        HDR_CAT, "- category one", HDR_SPEC, "- spec one", HDR_FILE, "- file_type one", HDR_CHAN, "- sales_channel one",
    ]


def test_top_k_cuts_spec_to_ten_and_file_type_to_five():
    spec = [ll.LookupRow("spec", f"s{i}", f"Spec {i:02d}", ("tint",)) for i in range(12)]
    ft = [ll.LookupRow("file_type", f"f{i}", f"File {i}", ("sheet",)) for i in range(7)]
    assert len(ll.shortlist("tint", spec, None)["spec"]) == 10
    assert len(ll.shortlist("sheet", ft, None)["file_type"]) == 5


# ------------------------------------------------------------------ numbers


@pytest.mark.parametrize("text", ["200 mm", "200mm", "20 cm", "20cm", "0.2 m", "0.2m", "200 MM"])
def test_normalise_number_reads_the_same_length_the_same(text):
    assert ll.normalise_number(text) == "200mm"


def test_normalise_number_sizes_and_garbage():
    assert ll.normalise_number("600 x 400 mm") == ll.normalise_number("600x400mm") is not None
    assert ll.normalise_number("60 x 40 cm") == ll.normalise_number("600x400mm")
    for bad in ("", "abc", "mm", "water closet"):
        assert ll.normalise_number(bad) is None, bad


def test_number_hits_offer_every_spec_holding_the_value(session_factory):
    seed_world(session_factory)
    db = scoped(session_factory)
    for message in ("any basin with 200mm trap", "200 mm", "20 cm trap"):
        got = ll.number_hits(message, db)
        assert all(h.row.list_name == "spec" for h in got), got
        assert sorted(h.row.label.casefold() for h in got) == ["zz trap length 200mm (zz_trap_len: 200)", "zz width 200mm (zz_width: 200)"], (message, got)


def test_a_number_no_spec_holds_offers_nothing(session_factory):
    seed_world(session_factory)
    db = scoped(session_factory)
    assert ll.number_hits("a 999mm basin", db) == []
    assert ll.number_hits("no numbers here", db) == []


@pytest.mark.parametrize("message", ["stock SRTWC200-SH", "where is PS200-0200", "DO20020012 status", "SRT200 please"])
def test_a_product_code_or_document_number_never_yields_a_number_hit(session_factory, message):
    seed_world(session_factory)
    assert ll.number_hits(message, scoped(session_factory)) == []


# ------------------------------------------------------------------ spec words, file types, categories via load_rows


def test_load_rows_carries_spec_and_file_type_rows(session_factory):
    seed_world(session_factory)
    rows = ll.load_rows(scoped(session_factory))
    spec = {r.label.casefold() for r in rows if r.list_name == "spec"}
    assert "zz finish gunmetal (zz_finish: gunmetal)" in spec and "zz finish matt black (zz_finish: matt black)" in spec, spec
    assert not any("trap length" in s for s in spec), "number keys are not word rows"
    files = {r.label.casefold() for r in rows if r.list_name == "file_type"}
    assert {"photo", "drawing", "certificate"} <= files, files


def test_spec_word_by_spelling_synonym_and_typo(session_factory):
    seed_world(session_factory)
    rows = ll.load_rows(scoped(session_factory))
    for word in ("gunmetal", "gun metal", "gunmetl"):
        assert "zz finish gunmetal (zz_finish: gunmetal)" in labels(ll.shortlist(f"any {word} basin", rows, None), "spec"), word


def test_spec_word_through_stubbed_meaning(session_factory):
    seed_world(session_factory)
    rows = ll.load_rows(scoped(session_factory))
    embed = meaning_embed({"anthracite", "gunmetal", "gun metal"})
    assert "zz finish gunmetal (zz_finish: gunmetal)" in labels(ll.shortlist("anthracite basin", rows, embed), "spec")
    assert labels(ll.shortlist("anthracite basin", rows, None), "spec") == []


@pytest.mark.parametrize("word,expect", [("gambar", "photo"), ("lukisan", "drawing"), ("sijil", "certificate")])
def test_file_type_words_without_an_embedder(session_factory, word, expect):
    seed_world(session_factory)
    rows = ll.load_rows(scoped(session_factory))
    assert expect in labels(ll.shortlist(f"hantar {word} produk", rows, None), "file_type"), word


@pytest.mark.parametrize("word", ["tandas", "马桶"])
def test_category_translations_without_an_embedder(session_factory, word):
    seed_world(session_factory)
    rows = ll.load_rows(scoped(session_factory))
    assert "water closet" in labels(ll.shortlist(word, rows, None), "category"), word


# ------------------------------------------------------------------ per-list meaning floors (text-embedding-3-small)


def _at(cosine: float):
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


def test_floor_by_list_table():
    # CHAT-V66-REGRESSIONS: recalibrated per list on 1,200 labelled real messages (owner ruling 26 Oct).
    assert ll.FLOOR_MEANING_BY_LIST == {
        "category": 0.57, "sales_channel": 0.55, "brand": 0.58, "spec": 0.74, "file_type": 0.59, "customer": 0.53,
        "promotion_kind": 0.66, "location": 0.55, "salesperson": 0.55,
    }
    assert ll.FLOOR_SPELLING == 0.5


@pytest.mark.parametrize("list_name,low,high", [
    ("category", 0.56, 0.58), ("file_type", 0.58, 0.60), ("spec", 0.73, 0.75), ("sales_channel", 0.54, 0.56),
])
def test_meaning_floor_is_per_list(list_name, low, high):
    row = ll.LookupRow(list_name, "k", "Target Row", ("target",))
    assert ll.shortlist("anchor", [row], _at(low)).get(list_name, []) == [], (list_name, low)
    assert [h.row.label for h in ll.shortlist("anchor", [row], _at(high))[list_name]] == ["Target Row"], (list_name, high)


def test_a_list_missing_from_the_floor_table_uses_055():
    row = ll.LookupRow("zz_other", "k", "Target Row", ("target",))
    assert ll.shortlist("anchor", [row], _at(0.54)).get("zz_other", []) == []
    assert len(ll.shortlist("anchor", [row], _at(0.56))["zz_other"]) == 1
