"""CHAT-V66-REGRESSIONS case 7: the shortlist scores only the rows that can be offered, with the same hits.

A staff turn walked every row (about 4,000 with customers) x every piece x every text in Python: 0.13 s for a short
message, 0.7 s for 40 plain words (Mac). A pre-filter now finds, with whole-array arithmetic, the rows whose spelling
(trigram Jaccard, the same integers) or meaning (the same cosines) can reach a floor; only those run the exact loop.
`FILTER_ROWS = False` is the reference: every row through the loop. Fake data only (ZZ prefix).
"""
from __future__ import annotations

import hashlib

import numpy as np
import pytest

from app.services.chatbot.head import lookup_lists as ll

WORDS = ["zzbasin", "zztap", "zzsink", "zzclosetbowl", "zzmirror", "zzshower", "zzbath", "zzsoap", "zzgold",
         "zzblack", "zzsingle", "zzdouble", "zzlever", "zzround", "zzsquare", "zztrading", "zzhardware", "zzbuilder"]


def _hash_embed(texts):
    out = []
    for t in texts:
        h = hashlib.sha256(t.encode()).digest()
        v = np.frombuffer(h, dtype=np.uint8).astype(np.float32)[:16] - 127.5
        shared = sum(hashlib.sha256(w.encode()).digest()[0] for w in t.split()) % 7  # nearby texts share a component
        v[shared] += 300.0
        out.append(v)
    return np.asarray(out, dtype=np.float32)


def _rows():
    rows = []
    for i in range(240):
        a, b, c = WORDS[i % 18], WORDS[(i * 7) % 18], WORDS[(i * 11) % 18]
        rows.append(ll.LookupRow("category", f"c{i}", f"ZZ {a} {b}", (f"{a} {b}", f"zzc{i}", f"{a}")))
        rows.append(ll.LookupRow("spec", f"s{i}", f"ZZ spec {c}", (f"{c} {a}", f"{c}")))
        rows.append(ll.LookupRow("customer", f"u{i}", f"{b.upper()} {c.upper()} SDN BHD {i}", (f"{b} {c} sdn bhd {i}",)))
    rows.append(ll.LookupRow("brand", "br", "ZZBRAND (ZZB)", ("zzbrand", "zzb")))
    rows.append(ll.LookupRow("sales_channel", "dealer", "dealer", ("dealer",)))
    return rows


def _near_floor_embed(texts):
    """Cosines just above and just below each list's meaning floor (piece 'zznear' against the row texts below)."""
    out = []
    for t in texts:
        if t == "zznear":
            out.append([1.0, 0.0, 0.0])
        elif t.startswith("zzfl "):
            c = float(t.split()[1])
            out.append([c, (1 - c * c) ** 0.5, 0.0])
        else:
            out.append([0.0, 0.0, 1.0])
    return np.asarray(out, dtype=np.float32)


def _near_floor_rows():
    rows = []
    for name, floor in {**ll.FLOOR_MEANING_BY_LIST, "promotion_kind": ll._FLOOR_MEANING_OTHER}.items():
        for d in (-0.002, 0.002):
            rows.append(ll.LookupRow(name, f"{name}{d}", f"ZZ {name} {d}", (f"zzfl {floor + d:.4f}",)))
    return rows


def test_the_prefilter_keeps_the_rows_just_above_each_floor(monkeypatch):
    rows = _near_floor_rows()
    monkeypatch.setattr(ll, "FILTER_ROWS", False)
    reference = ll.shortlist("zznear", rows, _near_floor_embed)
    monkeypatch.setattr(ll, "FILTER_ROWS", True)
    assert ll.shortlist("zznear", rows, _near_floor_embed) == reference
    assert sorted(h.row.key for hs in reference.values() for h in hs) == sorted(r.key for r in rows if "0.002" in r.key and "-" not in r.key)


def test_the_prefilter_keeps_a_word_matched_only_by_exact_equality(monkeypatch):
    # A Chinese word has no ASCII trigrams: `_spelling` places it by exact equality alone (PROMPT_SYNONYMS 马桶).
    rows = [ll.LookupRow("category", "wc", "ZZ Water closet", ("zz water closet", "马桶")), *_rows()]
    for flag in (False, True):
        monkeypatch.setattr(ll, "FILTER_ROWS", flag)
        assert [h.row.key for h in ll.shortlist("我要 马桶", rows, None).get("category", [])] == ["wc"], flag


MESSAGES = [
    "zzbasin zztap please", "pls check zzsink zzdouble x 3 for zzbrand", "zzclosetbowl zzgold zzlever dealer",
    "zztradng zzhardwre delivery this month", "zzbasn", "need zzshower zzround zzsquare zzblack zzsingle price list now",
    "SRTZZ1234 x 10", "zzmirror zzbath zzsoap zzgold zzblack zzsingle zzdouble zzlever zzround zzsquare zztrading",
]


@pytest.mark.parametrize("embed", [None, _hash_embed], ids=["spelling", "meaning"])
@pytest.mark.parametrize("message", MESSAGES)
def test_the_prefilter_gives_the_same_hits_as_every_row(monkeypatch, embed, message):
    rows = _rows()
    bw = frozenset({"zzbrand", "zzb"})
    held = {"brand": ("ZZBRAND",)}
    monkeypatch.setattr(ll, "FILTER_ROWS", False)
    reference = ll.shortlist(message, rows, embed, brand_words=bw, held=held)
    monkeypatch.setattr(ll, "FILTER_ROWS", True)
    assert ll.shortlist(message, rows, embed, brand_words=bw, held=held) == reference


def test_rows_that_cannot_reach_a_floor_never_enter_the_exact_loop(monkeypatch):
    rows = [ll.LookupRow("customer", f"u{i}", f"QQ NOMATCH {i}", (f"qq nomatch {i}",)) for i in range(4000)]
    rows.append(ll.LookupRow("category", "t", "ZZ Tap", ("zztap",)))
    calls = []
    real = ll._spelling
    monkeypatch.setattr(ll, "_spelling", lambda *a, **k: calls.append(1) or real(*a, **k))
    hits = ll.shortlist("zztap for my customer please check the price today", rows, None)
    assert [h.row.key for h in hits["category"]] == ["t"]
    assert len(calls) < 200, len(calls)
