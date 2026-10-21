"""CHAT-INDEX-VIZ BE-2: `trace_detail.compose_trace_detail(...)["index_match"]`.

Pure unit tests over hand-built trace records (contract:
documentation/plans/chatbot/chat-index-viz-20oct-contract.md, "BE-2" and the wording table).
No database: `compose_trace_detail` is called with a fake row and no session.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.chatbot.trace_detail import compose_trace_detail

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def _match(word, list_, entry, *, close=False, held=False, line=None) -> dict[str, Any]:
    return {
        "word": word, "list": list_, "entry": entry, "close_spelling": close, "held": held,
        "line": line if line is not None else (entry if held else f'- "{word}": {entry}'),
    }


def _entity(raw: str, hint: str, **extra: Any) -> dict[str, Any]:
    return {"raw": raw, "hint": hint, "canonical_code": None, "current_message": True, "confident": True, **extra}


def _stage(name: str, raw: dict | None = None) -> dict[str, Any]:
    return {"stage": name, "status": "ok", "started_at": NOW.isoformat(), "ms": 1, "summary": name,
            "why": name, "facts": {}, "error": None, "raw": raw or {}}


def _row(*, words, matches, entities=(), changes=None, failed=False, with_event=True, with_understood=True):
    trace: list[dict] = [_stage("received")]
    if with_understood:
        trace.append(_stage("understood", {"parser_raw": {"entities": list(entities)}, "derived": {}}))
    if with_event:
        trace.append({"kind": "closed_lists_index", "at": NOW.isoformat(), "words": list(words),
                      "matches": list(matches), "failed": failed})
    if changes is not None:
        trace.append({"kind": "grounding", "at": NOW.isoformat(), "changes": list(changes)})
    return SimpleNamespace(id="zzt-turn", created_at=NOW, trace=trace, contact_respond_id="ZZT-c", is_test=True,
                           envelope={})


def _im(**kw) -> dict[str, Any]:
    detail = compose_trace_detail(_row(**kw))
    assert "index_match" in detail, sorted(detail)
    return detail["index_match"]


FRG = _match("frg", "Specifications", "spec finish = french_gold (French Gold)")


# --------------------------------------------------------------------------- #
# Presence, words, rows
# --------------------------------------------------------------------------- #


def test_none_without_the_event():
    assert _im(words=[], matches=[], with_event=False) is None


def test_failed_is_passed_through():
    im = _im(words=["frg"], matches=[], failed=True)
    assert im["failed"] is True
    assert im["rows"] == [] and im["held"] == [] and im["not_from_lists"] == []
    assert _im(words=["frg"], matches=[FRG])["failed"] is False


def test_words_carry_a_matched_flag():
    im = _im(words=["stock", "frg"], matches=[FRG])
    assert im["words"] == [{"text": "stock", "matched": False}, {"text": "frg", "matched": True}]


def test_a_multi_word_gram_marks_each_of_its_words_matched():
    drawing = _match("zz idx drawing", "File types", "File type zz_idx_drawing: ZZ Idx Drawing.")
    im = _im(words=["send", "zz", "idx", "drawing", "stock"], matches=[drawing])
    assert [(w["text"], w["matched"]) for w in im["words"]] == [
        ("send", False), ("zz", True), ("idx", True), ("drawing", True), ("stock", False)]


def test_one_row_per_distinct_word_in_message_order_with_plain_entries_and_lines():
    a1 = _match("zza", "Specifications", "spec finish = white (White)")
    a2 = _match("zza", "Product types", "product type Basin (class = basin)", close=True,
                line='- "zza": spec finish = white (White); near product type Basin (class = basin)')
    b = _match("zzb", "Products", "code ZZB1 (ZZT ZZB1)")
    im = _im(words=["zza", "zzb"], matches=[a1, a2, b])
    assert [r["word"] for r in im["rows"]] == ["zza", "zzb"]
    first = im["rows"][0]
    assert first["matched"] == [
        {"list": "Specifications", "entry": "spec finish = white (White)", "close_spelling": False},
        {"list": "Product types", "entry": "product type Basin (class = basin)", "close_spelling": True},
    ]
    assert first["parser_got"] == [a1["line"], a2["line"]]
    assert im["rows"][1]["parser_got"] == [b["line"]]


def test_parser_got_lists_each_distinct_line_once():
    one = _match("frg", "Specifications", "spec finish = french_gold (French Gold)", line='- "frg": same')
    two = _match("frg", "Specifications", "spec finish = white (White)", line='- "frg": same')
    im = _im(words=["frg"], matches=[one, two])
    assert im["rows"][0]["parser_got"] == ['- "frg": same']


def test_held_matches_are_listed_apart_and_make_no_row():
    held = _match(None, "On record for the held product", "spec finish = chrome (Chrome)", held=True)
    im = _im(words=["frg"], matches=[FRG, held])
    assert im["held"] == ["spec finish = chrome (Chrome)"]
    assert [r["word"] for r in im["rows"]] == ["frg"]


# --------------------------------------------------------------------------- #
# Understood
# --------------------------------------------------------------------------- #


def test_contract_example_spec_kept_and_warehouse_dropped():
    entities = [
        _entity("frg", "specification", spec_key="finish", spec_value="french_gold"),
        _entity("frg", "warehouse"),
    ]
    changes = [{"from": "warehouse", "raw": "frg", "to": "dropped: a finish short form, no warehouse on file"}]
    im = _im(words=["frg"], matches=[FRG], entities=entities, changes=changes)
    row = im["rows"][0]
    assert row["understood"] == [
        {"text": '"frg" as a specification: finish = french_gold'},
        {"text": '"frg" as a warehouse'},
    ]
    assert row["result"] == [
        {"outcome": "kept", "text": "Kept"},
        {"outcome": "dropped", "text": "Dropped: a finish code ending, not on the warehouse list"},
    ]
    assert im["not_from_lists"] == []


def test_entity_raw_matches_by_fold_or_as_a_whole_word():
    entities = [
        _entity("FRG", "specification", spec_key="finish", spec_value="french_gold"),
        _entity("frg white", "specification", spec_key="finish", spec_value="white"),
        _entity("frgx", "specification", spec_key="finish", spec_value="nope"),
    ]
    im = _im(words=["frg"], matches=[FRG], entities=entities)
    texts = [u["text"] for u in im["rows"][0]["understood"]]
    assert texts == ['"FRG" as a specification: finish = french_gold',
                     '"frg white" as a specification: finish = white']
    assert [n["text"] for n in im["not_from_lists"]] == ['"frgx" as a specification: finish = nope']


@pytest.mark.parametrize("hint,plain", [
    ("product", "a product"), ("category", "a product type"), ("specification", "a specification"),
    ("spec", "a specification"), ("attachment_type", "a file"), ("warehouse", "a warehouse"),
    ("brand", "a brand"), ("customer", "a customer"), ("zz_other", "zz_other"),
])
def test_understood_text_names_the_hint_in_plain_words(hint, plain):
    im = _im(words=["zzw"], matches=[_match("zzw", "Products", "code ZZW1 (ZZT)")], entities=[_entity("zzw", hint)])
    assert im["rows"][0]["understood"] == [{"text": f'"zzw" as {plain}'}]


def test_understood_value_prefers_spec_pair_then_canonical_code_then_listed_item():
    word = _match("zzw", "Products", "code ZZW1 (ZZT)")
    spec = _entity("zzw", "specification", spec_key="finish", spec_value="white", canonical_code="IGNORED")
    code = _entity("zzw", "product", canonical_code="ZZW1", listed_item="ignored")
    listed = _entity("zzw", "attachment_type", listed_item="zz_idx_drawing")
    im = _im(words=["zzw"], matches=[word], entities=[spec, code, listed])
    assert [u["text"] for u in im["rows"][0]["understood"]] == [
        '"zzw" as a specification: finish = white',
        '"zzw" as a product: ZZW1',
        '"zzw" as a file: zz_idx_drawing',
    ]


def test_entities_matching_no_row_go_to_not_from_lists():
    im = _im(words=["frg"], matches=[FRG], entities=[_entity("IB", "warehouse")])
    assert im["not_from_lists"] == [{"text": '"IB" as a warehouse', "outcome": "kept", "result": "Kept"}]
    assert im["rows"][0]["understood"] == [] and im["rows"][0]["result"] == []


def test_not_from_lists_carries_the_grounding_result_too():
    changes = [{"from": "warehouse", "raw": "IB", "to": "dropped: a finish short form, no warehouse on file"}]
    im = _im(words=["frg"], matches=[FRG], entities=[_entity("IB", "warehouse")], changes=changes)
    assert im["not_from_lists"] == [{
        "text": '"IB" as a warehouse', "outcome": "dropped",
        "result": "Dropped: a finish code ending, not on the warehouse list"}]


# --------------------------------------------------------------------------- #
# Result wording: every row of the contract's table
# --------------------------------------------------------------------------- #


def _result(hint: str, to: Any, *, raw: str = "zzw", note_from: str | None = None) -> dict[str, str]:
    changes = [{"from": note_from or hint, "raw": raw, "to": to}]
    im = _im(words=[raw], matches=[_match(raw, "Products", "code ZZW1 (ZZT)")],
             entities=[_entity(raw, hint)], changes=changes)
    [res] = im["rows"][0]["result"]
    return res


@pytest.mark.parametrize("hint,to,outcome,text", [
    ("warehouse", "dropped: a finish short form, no warehouse on file", "dropped",
     "Dropped: a finish code ending, not on the warehouse list"),
    ("attachment_type", "dropped: not on the closed lists", "dropped", "Dropped: not on the file type list"),
    ("attachment_type", "dropped: not a listed document type", "dropped", "Dropped: not on the file type list"),
    ("category", "unknown product type", "dropped", "Dropped: not a known product type"),
    ("attachment_type", "on the attachment_type list: zz_idx_drawing", "kept",
     "Kept: on the file type list (zz_idx_drawing)"),
    ("attachment_type", "on the cert_kind list: zz_idx_cert", "kept",
     "Kept: on the certificate list (zz_idx_cert)"),
    ("attachment_type", "on the cert_scheme list: ZZSCH", "kept",
     "Kept: on the certificate scheme list (ZZSCH)"),
    ("product", "canonical dropped: not on the candidate block", "changed",
     "Changed: product code not among the matches, removed"),
    ("product", "canonical refused: tied near codes", "changed",
     "Changed: several product codes fit, the bot asks which"),
    ("product", "canonical refused: several codes hold the word", "changed",
     "Changed: several product codes fit, the bot asks which"),
    ("specification", [{"key": "finish", "label": "Finish", "said": "zzw", "value": "white"}], "changed",
     "Changed: read as Finish = white"),
    ("specification", [{"key": "zz_key", "label": "", "said": "zzw", "value": "red"},
                       {"key": "size", "label": "Size", "said": "zzw", "value": 600}], "changed",
     "Changed: read as zz_key = red; Size = 600"),
    ("product", "category", "changed", "Changed: read as category"),
])
def test_grounding_note_wording(hint, to, outcome, text):
    assert _result(hint, to) == {"outcome": outcome, "text": text}


def test_no_grounding_note_for_the_entity_reads_kept():
    assert _result("product", "category", raw="zzw", note_from="warehouse") == {"outcome": "kept", "text": "Kept"}


def test_a_note_for_another_raw_word_does_not_apply():
    changes = [{"from": "warehouse", "raw": "other", "to": "unknown product type"}]
    im = _im(words=["zzw"], matches=[_match("zzw", "Products", "code ZZW1 (ZZT)")],
             entities=[_entity("zzw", "warehouse")], changes=changes)
    assert im["rows"][0]["result"] == [{"outcome": "kept", "text": "Kept"}]


def test_note_raw_is_compared_folded():
    changes = [{"from": "warehouse", "raw": "FRG", "to": "dropped: a finish short form, no warehouse on file"}]
    im = _im(words=["frg"], matches=[FRG], entities=[_entity("frg", "warehouse")], changes=changes)
    assert im["rows"][0]["result"][0]["outcome"] == "dropped"


def test_no_internal_names_reach_any_text():
    entities = [_entity("frg", "specification", spec_key="finish", spec_value="french_gold"),
                _entity("frg", "warehouse")]
    changes = [{"from": "warehouse", "raw": "frg", "to": "dropped: a finish short form, no warehouse on file"}]
    im = _im(words=["frg"], matches=[FRG], entities=entities, changes=changes)
    blob = " ".join(r["text"] for r in im["rows"][0]["result"]).lower()
    for internal in ("grounding", "hidden_keys", "closed_lists_index", "hint", "dropped: a finish short form"):
        assert internal not in blob, blob


def test_product_type_hint_reads_as_a_product_type():
    im = _im(words=["zzw"], matches=[_match("zzw", "Products", "code ZZW1 (ZZT)")], entities=[_entity("zzw", "product_type")])
    assert im["rows"][0]["understood"] == [{"text": '"zzw" as a product type'}]


def test_no_hint_drops_the_as_part():
    plain = _entity("zzw", "")
    plain["canonical_code"] = "ZZW1"
    im = _im(words=["zzw"], matches=[_match("zzw", "Products", "code ZZW1 (ZZT)")], entities=[plain])
    assert im["rows"][0]["understood"] == [{"text": '"zzw": ZZW1'}]
    im = _im(words=["zzw"], matches=[_match("zzw", "Products", "code ZZW1 (ZZT)")], entities=[_entity("zzw", "")])
    assert im["rows"][0]["understood"] == [{"text": '"zzw"'}]


def test_split_note_skips_empty_pieces_and_never_prints_none():
    to = ["", {"key": "finish", "label": "Finish", "said": "zzw", "value": "french_gold"},
          {"key": "", "label": "", "said": "zz", "value": None}, {"key": "", "label": "", "said": "", "value": None}]
    assert _result("specification", to) == {"outcome": "changed", "text": "Changed: read as Finish = french_gold; zz"}
