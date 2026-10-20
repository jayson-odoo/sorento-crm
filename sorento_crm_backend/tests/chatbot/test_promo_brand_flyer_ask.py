"""CHAT-PROMO-BRAND-FLYER: a brand + file-kind ask ("Sorento A3 flyer") that names no product
looks promotions up by brand + kind (+ the contact's access level), never by a product set,
and the promotion tool runs even when nothing is held.

Owner exploratory test, 20 Oct 2026 (#1802 build): (1) with products held the fetch went out as
`product_ids` + `promotion_ids` (the brand word's promotion fan-out) and answered with a MOCHA A3
flyer; (2) after a new subject the promotion lane had brand Sorento + contains_flyer and the tool
never ran (trace `kind: tool, domain: promotion`, no name/args), reply 'Couldn't find "flyer"'.
The RESOLVER is the real one: it reads "Sorento A3 flyer" as the described set "Sorento products
that have a promotion" (`require: {promotion: true}`, "flyer" unrecognised) and answers the brand
word with promotions whose name starts with it, which is what both failures hang on; a fake
brand-only resolver hides both. Brand is the promotion's LINKED product brand (the route's own
`brand_ids` filter), never a company-name text. Fake names and codes only; the MCP double is
backed by the real route.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from app.main import app
from app.models.marketing import PromotionType
from app.models.product import Product
from app.services.chatbot.lanes.business import services as business_services
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import product
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_outstanding_lane import _run_turn
from tests.chatbot.test_promo_brand_category import _mcp
from tests.chatbot.test_promo_kind_subject import PROMO_TOOL, TODAY, _promo, _seed_world

LEVELS = ["Sorento Dealer", "Mocha Dealer"]
HELD = ("ZZTMHELD1", "ZZTMHELD2")


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _world(session_factory, *, sorento_live_flyer: bool = True) -> dict[str, Any]:
    """`_seed_world` plus: two Mocha products an earlier turn holds, one linked to a Mocha A3
    flyer the dealer's Sorento level can see (so a fetch keyed on the held set answers Mocha's
    file), and Sorento-named promotions so the brand word's promotion fan-out has rows."""
    ids = _seed_world(session_factory, sorento_live_flyer=sorento_live_flyer)
    db = session_factory()
    flyer = db.query(PromotionType).filter(PromotionType.type_code == "a3_flyer").one()
    held = []
    for code in HELD:
        row = product(db, company_id=DEFAULT_COMPANY_ID, code=code)
        row.brand_id = ids["mocha"]
        held.append(row)
    db.flush()
    _promo(db, "ZZT MOCHA HELD A3 FLYER", flyer, held[0], levels=["sorento_dealer", "mocha_dealer"])
    ids["srt_products"] = [str(pid) for (pid,) in db.query(Product.id).filter(Product.brand_id == ids["srt"]).all()]
    _promo(db, "SORENTO ZZT WC DEAL", flyer, held[1], levels=["sorento_dealer"],
           start=TODAY - timedelta(days=90), end=TODAY - timedelta(days=60), active=False)
    db.commit()
    from app.models.marketing import Promotion

    ids["held_ids"] = {p.product_code: str(p.id) for p in held}
    ids["mocha_promotions"] = [
        str(pid) for (pid,) in db.query(Promotion.id).filter(Promotion.description.like("ZZT MOCHA%")).all()
    ]
    return ids


def _turn(session_factory, monkeypatch, qf, text, msg_id) -> str:
    # The real resolver (`production_services`); only the contact's access levels are faked.
    monkeypatch.setattr(
        business_services, "_access_types",
        lambda db, default_space_id=None: (lambda **_: [{"name": n} for n in LEVELS]),
    )
    result, _ = _run_turn(session_factory, monkeypatch, qf=qf, text_body=text, msg_id=msg_id, real_resolver=True)
    return (result.reply or {}).get("text") or ""


def _held_qf():
    ents = [{"raw": c, "hint": "product", "canonical_code": c, "current_message": True, "confident": True} for c in HELD]
    return _parser_output(domain_hint="master_products", intent_hint="check_product", entities=ents)


def _brand_flyer_qf(*, kind: str | None = "a3_flyer", **over):
    ents = [{"raw": "Sorento", "hint": "brand", "canonical_code": "Sorento", "current_message": True, "confident": True}]
    return _parser_output(
        domain_hint="promotion", intent_hint="check_promotion", entities=ents,
        contains_flyer=True, promotion_kind=kind, **over,
    )


def _assert_brand_kind_calls(calls, ids, *, kind: str | None = "a3_flyer"):
    assert calls, "the promotion tool never ran"
    for a in calls:
        assert not a.get("product_ids"), a
        assert not a.get("promotion_ids"), a
        assert a.get("brand_ids") == [str(ids["srt"])], a
        assert a.get("promotion_types") == ([kind] if kind else None), a
        assert a.get("access_levels") == ["Sorento Dealer"], a


@pytest.mark.parametrize("entity_op", ["replace_combine", "reuse"])
def test_brand_flyer_ask_with_products_held_looks_up_by_brand_and_kind(session_factory, monkeypatch, entity_op):
    """Shape 1, end to end: Mocha products held from the turn before; the brand + kind ask is
    answered by brand + kind + level, never by the brand word's promotion fan-out, and no other
    brand's file reaches the reply. Whether the held set rides this turn's gate is the carry
    rule's call (CHAT-STATE); the gate the owner's turn reached, with product ids on it, is
    pinned at `run_fetch` by `test_owner_shape_product_and_promotion_ids_never_ride_a_brand_flyer_ask`."""
    ids = _world(session_factory)
    captured = _mcp(monkeypatch, session_factory)
    _turn(session_factory, monkeypatch, _held_qf(), "ZZTMHELD1 ZZTMHELD2", "zzt-pbf-held")
    n = len(captured)
    reply = _turn(session_factory, monkeypatch, _brand_flyer_qf(entity_op=entity_op), "Sorento A3 flyer", "zzt-pbf-ask")
    _assert_brand_kind_calls([a for name, a in captured[n:] if name == PROMO_TOOL], ids)
    assert "ZZT SORENTO A3 FLYER 2026" in reply, reply
    assert "MOCHA" not in reply.upper(), reply
    assert "SORENTO ZZT WC DEAL" not in reply, reply


def test_brand_flyer_ask_with_nothing_held_runs_the_promotion_tool(session_factory, monkeypatch):
    """Shape 2: nothing held: the tool runs by brand + kind + level and lists the live Sorento
    flyer; the unplaced word "flyer" is not a miss."""
    ids = _world(session_factory)
    captured = _mcp(monkeypatch, session_factory)
    reply = _turn(session_factory, monkeypatch, _brand_flyer_qf(), "Sorento A3 flyer", "zzt-pbf-fresh")
    _assert_brand_kind_calls([a for name, a in captured if name == PROMO_TOOL], ids)
    assert "ZZT SORENTO A3 FLYER 2026" in reply, reply
    assert "MOCHA" not in reply.upper(), reply
    assert "couldn't find" not in reply.lower() and "could not fetch" not in reply.lower(), reply


def test_brand_flyer_ask_with_no_kind_code_runs_by_brand_alone(session_factory, monkeypatch):
    """The parser flagged a flyer but named no listed kind: every kind stays in play (AC-19),
    still narrowed to the brand and never refused on the "has a promotion" set."""
    ids = _world(session_factory)
    captured = _mcp(monkeypatch, session_factory)
    reply = _turn(session_factory, monkeypatch, _brand_flyer_qf(kind=None), "Sorento flyer", "zzt-pbf-nokind")
    _assert_brand_kind_calls([a for name, a in captured if name == PROMO_TOOL], ids, kind=None)
    assert "ZZT SORENTO A3 FLYER 2026" in reply, reply
    assert "MOCHA" not in reply.upper(), reply


def test_brand_flyer_ask_with_only_an_expired_flyer_says_it_is_expired(session_factory, monkeypatch):
    """Only an ended Sorento A3 flyer the kind still serves: it is listed marked EXPIRED, never
    as live, and no other brand's file stands in for it."""
    ids = _world(session_factory, sorento_live_flyer=False)
    _ended_sorento_flyer(session_factory, ids)
    captured = _mcp(monkeypatch, session_factory)
    reply = _turn(session_factory, monkeypatch, _brand_flyer_qf(), "Sorento A3 flyer", "zzt-pbf-expired")
    _assert_brand_kind_calls([a for name, a in captured if name == PROMO_TOOL], ids)
    assert "ZZT SORENTO A3 FLYER JUST ENDED" in reply, reply
    assert "EXPIRED" in reply, reply
    assert "MOCHA" not in reply.upper(), reply


def _ended_sorento_flyer(session_factory, ids) -> None:
    db = session_factory()
    flyer = db.query(PromotionType).filter(PromotionType.type_code == "a3_flyer").one()
    srt_prod = db.query(Product).filter(Product.brand_id == ids["srt"]).first()
    _promo(db, "ZZT SORENTO A3 FLYER JUST ENDED", flyer, srt_prod, levels=["sorento_dealer"],
           start=TODAY - timedelta(days=40), end=TODAY - timedelta(days=2), active=False)
    db.commit()


@pytest.mark.parametrize("sorento_live_flyer", [True, False])
def test_brand_kind_ask_serves_the_rows_the_equivalent_product_ask_serves(session_factory, monkeypatch, sorento_live_flyer):
    """Crew ruling (a), 20 Oct: the serving policy is unchanged; the brand + kind ask yields the
    same rows it yields for the equivalent product ask (every Sorento product, same kind and
    level). Live world: the live flyer only (rule 2 hides the ended one of its type); ended-only
    world: the ended flyer the kind still serves, nothing older."""
    from app.services.contact_access_type_service import ContactAccessTypeService
    from app.services.marketing_service import PromotionService

    ids = _world(session_factory, sorento_live_flyer=sorento_live_flyer)
    _ended_sorento_flyer(session_factory, ids)
    db = session_factory()
    sorento_products = ids["srt_products"]
    served = PromotionService(db).list_promotions(
        page=1, limit=50, serving_policy=True,
        contact_access_codes=ContactAccessTypeService(db).translate_names_to_codes(["Sorento Dealer"]),
        product_ids=list(sorento_products), promotion_types=["a3_flyer"],
    )
    expected = sorted({p.description for p in served["data"]})
    assert sorento_products and expected, (sorento_products, served)
    _mcp(monkeypatch, session_factory)
    reply = _turn(session_factory, monkeypatch, _brand_flyer_qf(), "Sorento A3 flyer", "zzt-pbf-parity")
    listed = sorted({line.split("*Promotion:*", 1)[1].strip() for line in reply.splitlines() if "*Promotion:*" in line})
    assert listed == expected, reply


TIER_GATE = {
    "name": LEVELS, "tier_stated": [], "entitled_tiers": ["dealer"], "entitled_unknown": [],
    "query_brands": ["sorento"], "pending_pick": False, "tier_ask": False, "tier_proceed": True,
    "access_levels_recomposed": ["Sorento Dealer"], "tier_probe_plan": [], "brand_gate_empty": False,
    "brand_unheld": False, "tier_pick_domain": None,
}


def _fetch_with_owner_shape(session_factory, ids, parse_output, resolutions=()):
    """`run_fetch` on the gate the owner's shape-1 turn reached: product entities (the held /
    described set) beside the brand word's promotion fan-out, under a "has a promotion" set
    that qualifies them. Returns the promotions-list calls."""
    from app.services.chatbot.lanes import business as business_lane
    from app.services.chatbot.lanes.business.services import FetchServices
    db = session_factory()
    fan_out, held = ids["mocha_promotions"], list(ids["held_ids"].values())
    assert fan_out and len(held) == len(HELD)
    entities = [{"uuid": u, "entity_type": "product", "code": u} for u in held] + [
        {"uuid": u, "entity_type": "promotion", "code": u} for u in fan_out
    ]
    calls: list[tuple[str, dict[str, Any]]] = []

    def _mcp_call(name, args):
        calls.append((name, dict(args)))
        return '{"has_result": false, "items": []}'

    payload = {
        "gate": {
            "compatible_entities": entities,
            "predicate": {"require": {"promotion": True}, "qualifying_total": len(held), "truncated": False},
            "resolutions": list(resolutions),
        },
        "tier_gate": dict(TIER_GATE),
        "ctx": {"parse": {"output": parse_output}, "contact": {"id": "900000008"}},
    }
    business_lane.run_fetch(payload, services=FetchServices(mcp_call=_mcp_call), space_id="364817", db=db)
    # Only the fetch itself (built by `entity_ids_transformer`); an empty answer's AC-21
    # "Other A3 flyers" read is by kind alone on purpose.
    return [a for name, a in calls if name == PROMO_TOOL and "_diagnostics" in a], held


def test_owner_shape_product_and_promotion_ids_never_ride_a_brand_flyer_ask(session_factory):
    """The owner's shape-1 tool args (`product_ids` = the set, `promotion_ids` = the brand word's
    fan-out) never go out on a brand + kind ask that named no product: brand + kind + level do."""
    ids = _world(session_factory)
    calls, _held = _fetch_with_owner_shape(session_factory, ids, _brand_flyer_qf())
    _assert_brand_kind_calls(calls, ids)


def test_a_product_named_this_turn_keeps_the_product_path(session_factory):
    """Control: a product code the customer typed beside the brand and kind (placed by the
    resolver this turn) is the narrower ask and keeps `product_ids` (AC-17)."""
    ids = _world(session_factory)
    held_id = ids["held_ids"][HELD[0]]
    qf = _brand_flyer_qf()
    qf["entities"] = qf["entities"] + [
        {"raw": HELD[0], "hint": "product", "canonical_code": HELD[0], "current_message": True, "confident": True}
    ]
    resolutions = [{"token": HELD[0], "raw": HELD[0], "matches": [{"uuid": held_id, "entity_type": "product"}]}]
    calls, held = _fetch_with_owner_shape(session_factory, ids, qf, resolutions)
    assert calls and all(set(a.get("product_ids") or []) == set(held) for a in calls), calls
