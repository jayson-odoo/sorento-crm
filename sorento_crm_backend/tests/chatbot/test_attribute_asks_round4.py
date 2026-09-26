"""Owner console test of round 3 on PR #833 (27 Sep 2026 00:03 to 00:07 MYT, console :3084,
head 1683cb2f1, contact 487555417). Rulings R1 to R7 of the round 4 fix brief.

The owner's words (verbatim): "i want weights as brand preference instead of switch, i got
feedback more than that one wor, like Brand, product type needs to be line by line, label
needs to be bold, you see my conversation, bruh i said 10 but it come out so many, then the
ask about gunmetal wash basin means what ah, so it got match or not? i have no visibility
into whether it does the matching, i can see you fixed, but it can be better, then you see i
think the ask offered and the question not tally, like i clarify if it is tap or wash basin
and i said tap, you supposed to do the searching and tell me got more products is it? i
think you at last search by code isit? and also the water closet t trap ask, why it match s
trap? and why all the values are snake case? too technical, i don't want"

The eight exchanges live in `fixtures/owner_console_2026_09_27.json` (the owner's text, the
parser reading stubbed from what each reply shows, and the reply the owner saw). Every turn
runs `engine.run_turn` with the real resolver, class vocabulary, spec registry and brands
table; only the parser and the MCP tool call are stubbed (same substrate as round 3).

Every reply any test here produces is scanned for snake_case (`_Chat.say`, R7).
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text as sql

from tests.chatbot.test_attribute_asks_round3 import (  # noqa: F401 - fixtures used by name
    _Chat,
    _ask,
    _bare,
    _display,
    _entity,
    _product,
    world as r3world,
)
from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401 - fixtures used by name
from tests.chatbot.test_lane_require import _stock_for
from tests.chatbot.test_reverse_asks_owner_phrasings import _class_category, _incoming_for

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "owner_console_2026_09_27.json"

#: A snake_case token: lowercase words joined by "_", not part of a file name, a path, an
#: address or a code (those are bounded by ".", "/", "@" or "-").
SNAKE_RE = re.compile(r"(?<![\w./@-])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?![\w./@-])")


def snake_tokens(text: str) -> list[str]:
    return SNAKE_RE.findall(text or "")


# --------------------------------------------------------------------------- #
# World                                                                         #
# --------------------------------------------------------------------------- #


def _weigh(db, brand, weight: float) -> None:
    """R1: a brand's chatbot weight, as Master Data > Brands stores it."""
    if not _has_weights():
        return
    db.execute(sql("UPDATE brands SET chatbot_weight = :w WHERE id = :id"), {"w": weight, "id": brand.id})
    db.flush()


def _has_weights() -> bool:
    from app.models.product import Brand

    return hasattr(Brand, "chatbot_weight")


def _zero_every_weight(db) -> None:
    if not _has_weights():
        return
    db.execute(sql("UPDATE brands SET chatbot_weight = 0"))
    db.flush()


@pytest.fixture()
def world(r3world):
    """Round 3's world (Sorento water closets, basins, tubs; one Mocha water closet and
    basin), plus: two Sorento cold taps with stock, one Sorento wash basin with incoming
    (and no stock), and Cabana with two wash basins with stock. Weights: Sorento 1.5 (the
    seed), Mocha 0.5, Cabana 0 (unweighted)."""
    from app.models.product import Brand

    db = r3world["db"]
    _zero_every_weight(db)
    uom = r3world["srt_tubs"][0].base_uom_id
    tap_category = _class_category(db, "FT")
    basin_category = _class_category(db, "WB")
    sorento, mocha = r3world["sorento"], r3world["mocha"]
    cabana = Brand(id=str(uuid.uuid4()), brand_code=f"CBN{uuid.uuid4().hex[:6]}", brand_name=f"Cabana{uuid.uuid4().hex[:4]}", is_active=True)
    db.add(cabana)
    db.flush()
    taps = [
        _product(db, brand_id=sorento.id, category_id=tap_category, uom_id=uom, noun="COLD TAP", prefix="ZZR4T", name=f"Sorento Cold Tap {i}")
        for i in range(2)
    ]
    incoming_basin = _product(
        db, brand_id=sorento.id, category_id=basin_category, uom_id=uom, noun="WASH BASIN", prefix="ZZR4I", name="Sorento Incoming Basin"
    )
    cabana_basins = [
        _product(db, brand_id=cabana.id, category_id=basin_category, uom_id=uom, noun="WASH BASIN", prefix="ZZR4CB", name=f"Cabana Basin {i}")
        for i in range(2)
    ]
    for p in taps + cabana_basins:
        _stock_for(db, product_id=p.id, warehouse_id=r3world["warehouse"].id)
    _incoming_for(db, product_id=incoming_basin.id)
    _weigh(db, sorento, 1.5)
    _weigh(db, mocha, 0.5)
    db.commit()
    return {
        **r3world,
        "cabana": cabana,
        "taps": taps,
        "incoming_basin": incoming_basin,
        "cabana_basins": cabana_basins,
        "every": r3world["every"] + taps + [incoming_basin] + cabana_basins,
    }


class _ScannedChat(_Chat):
    """Round 3's chat, with every reply scanned for snake_case (R7)."""

    def say(self, text: str, verdict: dict[str, Any]) -> str:
        reply = super().say(text, verdict)
        assert not snake_tokens(reply), (text, snake_tokens(reply), reply)
        return reply


@pytest.fixture()
def chat(session_factory, monkeypatch, stub_parser, stub_access, world):
    return _ScannedChat(session_factory, monkeypatch, stub_parser, stub_access, world)


@pytest.fixture()
def list_max_2(monkeypatch):
    """The owner's 276 and 62 lowered to a list limit of 2, so this world's 3 Sorento
    wash basins and 5 P trap water closets are "too many to list" the way theirs were."""
    from app.services.chatbot.lanes.business import answer as answer_mod

    monkeypatch.setattr(answer_mod, "SET_LIST_MAX", 2)


def _product_ask(raw: str, goal: str) -> dict[str, Any]:
    from tests.chatbot.test_engine import _parser_output

    return _parser_output(entities=[_entity(raw, "product")], user_goal=goal, match_mode="and")


def _verdict(spec: dict[str, Any], text: str) -> dict[str, Any]:
    if "ask" in spec:
        return _ask(spec["ask"], spec["class_word"], text)
    if "bare" in spec:
        return _bare(**spec["bare"])
    return _product_ask(spec["product"], text)


def _exchanges() -> list[dict[str, Any]]:
    return json.loads(_FIXTURE.read_text())["exchanges"]


# Reply readers ------------------------------------------------------------ #

_ROW_RE = re.compile(r"^(\d+)\. (.+) \((\S+)\)(?: \*\(Discontinued\)\*)?$")


def _rows(text: str) -> list[dict[str, Any]]:
    """R3's compact rows: line 1 "N. <name> (<code>)", then at most one facts line."""
    out: list[dict[str, Any]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _ROW_RE.match(lines[i])
        if m:
            row = {"n": int(m.group(1)), "name": m.group(2), "code": m.group(3), "lines": [lines[i]]}
            j = i + 1
            while j < len(lines) and lines[j].strip() and not _ROW_RE.match(lines[j]):
                row["lines"].append(lines[j])
                j += 1
            out.append(row)
            i = j
        else:
            i += 1
    return out


def _header(text: str) -> list[str]:
    """The lines before the first blank line."""
    return text.split("\n\n", 1)[0].splitlines()


def _codes(products) -> set[str]:
    return {p.product_code for p in products}


# --------------------------------------------------------------------------- #
# R1: brand preference is a weight per brand                                    #
# --------------------------------------------------------------------------- #


def test_r1_the_highest_weighted_brand_heads_the_set_and_the_others_follow_the_weights(chat, world):
    """Mocha (0.5) is named before Cabana (0) although Cabana has more wash basins."""
    text = chat.say("which wash basin has stock", _ask("stock", "wash basin", "which wash basin has stock"))
    sorento, mocha, cabana = (_display(world[k].brand_name) for k in ("sorento", "mocha", "cabana"))
    assert _header(text)[0] == f"*Brand:* {sorento}", text
    assert text.splitlines()[-1] == f"Other brands with stock: {mocha} 1, {cabana} 2. Name one to see them.", text


def test_r1_raising_another_brand_above_sorento_makes_it_the_header_brand(chat, world):
    _weigh(world["db"], world["cabana"], 2.0)
    world["db"].commit()
    text = chat.say("which wash basin has stock", _ask("stock", "wash basin", "which wash basin has stock"))
    sorento, mocha, cabana = (_display(world[k].brand_name) for k in ("sorento", "mocha", "cabana"))
    assert _header(text)[0] == f"*Brand:* {cabana}", text
    assert {r["code"] for r in _rows(text)} == _codes(world["cabana_basins"]), text
    assert text.splitlines()[-1] == f"Other brands with stock: {sorento} 3, {mocha} 1. Name one to see them.", text


def test_r1_a_weighted_brand_the_set_does_not_reach_hands_the_header_to_the_next_weight(chat, world):
    """No Sorento tap has incoming; the Mocha weight is next, and Mocha has none either,
    so with no weighted brand in the set the set stays whole with no brand line."""
    _weigh(world["db"], world["sorento"], 0)
    _weigh(world["db"], world["mocha"], 0)
    world["db"].commit()
    text = chat.say("which wash basin has stock", _ask("stock", "wash basin", "which wash basin has stock"))
    assert not [ln for ln in _header(text) if ln.startswith("*Brand:*")], text
    assert "Other brands" not in text, text
    assert "6 wash basins have stock." in text, text


def test_r1_brands_store_a_weight_not_a_switch():
    from app.models.product import Brand

    assert hasattr(Brand, "chatbot_weight")
    assert not hasattr(Brand, "is_chatbot_default")


# --------------------------------------------------------------------------- #
# R2: the header is line by line, labels bold                                   #
# --------------------------------------------------------------------------- #


def test_r2_the_header_says_one_filter_per_line_with_bold_labels(chat, world):
    text = chat.say("which water closet has stock, p trap", _ask("stock", "water closet", "which water closet has stock, p trap", extra=[_entity("p trap", "spec")]))
    brand = _display(world["sorento"].brand_name)
    assert _header(text) == [
        f"*Brand:* {brand}",
        "*Product type:* Water closet",
        "*Trap:* P trap",
        "5 water closets have stock.",
    ], text


def test_r2_a_class_word_with_a_spec_after_it_keeps_its_product_type_line(chat, world):
    """Owner exchange 3: "any water closet p trap got stock" read as ONE class word lost
    the Product type from the header ("Brand: Sorento, Trap: P trap. 62 water closets")."""
    text = chat.say("any water closet p trap got stock", _ask("stock", "water closet p trap", "any water closet p trap got stock"))
    brand = _display(world["sorento"].brand_name)
    assert _header(text)[:3] == [f"*Brand:* {brand}", "*Product type:* Water closet", "*Trap:* P trap"], text
    assert {r["code"] for r in _rows(text)} == _codes(world["srt_ptrap"]), text


# --------------------------------------------------------------------------- #
# R3: a count answer is compact                                                 #
# --------------------------------------------------------------------------- #


def test_r3_a_stock_row_is_two_lines_name_with_code_then_the_stock(chat, world, list_max_2):
    """Owner exchanges 1 and 2: "10" came out as 10 blocks of 5 to 8 lines."""
    chat.say("any basin has stock", _ask("stock", "basin", "any basin has stock"))
    text = chat.say("10", _bare(top_n=10))
    rows = _rows(text)
    assert len(rows) == 2, text
    names = {p.product_code: p.product_name for p in world["srt_basins"]}
    for row in rows:
        assert row["code"] in names and row["name"] == names[row["code"]], row
        assert len(row["lines"]) <= 2, row
        assert row["lines"][1:] == ["*Total:* 10"], row
    assert not re.search(r"\*(Material|Finish or colour|Product Code):\*", text), text
    assert world["warehouse"].warehouse_code not in text, text


def test_r3_a_certificate_row_is_two_lines_too(chat, world):
    text = chat.say("which wash basin has cert", _ask("cert", "wash basin", "which wash basin has cert"))
    rows = _rows(text)
    assert {r["code"] for r in rows} == _codes(world["srt_basins"]), text
    for row in rows:
        assert len(row["lines"]) == 2, row
        assert row["lines"][1].startswith("*Certificate Number:* "), row
        assert "*Valid Until:* " in row["lines"][1], row
        assert "*File Name:*" not in row["lines"][1], row


def test_r3_an_incoming_row_is_two_lines_too(chat, world):
    text = chat.say("which bathtub has incoming", _ask("incoming", "bathtub", "which bathtub has incoming"))
    rows = _rows(text)
    assert {r["code"] for r in rows} == _codes(world["srt_tubs"]), text
    for row in rows:
        assert len(row["lines"]) <= 2, row


def test_r3_a_set_reply_of_fifty_rows_fits_one_whatsapp_message(chat, world, monkeypatch):
    """50 two-line rows stay under WhatsApp's 4,096 characters with names this long,
    leaving 400 for the header lines and the other-brands line (a blank line between
    products stays, round 3 ruling)."""
    from app.services.chatbot.lanes.business import fetch as fetch_mod

    items = [
        {
            "title": f"SRTWC{i:04d}-SH-NEW-P",
            "fields": [
                {"key": "product_code", "label": "Product Code", "value": f"SRTWC{i:04d}-SH-NEW-P"},
                {"key": "total_on_hand", "label": "Total", "value": 34},
                {"label": "BRW", "value": 12},
                {"label": "BRW-BB", "value": 22},
            ],
            "flags": {},
        }
        for i in range(50)
    ]
    labels = {f"SRTWC{i:04d}-SH-NEW-P": {"name": "Sorento Close Couple WC Soft Close"} for i in range(50)}
    text = fetch_mod.set_rows_text(items, labels, require={"stock": True}, offset=0)
    assert len(text) <= 4096 - 400, len(text)


# --------------------------------------------------------------------------- #
# R4: a miss says what was searched                                             #
# --------------------------------------------------------------------------- #


def test_r4_a_miss_names_the_value_searched_and_the_count_in_other_values(chat, world):
    """Owner exchange 5: "Couldn't find a gunmetal wash basin with incoming stock" said
    nothing about whether gunmetal was understood."""
    text = chat.say(
        "any gunmetal wash basin has incoming",
        _ask("incoming", "gunmetal wash basin", "any gunmetal wash basin has incoming"),
    )
    assert text.startswith(
        "No gunmetal wash basins with incoming stock "
        "(I looked for Finish or colour: Gunmetal among wash basins). "
        "1 wash basin has incoming stock in another finish or colour: "
    ), text
    offer = text.index("Would you like me to escalate")
    assert re.search(r"in another finish or colour: [A-Z][\w ]* 1\. ", text[:offer]), text


def test_r4_a_miss_with_nothing_in_any_value_says_so(chat, world):
    text = chat.say(
        "any gunmetal bathtub has cert",
        _ask("cert", "gunmetal bathtub", "any gunmetal bathtub has cert"),
    )
    assert text.startswith(
        "No gunmetal bathtubs with a certificate "
        "(I looked for Finish or colour: Gunmetal among bathtubs). "
        "No bathtubs have a certificate in any finish or colour. "
    ), text


# --------------------------------------------------------------------------- #
# R5: the clarify answer re-runs the original ask                               #
# --------------------------------------------------------------------------- #


def test_r5_answering_the_clarify_runs_the_counted_set_the_customer_asked_for(chat, world):
    """Owner exchanges 6 and 7: "tap" answered a code search ("Here are the matching
    products. 1. *Product Code:* SRTWT5906-COLD TAP-NL ...")."""
    ask = chat.say("any water tap basin", _ask("stock", "water tap basin", "any water tap basin"))
    assert ask == "I don't know 'water tap basin' as a product type. Did you mean tap or wash basin?", ask
    before = len(chat.calls)
    text = chat.say("tap", _product_ask("tap", "tap"))
    assert "Here are the matching products" not in text, text
    assert _header(text)[-2:] == ["*Product type:* Tap", "2 taps have stock."], text
    assert {r["code"] for r in _rows(text)} == _codes(world["taps"]), text
    assert [c["name"] for c in chat.calls[before:]] != ["crm_master_products_list"], chat.calls[before:]


def test_r5_the_other_option_runs_that_set(chat, world):
    chat.say("any water tap basin", _ask("stock", "water tap basin", "any water tap basin"))
    text = chat.say("wash basin", _product_ask("wash basin", "wash basin"))
    assert "3 wash basins have stock." in _header(text)[-1], text


def test_r5_a_reply_that_is_not_an_option_is_its_own_question(chat, world):
    chat.say("any water tap basin", _ask("stock", "water tap basin", "any water tap basin"))
    text = chat.say("which bathtub has incoming", _ask("incoming", "bathtub", "which bathtub has incoming"))
    assert "bathtubs have incoming stock." in _header(text)[-1], text
    # And the clarify is spent: a later bare "tap" is not read as its answer.
    later = chat.say("tap", _product_ask("tap", "tap"))
    assert "taps have stock" not in later, later


# --------------------------------------------------------------------------- #
# R6: an unknown attribute value is said back, never matched to a neighbour     #
# --------------------------------------------------------------------------- #


def test_r6_unknown_values_are_found_by_the_registry_not_by_a_list():
    from app.services.product_spec_search import unknown_spec_values
    from tests._pg_fixture import pg_session

    with pg_session() as db:
        from app.services.product_spec_registry import seed_spec_registry

        seed_spec_registry(db)
        found = unknown_spec_values(db, "any water clost t trap?")
        assert [(u["said"], u["label"], u["known"]) for u in found] == [("t trap", "Trap", ["P trap", "S trap"])]
        for fine in ("water closet p trap", "water closet s-trap 250mm", "water closet trap 250mm", "wash basin", "floor waste wc"):
            assert unknown_spec_values(db, fine) == [], fine


def test_r6_a_product_ask_with_an_unknown_value_is_said_back(chat, world):
    """Owner exchange 8: "any water clost t trap?" listed s trap water closets."""
    text = chat.say("any water clost t trap?", _product_ask("water clost t trap", "any water closet t trap"))
    assert text == "I don't know 't trap' as a trap. I know P trap and S trap.", text
    assert not [c for c in chat.calls if c["name"] == "crm_master_products_list"], chat.calls


def test_r6_a_set_ask_with_an_unknown_value_is_said_back_and_the_answer_reruns_it(chat, world):
    text = chat.say(
        "which water closet t trap has stock",
        _ask("stock", "water closet", "which water closet t trap has stock", extra=[_entity("t trap", "spec")]),
    )
    assert text == "I don't know 't trap' as a trap. I know P trap and S trap.", text
    assert not _codes(world["srt_strap"]) & {r["code"] for r in _rows(text)}, text
    again = chat.say("p trap", _product_ask("p trap", "p trap"))
    assert "*Trap:* P trap" in _header(again), again
    assert {r["code"] for r in _rows(again)} == _codes(world["srt_ptrap"]), again


# --------------------------------------------------------------------------- #
# R7: every value is in plain words                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw, plain",
    [
        ("cold_only", "Cold only"),
        ("s_trap", "S trap"),
        ("toilet_seat", "Toilet seat"),
        ("free_standing", "Free standing"),
        ("pp", "PP"),
        ("stainless_steel", "Stainless steel"),
        ("White", "White"),
        (250, "250"),
    ],
)
def test_r7_a_stored_value_reads_as_plain_words(raw, plain):
    from app.services.product_spec_registry import display_spec_value

    assert display_spec_value(raw) == plain


def test_r7_a_curated_value_label_wins():
    from app.services.product_spec_registry import display_spec_value

    assert display_spec_value("s_trap", {"s_trap": "S-trap (floor outlet)"}) == "S-trap (floor outlet)"


def test_r7_every_enum_value_in_the_registry_seed_has_plain_words():
    from app.services.product_spec_registry import SPEC_REGISTRY_SEED, display_spec_value

    for row in SPEC_REGISTRY_SEED:
        for value in row.get("allowed_values") or []:
            shown = display_spec_value(value, row.get("value_labels"))
            assert "_" not in shown and not snake_tokens(shown), (row["spec_key"], value, shown)


def test_r7_the_product_list_carries_each_spec_value_in_plain_words(world):
    from app.services.product_service import ProductService

    db = world["db"]
    tap = world["taps"][0]
    specs = ProductService(db).spec_list_for_products([tap.id])[str(tap.id)]
    water = [s for s in specs if s["key"] == "water_supply"]
    assert water and water[0]["value"] == "cold_only" and water[0]["display_value"] == "Cold only", specs


def test_r7_a_product_search_reply_never_prints_a_stored_value(chat, world, monkeypatch):
    """Owner exchange 7's reply: "*Specs:* Product class: Tap, Water supply: cold_only,
    ..., Finish or colour: nickel"."""
    from app.services.chatbot.lanes.business import fetch as fetch_mod

    envelope = {
        "result_type": "products",
        "intro": "Here are the matching products.",
        "has_result": True,
        "spec_vocabulary": {"class": "Product class", "water_supply": "Water supply", "trap_type": "Trap", "wc_type": "Type"},
        "items": [
            {
                "title": "SRTWT5906-COLD TAP-NL",
                "fields": [
                    {"label": "Product Code", "value": "SRTWT5906-COLD TAP-NL"},
                    {"key": "spec:class", "label": "Product class", "value": "Tap"},
                    {"key": "spec:water_supply", "label": "Water supply", "value": "cold_only"},
                    {"key": "spec:trap_type", "label": "Trap", "value": "s_trap"},
                    {"key": "spec:wc_type", "label": "Type", "value": "toilet_seat"},
                ],
                "flags": {},
            }
        ],
    }
    fetch_mod._project_product_specs(envelope, [])
    [specs] = [f["value"] for f in envelope["items"][0]["fields"] if f.get("label") == "Specs"]
    assert specs == "Product class: Tap, Water supply: Cold only, Trap: S trap, Type: Toilet seat", specs


# --------------------------------------------------------------------------- #
# The owner's eight exchanges, replayed                                         #
# --------------------------------------------------------------------------- #


def test_replay_the_owners_eight_exchanges(chat, world, list_max_2):
    """The eight turns in order, one conversation. Each reply is scanned for snake_case
    by `_ScannedChat`; the assertions are each ruling's own, turn by turn."""
    sorento = _display(world["sorento"].brand_name)
    replies = [chat.say(x["text"], _verdict(x["verdict"], x["text"])) for x in _exchanges()]
    one, two, three, four, five, six, seven, eight = replies

    # 1: R1 + R2. Line by line; the weighted brand heads it; the others by weight.
    assert _header(one)[:2] == [f"*Brand:* {sorento}", "*Product type:* Wash basin"], one
    assert _header(one)[2].startswith("3 wash basins have stock. That is too many to list"), one
    # 2: R3. "10" lists what fits, two lines a product.
    assert len(_rows(two)) == 2 and all(len(r["lines"]) <= 2 for r in _rows(two)), two
    # 3: R2. The Product type line is there.
    assert "*Product type:* Water closet" in _header(three) and "*Trap:* P trap" in _header(three), three
    # 4: R3.
    assert all(len(r["lines"]) <= 2 for r in _rows(four)) and _rows(four), four
    # 5: R4.
    assert five.startswith("No gunmetal wash basins with incoming stock (I looked for Finish or colour: Gunmetal among wash basins)."), five
    # 6 and 7: R5.
    assert six.endswith("Did you mean tap or wash basin?"), six
    assert "2 taps have stock." in _header(seven), seven
    # 8: R6.
    assert eight == "I don't know 't trap' as a trap. I know P trap and S trap.", eight


def test_the_console_cases_expect_no_snake_case():
    """R7 over the recorded console cases too: no expected reply names a stored value."""
    import yaml

    path = Path(__file__).resolve().parent / "console_cases" / "2026-09-11-attribute-first-asks.yaml"
    body = yaml.safe_load(path.read_text())
    found: list[str] = []

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, str(k))
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, str) and key in ("reply_contains", "reply_starts_with", "reply_equals", "reply_first_line"):
            found.extend(snake_tokens(node))

    walk(body)
    assert not found, found
