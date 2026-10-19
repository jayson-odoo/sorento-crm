"""R6-3 NAMES-OWN-CLASS-AT-EVERY-SEAM (HELD-OVER-NEW-CLASS; TRAIN cp0-12bd74671a, cp0-b0b71b2581; ZZ data).

The rule "a message that names its own class is not about the held products" was missed at two seams:
(1) an answered one-product stock task read a quantity in a class ask ("6 pcs") as the held product at 6
and locked the fetch to it; (2) grounding rewrote the parser's category "basin cabinet" into a
furniture_type spec, so the rule saw no class entity after grounding. A refine with a brand, spec or size
(CHAT-STATE R1) still keeps the held subject.
"""
from __future__ import annotations

import uuid

import app.main  # noqa: F401  isort:skip
from app.models.product import ProductCategory
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot._attach_world import World, entity, real_parse, run_turns, text_of
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401

from app.services.chatbot.turn import task as task_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.state import Focus
from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict

STOCK = "crm_inventory_stock_balance_list"


def _stock_fetches(calls) -> list[dict]:
    return [a for n, a in calls if n == STOCK]


def _stock_parse(entities, **over):
    return real_parse(entities, intent_hint="check_stock", domain_hint="inventory", user_goal="stock", **over)


def _answered_ten():
    """ZZKT10 x 10 answered: the one-product check kept on the focus."""
    tasks = task_mod.tasks_after_reply(
        (), ht.envelopes(ht.row("ZZKT10", needs_quantity=False, requested_qty=10, branch="in_stock")), turn_no=7,
    )
    return ht.state(Focus(tasks=tasks, domains=["inventory"], products=ht.product_rows("ZZKT10")), turn_no=8)


def _revised(plan) -> bool:
    return "task_revised_stock_qty" in plan.trace.rules_fired


_CLASS_ASK = [
    {"raw": "zzbrand", "hint": "brand", "canonical_code": "ZZBRAND", "current_message": True, "confident": True},
    {"raw": "zz basin", "hint": "category", "canonical_code": None, "current_message": True, "confident": True},
]


def test_a_quantity_in_a_class_ask_is_not_a_revision_of_the_held_product():
    """The lane's real verdict carries `closed_lists` (engine.closed_lists_verdict)."""
    v = verdict(
        entities=list(_CLASS_ASK), demand_qty=6, closed_lists=True,
        # the real top-level fields of cp0-12bd74671a (g1755c, understood stage)
        domain_in_message=False, entity_op="replace_combine", domain_hint="master_products", intent_hint="check_product",
        scope_intent="specific", message_type="business_query", continuation=False, topic_reset=False, match_mode="and",
    )

    _state2, plan = apply(_answered_ten(), v, build_policy())

    assert not _revised(plan), plan.trace.rules_fired
    assert all(ht.uuid_of("ZZKT10") not in [e.get("uuid") for e in spec.entities] for spec in ht.inventory_specs(plan)), plan.fetch


def test_guard_gate_off_the_quantity_still_revises_the_held_check():
    v = verdict(entities=list(_CLASS_ASK), demand_qty=6, domain_hint="inventory")

    _state2, plan = apply(_answered_ten(), v, build_policy())

    assert _revised(plan), plan.trace.rules_fired


def test_guard_a_bare_number_still_revises_the_answered_check():
    _state2, plan = apply(
        _answered_ten(), verdict(entities=[], demand_qty=6, correction=True, domain_hint="inventory"), build_policy(),
    )

    assert _revised(plan), plan.trace.rules_fired


# --- seam (2): a category grounding turns into a spec still names the class ----------------------


def _furniture_world(session_factory) -> World:
    w = World(session_factory)
    db = w.db
    for label in ("ZZ Basin", "ZZ Cabinet"):
        w.category(label)
    db.add(ProductSpecRegistry(
        id=str(uuid.uuid4()), spec_key="class", label="Class", data_type="enum", allowed_values=[],
        synonyms={"ZZ Basin": ["zzbasin"], "ZZ Cabinet": ["zzcabinet"]},
    ))
    db.add(ProductSpecRegistry(
        id=str(uuid.uuid4()), spec_key="furniture_type", label="Furniture type", data_type="enum",
        allowed_values=["zz_basin_cabinet"], synonyms={"zz_basin_cabinet": ["zzbasin zzcabinet"]},
    ))
    db.flush()
    from app.models.inventory import Stock, Warehouse
    from tests._pg_fixture import unique_code

    wh = Warehouse(id=str(uuid.uuid4()), warehouse_code=unique_code("WH")[:20], warehouse_name="ZZT WH", company_id=DEFAULT_COMPANY_ID)
    db.add(wh)
    db.flush()
    for code in ("ZZBF100", "ZZBC200", "ZZBC300"):
        p = w.product(code, category="ZZ Cabinet")
        db.add(Stock(id=str(uuid.uuid4()), product_id=p.id, warehouse_id=wh.id, quantity_on_hand=5, company_id=DEFAULT_COMPANY_ID))
        db.add(ProductSpecifications(
            id=str(uuid.uuid4()), product_id=p.id, values={"class": {"value": "ZZ Cabinet"}, "furniture_type": {"value": "zz_basin_cabinet"}},
        ))
    return w.commit()


def test_a_category_grounding_turns_into_a_spec_still_names_the_class(session_factory, seeded, stub_access, monkeypatch):
    w = _furniture_world(session_factory)
    held = _stock_parse([entity("ZZBF100", "product", canonical="ZZBF100")])
    named = _stock_parse([entity("zzbasin zzcabinet", "category")])

    (_r1, _c1), (r2, c2) = run_turns(session_factory, stub_access, monkeypatch, [("ZZBF100", held), ("any zzbasin zzcabinet?", named)], w)

    sent = {pid for a in _stock_fetches(c2) for pid in a.get("product_ids") or []}
    assert sent != {w.products["ZZBF100"].id}, (text_of(r2), c2)
    assert {w.products["ZZBC200"].id, w.products["ZZBC300"].id} <= sent, (text_of(r2), c2)


def test_guard_a_parser_emitted_spec_is_a_refine_of_the_held_subject(session_factory, seeded, stub_access, monkeypatch):
    w = _furniture_world(session_factory)
    held = _stock_parse([entity("ZZBF100", "product", canonical="ZZBF100")])
    spec = entity("zzbasin zzcabinet", "specification", spec_key="furniture_type", spec_value="zz_basin_cabinet")

    (_r1, _c1), (r2, c2) = run_turns(session_factory, stub_access, monkeypatch, [("ZZBF100", held), ("zzbasin zzcabinet one?", _stock_parse([spec]))], w)

    sent = {pid for a in _stock_fetches(c2) for pid in a.get("product_ids") or []}
    assert w.products["ZZBF100"].id in sent, (text_of(r2), c2)
