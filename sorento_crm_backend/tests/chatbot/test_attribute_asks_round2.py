"""Owner hand test round 2 on PR #833 (26 Sep 2026, contact 487555417, a dealer spanning
Mocha + Sorento). W1 to W6 of the fix brief, as whole turns.

Each case runs `engine.run_turn` with the v3 verdict shape, the real resolver, the real
class vocabulary and the real brands table, with only the MCP tool call stubbed (same
substrate as `test_reverse_asks_owner_phrasings.py`).

The owner's turns this pins (verbatim):
  5. "whici sorento wash basin has stock" -> "2,306 products have stock" (brand AND class lost)
  9. "which sorento wall hung basin has stock?" -> "144 products have stock" (noun lost)
 10. "10" -> "334 products have stock. Here are the first 10" (the page dropped the brand)
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import pytest

from tests.chatbot.test_counted_set_no_paging import _link_to_default_company
from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401 - fixtures used by name
from tests.chatbot.test_lane_require import (
    _s4_contact_id,
    _s4_envelope,
    _s4_real_resolve_entity,
    _s4_seed_contact,
    _s4_wire_engine,
    _seed_category_and_uom,
    _seed_registry,
    _stock_for,
    _warehouse,
)
from tests.chatbot.test_reverse_asks_owner_phrasings import _class_category


# --------------------------------------------------------------------------- #
# World                                                                         #
# --------------------------------------------------------------------------- #


def _brand(db, name: str, *, default: bool = False):
    from app.models.product import Brand

    row = db.query(Brand).filter(Brand.brand_name == name).first()
    if row is None:
        row = Brand(id=str(uuid.uuid4()), brand_code=name.upper()[:50], brand_name=name, is_active=True)
        db.add(row)
        db.flush()
    if hasattr(row, "is_chatbot_default"):
        row.is_chatbot_default = default
        db.flush()
    return row


def _product(db, *, brand_id: str, category_id: str, uom_id: str, noun: str, prefix: str, name: str | None = None):
    """A product whose description's TRAILING noun is its class (`derive_for_code` reads
    the tail), with its real brand row so the derived spec carries `brand`."""
    from app.models.product import Product
    from app.services.product_spec_derivation import derive_for_code
    from tests._pg_fixture import unique_code

    code = unique_code(prefix)[:50]
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=name or f"{noun.title()} {code[-4:]}",
        description=f"{code} WHITE {noun}",
        category_id=category_id,
        base_uom_id=uom_id,
        brand_id=brand_id,
        list_price=10,
        is_active=True,
    )
    db.add(row)
    db.flush()
    derive_for_code(db, code)
    return row


@pytest.fixture()
def world(session_factory):
    """Sorento: 3 counter basins with stock and 1 without, 2 wall hung basins with stock,
    1 wall hung water closet with stock, 2 taps with stock.
    Mocha: 2 counter basins and 1 wall hung basin, all with stock."""
    from app.models.product import Brand

    db = session_factory()
    # Clear any default a previous test left, so each test states its own.
    if hasattr(Brand, "is_chatbot_default"):
        db.query(Brand).update({Brand.is_chatbot_default: False})
    _category_id, uom_id = _seed_category_and_uom(db)
    basin_category = _class_category(db, "WB")
    tap_category = _class_category(db, "FT")
    wc_category = _class_category(db, "WC")
    sorento = _brand(db, f"Sorento{uuid.uuid4().hex[:4]}")
    mocha = _brand(db, f"Mocha{uuid.uuid4().hex[:4]}")
    _seed_registry(db)
    wh = _warehouse(db)

    def make(brand, category, noun, prefix, name=None):
        return _product(db, brand_id=brand.id, category_id=category, uom_id=uom_id, noun=noun, prefix=prefix, name=name)

    srt_basins = [make(sorento, basin_category, "WASH BASIN", "ZZSB", f"Sorento Counter Basin {i}") for i in range(4)]
    srt_wall = [make(sorento, basin_category, "WALL HUNG WASH BASIN", "ZZSW", f"Sorento Wall Basin {i}") for i in range(2)]
    srt_wc = [make(sorento, wc_category, "WALL HUNG WATER CLOSET", "ZZSC")]
    srt_taps = [make(sorento, tap_category, "BASIN TAP", "ZZST") for _ in range(2)]
    mch_basins = [make(mocha, basin_category, "WASH BASIN", "ZZMB") for _ in range(2)]
    mch_wall = [make(mocha, basin_category, "WALL HUNG WASH BASIN", "ZZMW")]
    for p in srt_basins[:3] + srt_wall + srt_wc + srt_taps + mch_basins + mch_wall:
        _stock_for(db, product_id=p.id, warehouse_id=wh.id)
    db.commit()
    return {
        "db": db,
        "sorento": sorento,
        "mocha": mocha,
        "srt_basins": srt_basins,
        "srt_wall": srt_wall,
        "srt_wc": srt_wc,
        "srt_taps": srt_taps,
        "mch_basins": mch_basins,
        "mch_wall": mch_wall,
        "every": srt_basins + srt_wall + srt_wc + srt_taps + mch_basins + mch_wall,
    }


def _stock_summary_tool(db, calls: list[dict[str, Any]]):
    """The stock tool's summary mode, as the owner saw it: one row per product,
    "Product Code" and "Total", titled by the code."""
    from app.models.inventory import Stock
    from app.models.product import Product

    def fake_call_tool(name: str, args: dict[str, Any]) -> str:
        calls.append({"name": name, "args": dict(args)})
        ids = list(args.get("product_ids") or [])
        rows = db.query(Product).filter(Product.id.in_(ids)).order_by(Product.product_code).all() if ids else []
        items = []
        for p in rows:
            total = sum(int(s.quantity_on_hand or 0) for s in db.query(Stock).filter(Stock.product_id == p.id))
            items.append(
                {
                    "title": p.product_code,
                    "fields": [
                        {"key": "product_code", "label": "Product Code", "value": p.product_code},
                        {"key": "total", "label": "Total", "value": total},
                    ],
                    "flags": {},
                }
            )
        return json.dumps(
            {
                "result_type": "stock",
                "intro": "Stock summary for the requested products.",
                "items": items,
                "has_result": bool(items),
            }
        )

    return fake_call_tool


def _stock_verdict(entities: list[dict[str, Any]], goal: str, **overrides: Any) -> dict[str, Any]:
    from tests.chatbot.test_engine import _parser_output

    base = dict(
        intent_hint="check_stock",
        domain_hint="inventory",
        match_mode="or",
        user_goal=goal,
        requested_attributes=["stock"],
        entities=[
            {"canonical_code": None, "current_message": True, "confident": True, **e} for e in entities
        ],
    )
    base.update(overrides)
    return _parser_output(**base)


class _Chat:
    def __init__(self, session_factory, monkeypatch, stub_parser, stub_access, world):
        self.session_factory = session_factory
        self.stub_parser = stub_parser
        self.stub_access = stub_access
        self.calls: list[dict[str, Any]] = []
        self.contact_id = _s4_contact_id(f"r2{uuid.uuid4().hex[:6]}")
        _s4_seed_contact(session_factory, contact_id=self.contact_id, session_vars={"variables": {}})
        _link_to_default_company(session_factory, self.contact_id)
        self.engine = _s4_wire_engine(
            session_factory,
            monkeypatch,
            resolve_entity=_s4_real_resolve_entity(world["db"]),
            fetch_mcp_call=_stock_summary_tool(world["db"], self.calls),
        )
        self.n = 0

    def say(self, text: str, verdict: dict[str, Any]) -> str:
        self.n += 1
        self.stub_parser(verdict)
        self.stub_access()
        turn = self.engine.run_turn(
            _s4_envelope(contact_id=self.contact_id, message_id=f"ZZT-{self.contact_id}-{self.n}", text=text),
            session_factory=self.session_factory,
        )
        assert turn.status == "done", turn.error
        return (turn.reply or {}).get("text") or ""


@pytest.fixture()
def chat(session_factory, monkeypatch, stub_parser, stub_access, world):
    return _Chat(session_factory, monkeypatch, stub_parser, stub_access, world)


def _codes(products) -> set[str]:
    return {p.product_code for p in products}


def _codes_in(text: str, world) -> set[str]:
    return {p.product_code for p in world["every"] if p.product_code in text}


# The two shapes the live parser gives a brand-plus-class ask: the brand as its own
# entity, or folded into the class word's raw.
def _brand_entity_shapes(brand: str, class_word: str) -> list[list[dict[str, Any]]]:
    return [
        [{"raw": brand, "hint": "brand"}, {"raw": class_word, "hint": "product_type"}],
        [{"raw": f"{brand} {class_word}", "hint": "product_type"}],
    ]


# --------------------------------------------------------------------------- #
# W1: the brand word is honoured                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("shape", [0, 1], ids=["brand_entity", "brand_in_class_raw"])
def test_w1_sorento_wash_basin_is_the_sorento_basin_set_never_wider(chat, world, shape):
    """Owner turn 5: "whici sorento wash basin has stock" answered "2,306 products"."""
    brand = world["sorento"].brand_name.lower()
    text = chat.say(
        f"whici {brand} wash basin has stock",
        _stock_verdict(_brand_entity_shapes(brand, "wash basin")[shape], f"which {brand} wash basin has stock"),
    )
    assert "5 wash basins have stock." in text, text
    assert _codes_in(text, world) == _codes(world["srt_basins"][:3] + world["srt_wall"]), text
    # The brand word scoped the set, so it was found.
    assert "could not find" not in text, text


@pytest.mark.parametrize("shape", [0, 1], ids=["brand_entity", "brand_in_class_raw"])
def test_w1_sorento_wall_hung_basin_keeps_brand_class_and_mounting(chat, world, shape):
    """Owner turn 9: "which sorento wall hung basin has stock?" answered "144 products"."""
    brand = world["sorento"].brand_name.lower()
    text = chat.say(
        f"which {brand} wall hung basin has stock?",
        _stock_verdict(_brand_entity_shapes(brand, "wall hung basin")[shape], f"which {brand} wall hung basin has stock"),
    )
    assert "2 wash basins have stock." in text, text
    assert _codes_in(text, world) == _codes(world["srt_wall"]), text


def test_w1_wall_hung_basin_keeps_the_basin_class(chat, world):
    """Owner turn 7: "which wall hung basin has stock" answered "334 products": the
    class word at the tail of a longer term was lost, so every wall hung product
    (water closets included) qualified."""
    text = chat.say(
        "which wall hung basin has stock",
        _stock_verdict([{"raw": "wall hung basin", "hint": "product_type"}], "which wall hung basin has stock"),
    )
    assert "3 wash basins have stock." in text, text
    assert _codes_in(text, world) == _codes(world["srt_wall"] + world["mch_wall"]), text


def test_w1_a_brand_word_in_the_class_term_is_a_brand_binding_off_the_brands_table(world):
    """The brand is read off `Product.brand_id` through the brands table, never off the
    derived spec value: a product re-branded since its spec row was derived still
    answers under its real brand."""
    from app.models.product_spec import ProductSpecifications
    from app.services.product_predicate_service import resolve_product_set

    db = world["db"]
    stale = world["srt_wall"][0]
    row = db.query(ProductSpecifications).filter(ProductSpecifications.product_id == stale.id).one()
    values = dict(row.values)
    values["brand"] = {**(values.get("brand") or {}), "value": world["mocha"].brand_name}
    row.values = values
    db.flush()

    brand = world["sorento"].brand_name
    outcome = resolve_product_set(db, require={"stock": True}, scope_terms=[f"{brand.lower()} wall hung basin"])

    assert outcome["brand"] == brand
    assert outcome["qualifying_total"] == 2, outcome
    assert {c["product_code"] for c in outcome["candidates"]} == _codes(world["srt_wall"])


# --------------------------------------------------------------------------- #
# W2: say what was identified, in plain words                                   #
# --------------------------------------------------------------------------- #


def _display(brand_name: str) -> str:
    return brand_name.title() if brand_name.isupper() else brand_name


@pytest.mark.parametrize("shape", [0, 1], ids=["brand_entity", "brand_in_class_raw"])
def test_w2_the_header_names_brand_type_and_mounting_in_plain_words(chat, world, shape):
    brand = world["sorento"].brand_name
    text = chat.say(
        f"which {brand.lower()} wall hung basin has stock?",
        _stock_verdict(_brand_entity_shapes(brand.lower(), "wall hung basin")[shape], "which wall hung basin has stock"),
    )
    first = text.splitlines()[0]
    assert first == (
        f"Brand: {_display(brand)}, Product type: Wash basin, Mounting: Wall hung. 2 wash basins have stock."
    ), text
    assert "wall_hung" not in text and "_" not in first, text


def test_w2_without_a_brand_the_header_still_names_the_spec(chat, world):
    text = chat.say(
        "which wall hung basin has stock",
        _stock_verdict([{"raw": "wall hung basin", "hint": "product_type"}], "which wall hung basin has stock"),
    )
    assert text.splitlines()[0] == "Product type: Wash basin, Mounting: Wall hung. 3 wash basins have stock.", text


def test_w2_a_word_that_was_not_understood_is_said_never_silently_dropped(chat, world):
    text = chat.say(
        "which zzqx wash basin has stock",
        _stock_verdict(
            [{"raw": "wash basin", "hint": "product_type"}, {"raw": "zzqx", "hint": "product_type"}],
            "which zzqx wash basin has stock",
        ),
    )
    first = text.splitlines()[0]
    assert "Product type: Wash basin." in first, text
    assert "I did not understand \"zzqx\"" in first, text


# --------------------------------------------------------------------------- #
# W3: rows a dealer can read                                                    #
# --------------------------------------------------------------------------- #


def test_w3_each_row_leads_with_the_product_name_and_key_spec_then_code_and_stock(chat, world):
    brand = world["sorento"].brand_name.lower()
    text = chat.say(
        f"which {brand} wash basin has stock",
        _stock_verdict([{"raw": brand, "hint": "brand"}, {"raw": "wash basin", "hint": "product_type"}],
                       f"which {brand} wash basin has stock"),
    )
    lines = text.splitlines()
    for p in world["srt_wall"]:
        [line] = [ln for ln in lines if p.product_code in ln]
        assert re.match(
            rf"^\d+\. {re.escape(p.product_name)} \(Mounting: Wall hung, Finish or colour: White\) \| "
            rf"\*Product Code:\* {re.escape(p.product_code)} \| \*Total:\* 10$",
            line,
        ), text
    for p in world["srt_basins"][:3]:
        [line] = [ln for ln in lines if p.product_code in ln]
        assert re.match(
            rf"^\d+\. {re.escape(p.product_name)} \(Finish or colour: White\) \| \*Product Code:\* {re.escape(p.product_code)} \| \*Total:\* 10$",
            line,
        ), text
    # One line per row: no field is left dangling on a line of its own.
    assert not [ln for ln in lines if ln.startswith("*Total:*") or ln.startswith("*Product Code:*")], text
