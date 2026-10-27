"""ENTITY-EXTRACT-MATCH S1: head/list_resolver (UAC AC-S1-1..11, AC-S1-14). Pure, no DB.

All names are invented. Red until app/services/chatbot/head/list_resolver.py exists.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.chatbot.head.lookup_lists import LookupRow


def _lr():
    from app.services.chatbot.head import list_resolver

    return list_resolver


def R(list_name, key, label, *texts):
    return LookupRow(list_name, key, label, tuple(texts) if texts else (label,))


def _one(span_text, span_type, rows, **kw):
    lr = _lr()
    out = lr.resolve([lr.Span(span_text, span_type)], rows, **kw)
    assert len(out) == 1
    return out[0]


BASE = [
    R("brand", "b1", "MOCHA"),
    R("brand", "b2", "SORENTO", "SORENTO", "SRT"),
    R("brand", "b3", "JOHNSON SUISSE"),
    R("brand", "b4", "CABANA"),
    R("category", "c1", "Water Closet", "Water Closet", "马桶"),
    R("category", "c2", "Water pump"),
    R("category", "c3", "Kitchen Sink"),
    R("file_type", "f1", "Photo"),
    R("file_type", "f2", "Certificate"),
    R("promotion_kind", "p1", "A3 Flyer"),
    R("promotion_kind", "p2", "Roadshow Banner"),
]


# AC-S1-1
def test_exact_folded_match_resolves_first_with_exact_signal():
    res = _one("Mocha", "brand", BASE)
    assert res.status == "resolved"
    assert res.candidates[0].row.key == "b1" and res.candidates[0].row.label == "MOCHA"
    assert res.candidates[0].signal == "exact"


# AC-S1-2
def test_alias_text_on_row_resolves():
    assert _one("srt", "brand", BASE).candidates[0].row.key == "b2"
    res = _one("马桶", "category", BASE)
    assert res.status == "resolved" and res.candidates[0].row.key == "c1"


def test_module_holds_no_alias_words_srt_unresolved_without_alias_text():
    rows = [R("brand", "b1", "MOCHA"), R("brand", "b2", "SORENTO"), R("brand", "b4", "CABANA")]
    res = _one("srt", "brand", rows)
    assert res.status != "resolved"
    assert not any(c.row.key == "b2" for c in res.candidates if res.status == "resolved")


# AC-S1-3
def test_typo_resolves_by_spelling():
    res = _one("jhonson suise", None, BASE)
    assert res.status == "resolved" and res.candidates[0].row.key == "b3"


# AC-S1-4
CUSTOMERS = [
    R("customer", f"u{i}", n)
    for i, n in enumerate(
        [
            "KIMLAN TRADING SDN BHD",
            "BUMI CERAMIC SDN BHD",
            "TERAS JAYA TRADING SDN BHD",
            "LAUT BIRU ENTERPRISE SDN BHD",
            "SERI MAJU HARDWARE SDN BHD",
            "DELTA TILES TRADING SDN BHD",
            "ORKID BUILDERS SDN BHD",
            "PUNCAK UTAMA SDN BHD",
        ]
    )
]


def test_partial_name_and_one_letter_typo_resolve_to_right_customer():
    kim = _one("Kimlan", "customer", CUSTOMERS)
    assert kim.status == "resolved" and kim.candidates[0].row.label == "KIMLAN TRADING SDN BHD"
    bumi = _one("Bumi ceramics", "customer", CUSTOMERS)
    assert bumi.status == "resolved" and bumi.candidates[0].row.label == "BUMI CERAMIC SDN BHD"


def test_common_tokens_only_never_resolve_to_one_customer():
    res = _one("trading sdn bhd", "customer", CUSTOMERS)
    assert res.status in ("unresolved", "ambiguous")
    assert res.status != "resolved"


# AC-S1-5
def test_type_is_tie_break_not_filter():
    res = _one("A3 flyer", "file_type", BASE)
    assert res.status == "resolved" and res.candidates[0].row.list_name == "promotion_kind"
    assert res.candidates[0].row.key == "p1"


def test_typed_list_wins_equal_match_untyped_sees_all():
    rows = BASE + [R("customer", "u9", "SORENTO"), R("customer", "u8", "OTHER ENTERPRISE SDN BHD")]
    as_brand = _one("Sorento", "brand", rows)
    assert as_brand.candidates[0].row.list_name == "brand"
    as_customer = _one("Sorento", "customer", rows)
    assert as_customer.candidates[0].row.list_name == "customer"
    untyped = _one("Sorento", None, rows)
    assert {c.row.list_name for c in untyped.candidates} >= {"brand", "customer"}


# AC-S1-6
SALES = [
    R("salesperson", "s1", "LEE - I", "LEE - I", "LEE"),
    R("salesperson", "s2", "LEE - II", "LEE - II", "LEE"),
    R("salesperson", "s3", "TANGO - I", "TANGO - I"),
    R("salesperson", "s4", "ROMEO - I", "ROMEO - I"),
]


def test_shared_text_is_ambiguous_with_every_row():
    res = _one("Lee", "salesperson", SALES)
    assert res.status == "ambiguous"
    assert {c.row.key for c in res.candidates} == {"s1", "s2"}


def test_scores_within_margin_are_ambiguous_best_first():
    rows = [
        R("customer", "n1", "NORTHMOOR EAST"),
        R("customer", "n2", "NORTHMOOR WEST"),
        R("customer", "n3", "KESTREL HARDWARE"),
        R("customer", "n4", "LOTUS PAINTS"),
        R("customer", "n5", "QUARTZ TILES"),
    ]
    res = _one("Northmoor", "customer", rows)
    assert res.status == "ambiguous"
    assert {c.row.key for c in res.candidates} == {"n1", "n2"}
    scores = [c.score for c in res.candidates]
    assert scores == sorted(scores, reverse=True)


# AC-S1-7
@pytest.mark.parametrize("text", ["stock", "please"])
def test_nothing_named_is_unresolved_without_candidates(text):
    res = _one(text, None, BASE)
    assert res.status == "unresolved" and res.candidates == ()


def test_one_floors_constant_covers_every_list():
    lr = _lr()
    needed = {
        "category", "spec", "file_type", "brand", "promotion_kind", "location", "salesperson",
        "customer", "sales_channel", "spec_key",
    }
    tables = [
        v for k, v in vars(lr).items()
        if not k.startswith("__") and isinstance(v, dict) and needed <= set(v)
    ]
    assert len(tables) == 1, "expected exactly one floors table covering every list"
    assert all(tables[0][name] for name in needed)


# AC-S1-8
def test_product_code_span_is_skipped():
    res = _one("SRTWC8065", "product_code", BASE + [R("category", "c9", "SRTWC8065")])
    assert res.status == "skipped" and res.candidates == ()


# AC-S1-9
def _fake_embedder():
    dim = 256
    seen: dict[str, int] = {}

    def vec(text):
        t = " ".join(text.casefold().split())
        if t in ("pam air", "water pump"):
            v = [0.0] * dim
            v[255] = 1.0
            v[254] = 0.1 if t == "pam air" else 0.0
            return v
        idx = seen.setdefault(t, len(seen))
        v = [0.0] * dim
        v[idx % 250] = 1.0
        return v

    def embed(texts):
        return [vec(t) for t in texts]

    return embed


def test_meaning_resolves_with_embedder_signal_meaning():
    res = _one("pam air", "category", BASE, embed=_fake_embedder())
    assert res.status == "resolved"
    assert res.candidates[0].row.key == "c2" and res.candidates[0].signal == "meaning"


def test_no_embedder_still_resolves_spelled_spans():
    assert _one("Mocha", "brand", BASE, embed=None).status == "resolved"
    assert _one("pam air", "category", BASE, embed=None).status != "resolved"


def test_raising_embedder_never_raises_and_spelled_spans_resolve():
    def boom(texts):
        raise RuntimeError("provider down")

    lr = _lr()
    out = lr.resolve([lr.Span("Mocha", "brand"), lr.Span("pam air", "category")], BASE, embed=boom)
    assert out[0].status == "resolved" and out[0].candidates[0].row.key == "b1"
    assert out[1].status != "resolved"


# AC-S1-10
def test_one_result_per_span_in_input_order():
    lr = _lr()
    spans = [lr.Span("Mocha", "brand"), lr.Span("stock", None), lr.Span("SRTWC8065", "product_code")]
    out = lr.resolve(spans, BASE)
    assert [r.span for r in out] == spans
    assert [r.status for r in out] == ["resolved", "unresolved", "skipped"]


def test_empty_spans_and_blank_span():
    lr = _lr()
    assert lr.resolve([], BASE) == []
    assert lr.resolve([lr.Span("  ")], BASE)[0].status == "unresolved"


# AC-S1-11
def _entry(spec_key, label, synonyms=None, user=None, suppressed=None, active=True):
    return SimpleNamespace(
        spec_key=spec_key, label=label, synonyms=synonyms or {}, user_synonyms=user or {},
        suppressed_synonyms=suppressed or {}, suppressed_values=[], is_active=active,
    )


def test_spec_key_rows_from_registry_entries():
    lr = _lr()
    reg = [
        _entry(
            "finish", "Finish or colour",
            synonyms={"black": ["black", "matte black"], "grey": ["grey", "gray"]},
            user={"chrome": ["colour"]},
            suppressed={"black": ["matte black"]},
        ),
        _entry("pipe_size", "Pipe size"),
        _entry("retired_key", "Retired", active=False),
    ]
    rows = lr.spec_key_rows(reg)
    by_key = {r.key: r for r in rows}
    assert set(by_key) == {"finish", "pipe_size"}
    fin = by_key["finish"]
    assert fin.list_name == "spec_key" and fin.label == "Finish or colour"
    texts = {t.casefold() for t in fin.texts}
    assert {"finish or colour", "finish", "black", "grey", "gray", "colour"} <= texts
    assert "matte black" not in texts
    assert "pipe size" in {t.casefold() for t in by_key["pipe_size"].texts}
    res = _one("colour", "spec_key", rows)
    assert res.status == "resolved" and res.candidates[0].row.key == "finish"


# AC-S1-14 narrowed on purpose by AC-S2-9: only the span pass and the engine seam import the resolver
def _importers(root: Path) -> list[str]:
    return sorted(
        str(p.relative_to(root)) for p in root.rglob("*.py")
        if p.name != "list_resolver.py" and "list_resolver" in p.read_text(encoding="utf-8", errors="ignore")
    )


def test_only_span_extract_and_the_engine_import_list_resolver():
    root = Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot"
    assert (root / "head" / "list_resolver.py").is_file()
    assert (root / "head" / "span_extract.py").is_file(), "AC-S2-9: the span pass module must exist"
    assert _importers(root) == ["engine.py", "head/span_extract.py"]


# AC-S1-6 guard: the margin itself (a zero margin must fail this)
def test_ambiguity_margin_separates_close_from_clear_gap():
    filler = [
        R("customer", "f1", "KESTREL HARDWARE"), R("customer", "f2", "LOTUS PAINTS"),
        R("customer", "f3", "QUARTZ TILES"), R("customer", "f4", "DELTA PIPES"),
    ]
    span = "harbour glas supply"
    # scores 0.654 vs 0.630: a small non-zero gap inside the margin
    close = [R("customer", "a", "HARBOUR GLASS SUPPLIES"), R("customer", "b", "HARBOUR GLASS SUPPLIERS")]
    res = _one(span, "customer", close + filler)
    assert res.status == "ambiguous"
    assert [c.row.key for c in res.candidates] == ["a", "b"]
    assert 0 < res.candidates[0].score - res.candidates[1].score < 0.03
    # scores 0.704 vs 0.654: a gap clearly above the margin
    far = [R("customer", "a", "HARBOUR GLASSWORKS SUPPLY"), R("customer", "b", "HARBOUR GLASS SUPPLIES")]
    res = _one(span, "customer", far + filler)
    assert res.status == "resolved" and res.candidates[0].row.key == "a"


# ---- S1 review round -------------------------------------------------------------------------------------
# AC-S1-4: a typo of a common word is not a rare word
@pytest.mark.parametrize("text", ["tradng sdn bhd", "traiding sdn bhd"])
def test_typo_of_common_word_is_not_a_rare_word(text):
    res = _one(text, "customer", CUSTOMERS)
    assert res.status == "unresolved", [(c.row.label, c.score) for c in res.candidates]


# AC-S1-5 "never a filter": a typed list wins only within the margin
def test_type_never_filters_exact_row_of_other_list_beats_weak_typed_row():
    rows = [R("brand", "b1", "KITCHEN KING"), R("category", "c1", "Kitchen Sink"), R("brand", "b2", "ZEPHYR")]
    res = _one("kitchen sink", "brand", rows)
    assert res.status == "resolved"
    assert res.candidates[0].row.list_name == "category" and res.candidates[0].row.key == "c1"


# AC-S1-6: equal scores are ambiguous, never a silent pick
def test_equal_score_category_rows_are_ambiguous():
    rows = [r for r in BASE if r.list_name == "category"] + [
        R("category", "c4", "Floor Tile"), R("category", "c5", "Door Handle"), R("category", "c6", "Wall Paint"),
        R("category", "c7", "Booster Pump"), R("category", "c8", "Sump Pump"),
    ]
    res = _one("water", None, rows)
    assert res.status == "ambiguous"
    assert {c.row.key for c in res.candidates} == {"c1", "c2"}


def test_customer_name_prefix_of_two_rows_is_ambiguous():
    rows = [
        R("customer", "n1", "NORTHMOOR WEST HARDWARE"), R("customer", "n2", "NORTHMOOR EAST HARDWARE"),
        R("customer", "n3", "KESTREL HARDWARE"), R("customer", "n4", "LOTUS HARDWARE"),
        R("customer", "n5", "QUARTZ TILES"), R("customer", "n6", "WEST COAST TILES"), R("customer", "n7", "WEST BAY PAINTS"),
    ]
    res = _one("Northmoor", "customer", rows)
    assert res.status == "ambiguous"
    assert {c.row.key for c in res.candidates} == {"n1", "n2"}


# AC-S1-6 "every close row": no per-list cap
def test_five_close_rows_all_returned_ambiguous():
    rows = [R("salesperson", f"s{i}", f"LEE - {n}", f"LEE - {n}", "LEE") for i, n in enumerate(["I", "II", "III", "IV", "V"])]
    rows += [R("salesperson", "x1", "TANGO - I"), R("salesperson", "x2", "ROMEO - I")]
    res = _one("Lee", "salesperson", rows)
    assert res.status == "ambiguous"
    assert {c.row.key for c in res.candidates} == {f"s{i}" for i in range(5)}


# AC-S1-3/5: one edit must not score like an exact match
def test_exact_other_list_beats_one_edit_typed_row():
    rows = [R("brand", "b1", "MOCHA"), R("category", "c1", "Mochi Tray"), R("category", "c2", "Floor Tile")]
    res = _one("Mocha", "category", rows)
    assert res.status == "resolved"
    assert res.candidates[0].row.list_name == "brand" and res.candidates[0].row.key == "b1"


# AC-S1-14 widened, then narrowed by AC-S2-9: nothing else under app/ references it
def test_nothing_else_in_app_references_list_resolver():
    root = Path(__file__).resolve().parents[2] / "app"
    assert _importers(root) == ["services/chatbot/engine.py", "services/chatbot/head/span_extract.py"]


# nit: a one-row list is not all-common
def test_single_row_list_word_is_not_common():
    res = _one("riverside", "location", [R("location", "l1", "Riverside Depot")])
    assert res.status == "resolved" and res.candidates[0].row.key == "l1"


# AC-S1-5 guard: the type margin itself (a zero margin must fail this)
def test_typed_list_wins_when_slightly_below_other_list():
    rows = [
        R("brand", "b1", "HARBOUR GLASSWARE"), R("customer", "c1", "HARBOUR GLASSES"),
        R("brand", "b2", "ZEPHYR"), R("customer", "c2", "KESTREL"),
    ]
    res = _one("harbour glass", "brand", rows)  # brand 0.684 vs customer 0.765
    assert res.status == "resolved" and res.candidates[0].row.key == "b1"


# AC-S1-6: among close rows, the one the span equals outright is the answer (exact-class rule)
def test_exact_row_beats_longer_row_containing_it():
    rows = [
        R("spec_key", "k1", "Length"), R("spec_key", "k2", "Trap outlet length"),
        R("spec_key", "k3", "Pipe size"), R("spec_key", "k4", "Finish or colour"), R("spec_key", "k5", "Wall thickness"),
    ]
    res = _one("length", None, rows)
    assert res.status == "resolved" and res.candidates[0].row.key == "k1"


# F1: a span word matches a row word with the same consonant skeleton (typos that drop vowels)
SKEL = [
    R("brand", "s1", "ZZSORENTO"),
    R("category", "s2", "Flush type ZZWashdown"),
    R("brand", "s3", "ZZOMEGA"),
]


def test_consonant_skeleton_matches_a_dropped_vowel_brand():
    res = _one("zzsrnto", "brand", SKEL)
    assert res.status == "resolved" and res.candidates[0].row.key == "s1", res


def test_consonant_skeleton_matches_a_dropped_vowel_in_a_multiword_label():
    res = _one("zzwshdwn", "category", SKEL)
    assert res.status == "resolved" and res.candidates[0].row.key == "s2", res


def test_a_two_consonant_skeleton_does_not_match():
    res = _one("zz", "brand", [R("brand", "t1", "zoo")])
    assert res.status != "resolved", res


def test_a_different_first_letter_does_not_match():
    res = _one("rstq", "brand", [R("brand", "u1", "arstq")])
    assert res.status != "resolved", res


def test_an_exact_row_still_beats_a_skeleton_match():
    rows = [R("brand", "e1", "ZZSORENTO"), R("brand", "e2", "ZZSRNTO")]
    res = _one("zzsrnto", "brand", rows)
    assert res.candidates[0].row.key == "e2" and res.candidates[0].signal == "exact", res
