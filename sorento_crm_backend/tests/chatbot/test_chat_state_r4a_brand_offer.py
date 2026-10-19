"""CHAT-STATE round 4, R4-A (red): the brand offer reaches the State and narrows the held set.

After the bot shows a product set and offers other brands, the offer is stored at
`focus.set_page["set_key"]["other_brands"]` (the writer returns `{"set_key": key}`,
`turn_runtime` ~4453). `turn/chat_state.py` reads `focus.set_page["other_brands"]` at the
TOP level, so the parser's State block never shows the offer, and on a state-led turn the
engine skips the brand pick (`if not state_led or answering`), so the brand word widens to
every catalogue product named after it instead of narrowing the held set (card R1: a refine
keeps the subject and adds that axis; card R9: a short reply to a bot list keeps the held item).

Real members (train2_refine): es-e9d2507a71 ("only sorento", 37 held basins, an owed
how-many task, offer Sorento 18 / Bravat 15 / Others 2 / Cabana 1 / Mocha 1) and
es-242b332bca ("Sorento", 182 held P trap WCs, offer Sorento 128 / Cabana 22 / ...). Held
codes are real codes from the members' gold; A611 and ACC-SRT1021 are real catalogue
SORENTO-named products that are NOT held (the widening the live run produced). The parser
output is stubbed (it said `brand Sorento` correctly); the code executes.

Unclear from the gold: a brand named in a different script or language ("只要Sorento") is
asserted to behave like the English one, because the parser emits the same brand entity.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.product import Brand, Product
from app.services.chatbot.turn import chat_state, task as task_mod
from app.services.chatbot.turn.state import Focus, State, focus_to_wire
from tests.chatbot._r9_engine_console import SORENTO
from tests.chatbot._turn_helpers import entity
from tests.chatbot.test_chat_state_r3a_fetch_quantity import _seed_more
from tests.chatbot.test_chat_state_seam import Seam, _emit, _op, seam  # noqa: F401
from tests.chatbot.test_engine import stub_access  # noqa: F401

DECOYS = ["A611", "ACC-SRT1021"]  # catalogue products named SORENTO, never held

E9 = {
    "offer": [("Sorento", 18), ("Bravat", 15), ("Others", 2), ("Cabana", 1), ("Mocha", 1)],
    "held": {
        "Sorento": ["SRTWB1086", "SRTWB1090", "SRTWB1096"],
        "Bravat": ["BRBC22207W-1", "BRBC22213W"],
        "Cabana": ["CWB1096-CB"],
        "Mocha": ["MWB7014"],
    },
    "total": 37, "noun": "basins", "task": "open",
}
M242 = {
    "offer": [("Sorento", 128), ("Cabana", 22), ("Bravat", 13), ("Mocha", 12), ("Others", 4), ("Infinity", 2), ("Iborn", 1)],
    "held": {
        "Sorento": ["SRTWC286-SH-P", "SRTWC8354-SH-P", "SRTWC6030-SH-BL"],
        "Cabana": ["CWC7601-P-RL", "CWC603-P"],
        "Mocha": ["MWC7602-P"],
        "Bravat": ["BRC21120UW-P-MY"],
        "Infinity": ["IDCSA-0167-P-UF"],
    },
    "total": 182, "noun": "water closets", "task": "answered",
}


def _offer(member: dict) -> list[dict]:
    return [{"brand": b, "count": n} for b, n in member["offer"]]


def _set_page(member: dict) -> dict:
    return {"set_key": {"require": {}, "scope_terms": [], "domain": "inventory", "set_noun": member["noun"],
                        "access_levels": [], "total": member["total"], "shown": 20,
                        "other_brands": _offer(member)}}


def _held_codes(member: dict) -> list[str]:
    return [c for codes in member["held"].values() for c in codes]


def _seed(seam: Seam, member: dict) -> None:
    codes = [c for c in _held_codes(member) + DECOYS if c not in seam.uuid_of]
    _seed_more(seam, codes)
    db = seam.session_factory()
    db.info["company_scope"] = frozenset({SORENTO})
    brands: dict[str, str] = {}
    for name in list(member["held"]) + ["Sorento"]:
        if name in brands:
            continue
        row = db.query(Brand).filter(Brand.brand_code == name.upper(), Brand.company_id == SORENTO).first()
        if row is None:
            row = Brand(id=str(uuid.uuid4()), brand_code=name.upper(), brand_name=name, company_id=SORENTO)
            db.add(row)
            db.flush()
        brands[name] = row.id
    for name, held in member["held"].items():
        for code in held:
            db.query(Product).filter(Product.id == seam.uuid_of[code]).update({"brand_id": brands[name]})
    for code in DECOYS:
        db.query(Product).filter(Product.id == seam.uuid_of[code]).update({"brand_id": brands["Sorento"]})
    db.commit()


def _held_state(seam: Seam, member: dict) -> dict:
    _seed(seam, member)
    rows, slots = [], []
    for code in _held_codes(member):
        key = seam.uuid_of[code]
        rows.append({"raw": code, "canonical_code": code, "hint": "product", "uuid": key, "current_message": False})
        slots.append(task_mod.Slot(key, code, None if member["task"] == "open" else 10))
    status = task_mod.OPEN if member["task"] == "open" else task_mod.ANSWERED
    task = task_mod.Task(kind="stock_qty", domain="inventory", status=status, slots=tuple(slots))
    focus = Focus(products=rows, domains=["inventory"], tasks=(task,), set_page=_set_page(member))
    return {"focus": focus_to_wire(focus), "open_question": None}


def _brand_pick(raw: str, code: str | None = None) -> dict:
    return _emit(domain_hint="inventory", intent_hint="check_stock",
                 entities=[entity(raw, "brand", canonical_code=code or raw.upper())],
                 state_changes=[_op("set", "brand")])


def _ids_in_calls(calls) -> set[str]:
    found: set[str] = set()

    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                if k in ("product_ids", "product_id") and x:
                    found.update(x if isinstance(x, list) else [x])
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str) and v.startswith("{"):
            try:
                walk(json.loads(v))
            except ValueError:
                pass

    for _name, args in calls:
        walk(args)
    return found


# (id, member, message, brand raw, brand name the message picks)
CASES = [
    ("e9_en_only_sorento", E9, "only sorento", "sorento", "Sorento"),
    ("e9_en_sorento_only_please", E9, "sorento only please", "Sorento", "Sorento"),
    ("e9_bm_sorento_je", E9, "Sorento je", "Sorento", "Sorento"),
    ("e9_zh_zhi_yao", E9, "只要Sorento", "Sorento", "Sorento"),
    ("e9_en_bravat", E9, "bravat only", "bravat", "Bravat"),
    ("242_en_sorento", M242, "Sorento", "Sorento", "Sorento"),
    ("242_en_show_me", M242, "show me Sorento", "Sorento", "Sorento"),
    ("242_bm_yang_sorento", M242, "yang Sorento", "Sorento", "Sorento"),
    ("242_zh_sorento_de", M242, "Sorento的", "Sorento", "Sorento"),
    ("242_en_cabana", M242, "Cabana", "Cabana", "Cabana"),
]


# --------------------------------------------------------------------------- #
# (a) the State the parser sees carries the offer
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("member", [E9, M242], ids=["e9", "242"])
def test_r4a_the_state_block_carries_the_brands_offered(member):
    rows = [{"raw": c, "canonical_code": c, "hint": "product", "current_message": False} for c in _held_codes(member)]
    state = State(focus=Focus(products=rows, domains=["inventory"], set_page=_set_page(member)))
    v = chat_state.view(state, None)
    assert v["open_question"] and v["open_question"].get("other_brands"), v["open_question"]
    text = chat_state.render(v)
    for brand, _n in member["offer"]:
        assert brand in text, (brand, text)


@pytest.mark.parametrize("member", [E9, M242], ids=["e9", "242"])
def test_r4a_guard_a_set_with_no_offer_shows_no_offer(member):
    page = {"set_key": {k: v for k, v in _set_page(member)["set_key"].items() if k != "other_brands"}}
    rows = [{"raw": c, "canonical_code": c, "hint": "product", "current_message": False} for c in _held_codes(member)]
    v = chat_state.view(State(focus=Focus(products=rows, domains=["inventory"], set_page=page)), None)
    assert not (v["open_question"] or {}).get("other_brands"), v["open_question"]


def test_r4a_guard_an_empty_state_renders_no_block():
    assert not chat_state.render(chat_state.view(State(focus=Focus()), None))


# --------------------------------------------------------------------------- #
# (b) a message naming an offered brand narrows the HELD set to it
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("member,message,raw,brand", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_r4a_a_brand_the_offer_listed_narrows_the_held_set_to_that_brand(seam, member, message, raw, brand):
    prev = _held_state(seam, member)
    seam.say(message, _brand_pick(raw), previous=prev)
    want = {seam.uuid_of[c] for c in member["held"][brand]}
    ids = _ids_in_calls([c for calls in seam.turn_calls[-1:] for c in calls])
    assert ids, ("no product-scoped fetch", seam.turn_calls[-1], seam.rules_fired)
    assert ids <= want, ("fetch left the held products of the brand", seam.turn_calls[-1], seam.rules_fired)
    after = {p["canonical_code"] for p in (seam.state["focus"].get("products") or [])}
    assert not after & set(DECOYS), (after, seam.rules_fired)
    others = {c for b, cs in member["held"].items() if b != brand for c in cs}
    assert not after & others, (after, seam.rules_fired)


# --------------------------------------------------------------------------- #
# Guard: a brand NOT in the offer is not a pick of the offer
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("member,message,raw", [(E9, "only grohe", "grohe"), (M242, "Hansgrohe", "Hansgrohe")],
                         ids=["e9", "242"])
def test_r4a_guard_a_brand_not_offered_does_not_pick_from_the_offer(seam, member, message, raw):
    prev = _held_state(seam, member)
    seam.say(message, _brand_pick(raw), previous=prev)
    assert "set_brand_chosen" not in seam.rules_fired, seam.rules_fired
