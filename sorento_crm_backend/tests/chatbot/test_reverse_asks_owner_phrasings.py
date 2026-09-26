"""Reverse asks in the owner's own words (revive of PR #833, 26 Sep 2026).

Owner, 26 Sep 2026: "I need to be able to ask like which water tap got stock which water
tap got certificate which water basin blah blah blah got stock or got incoming all this
reverse asking need to be able to cater to that".

Each case runs a whole turn through `engine.run_turn` with main's v3 verdict shape (the
class word as a `product_type` entity, the attribute in `requested_attributes`), the real
resolver and the real class vocabulary (`backfill_category_signals` + the spec registry,
products classed by `derive_for_code` off their description), with only the MCP tool call
stubbed. The console cases in `console_cases/2026-09-11-attribute-first-asks.yaml` carry
the same four phrasings against the live parser.
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401 - fixtures used by name
from tests.chatbot.test_lane_require import (
    _basin_product,
    _cert_fake_call_tool,
    _certificate_for,
    _s4_contact_id,
    _s4_envelope,
    _s4_real_resolve_entity,
    _s4_seed_contact,
    _s4_wire_engine,
    _seed_category_and_uom,
    _seed_registry,
    _stock_fake_call_tool,
    _stock_for,
    _tap_product,
    _warehouse,
)


def _verdict(*, domain: str, intent: str, attribute: str, class_word: str, goal: str) -> dict[str, Any]:
    from tests.chatbot.test_engine import _parser_output

    return _parser_output(
        intent_hint=intent,
        domain_hint=domain,
        match_mode="or",
        user_goal=goal,
        requested_attributes=[attribute],
        entities=[
            {
                "raw": class_word,
                "hint": "product_type",
                "canonical_code": None,
                "current_message": True,
                "confident": True,
            }
        ],
    )


def _incoming_for(db, *, product_id: str, qty: int = 20) -> None:
    from app.models.procurement import InboundShipment, InboundShipmentLine
    from tests._pg_fixture import unique_code

    shipment = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=unique_code("SHIP")[:50],
        shipment_date=date(2026, 9, 1),
        shipment_status="in_transit",
    )
    db.add(shipment)
    db.flush()
    db.add(
        InboundShipmentLine(
            id=str(uuid.uuid4()), shipment_id=shipment.id, product_id=product_id, quantity_shipped=qty
        )
    )
    db.flush()


def _incoming_fake_call_tool(db, calls: list[dict[str, Any]]):
    """One incoming row per requested product, in the render envelope's shape."""
    from app.models.product import Product

    def fake_call_tool(name: str, args: dict[str, Any]) -> str:
        calls.append({"name": name, "args": dict(args)})
        ids = list(args.get("product_ids") or [])
        rows = db.query(Product).filter(Product.id.in_(ids)).order_by(Product.product_code).all() if ids else []
        items = [
            {
                "title": p.product_code,
                "fields": [
                    {"key": "product_code", "label": "Product Code", "value": p.product_code},
                    {"key": "eta", "label": "ETA", "value": "01/10/2026"},
                ],
                "flags": {},
            }
            for p in rows
        ]
        return json.dumps(
            {
                "result_type": "incoming_stock",
                "intro": "Incoming stock found for the requested products.",
                "items": items,
                "has_result": bool(items),
            }
        )

    return fake_call_tool


def _recording(inner, calls: list[dict[str, Any]]):
    def fake_call_tool(name: str, args: dict[str, Any]) -> Any:
        calls.append({"name": name, "args": dict(args)})
        return inner(name, args)

    return fake_call_tool


def _run(session_factory, monkeypatch, stub_parser, stub_access, *, tag, text, verdict, fake_call_tool):
    contact_id = _s4_contact_id(tag)
    db = session_factory()
    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})
    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=fake_call_tool,
    )
    stub_parser(verdict)
    stub_access()
    turn = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id=f"ZZT-{tag}-1", text=text),
        session_factory=session_factory,
    )
    assert turn.status == "done", turn.error
    return (turn.reply or {}).get("text") or ""


def _class_category(db, suffix: str) -> str:
    """A category coded the way the catalogue codes them (`<brand>-<class suffix>`), so
    `backfill_category_signals` gives it its real class label and customer synonyms
    (`product_class_signal.CLASS_SUFFIXES` / `CLASS_SYNONYMS`) - the path "basin" takes
    to Wash Basin on prod."""
    from app.models.product import ProductCategory

    row = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=f"ZZT{uuid.uuid4().hex[:6].upper()}-{suffix}",
        category_name=f"ZZT {suffix} category",
    )
    db.add(row)
    db.flush()
    return row.id


def _seed_taps_and_basins(db, *, taps: int = 3, basins: int = 2):
    _category_id, uom_id = _seed_category_and_uom(db)
    tap_category = _class_category(db, "FT")
    basin_category = _class_category(db, "WB")
    _seed_registry(db)
    tap_rows = [_tap_product(db, category_id=tap_category, uom_id=uom_id) for _ in range(taps)]
    basin_rows = [_basin_product(db, category_id=basin_category, uom_id=uom_id) for _ in range(basins)]
    return tap_rows, basin_rows


def test_which_water_tap_got_stock(session_factory, stub_parser, stub_access, monkeypatch):
    db = session_factory()
    taps, basins = _seed_taps_and_basins(db)
    wh = _warehouse(db)
    for p in taps[:2] + basins:
        _stock_for(db, product_id=p.id, warehouse_id=wh.id)
    db.commit()

    calls: list[dict[str, Any]] = []
    text = _run(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        tag="wtapstock",
        text="which water tap got stock",
        verdict=_verdict(
            domain="inventory",
            intent="check_stock",
            attribute="stock",
            class_word="water tap",
            goal="which water tap got stock",
        ),
        fake_call_tool=_recording(_stock_fake_call_tool(db), calls),
    )
    assert "2 taps have stock." in text, text
    for p in taps[:2]:
        assert p.product_code in text, text
    assert taps[2].product_code not in text, text
    for p in basins:
        assert p.product_code not in text, text
    assert "I don't know" not in text, text


def test_which_water_tap_got_certificate(session_factory, stub_parser, stub_access, monkeypatch):
    db = session_factory()
    taps, basins = _seed_taps_and_basins(db)
    for p in taps[:2] + basins[:1]:
        _certificate_for(db, product_id=p.id)
    db.commit()

    text = _run(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        tag="wtapcert",
        text="which water tap got certificate",
        verdict=_verdict(
            domain="product_attachment",
            intent="check_product_attachment",
            attribute="certificate",
            class_word="water tap",
            goal="which water tap got certificate",
        ),
        fake_call_tool=_cert_fake_call_tool(db),
    )
    assert "2 taps have certificates." in text, text
    for p in taps[:2]:
        assert p.product_code in text, text
    assert basins[0].product_code not in text, text
    assert "Which kind of file" not in text, text


def test_which_water_basin_got_stock(session_factory, stub_parser, stub_access, monkeypatch):
    db = session_factory()
    taps, basins = _seed_taps_and_basins(db, basins=3)
    wh = _warehouse(db)
    for p in basins[:2] + taps:
        _stock_for(db, product_id=p.id, warehouse_id=wh.id)
    db.commit()

    text = _run(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        tag="wbasinstock",
        text="which water basin got stock",
        verdict=_verdict(
            domain="inventory",
            intent="check_stock",
            attribute="stock",
            class_word="water basin",
            goal="which water basin got stock",
        ),
        fake_call_tool=_stock_fake_call_tool(db),
    )
    assert "2 wash basins have stock." in text, text
    for p in basins[:2]:
        assert p.product_code in text, text
    for p in taps:
        assert p.product_code not in text, text


def test_which_basin_got_incoming(session_factory, stub_parser, stub_access, monkeypatch):
    db = session_factory()
    taps, basins = _seed_taps_and_basins(db, basins=3)
    for p in basins[:2] + taps[:1]:
        _incoming_for(db, product_id=p.id)
    db.commit()

    calls: list[dict[str, Any]] = []
    text = _run(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        tag="basinincoming",
        text="which basin got incoming",
        verdict=_verdict(
            domain="incoming",
            intent="check_incoming",
            attribute="incoming",
            class_word="basin",
            goal="which basin got incoming",
        ),
        fake_call_tool=_incoming_fake_call_tool(db, calls),
    )
    assert "2 wash basins have incoming stock." in text, text
    for p in basins[:2]:
        assert p.product_code in text, text
    assert taps[0].product_code not in text, text


# --------------------------------------------------------------------------- #
# A dealer on an "Availability only" stock visibility policy (stock ask v2's   #
# scope, PLAN-chatbot-stock-ask-v2-24sep.md R1/R3): the counted set is judged  #
# over the locations the dealer's policy allows - the same `warehouse_         #
# criterion` the stock tool itself answers from - and no quantity reaches the  #
# reply. Before the fix the stock leg counted every active warehouse, so a     #
# product held only in a location the policy hides still counted ("2 taps     #
# have stock.") beside rows the tool itself would not confirm.                 #
# --------------------------------------------------------------------------- #


def _availability_fake_call_tool(db, calls: list[dict[str, Any]]):
    """The stock tool's availability-mode render (`presenters._stock_availability`):
    one item per named product, NO fields, and the quantity question as the intro."""
    from app.models.product import Product

    def fake_call_tool(name: str, args: dict[str, Any]) -> str:
        calls.append({"name": name, "args": dict(args)})
        ids = list(args.get("product_ids") or [])
        rows = db.query(Product).filter(Product.id.in_(ids)).order_by(Product.product_code).all() if ids else []
        items = [
            {"title": p.product_code, "fields": [], "flags": {"needs_quantity": True, "available": None}}
            for p in rows
        ]
        return json.dumps(
            {
                "result_type": "stock_availability",
                "intro": "How many units do you need?",
                "items": items,
                "has_result": bool(items),
            }
        )

    return fake_call_tool


def test_dealer_on_availability_only_counts_only_allowed_locations_and_sees_no_quantity(
    session_factory, stub_parser, stub_access, monkeypatch
):
    from sqlalchemy import text as sa_text

    from app.models.access import StockVisibilityPolicy

    db = session_factory()
    taps, _basins = _seed_taps_and_basins(db, taps=3, basins=0)
    allowed = _warehouse(db)
    hidden = _warehouse(db)
    _stock_for(db, product_id=taps[0].id, warehouse_id=allowed.id, on_hand=37)
    _stock_for(db, product_id=taps[1].id, warehouse_id=hidden.id, on_hand=41)
    db.commit()

    contact_id = _s4_contact_id("dealeravail")
    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})
    internal_id = db.execute(
        sa_text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), {"c": contact_id}
    ).scalar()
    db.add(
        StockVisibilityPolicy(
            id=str(uuid.uuid4()), contact_id=internal_id, mode="availability", warehouse_ids=[allowed.id]
        )
    )
    db.commit()

    calls: list[dict[str, Any]] = []
    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_availability_fake_call_tool(db, calls),
    )
    stub_parser(
        _verdict(
            domain="inventory",
            intent="check_stock",
            attribute="stock",
            class_word="tap",
            goal="which tap got stock",
        )
    )
    stub_access()
    turn = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-dealeravail-1", text="which tap got stock"),
        session_factory=session_factory,
    )
    assert turn.status == "done", turn.error
    text = (turn.reply or {}).get("text") or ""

    assert "1 tap has stock." in text, text
    assert taps[0].product_code in text, text
    assert taps[1].product_code not in text, text
    assert taps[2].product_code not in text, text
    # No quantity of ours: neither on-hand figure, and no quantity field label.
    assert "37" not in text and "41" not in text, text
    assert "Quantity" not in text, text
    # The tool was asked only about the product the policy lets the dealer see.
    asked = {pid for c in calls for pid in (c["args"].get("product_ids") or [])}
    assert asked == {taps[0].id}, asked
