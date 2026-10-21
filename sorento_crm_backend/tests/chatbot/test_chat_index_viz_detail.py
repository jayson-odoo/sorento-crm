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
from tests.chatbot.conftest import session_factory  # noqa: F401

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def _match(word, list_, entry, *, close=False, held=False, line=None, plain=None, source=None) -> dict[str, Any]:
    return {
        "word": word, "list": list_, "entry": entry, "close_spelling": close, "held": held,
        "line": line if line is not None else (entry if held else f'- "{word}": {entry}'),
        "plain": plain if plain is not None else entry,
        "source": source if source is not None else "from the test list",
    }


def _entity(raw: str, hint: str, **extra: Any) -> dict[str, Any]:
    return {"raw": raw, "hint": hint, "canonical_code": None, "current_message": True, "confident": True, **extra}


def _stage(name: str, raw: dict | None = None) -> dict[str, Any]:
    return {"stage": name, "status": "ok", "started_at": NOW.isoformat(), "ms": 1, "summary": name,
            "why": name, "facts": {}, "error": None, "raw": raw or {}}


def _row(*, words, matches, entities=(), changes=None, failed=False, with_event=True, with_understood=True, tool=None):
    trace: list[dict] = [_stage("received")]
    if with_understood:
        trace.append(_stage("understood", {"parser_raw": {"entities": list(entities)}, "derived": {}}))
    if with_event:
        trace.append({"kind": "closed_lists_index", "at": NOW.isoformat(), "words": list(words),
                      "matches": list(matches), "failed": failed})
    if changes is not None:
        trace.append({"kind": "grounding", "at": NOW.isoformat(), "changes": list(changes)})
    if tool is not None:
        trace.append({"kind": "tool", "at": NOW.isoformat(), **tool})
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
    a1 = _match("zza", "Specifications", "spec finish = white (White)", plain="Finish: White",
                source="from the product finish list")
    a2 = _match("zza", "Product types", "product type Basin (class = basin)", close=True,
                plain="Product type: Basin", source="from the product type list",
                line='- "zza": spec finish = white (White); near product type Basin (class = basin)')
    b = _match("zzb", "Products", "code ZZB1 (ZZT ZZB1)")
    im = _im(words=["zza", "zzb"], matches=[a1, a2, b])
    assert [r["word"] for r in im["rows"]] == ["zza", "zzb"]
    first = im["rows"][0]
    assert first["matched"] == [
        {"plain": "Finish: White", "source": "from the product finish list", "close_spelling": False},
        {"plain": "Product type: Basin", "source": "from the product type list", "close_spelling": True},
    ]
    assert first["parser_got"] == [a1["line"], a2["line"]]
    assert im["rows"][1]["parser_got"] == [b["line"]]


def test_parser_got_lists_each_distinct_line_once():
    one = _match("frg", "Specifications", "spec finish = french_gold (French Gold)", line='- "frg": same')
    two = _match("frg", "Specifications", "spec finish = white (White)", line='- "frg": same')
    im = _im(words=["frg"], matches=[one, two])
    assert im["rows"][0]["parser_got"] == ['- "frg": same']


def test_held_matches_are_listed_apart_and_make_no_row():
    held = _match(None, "On record for the held product", "spec finish = chrome (Chrome)", held=True,
                  plain="Finish: Chrome", source="on record for the held product")
    im = _im(words=["frg"], matches=[FRG, held])
    assert im["held"] == ["Finish: Chrome"]
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
        {"text": '"frg" read as Finish: french gold'},
        {"text": '"frg" read as a warehouse'},
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
    assert texts == ['"FRG" read as Finish: french gold',
                     '"frg white" read as Finish: white']
    assert [n["text"] for n in im["not_from_lists"]] == ['"frgx" read as Finish: nope']


@pytest.mark.parametrize("hint,plain", [
    ("product", "a product"), ("category", "a product type"), ("specification", "a specification"),
    ("spec", "a specification"), ("attachment_type", "a file"), ("warehouse", "a warehouse"),
    ("brand", "a brand"), ("customer", "a customer"), ("sales_agent", "a sales agent"), ("zz_other", "zz other"),
])
def test_understood_text_names_the_hint_in_plain_words(hint, plain):
    im = _im(words=["zzw"], matches=[_match("zzw", "Products", "code ZZW1 (ZZT)")], entities=[_entity("zzw", hint)])
    assert im["rows"][0]["understood"] == [{"text": f'"zzw" read as {plain}'}]


def test_understood_value_prefers_spec_pair_then_canonical_code_then_listed_item():
    word = _match("zzw", "Products", "code ZZW1 (ZZT)")
    spec = _entity("zzw", "specification", spec_key="finish", spec_value="white", canonical_code="IGNORED")
    code = _entity("zzw", "product", canonical_code="ZZW1", listed_item="ignored")
    listed = _entity("zzw", "attachment_type", listed_item="zz_idx_drawing")
    im = _im(words=["zzw"], matches=[word], entities=[spec, code, listed])
    assert [u["text"] for u in im["rows"][0]["understood"]] == [
        '"zzw" read as Finish: white',
        '"zzw" read as product ZZW1',
        '"zzw" read as file type zz idx drawing',
    ]


def test_entities_matching_no_row_go_to_not_from_lists():
    im = _im(words=["frg"], matches=[FRG], entities=[_entity("IB", "warehouse")])
    assert im["not_from_lists"] == [{"text": '"IB" read as a warehouse', "outcome": "kept", "result": "Kept"}]
    assert im["rows"][0]["understood"] == [] and im["rows"][0]["result"] == []


def test_not_from_lists_carries_the_grounding_result_too():
    changes = [{"from": "warehouse", "raw": "IB", "to": "dropped: a finish short form, no warehouse on file"}]
    im = _im(words=["frg"], matches=[FRG], entities=[_entity("IB", "warehouse")], changes=changes)
    assert im["not_from_lists"] == [{
        "text": '"IB" read as a warehouse', "outcome": "dropped",
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
     "Kept: on the file type list (zz idx drawing)"),
    ("attachment_type", "on the cert_kind list: zz_idx_cert", "kept",
     "Kept: on the certificate list (zz idx cert)"),
    ("attachment_type", "on the cert_scheme list: ZZSCH", "kept",
     "Kept: on the certificate scheme list (ZZSCH)"),
    ("product", "canonical dropped: not on the candidate block", "changed",
     "Changed: product code not among the matches, removed"),
    ("product", "canonical refused: tied near codes", "changed",
     "Changed: several product codes fit, the bot asks which"),
    ("product", "canonical refused: several codes hold the word", "changed",
     "Changed: several product codes fit, the bot asks which"),
    ("specification", [{"key": "finish", "label": "Finish", "said": "zzw", "value": "white"}], "changed",
     "Changed: read as Finish: white"),
    ("specification", [{"key": "zz_key", "label": "", "said": "zzw", "value": "red"},
                       {"key": "size", "label": "Size", "said": "zzw", "value": 600}], "changed",
     "Changed: read as Zz key: red; Size: 600"),
    ("product", "category", "changed", "Changed: read as a product type"),
    ("category", "listed product type: Basin", "changed", "Changed: read as the product type Basin"),
    ("category", "Order", "changed", "Changed: read as Order"),
    ("category", "zz_type", "changed", "Changed: read as zz type"),
    ("specification", [{"key": "", "label": "", "said": "", "value": None}], "changed", "Changed"),
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
    assert im["rows"][0]["understood"] == [{"text": '"zzw" read as a product type'}]


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
    assert _result("specification", to) == {"outcome": "changed", "text": "Changed: read as Finish: french gold; zz"}


# Review round 2 (owner bar: no internal name on screen): every hint the engine reads reads as
# plain words, and an unmapped one never shows an underscore.
@pytest.mark.parametrize("hint, words", [
    ("sales_agent", "a sales agent"),
    ("order", "an order"),
    ("promotion", "a promotion"),
    ("product_attachment", "a product file"),
    ("inventory", "stock"),
    ("incoming", "incoming stock"),
    ("zz_new_kind", "zz new kind"),
])
def test_every_hint_reads_as_plain_words(hint, words):
    im = _im(words=["ali"], matches=[], entities=[_entity("ali", hint)], changes=[])
    [item] = im["not_from_lists"]
    assert item["text"] == f'"ali" read as {words}'
    assert "_" not in item["text"]


# --------------------------------------------------------------------------- #
# v2: plain values (kinds), db labels, the looked-up step, no internal words
# --------------------------------------------------------------------------- #


def _one(entity, *, changes=None, raw="zzw"):
    im = _im(words=[raw], matches=[_match(raw, "Products", "code ZZW1 (ZZT)")], entities=[entity], changes=changes)
    return im["rows"][0]["understood"][0]["text"], (im["rows"][0]["result"] or [None])[0]


def test_product_type_and_category_read_as_product_type_value():
    text, _ = _one(_entity("basin", "category", canonical_code="Basin"), raw="basin")
    assert text == '"basin" read as product type Basin'
    text, _ = _one(_entity("basin", "product_type", spec_value="Basin"), raw="basin")
    assert text == '"basin" read as product type Basin'


def test_certificate_scheme_and_kind_read_from_the_kept_note():
    scheme = _entity("ce", "attachment_type", listed_item="CE")
    text, res = _one(scheme, raw="ce", changes=[{"from": "attachment_type", "raw": "ce", "to": "on the cert_scheme list: CE"}])
    assert text == '"ce" read as certificate scheme CE'
    assert res == {"outcome": "kept", "text": "Kept: on the certificate scheme list (CE)"}
    kind = _entity("cert", "attachment_type", listed_item="zz_cert")
    text, _ = _one(kind, raw="cert", changes=[{"from": "attachment_type", "raw": "cert", "to": "on the cert_kind list: zz_cert"}])
    assert text == '"cert" read as certificate zz cert'


def test_sales_agent_reads_plain():
    text, _ = _one(_entity("ali", "sales_agent"), raw="ali")
    assert text == '"ali" read as a sales agent'


# -- looked_up -------------------------------------------------------------- #


def _tool(args, name="check_stock_levels"):
    return {"name": name, "args": args, "envelope": {}, "ms": 3}


def test_looked_up_is_none_without_a_tool_event():
    assert _im(words=["frg"], matches=[FRG])["looked_up"] is None


def test_looked_up_names_the_tool_and_lists_plain_details_in_order():
    args = {"product_code": "ZZP1", "warehouse_codes": ["ZZA", "ZZB"], "limit": 5, "note": "", "none": None,
            "empty": [], "nested": {"x": 1}}
    im = _im(words=["frg"], matches=[FRG], tool=_tool(args))
    assert im["looked_up"] == {"what": "Check stock levels", "details": ["Product code: ZZP1", "Warehouse codes: ZZA, ZZB", "Limit: 5"]}


def test_looked_up_skips_uuid_looking_values_and_caps_at_eight_details():
    args = {"customer_id": "123e4567-e89b-12d3-a456-426614174000", "ids": ["123e4567-e89b-12d3-a456-426614174000"]}
    args.update({f"key_{i}": f"v{i}" for i in range(12)})
    im = _im(words=["frg"], matches=[FRG], tool=_tool(args))
    details = im["looked_up"]["details"]
    assert len(details) == 8
    assert details[0] == "Key 0: v0"
    assert not any("123e4567" in d for d in details)
    assert not any(d.startswith("Customer id") or d.startswith("Ids") for d in details)


# -- no internal words ------------------------------------------------------- #


def _texts(im):
    out = [w["text"] for w in im["words"]] + list(im["held"])
    for row in im["rows"]:
        for m in row["matched"]:
            out += [m["plain"], m["source"]]
        out += [u["text"] for u in row["understood"]] + [r["text"] for r in row["result"]]
    for n in im["not_from_lists"]:
        out += [n["text"], n["result"]]
    if im["looked_up"]:
        out += [im["looked_up"]["what"], *im["looked_up"]["details"]]
    return out


def test_no_on_screen_text_has_snake_case_or_internal_words():
    import re

    entities = [
        _entity("frg", "specification", spec_key="finish_type", spec_value="french_gold"),
        _entity("frg", "sales_agent"),
        _entity("drw", "attachment_type", listed_item="zz_idx_drawing"),
        _entity("basin", "product_type", spec_value="wash_basin"),
        _entity("qq", "some_new_hint"),
    ]
    changes = [
        {"from": "specification", "raw": "frg", "to": [{"key": "finish_type", "label": "", "said": "frg", "value": "french_gold"}]},
        {"from": "attachment_type", "raw": "drw", "to": "on the attachment_type list: zz_idx_drawing"},
        {"from": "some_new_hint", "raw": "qq", "to": "canonical refused: tied near codes"},
    ]
    matches = [_match("frg", "Specifications", "x", plain="Finish: French gold", source="from the product finish list"),
               _match("drw", "File types", "y", plain="ZZ Drawing", source="from the file type list")]
    im = _im(words=["frg", "drw"], matches=matches, entities=entities, changes=changes,
             tool=_tool({"product_code": "ZZP1", "warehouse_codes": ["a_b"]}, name="check_stock_levels"))
    blob = " ".join(_texts(im))
    assert not re.search(r"[A-Za-z]_[A-Za-z]", blob), blob
    for word in ("parser", "token", "grounding"):
        assert word not in blob.lower(), word


# -- labels from the database ------------------------------------------------- #


def test_db_labels_and_type_names_are_used_when_a_session_is_given(session_factory):
    import uuid

    from app.models.base import set_company_scope
    from app.models.product_spec import ProductSpecRegistry
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests.chatbot._attach_world import World

    setup = session_factory()
    setup.add(ProductSpecRegistry(id=str(uuid.uuid4()), spec_key="zz_dbfinish", label="ZZ Db Finish", data_type="enum",
                                  allowed_values=["zz_gold"], value_labels={"zz_gold": "ZZ Gold Label"}))
    setup.commit()
    world = World(session_factory)
    world.type("ZZ Technical Drawing", code="zz_tech_dwg")
    world.commit()

    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    entities = [
        _entity("frg", "specification", spec_key="zz_dbfinish", spec_value="zz_gold"),
        _entity("drawing", "attachment_type", listed_item="zz_tech_dwg"),
    ]
    changes = [
        {"from": "specification", "raw": "frg", "to": [{"key": "zz_dbfinish", "label": "", "said": "frg", "value": "zz_gold"}]},
        {"from": "attachment_type", "raw": "drawing", "to": "on the attachment_type list: zz_tech_dwg"},
    ]
    matches = [_match("frg", "Specifications", "x"), _match("drawing", "File types", "y")]
    row = _row(words=["frg", "drawing"], matches=matches, entities=entities, changes=changes)
    im = compose_trace_detail(row, db)["index_match"]
    by_word = {r["word"]: r for r in im["rows"]}
    assert by_word["frg"]["understood"] == [{"text": '"frg" read as ZZ Db Finish: ZZ Gold Label'}]
    assert by_word["frg"]["result"] == [{"outcome": "changed", "text": "Changed: read as ZZ Db Finish: ZZ Gold Label"}]
    assert by_word["drawing"]["understood"] == [{"text": '"drawing" read as file type ZZ Technical Drawing'}]
    assert by_word["drawing"]["result"] == [{"outcome": "kept", "text": "Kept: on the file type list (ZZ Technical Drawing)"}]
