"""Owner hand test of round 2 on PR #833 (26 Sep 2026 ~13:07Z to 13:11Z, console :3084,
contact 487555417). W1 to W5 of the round 3 fix brief, as whole turns.

Each case runs `engine.run_turn` with the v3 verdict shape, the real resolver, the real
class vocabulary and the real brands table, with only the MCP tool call stubbed (same
substrate as `test_attribute_asks_round2.py`).

The owner's words (verbatim): "first i think the message too long already, i prefer it to
be line by line, don't want to read from left to right, second is yes I said we want to
show spec but it needs to be vertical, don't use lie |, and why when i say 10, it gives
some other answer, and you see when i ask which basin has cert, it gives weird answer,
what does sorento (default) mean, that is kinda sus, and I need the label to be bold".

The turns this pins:
  1. "which water closet has stock, p trap" -> 62, "How many should I show (up to 50)?"
  2. "30"  -> 30 rows, each "1. Seat cover material: Pp, Length: 680mm | *Product Code:* ..."
  3. "10"  -> no header, the old "Stock summary ..." dump of the SAME first products
  4. "which basin has cert" -> "Product: SRTWC286-SH-NEW-P, ..." (the water closet codes)
  5. "which wash basin has stock" -> "Brand: Sorento (default), ... Other brands: ..."
  6. "10"  -> GB codes under a Sorento header
  7-9. incoming and certificate lists rendered with "|"
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import pytest

from tests.chatbot.test_attribute_asks_round2 import _brand, _product
from tests.chatbot.test_counted_set_no_paging import _link_to_default_company
from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401 - fixtures used by name
from tests.chatbot.test_lane_require import (
    _cert_fake_call_tool,
    _certificate_for,
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
from tests.chatbot.test_reverse_asks_owner_phrasings import (
    _class_category,
    _incoming_fake_call_tool,
    _incoming_for,
)


# --------------------------------------------------------------------------- #
# World                                                                         #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def world(session_factory):
    """Sorento (the chatbot default brand):
      - 5 P trap water closets with stock, 1 S trap water closet with stock;
      - 3 wash basins with a certificate and stock, 1 of them named like the GB glass
        basin line;
      - 2 bathtubs with incoming.
    Mocha:
      - 1 P trap water closet with stock;
      - 1 wash basin with a certificate and stock, whose code starts "GB" too, so a
        brand scope read off the code instead of `Product.brand_id` would list it.
    """
    from app.models.product import Brand

    db = session_factory()
    db.query(Brand).update({Brand.chatbot_weight: 0})
    _category_id, uom_id = _seed_category_and_uom(db)
    wc_category = _class_category(db, "WC")
    basin_category = _class_category(db, "WB")
    tub_category = _class_category(db, "BT")
    sorento = _brand(db, f"Sorento{uuid.uuid4().hex[:4]}", default=True)
    mocha = _brand(db, f"Mocha{uuid.uuid4().hex[:4]}")
    _seed_registry(db)
    wh = _warehouse(db)

    def make(brand, category, noun, prefix, name=None):
        return _product(db, brand_id=brand.id, category_id=category, uom_id=uom_id, noun=noun, prefix=prefix, name=name)

    srt_ptrap = [make(sorento, wc_category, "P TRAP WATER CLOSET", "ZZR3P", f"Sorento Close Couple WC {i}") for i in range(5)]
    srt_strap = [make(sorento, wc_category, "S TRAP WATER CLOSET", "ZZR3S", "Sorento S Trap WC")]
    mch_ptrap = [make(mocha, wc_category, "P TRAP WATER CLOSET", "ZZR3M", "Mocha P Trap WC")]
    srt_basins = [make(sorento, basin_category, "WASH BASIN", "ZZR3B", f"Sorento Counter Basin {i}") for i in range(2)]
    srt_basins.append(make(sorento, basin_category, "GLASS WASH BASIN", "GBZZR3", "Sorento Glass Basin"))
    mch_basins = [make(mocha, basin_category, "GLASS WASH BASIN", "GBZZR3M", "Mocha Glass Basin")]
    srt_tubs = [make(sorento, tub_category, "BATHTUB", "ZZR3T", f"Sorento Bathtub {i}") for i in range(2)]
    for p in srt_ptrap + srt_strap + mch_ptrap + srt_basins + mch_basins:
        _stock_for(db, product_id=p.id, warehouse_id=wh.id)
    for p in srt_basins + mch_basins:
        _certificate_for(db, product_id=p.id)
    for p in srt_tubs:
        _incoming_for(db, product_id=p.id)
    db.commit()
    return {
        "db": db,
        "sorento": sorento,
        "mocha": mocha,
        "srt_ptrap": srt_ptrap,
        "srt_strap": srt_strap,
        "mch_ptrap": mch_ptrap,
        "srt_basins": srt_basins,
        "mch_basins": mch_basins,
        "srt_tubs": srt_tubs,
        "every": srt_ptrap + srt_strap + mch_ptrap + srt_basins + mch_basins + srt_tubs,
        "warehouse": wh,
    }


def _stock_tool(db, warehouse_code: str):
    """The stock tool's compact mode, as the owner saw it: Product Code, Total, then one
    field per allowed location."""
    from app.models.inventory import Stock
    from app.models.product import Product

    def call(args: dict[str, Any]) -> str:
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
                        {"label": warehouse_code, "value": total},
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

    return call


def _attachments_tool(db):
    """The attachments presenter's real shape: "Product Code" is an UNKEYED field
    (`sorento_crm_mcp.presenters._product_attachments`), and the row carries a
    "Product Name"."""
    inner = _cert_fake_call_tool(db)

    def call(args: dict[str, Any]) -> str:
        env = json.loads(inner("crm_master_product_attachments_list", args))
        for it in env.get("items") or []:
            for f in it["fields"]:
                if f.get("key") == "product_code":
                    f.pop("key")
        return json.dumps(env)

    return call


def _tools(world, calls: list[dict[str, Any]]):
    db = world["db"]
    stock = _stock_tool(db, world["warehouse"].warehouse_code)
    certs = _attachments_tool(db)
    incoming = _incoming_fake_call_tool(db, [])

    def fake_call_tool(name: str, args: dict[str, Any]) -> str:
        calls.append({"name": name, "args": dict(args)})
        if name == "crm_master_product_attachments_list":
            return certs(args)
        if "incoming" in name or "shipment" in name:
            return incoming(name, args)
        return stock(args)

    return fake_call_tool


def _entity(raw: str, hint: str = "product_type") -> dict[str, Any]:
    return {"raw": raw, "hint": hint, "canonical_code": None, "current_message": True, "confident": True}


def _ask(kind: str, class_word: str, goal: str, *, extra: list[dict[str, Any]] | None = None, **overrides):
    from tests.chatbot.test_engine import _parser_output

    domain, intent, attribute = {
        "stock": ("inventory", "check_stock", "stock"),
        "cert": ("product_attachment", "check_product_attachment", "cert"),
        "incoming": ("incoming", "check_incoming", "incoming"),
    }[kind]
    base = dict(
        intent_hint=intent,
        domain_hint=domain,
        match_mode="or",
        user_goal=goal,
        requested_attributes=[attribute],
        entities=[_entity(class_word), *(extra or [])],
    )
    base.update(overrides)
    return _parser_output(**base)


def _bare(**overrides: Any) -> dict[str, Any]:
    from tests.chatbot.test_engine import _parser_output

    base = dict(intent_hint=None, domain_hint=None, entities=[], user_goal=None)
    base.update(overrides)
    return _parser_output(**base)


class _Chat:
    def __init__(self, session_factory, monkeypatch, stub_parser, stub_access, world):
        self.session_factory = session_factory
        self.stub_parser = stub_parser
        self.stub_access = stub_access
        self.calls: list[dict[str, Any]] = []
        self.contact_id = _s4_contact_id(f"r3{uuid.uuid4().hex[:6]}")
        _s4_seed_contact(session_factory, contact_id=self.contact_id, session_vars={"variables": {}})
        _link_to_default_company(session_factory, self.contact_id)
        self.engine = _s4_wire_engine(
            session_factory,
            monkeypatch,
            resolve_entity=_s4_real_resolve_entity(world["db"]),
            fetch_mcp_call=_tools(world, self.calls),
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


@pytest.fixture()
def small_list(monkeypatch):
    from app.services.chatbot.lanes.business import answer as answer_mod

    monkeypatch.setattr(answer_mod, "SET_LIST_MAX", 3)


def _display(name: str) -> str:
    return name.title() if name.isupper() else name


def _codes(products) -> set[str]:
    return {p.product_code for p in products}


def _codes_in(text: str, world) -> set[str]:
    return {p.product_code for p in world["every"] if re.search(rf"(?<![\w-]){re.escape(p.product_code)}(?![\w-])", text)}


def _blocks(text: str) -> list[list[str]]:
    """The numbered product blocks of a reply: each a list of lines, the first "N. name"."""
    out: list[list[str]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if re.match(r"^\d+\. ", line):
            current = [line]
            out.append(current)
        elif current is not None and line.strip():
            current.append(line)
        else:
            current = None
    return out


def _block_code(block: list[str]) -> str | None:
    for line in block:
        m = re.match(r"^\*Product Code:\* (\S+)$", line)
        if m:
            return m.group(1)
    return None


def _listed(text: str) -> list[str]:
    return [c for c in (_block_code(b) for b in _blocks(text)) if c]


def _wc_ptrap(**overrides):
    # The two words of the owner's turn 1 as the live parser splits them: the class word
    # and the spec word, each its own entity.
    return _ask(
        "stock",
        "water closet",
        "which water closet has stock, p trap",
        extra=[_entity("p trap", "spec")],
        **overrides,
    )


# --------------------------------------------------------------------------- #
# W1: every list reads top to bottom                                            #
# --------------------------------------------------------------------------- #


def test_w1_a_stock_row_is_a_vertical_block_led_by_the_product_name(chat, world):
    text = chat.say("which water closet has stock, p trap", _wc_ptrap())

    assert "|" not in text, text
    blocks = _blocks(text)
    assert len(blocks) == 5, text
    by_code = {p.product_code: p for p in world["srt_ptrap"]}
    for block in blocks:
        code = _block_code(block)
        assert code in by_code, block
        product = by_code[code]
        # Line 1: the product name, never spec values in its place.
        assert re.match(rf"^\d+\. {re.escape(product.product_name)}$", block[0]), block
        # Then one "*Label:* value" line per field, Product code first.
        assert block[1] == f"*Product Code:* {code}", block
        for line in block[1:]:
            assert re.match(r"^\*[^*]+:\* \S", line), block
        # The header already says Trap and Product type; a row never repeats them.
        assert not [ln for ln in block if ln.startswith("*Trap:*") or ln.startswith("*Product type:*")], block
        assert "*Total:* 10" in block, block
        assert f"*{world['warehouse'].warehouse_code}:* 10" in block, block
    # A blank line between products.
    assert re.search(r"\n\n2\. ", text), text


def test_w1_the_header_is_one_short_line(chat, world):
    text = chat.say("which water closet has stock, p trap", _wc_ptrap())
    first, second = text.splitlines()[:2]
    brand = _display(world["sorento"].brand_name)
    assert first == f"Brand: {brand}, Product type: Water closet, Trap: P trap. 5 water closets have stock.", text
    # The tool's own intro is not repeated under the set header.
    assert "Stock summary for the requested products" not in text, text


def test_w1_a_certificate_row_is_a_vertical_block_too(chat, world):
    """Owner turn 8: "1. Material: Glass | GB3011B | *Product Code:* GB3011B | *Attachment
    Type:* Certification | ..." (the attachments tool's Product Code field has no key)."""
    text = chat.say("which wash basin has cert", _ask("cert", "wash basin", "which wash basin has cert"))

    assert "|" not in text, text
    blocks = _blocks(text)
    names = {p.product_code: p.product_name for p in world["srt_basins"]}
    assert {_block_code(b) for b in blocks} == set(names), text
    for block in blocks:
        code = _block_code(block)
        assert re.match(rf"^\d+\. {re.escape(names[code])}$", block[0]), block
        assert block[1] == f"*Product Code:* {code}", block
        # The code is said once as the code, never bare beside its labelled twin.
        assert [ln for ln in block if ln.startswith("*Product Code:*")] == [f"*Product Code:* {code}"], block
        assert not [ln for ln in block if ln.strip() == code], block
        assert "*Attachment Type:* Certification" in block, block


def test_w1_an_incoming_row_is_a_vertical_block_too(chat, world):
    """Owner turns 7 and 9: incoming rows rendered with pipes."""
    text = chat.say("which bathtub has incoming", _ask("incoming", "bathtub", "which bathtub has incoming"))

    assert "|" not in text, text
    blocks = _blocks(text)
    assert {_block_code(b) for b in blocks} == _codes(world["srt_tubs"]), text
    names = {p.product_code: p.product_name for p in world["srt_tubs"]}
    for block in blocks:
        code = _block_code(block)
        assert block[0].split(". ", 1)[1] == names[code], block
        assert block[1] == f"*Product Code:* {code}", block


# --------------------------------------------------------------------------- #
# W2: a count after a listed page continues the same set                        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "parser_reads",
    [{}, {"top_n": 2}, {"reference_positions": [2]}],
    ids=["parser_null", "parser_top_n", "parser_position"],
)
def test_w2_a_count_after_a_listed_page_continues_the_same_set(chat, world, small_list, parser_reads):
    """Owner turns 1 to 3: "which water closet has stock, p trap" -> "30" -> "10". The
    third answered the old "Stock summary" dump of the SAME first products, no header."""
    brand = _display(world["sorento"].brand_name)
    ask = chat.say("which water closet has stock, p trap", _wc_ptrap())
    assert "5 water closets have stock. That is too many to list" in ask, ask

    page1 = chat.say("2", _bare(top_n=2))
    page2 = chat.say("2", _bare(**parser_reads))

    head = f"Brand: {brand}, Product type: Water closet, Trap: P trap. 5 water closets have stock."
    assert page2.splitlines()[0] == f"{head} Here are 3 to 4.", page2
    assert "Stock summary" not in page2, page2
    assert [b[0].split(".")[0] for b in _blocks(page2)] == ["3", "4"], page2
    one, two = _listed(page1), _listed(page2)
    every = sorted(_codes(world["srt_ptrap"]))
    assert one + two == every[:4], (page1, page2)

    page3 = chat.say("2", _bare(**parser_reads))
    assert page3.splitlines()[0] == f"{head} Here are 5 to 5.", page3
    assert _listed(page3) == every[4:], page3

    before = len(chat.calls)
    done = chat.say("2", _bare(**parser_reads))
    assert done.splitlines()[0] == f"{head} That is all 5.", done
    assert _blocks(done) == [], done
    assert len(chat.calls) == before, chat.calls[before:]


def test_w2_the_owner_sequence_30_then_10_lists_31_to_40(chat, world, monkeypatch):
    """The same sequence at the owner's own sizes, 62 lowered to 5 with a list limit of
    3: the count asked, then "3", then "10" continues with the 2 left and says so."""
    from app.services.chatbot.lanes.business import answer as answer_mod

    monkeypatch.setattr(answer_mod, "SET_LIST_MAX", 3)
    chat.say("which water closet has stock, p trap", _wc_ptrap())
    chat.say("3", _bare(top_n=3))
    page = chat.say("10", _bare(top_n=10))
    assert page.splitlines()[0].endswith("5 water closets have stock. Here are 4 to 5."), page
    assert len(_blocks(page)) == 2, page


# --------------------------------------------------------------------------- #
# W3: a new class word or attribute word starts a new set                       #
# --------------------------------------------------------------------------- #


def test_w3_which_basin_has_cert_after_a_water_closet_set_is_a_new_certificate_set(chat, world, small_list):
    """Owner turns 1 to 4, the exact sequence: the fourth answered "Product:
    SRTWC286-SH-NEW-P, SRTWC286-SH-P, ..." (the carried water closet codes). The parser
    reads the listed codes back off the conversation as earlier-turn entities."""
    chat.say("which water closet has stock, p trap", _wc_ptrap())
    page1 = chat.say("2", _bare(top_n=2))
    page2 = chat.say("2", _bare(top_n=2))
    listed = [c for c in _codes(world["srt_ptrap"]) if c in page1 + page2]
    before = len(chat.calls)
    text = chat.say(
        "which basin has cert",
        _ask(
            "cert",
            "basin",
            "which basin has cert",
            extra=[{**_entity(c, "product"), "current_message": False} for c in sorted(listed)],
        ),
    )

    brand = _display(world["sorento"].brand_name)
    assert text.splitlines()[0] == f"Brand: {brand}, Product type: Wash basin. 3 wash basins have certificates.", text
    assert _codes_in(text, world) == _codes(world["srt_basins"]), text
    assert not text.startswith("Product:"), text
    calls = chat.calls[before:]
    assert [c["name"] for c in calls] == ["crm_master_product_attachments_list"], calls


@pytest.mark.parametrize(
    "carried", ["clean", "old_class_words", "old_codes"], ids=["parser_clean", "parser_carries_old_words", "parser_carries_old_codes"]
)
def test_w3_a_new_class_word_replaces_the_carried_set_whatever_the_parser_carries(
    chat, world, small_list, carried
):
    """The live parser can hand the earlier subject back with `current_message: false`
    beside the new class word: the old class and spec words, or the old set's codes it
    read off the listed rows. The new word still starts a new set, and nothing of the
    old set is named (owner turn 4 printed "Product: SRTWC286-SH-NEW-P, ...")."""
    chat.say("which water closet has stock, p trap", _wc_ptrap())
    chat.say("2", _bare(top_n=2))
    old = {
        "clean": [],
        "old_class_words": [
            {**_entity("water closet"), "current_message": False},
            {**_entity("p trap", "spec"), "current_message": False},
        ],
        "old_codes": [
            {**_entity(p.product_code, "product"), "current_message": False} for p in world["srt_ptrap"][:3]
        ],
    }[carried]
    text = chat.say("which basin has cert", _ask("cert", "basin", "which basin has cert", extra=old))
    assert "3 wash basins have certificates." in text.splitlines()[0], text
    assert _codes_in(text, world) == _codes(world["srt_basins"]), text


def test_w3_a_new_attribute_word_on_the_same_class_starts_a_new_set(chat, world, small_list):
    """"which water closet has stock" then "which water closet has incoming": the new
    attribute is a new set, never a page of the stock set."""
    chat.say("which water closet has stock, p trap", _wc_ptrap())
    chat.say("2", _bare(top_n=2))
    text = chat.say("which bathtub has incoming", _ask("incoming", "bathtub", "which bathtub has incoming"))
    assert "bathtubs have incoming stock." in text.splitlines()[0], text
    assert _codes_in(text, world) == _codes(world["srt_tubs"]), text


# --------------------------------------------------------------------------- #
# W4: no "(default)"; the other brands close the reply                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "kind, class_word, closing",
    [
        ("stock", "wash basin", "Other brands with stock"),
        ("cert", "wash basin", "Other brands with certificates"),
    ],
)
def test_w4_the_default_brand_reads_plainly_and_the_other_brands_close_the_reply(
    chat, world, kind, class_word, closing
):
    text = chat.say(f"which {class_word} has {kind}", _ask(kind, class_word, f"which {class_word} has {kind}"))
    brand, other = _display(world["sorento"].brand_name), _display(world["mocha"].brand_name)
    noun = "stock" if kind == "stock" else "certificates"
    assert text.splitlines()[0] == f"Brand: {brand}, Product type: Wash basin. 3 wash basins have {noun}.", text
    assert "(default)" not in text, text
    assert text.splitlines()[-1] == f"{closing}: {other} 1. Name one to see them.", text


def test_w4_incoming_names_the_other_brands_with_incoming(chat, world):
    db = world["db"]
    mocha_tub = _product(
        db,
        brand_id=world["mocha"].id,
        category_id=_class_category(db, "BT"),
        uom_id=world["srt_tubs"][0].base_uom_id,
        noun="BATHTUB",
        prefix="ZZR3MT",
        name="Mocha Bathtub",
    )
    _incoming_for(db, product_id=mocha_tub.id)
    db.commit()
    text = chat.say("which bathtub has incoming", _ask("incoming", "bathtub", "which bathtub has incoming"))
    assert text.splitlines()[-1] == f"Other brands with incoming: {_display(world['mocha'].brand_name)} 1. Name one to see them.", text


def test_w4_a_withheld_set_still_closes_with_the_other_brands(chat, world, small_list):
    text = chat.say("which water closet has stock, p trap", _wc_ptrap())
    assert "(default)" not in text, text
    assert "How many should I show (up to 3)?" in text.splitlines()[0], text
    assert text.splitlines()[-1] == f"Other brands with stock: {_display(world['mocha'].brand_name)} 1. Name one to see them.", text


def test_w4_a_named_brand_answers_that_brand_only(chat, world):
    mocha = world["mocha"].brand_name
    text = chat.say(
        f"which {mocha.lower()} wash basin has stock",
        _ask("stock", "wash basin", "which wash basin has stock", extra=[_entity(mocha.lower(), "brand")]),
    )
    assert text.splitlines()[0] == f"Brand: {_display(mocha)}, Product type: Wash basin. 1 wash basin has stock.", text
    assert "Other brands" not in text, text


# --------------------------------------------------------------------------- #
# W5: every listed product belongs to the header's brand                        #
# --------------------------------------------------------------------------- #


def _brand_of(db, code: str) -> str | None:
    from app.models.product import Brand, Product

    row = db.query(Brand.brand_name).join(Product, Product.brand_id == Brand.id).filter(Product.product_code == code).first()
    return row[0] if row else None


@pytest.mark.parametrize("kind", ["stock", "cert"])
def test_w5_every_listed_product_belongs_to_the_header_brand(chat, world, kind):
    """Owner turns 6 and 8: GB3006C / GB3011B under a Sorento header. Membership is read
    off `Product.brand_id` through the brands table, so a GB-coded product of another
    brand is never listed under the default brand; one that IS that brand's is."""
    text = chat.say("which wash basin has x", _ask(kind, "wash basin", f"which wash basin has {kind}"))
    brand = world["sorento"].brand_name
    assert text.startswith(f"Brand: {_display(brand)},"), text
    listed = _listed(text)
    assert listed and {_brand_of(world["db"], c) for c in listed} == {brand}, (listed, text)
    assert world["srt_basins"][2].product_code in listed, text
    assert world["mch_basins"][0].product_code not in text, text


def test_w5_a_page_of_the_default_brand_set_stays_in_that_brand(chat, world, small_list):
    """Owner turn 6 was a page ("10") of the default brand set."""
    chat.say("which water closet has stock, p trap", _wc_ptrap())
    page = chat.say("5", _bare(top_n=5))
    listed = _listed(page)
    assert listed and {_brand_of(world["db"], c) for c in listed} == {world["sorento"].brand_name}, page
    assert world["mch_ptrap"][0].product_code not in page, page


def test_w3_a_question_after_a_set_never_names_the_old_set_as_its_subject(chat, world, small_list):
    """Owner turn 4's reply opened "Product: SRTWC286-SH-NEW-P, ..." - a question whose
    subject line named the water closet set the customer had moved on from."""
    chat.say("which water closet has stock, p trap", _wc_ptrap())
    chat.say("2", _bare(top_n=2))
    text = chat.say("which aqua tub has cert", _ask("cert", "aqua tub", "which aqua tub has cert"))
    assert not _codes_in(text, world), text
    assert not text.startswith("Product:"), text


def test_w1_a_product_named_only_by_its_code_leads_with_its_description_never_spec_values(world):
    """Owner turn 2: "1. Seat cover material: Pp, Length: 680mm | *Product Code:* ..." -
    a product whose name is its own code was led by spec values."""
    from app.services.product_predicate_service import resolve_product_set

    db = world["db"]
    product = world["srt_ptrap"][0]
    product.product_name = product.product_code
    db.flush()

    outcome = resolve_product_set(db, require={"stock": True}, scope_terms=["water closet"])
    lead = outcome["row_labels"][product.product_code]
    assert lead["name"] == product.description, lead
    assert all(s["label"] and s["value"] for s in lead["specs"]), lead
