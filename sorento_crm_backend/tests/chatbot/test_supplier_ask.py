"""SUPPLIER-ASK: a supplier is an entity kind the bot resolves, and "outstanding / POs for
supplier X" lists that supplier's open purchase orders (not yet received).

`documentation/plans/chatbot/PLAN-supplier-ask-01nov.md`, UAC
`supplier-ask-acceptance-criteria.md` AC-1..AC-4.

Turn level: one real `engine.run_turn` with the REAL resolver over rows seeded on the blank
schema (`test_outstanding_lane._run_turn(real_resolver=True)`); only the parser, the access
check and the MCP network edge are doubled. Staff = `chatbot_profile.tier == "office"`.

The parser double answers what the real parser answers when the Supplier candidates block
(span pass, `head/lookup_lists`) names the row: the user's raw words, hint `supplier`, and
the picked label as `canonical_code`. The span pass itself (any language, typos) is graded
below on `list_resolver`, where code scores the spans.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest

from app.services.chatbot import contracts
from app.services.chatbot.head import list_resolver
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.lanes.business import fetch as fetch_mod
from app.services.chatbot.lanes.business import gate as gate_mod
from app.services.chatbot.lanes.business import resolve_gate
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_lookup_lists_s2 import meaning_embed, scoped
from tests.chatbot.test_outstanding_lane import _run_turn, _seed_contact
from tests.chatbot.test_po_ref_ask import _make_staff

#: The owner's message, verbatim (Chatbot Console, 1 Nov 2026).
OWNER_MESSAGE = "the outstanding for 太阳"
NATIVE = "太阳"
SUPPLIER = "ZZT TAIYANG TECHNOLOGY CO.,LTD"
OTHER = "ZZT JINBAI SANITARY WARE CO LTD"
PO_TOOL = "crm_procurement_po_placed_list"
PLACED = "purchase_orders.placed"
SUPPLIER_GRANT = "purchase_orders.supplier"
STAFF_GRANTS = (PLACED, SUPPLIER_GRANT, "sales_orders.outstanding")


# --------------------------------------------------------------------------- #
# seeds
# --------------------------------------------------------------------------- #


def _seed_suppliers(session_factory) -> dict[str, Any]:
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
    from tests._mc_lookup_seed import product

    db = session_factory()
    ours = Supplier(
        id=str(uuid.uuid4()), supplier_code="ZZTSUP-TY01", supplier_name=SUPPLIER, company_id=DEFAULT_COMPANY_ID,
    )
    other = Supplier(
        id=str(uuid.uuid4()), supplier_code="ZZTSUP-JB02", supplier_name=OTHER, company_id=DEFAULT_COMPANY_ID,
    )
    gone = Supplier(
        id=str(uuid.uuid4()), supplier_code="ZZTSUP-OLD9", supplier_name="ZZT RETIRED VALVE CO",
        company_id=DEFAULT_COMPANY_ID, is_active=False,
    )
    db.add_all([ours, other, gone])
    db.flush()
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    for sup, number, ordered, received in (
        (ours, "PO-ZZT-OURS-1", 10, 4),
        (ours, "PO-ZZT-OURS-DONE", 5, 5),
        (other, "PO-ZZT-OTHER-1", 9, 0),
    ):
        po = PurchaseOrder(
            id=str(uuid.uuid4()), po_number=number, supplier_id=sup.id, company_id=DEFAULT_COMPANY_ID,
            expected_date=date(2026, 12, 1),
        )
        db.add(po)
        db.flush()
        db.add(
            PurchaseOrderLine(
                id=str(uuid.uuid4()), purchase_order_id=po.id, product_id=prod.id, qty_ordered=ordered,
                qty_received=received, line_status="open", company_id=DEFAULT_COMPANY_ID,
            )
        )
    db.commit()
    return {"ours": ours.id, "other": other.id, "code": ours.supplier_code}


def _ask(raw: str, canonical: str | None, *, domain: str = "order", hint: str = "supplier") -> dict[str, Any]:
    return _parser_output(
        domain_hint=domain,
        intent_hint="check_order" if domain == "order" else "check_po",
        order_status=None,
        entities=[{"raw": raw, "hint": hint, "canonical_code": canonical, "current_message": True, "confident": True}],
    )


def _turn(session_factory, monkeypatch, qf, text_body: str, *, attributes=STAFF_GRANTS):
    result, captured = _run_turn(
        session_factory,
        monkeypatch,
        qf=qf,
        text_body=text_body,
        msg_id=f"ZZT-supplier-ask-{uuid.uuid4().hex[:10]}",
        attributes=list(attributes),
        real_resolver=True,
        mcp_response=None,
    )
    return ((result.reply or {}).get("text") or ""), captured


def _po_calls(captured) -> list[dict[str, Any]]:
    return [args for name, args in captured if name == PO_TOOL]


# --------------------------------------------------------------------------- #
# AC-1 / AC-2: the turn (staff)
# --------------------------------------------------------------------------- #


def test_owner_message_lists_the_suppliers_open_pos(session_factory, monkeypatch):
    """AC-1: "the outstanding for 太阳" (an order-domain outstanding ask) names a supplier:
    it is answered from the open PO book filtered to that supplier, never the SO report."""
    ids = _seed_suppliers(session_factory)
    _seed_contact(session_factory, variables={})
    _make_staff(session_factory)
    _reply, captured = _turn(session_factory, monkeypatch, _ask(NATIVE, SUPPLIER), OWNER_MESSAGE)
    calls = _po_calls(captured)
    assert calls, f"the open PO book was never asked: {captured}"
    assert calls[0].get("supplier_ids") == [ids["ours"]], calls[0]
    assert not [n for n, _ in captured if n == "crm_report_ask"], "a supplier is not a customer outstanding report"


@pytest.mark.parametrize(
    "raw,canonical,text_body",
    [
        ("taiyang", None, "outstanding PO for taiyang"),  # an English (romanised) name the resolver matches by word
        ("ZZTSUP-TY01", None, "POs for ZZTSUP-TY01"),  # the supplier's code
        ("taiyng", SUPPLIER, "outstanding for taiyng"),  # a typo the span pass placed on the row
    ],
)
def test_name_code_and_typo_list_the_same_suppliers_open_pos(session_factory, monkeypatch, raw, canonical, text_body):
    """AC-2."""
    ids = _seed_suppliers(session_factory)
    _seed_contact(session_factory, variables={})
    _make_staff(session_factory)
    _reply, captured = _turn(session_factory, monkeypatch, _ask(raw, canonical), text_body)
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["ours"]], captured


def test_a_po_domain_ask_for_a_supplier_filters_by_it(session_factory, monkeypatch):
    """"POs for supplier X" parsed straight into the purchase_order domain."""
    ids = _seed_suppliers(session_factory)
    _seed_contact(session_factory, variables={})
    _make_staff(session_factory)
    _reply, captured = _turn(
        session_factory, monkeypatch, _ask("taiyang", None, domain="purchase_order"), "POs for taiyang"
    )
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["ours"]], captured


# --------------------------------------------------------------------------- #
# AC-4: a dealer never gets a supplier
# --------------------------------------------------------------------------- #


def test_a_dealer_never_resolves_a_supplier(session_factory, monkeypatch):
    _seed_suppliers(session_factory)
    _seed_contact(session_factory, variables={})
    # A dealer's turn carries no Supplier candidates block, so its parser has only the raw words.
    reply, captured = _turn(
        session_factory, monkeypatch, _ask("taiyang", None), "the outstanding for taiyang",
        attributes=("sales_orders.outstanding",),
    )
    assert not [a for a in _po_calls(captured) if a.get("supplier_ids")], captured
    # The asker's own word may be echoed; the supplier record (its full name) never is.
    assert SUPPLIER not in reply, reply


def test_staff_without_the_supplier_reveal_never_resolves_a_supplier(session_factory, monkeypatch):
    _seed_suppliers(session_factory)
    _seed_contact(session_factory, variables={})
    _make_staff(session_factory)
    reply, captured = _turn(
        session_factory, monkeypatch, _ask("taiyang", None), "the outstanding for taiyang", attributes=(PLACED,)
    )
    assert not [a for a in _po_calls(captured) if a.get("supplier_ids")], captured
    assert SUPPLIER not in reply, reply


def test_supplier_visibility_needs_staff_and_the_reveal():
    assert contracts.supplier_visible([SUPPLIER_GRANT], True) is True
    assert contracts.supplier_visible([SUPPLIER_GRANT], False) is False
    assert contracts.supplier_visible([PLACED], True) is False
    assert contracts.supplier_visible(None, True) is False


# --------------------------------------------------------------------------- #
# kinds, gate, fetch
# --------------------------------------------------------------------------- #


def test_supplier_is_an_entity_kind_with_a_seed_row():
    from app.services.chatbot.turn.policy_rows import DEFAULT_KIND_ROWS

    assert "supplier" in contracts.ENTITY_HINTS
    row = next(r for r in DEFAULT_KIND_ROWS if r["kind"] == "supplier")
    assert row["resolver_source"] == "suppliers"


def test_the_migration_inserts_the_supplier_kind_once(session_factory):
    import importlib.util
    from pathlib import Path

    from sqlalchemy import text

    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "sask_0001_supplier_kind.py"
    spec = importlib.util.spec_from_file_location("_sask_0001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    db = session_factory()
    conn = db.connection()
    conn.execute(text("DELETE FROM chatbot_entity_kinds WHERE kind = 'supplier'"))
    assert module.insert_kind(conn) is True
    assert module.insert_kind(conn) is False
    assert conn.execute(text("SELECT count(*) FROM chatbot_entity_kinds WHERE kind = 'supplier'")).scalar() == 1


def test_the_po_domain_admits_a_supplier_and_fetch_maps_it():
    assert "supplier" in gate_mod.ALLOWED["purchase_order"]
    assert fetch_mod.TYPE_TO_PARAM["supplier"] == "supplier_ids"
    sid = str(uuid.uuid4())
    out = fetch_mod.entity_ids_transformer(
        {
            "tool": PO_TOOL,
            "semantic_input": {},
            "entities": [{"uuid": sid, "entity_type": "supplier", "code": "ZZTSUP-TY01"}],
        }
    )
    assert out["supplier_ids"] == [sid]


def _resolved(*types: str) -> dict[str, Any]:
    return {
        "resolutions": [
            {"token": f"t{i}", "matches": [{"entity_type": t, "uuid": str(uuid.uuid4()), "canonical_code": t}]}
            for i, t in enumerate(types)
        ]
    }


def _verdict(domain: str, *hints: str) -> dict[str, Any]:
    return {
        "domain_hint": domain,
        "intent_hint": "check_order",
        "order_status": "so_outstanding",
        "entities": [{"raw": h, "hint": h, "current_message": True} for h in hints],
    }


@pytest.mark.parametrize("domain", ["order", "sales"])
def test_a_supplier_only_order_ask_reads_the_po_book(domain):
    before = _verdict(domain, "supplier")
    out = resolve_gate.supplier_ask_reads_purchase_orders(before)
    assert (out["domain_hint"], out["intent_hint"], out["order_status"]) == ("purchase_order", "check_po", None)
    assert before["domain_hint"] == domain, "the verdict passed in is not changed"


def test_a_product_beside_the_supplier_still_reads_the_po_book():
    out = resolve_gate.supplier_ask_reads_purchase_orders(_verdict("order", "supplier", "product"))
    assert out["domain_hint"] == "purchase_order"


def test_a_customer_beside_the_supplier_keeps_the_order_domain():
    v = _verdict("order", "supplier", "customer")
    assert resolve_gate.supplier_ask_reads_purchase_orders(v) is v


def test_another_domain_is_left_alone():
    v = _verdict("inventory", "supplier")
    assert resolve_gate.supplier_ask_reads_purchase_orders(v) is v


def test_supplier_rows_are_dropped_for_an_asker_who_may_not_see_them():
    resolved = _resolved("supplier", "product")
    resolve_gate.without_rows_of(resolved, "supplier")
    kinds = [m["entity_type"] for r in resolved["resolutions"] for m in r["matches"]]
    assert kinds == ["product"]


def test_a_supplier_token_is_sent_only_when_the_asker_may_see_suppliers():
    qf = _ask(NATIVE, SUPPLIER)
    ctx = {"parse": {"output": qf}, "text": {"message": {"message": {"text": OWNER_MESSAGE}}}}
    hidden = resolve_gate.resolve_entity_body(ctx)
    assert hidden["tokens"] == [] and "supplier" not in hidden["allowed_entity_types"], hidden
    shown = resolve_gate.resolve_entity_body({**ctx, "supplier_visible": True})
    assert shown["tokens"] == [SUPPLIER] and shown["allowed_entity_types"] == ["supplier"], shown


# --------------------------------------------------------------------------- #
# the span pass: supplier rows, scored like every other closed list
# --------------------------------------------------------------------------- #


def test_supplier_lookup_constants():
    assert "supplier" in list_resolver.SPAN_TYPES
    assert ll.HEADER_NOUN["supplier"] == "Supplier"
    assert "supplier" in ll.DEFAULT_ORDER and ll.TOP_K["supplier"] >= 1
    from app.services.chatbot.head import span_extract

    enum = span_extract.SCHEMA["properties"]["spans"]["items"]["properties"]["type"]["enum"]
    assert "supplier" in enum


def test_supplier_rows_are_off_by_default_active_only_and_carry_the_code(session_factory):
    _seed_suppliers(session_factory)
    db = scoped(session_factory)
    assert not [r for r in ll.load_rows(db) if r.list_name == "supplier"]
    rows = [r for r in ll.load_rows(db, include_suppliers=True) if r.list_name == "supplier"]
    assert {r.label for r in rows} == {SUPPLIER, OTHER}
    ours = next(r for r in rows if r.label == SUPPLIER)
    assert "ZZTSUP-TY01" in ours.texts


def _resolve(session_factory, span: list_resolver.Span, embed=None) -> list_resolver.Resolution:
    rows = ll.load_rows(scoped(session_factory), include_suppliers=True)
    return list_resolver.resolve([span], rows, embed=embed)[0]


@pytest.mark.parametrize(
    "span",
    [
        list_resolver.Span("taiyang", "supplier"),  # English (romanised) name, one distinctive word
        list_resolver.Span("ZZT Taiyang Technology"),  # the name as written, untyped
        list_resolver.Span("ZZTSUP-TY01"),  # the code
        list_resolver.Span("taiyng", "supplier"),  # a typo
        list_resolver.Span(NATIVE, "supplier", meaning="Taiyang"),  # native script, read by its plain form
    ],
)
def test_a_span_naming_the_supplier_resolves_to_its_row(session_factory, span):
    _seed_suppliers(session_factory)
    res = _resolve(session_factory, span)
    assert res.status == "resolved", (span, res.status, [c.row.label for c in res.candidates])
    assert res.candidates[0].row.list_name == "supplier" and res.candidates[0].row.label == SUPPLIER


def test_the_native_name_resolves_by_meaning_alone(session_factory):
    """No word list: "太阳" reaches the row through the embedder (stubbed here: the span
    and the row's texts share one axis), the same `meaning` signal every list uses."""
    _seed_suppliers(session_factory)
    embed = meaning_embed({NATIVE.casefold(), SUPPLIER.casefold()})
    res = _resolve(session_factory, list_resolver.Span(NATIVE, "supplier"), embed=embed)
    assert res.status == "resolved", (res.status, [c.row.label for c in res.candidates])
    assert res.candidates[0].row.label == SUPPLIER and res.candidates[0].signal == "meaning"


def test_the_supplier_block_renders_with_its_header():
    row = ll.LookupRow("supplier", "k", SUPPLIER, (SUPPLIER,))
    lines = ll.render({"supplier": [ll.Hit(row, NATIVE, 0.0, 0.9)]})
    assert lines == [ll.header("supplier"), f"- {SUPPLIER}"]
