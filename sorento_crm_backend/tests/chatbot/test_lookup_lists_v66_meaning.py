"""CHAT-V66-REGRESSIONS case 2 (owner ruling 26 Oct): meaning matching stays on every list, its noise cut by data.

On 1,200 labelled real inbound messages the per-turn lookup offered about 1,280 rows by meaning that the message never
named ("promotion" -> pp (PP Promo), "check" -> customer TEST, "got" -> Steel grade 201). The rule, calibrated per
list on that set (crew/state/eval/v66/calib.py): a meaning hit needs the list's floor, must beat the best row that
does not spell like it by the list's margin, and the piece must be rarer in real traffic than the list's cap.
Fake data only (ZZ prefix).
"""
from __future__ import annotations

import collections
import math

import numpy as np

from app.services.chatbot.head import lookup_lists as ll


def _embed(scores: dict[str, float], piece: str = "zzq"):
    """Unit vectors with cos(piece, text) = scores[text]; any other text is orthogonal."""

    def embed(texts):
        out = []
        for t in texts:
            if t == piece:
                out.append([1.0, 0.0, 0.0])
            elif t in scores:
                c = scores[t]
                out.append([c, math.sqrt(max(0.0, 1 - c * c)), 0.0])
            else:
                out.append([0.0, 0.0, 1.0])
        return np.asarray(out, dtype=np.float32)

    return embed


def _keys(hits, name):
    return sorted(h.row.key for h in hits.get(name) or [])


def test_a_meaning_hit_must_stand_out_from_the_next_best_row():
    rows = [ll.LookupRow("category", "a", "ZZ Alpha", ("zz alpha",)), ll.LookupRow("category", "b", "ZZ Beta", ("zz beta",))]
    close = ll.shortlist("zzq", rows, _embed({"zz alpha": 0.70, "zz beta": 0.66}))
    assert _keys(close, "category") == [], close  # equally near both rows: the piece names neither
    clear = ll.shortlist("zzq", rows, _embed({"zz alpha": 0.70, "zz beta": 0.55}))
    assert _keys(clear, "category") == ["a"], clear  # the runner-up gets nothing from this piece


def test_rows_that_spell_like_the_best_text_are_not_its_rivals():
    rows = [ll.LookupRow("customer", "c1", "ZZ TRADING SDN BHD [A/C I]", ("ZZ TRADING SDN BHD [A/C I]",)),
            ll.LookupRow("customer", "c4", "ZZ TRADING SDN BHD [A/C IV]", ("ZZ TRADING SDN BHD [A/C IV]",)),
            ll.LookupRow("customer", "x", "ZZ OTHER SUPPLY", ("ZZ OTHER SUPPLY",))]
    hits = ll.shortlist("zzq", rows, _embed({"ZZ TRADING SDN BHD [A/C I]": 0.60, "ZZ TRADING SDN BHD [A/C IV]": 0.599,
                                             "ZZ OTHER SUPPLY": 0.40}))
    assert _keys(hits, "customer") == ["c1"], hits


def test_every_row_holding_the_best_text_takes_the_hit():
    rows = [ll.LookupRow("category", "s", "ZZ-SRT-WC", ("ZZ-SRT-WC", "zz closet")),
            ll.LookupRow("category", "m", "ZZ-M-WC", ("ZZ-M-WC", "zz closet")),
            ll.LookupRow("category", "k", "ZZ Sink", ("zz sink",))]
    hits = ll.shortlist("zzq", rows, _embed({"zz closet": 0.72, "zz sink": 0.40}))
    assert _keys(hits, "category") == ["m", "s"], hits


def test_the_calibrated_rule_table():
    assert ll.FLOOR_MEANING_BY_LIST == {
        "category": 0.57, "sales_channel": 0.55, "brand": 0.58, "spec": 0.74, "file_type": 0.59, "customer": 0.53,
        "promotion_kind": 0.66, "location": 0.55, "salesperson": 0.55,
    }
    assert ll.MARGIN_BY_LIST == {
        "category": 0.08, "sales_channel": 0.0, "brand": 0.01, "spec": 0.02, "file_type": 0.0, "customer": 0.01,
        "promotion_kind": 0.115, "location": 0.01, "salesperson": 0.01,
    }
    assert ll.COMMON_CAP_BY_LIST == {
        "category": 0.50, "sales_channel": 0.35, "brand": 0.35, "spec": 0.40, "file_type": 0.55, "customer": 0.35,
        "promotion_kind": 0.35, "location": 0.35, "salesperson": 0.35,
    }


def _df(n: int, counts: dict[str, int]) -> ll.WordStats:
    return ll.WordStats(n, collections.Counter(counts))


def test_commonness_is_the_rarest_words():
    df = _df(100, {"zzcheck": 80, "zzhanlim": 1})
    assert ll.commonness("zzcheck", df) == 1 - math.log(100 / 81) / math.log(100)
    assert ll.commonness("zzcheck zzhanlim", df) == 1 - math.log(100 / 2) / math.log(100)
    assert ll.commonness("zzunseen", df) == 0.0
    assert ll.commonness("zzcheck", None) == 0.0 and ll.commonness("zzcheck", _df(0, {})) == 0.0


def test_a_piece_as_common_as_filler_never_matches_by_meaning():
    rows = [ll.LookupRow("customer", "t", "ZZ TEST", ("ZZ TEST",))]
    embed = _embed({"ZZ TEST": 0.62})
    common = _df(1000, {"zzq": 700})
    assert _keys(ll.shortlist("zzq", rows, embed, words=common), "customer") == []
    assert _keys(ll.shortlist("zzq", rows, embed, words=_df(1000, {"zzq": 2})), "customer") == ["t"]
    assert _keys(ll.shortlist("zzq", rows, embed), "customer") == ["t"]  # no traffic counts: the cap reads nothing


def test_spelling_hits_never_meet_the_meaning_rule():
    rows = [ll.LookupRow("customer", "t", "ZZ TEST", ("zzq",))]
    hits = ll.shortlist("zzq", rows, _embed({"zzq": 1.0}), words=_df(1000, {"zzq": 900}))
    assert _keys(hits, "customer") == ["t"], hits


def test_word_stats_count_each_word_once_per_message_and_are_read_once(monkeypatch):
    calls = []

    def texts(db):
        calls.append(db)
        return ["ZZ check stock", "zz check check", "zz hanlim"]

    monkeypatch.setattr(ll, "_recent_inbound_texts", texts)
    monkeypatch.setattr(ll, "_word_stats", None)
    stats = ll.word_stats("db1")
    assert stats.n == 3 and stats.df["check"] == 2 and stats.df["zz"] == 3 and stats.df["hanlim"] == 1
    assert ll.word_stats("db2") is stats and calls == ["db1"]
