"""CHAT-SLIM-INDEX S1, red tests of `head/lookup_lists.py` (pure functions, no database).

Contract: documentation/plans/chatbot/PLAN-chat-lookup-lists-25oct.md, "S1 code contract".
Covers AC-3, AC-4, AC-5, AC-11 (brand word -> no category), AC-12, AC-13.
The embedder is a deterministic stub: no network. Fake names only.
"""
from __future__ import annotations

import hashlib
import math

import pytest

from app.services.chatbot.head import candidates
from app.services.chatbot.head import lookup_lists as ll

HEADER_CATEGORY = "Category candidates (pick one only if the message means it):"
HEADER_CHANNEL = "Sales channel candidates (pick one only if the message means it):"

DIM = 4096
#: Strings the stub embeds onto one shared axis: the "water closet" concept in four languages.
WC_CONCEPT = {"water closet", "wc", "tandas", "马桶", "toilet"}


def _axis(text: str) -> int:
    return int(hashlib.md5(text.casefold().encode()).hexdigest(), 16) % (DIM - 1) + 1


def stub_embed(texts: list[str]) -> list[list[float]]:
    """One-hot vectors; the water-closet concept shares axis 0, every other string its own axis."""
    out = []
    for t in texts:
        v = [0.0] * DIM
        v[0 if t.casefold().strip() in WC_CONCEPT else _axis(t)] = 1.0
        out.append(v)
    return out


def cos_embed(pairs: dict[str, float]):
    """Vectors with a chosen cosine to the unit axis 0 for the named strings; others orthogonal."""

    def embed(texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * DIM
            key = t.casefold().strip()
            if key == "anchor":
                v[0] = 1.0
            elif key in pairs:
                c = pairs[key]
                v[0] = c
                v[1] = math.sqrt(1 - c * c)
            else:
                v[_axis(t)] = 1.0
            out.append(v)
        return out

    return embed


def cat(key: str, label: str, *texts: str) -> ll.LookupRow:
    return ll.LookupRow("category", key, label, tuple(texts) or (label,))


def chan(value: str) -> ll.LookupRow:
    return ll.LookupRow("sales_channel", value, value, (value,))


WC = cat("WC", "Water Closet", "Water Closet", "WC")
TILES = cat("TL", "Tiles", "Tiles")
CHANNELS = [chan("dealer"), chan("project")]


def labels(hits: dict, name: str) -> list[str]:
    return [h.row.label for h in hits.get(name, [])]


# --------------------------------------------------------------------------- gate and header


def test_constants_and_header_text_are_exact():
    assert ll.MARKER == "== LOOKUP LISTS =="
    assert ll.HEADER_NOUN == {"category": "Category", "sales_channel": "Sales channel"}
    assert ll.header("category") == HEADER_CATEGORY
    assert ll.header("sales_channel") == HEADER_CHANNEL
    assert (ll.FLOOR_SPELLING, ll.FLOOR_MEANING) == (0.5, 0.5)
    assert ll.TOP_K == {"category": 10, "sales_channel": 2}


def test_gate_on_needs_the_marker_on_its_own_line():
    assert ll.gate_on("Rules.\n== LOOKUP LISTS ==\nMore rules.") is True
    assert ll.gate_on("== LOOKUP LISTS ==") is True
    assert ll.gate_on("Rules only.\nNothing here.") is False
    assert ll.gate_on("") is False
    assert ll.gate_on(None) is False
    assert ll.gate_on("Rules mention == LOOKUP LISTS == inline, so no.") is False


# --------------------------------------------------------------------------- pieces


def test_pieces_are_every_one_to_four_word_run_folded_and_deduped():
    out = ll.pieces("Water CLOSET dealer only price")
    assert len(out) == len(set(out))
    expect_single = ["water", "closet", "dealer", "only", "price"]
    assert [p for p in out if " " not in p] == expect_single
    assert [p for p in out if p.count(" ") == 1] == ["water closet", "closet dealer", "dealer only", "only price"]
    assert "water closet dealer only" in out and "closet dealer only price" in out
    assert not any(p.count(" ") >= 4 for p in out)
    assert len(out) == 5 + 4 + 3 + 2


def test_pieces_max_words_and_duplicate_words():
    assert ll.pieces("a b c", max_words=2) == ["a", "b", "c", "a b", "b c"] or set(ll.pieces("a b c", max_words=2)) == {
        "a", "b", "c", "a b", "b c"
    }
    out = ll.pieces("wc wc")
    assert sorted(out) == ["wc", "wc wc"]
    assert ll.pieces("") == []


def test_pieces_fold_like_candidates_phrase():
    assert ll.pieces("SRTWC286-SH") == ["srtwc286", "sh", "srtwc286 sh"] or set(ll.pieces("SRTWC286-SH")) == {
        "srtwc286", "sh", "srtwc286 sh"
    }
    assert candidates._phrase("Water  Closet") in ll.pieces("Water  Closet")


# --------------------------------------------------------------------------- shortlist: floors


def test_spelling_floor_keeps_a_near_spelling_and_drops_a_far_one():
    near = ll.shortlist("watr closet", [WC, TILES], None)
    s = candidates.similarity(candidates.trigrams("watr closet"), candidates.trigrams("water closet"))
    assert s >= 0.5, s  # the case is built to sit above the floor
    assert labels(near, "category") == ["Water Closet"]
    assert near["category"][0].spelling >= 0.5
    assert ll.shortlist("zzqxv", [WC, TILES], None).get("category", []) == []


def test_exact_folded_equality_scores_one():
    hits = ll.shortlist("show WATER   closet", [WC], None)["category"]
    assert hits[0].spelling == 1.0 and hits[0].piece == "water closet"


def test_meaning_floor_keeps_a_row_with_no_spelling_overlap():
    row = cat("SK", "Kitchen Sink", "Kitchen Sink")
    keep = ll.shortlist("anchor", [row], cos_embed({"kitchen sink": 0.6}))
    drop = ll.shortlist("anchor", [row], cos_embed({"kitchen sink": 0.4}))
    assert labels(keep, "category") == ["Kitchen Sink"]
    assert keep["category"][0].meaning == pytest.approx(0.6, abs=1e-6)
    assert drop.get("category", []) == []


def test_spelling_or_meaning_either_keeps_the_row():
    by_meaning = cat("A", "Alpha", "Alpha")
    by_spelling = cat("B", "Beta", "Beta")
    hits = ll.shortlist("beta", [by_meaning, by_spelling], cos_embed({"alpha": 0.9, "beta": 0.0}))
    # "beta" spells row B; row A's vector is far from every piece of this message
    assert labels(hits, "category") == ["Beta"]
    hits = ll.shortlist("anchor", [by_meaning, by_spelling], cos_embed({"alpha": 0.9}))
    assert labels(hits, "category") == ["Alpha"]


def test_best_hit_per_row_and_ordering_score_then_label():
    zed = cat("Z", "Zed", "Zed")  # exact: 1.0
    beta = cat("B", "Beta", "Beta")  # exact: 1.0
    alpha = cat("A", "Alpha", "Alpha")  # meaning 0.8
    hits = ll.shortlist("beta zed anchor", [alpha, zed, beta], cos_embed({"alpha": 0.8}))["category"]
    assert [h.row.label for h in hits] == ["Beta", "Zed", "Alpha"]
    assert len({h.row.key for h in hits}) == len(hits)
    # one row, several matching pieces and texts: still one hit, the best
    multi = cat("M", "Multi", "multi", "multiple")
    one = ll.shortlist("multi multiple", [multi], None)["category"]
    assert len(one) == 1 and one[0].spelling == 1.0


def test_top_k_cuts_category_to_ten_and_sales_channel_to_two():
    rows = [cat(f"K{i:02d}", f"Tile {i:02d}", "tiles") for i in range(12)]
    cut = ll.shortlist("tiles", rows, None)["category"]
    assert len(cut) == 10
    assert [h.row.label for h in cut] == [f"Tile {i:02d}" for i in range(10)]
    chans = [chan("dealer"), ll.LookupRow("sales_channel", "d2", "dealer two", ("dealer",)),
             ll.LookupRow("sales_channel", "d3", "dealer three", ("dealer",))]
    assert len(ll.shortlist("dealer", chans, None)["sales_channel"]) == 2


# --------------------------------------------------------------------------- AC-13: no embedder


def test_no_embedder_or_a_raising_embedder_gives_spelling_only():
    def boom(texts):
        raise RuntimeError("zz embedding down")

    for embed in (None, boom):
        hits = ll.shortlist("water closet and tandas", [WC, TILES], embed)
        assert labels(hits, "category") == ["Water Closet"]
        assert hits["category"][0].meaning == 0.0
    # a word only meaning can place is simply not offered without the embedder
    assert ll.shortlist("tandas", [WC], None).get("category", []) == []
    assert ll.shortlist("tandas", [WC], boom).get("category", []) == []


# --------------------------------------------------------------------------- AC-4, AC-5, AC-11, AC-12


@pytest.mark.parametrize("word", ["water closet", "tandas", "马桶", "wc"])
def test_water_closet_words_offer_the_water_closet_row(word):
    hits = ll.shortlist(word, [WC, TILES], stub_embed)
    assert labels(hits, "category") == ["Water Closet"], word


def test_water_closet_and_wc_reach_the_row_by_spelling_alone():
    assert labels(ll.shortlist("water closet", [WC, TILES], None), "category") == ["Water Closet"]
    assert labels(ll.shortlist("wc", [WC, TILES], None), "category") == ["Water Closet"]


def test_dealer_only_offers_the_dealer_channel():
    hits = ll.shortlist("dealer only", CHANNELS, None)
    assert labels(hits, "sales_channel") == ["dealer"]
    assert labels(ll.shortlist("channel project sahaja", CHANNELS, None), "sales_channel") == ["project"]


def test_a_brand_word_piece_offers_no_category():
    srt = cat("SRT", "SRT", "SRT")
    assert ll.shortlist("srt a3 flyer", [srt], None).get("category", []) == [] or labels(
        ll.shortlist("srt a3 flyer", [srt], None), "category"
    ) == ["SRT"], "control"
    with_brand = ll.shortlist("srt a3 flyer", [srt], None, brand_words=frozenset({"srt"}))
    assert with_brand.get("category", []) == []
    # the control: without the brand set the same exact word is a category hit
    assert labels(ll.shortlist("srt a3 flyer", [srt], None), "category") == ["SRT"]
    # a different word in the same message still reaches its category
    both = ll.shortlist("srt tiles", [srt, TILES], None, brand_words=frozenset({"srt"}))
    assert labels(both, "category") == ["Tiles"]


@pytest.mark.parametrize("message", ["stock SRTWC286-SH", "where is PS202609-0469", "DO202610-0012 status"])
def test_product_codes_and_document_numbers_are_never_offered(message):
    hits = ll.shortlist(message, [WC, TILES, *CHANNELS], stub_embed)
    assert hits.get("category", []) == [] and hits.get("sales_channel", []) == [], hits


# --------------------------------------------------------------------------- render


def _hit(row: ll.LookupRow, piece: str = "x") -> ll.Hit:
    return ll.Hit(row, piece, 1.0, 0.0)


def test_render_prints_header_then_one_dash_line_per_label():
    out = ll.render({"category": [_hit(WC), _hit(TILES)], "sales_channel": [_hit(chan("dealer"))]})
    assert out == [HEADER_CATEGORY, "- Water Closet", "- Tiles", HEADER_CHANNEL, "- dealer"]


def test_render_dedupes_labels_and_skips_empty_lists():
    twin = cat("WC2", "Water Closet", "Water Closet")
    assert ll.render({"category": [_hit(WC), _hit(twin)]}) == [HEADER_CATEGORY, "- Water Closet"]
    assert ll.render({"category": [], "sales_channel": []}) == []
    assert ll.render({}) == []
    assert ll.render({"category": [], "sales_channel": [_hit(chan("project"))]}) == [HEADER_CHANNEL, "- project"]
