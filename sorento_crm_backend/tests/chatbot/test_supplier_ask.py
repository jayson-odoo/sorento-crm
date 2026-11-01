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


def _seed_twin(session_factory) -> str:
    """A second supplier the same distinctive word names (the prod copy has three)."""
    from app.models.procurement import Supplier

    db = session_factory()
    twin = Supplier(
        id=str(uuid.uuid4()), supplier_code="ZZTSUP-TY02", supplier_name="ZZT TAIYANG SANITARY CO LTD",
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(twin)
    db.commit()
    return twin.id


@pytest.mark.parametrize("text_body", ["outstanding PO for taiyang", "outstanding for taiyng"])
def test_several_equal_suppliers_ask_which_one_and_never_drop_the_filter(session_factory, monkeypatch, text_body):
    """Crew console pass (1 Nov 2026): "taiyang" placed several suppliers equally and the turn
    answered with no supplier filter. Two suppliers for one ask is a question."""
    _seed_suppliers(session_factory)
    _seed_twin(session_factory)
    _seed_contact(session_factory, variables={})
    _make_staff(session_factory)
    reply, captured = _turn(session_factory, monkeypatch, _ask("taiyang", None), text_body)
    assert "Which one do you mean?" in reply, reply  # the roster every optional filter asks with
    assert SUPPLIER in reply and "ZZT TAIYANG SANITARY CO LTD" in reply, reply
    assert not _po_calls(captured), f"no unfiltered (or all-supplier) PO list before the pick: {captured}"
    assert not [n for n, _ in captured if n == "crm_report_ask"], captured


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
    assert not _po_calls(captured), f"a dealer's order ask never becomes a PO ask: {captured}"
    # The asker's own word may be echoed; the supplier record (its full name) never is.
    assert SUPPLIER not in reply, reply


def test_staff_without_the_supplier_reveal_never_resolves_a_supplier(session_factory, monkeypatch):
    _seed_suppliers(session_factory)
    _seed_contact(session_factory, variables={})
    _make_staff(session_factory)
    reply, captured = _turn(
        session_factory, monkeypatch, _ask("taiyang", None), "the outstanding for taiyang", attributes=(PLACED,)
    )
    assert not _po_calls(captured), f"without the reveal the order ask is never swapped: {captured}"
    assert SUPPLIER not in reply, reply


@pytest.mark.parametrize(
    "raw,hint",
    [("taiyang", "supplier"), ("ZZTSUP-TY01", "customer"), ("ZZTSUP-TY01", "product")],
)
def test_staff_without_the_reveal_get_no_supplier_filter_on_a_po_ask(session_factory, monkeypatch, raw, hint):
    """A PO-domain ask (PO view held, supplier reveal not): neither the parser's supplier hint nor
    the resolver placing another word on a supplier (its code) turns into a supplier filter."""
    _seed_suppliers(session_factory)
    _seed_contact(session_factory, variables={})
    _make_staff(session_factory)
    reply, captured = _turn(
        session_factory, monkeypatch, _ask(raw, None, domain="purchase_order", hint=hint), f"POs for {raw}",
        attributes=(PLACED,),
    )
    assert not [a for a in _po_calls(captured) if a.get("supplier_ids")], captured
    assert SUPPLIER not in reply, reply


def test_the_owner_message_with_asks_still_reads_the_po_book(session_factory, monkeypatch):
    """The plan reads `asks` before `domain_hint`, so the swap rewrites both."""
    ids = _seed_suppliers(session_factory)
    _seed_contact(session_factory, variables={})
    _make_staff(session_factory)
    qf = {**_ask(NATIVE, SUPPLIER), "asks": [{"domain": "order"}]}
    _reply, captured = _turn(session_factory, monkeypatch, qf, OWNER_MESSAGE)
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["ours"]], captured


@pytest.mark.parametrize(
    "staff,keys,expected",
    [(True, [SUPPLIER_GRANT], True), (True, [PLACED], False), (False, [SUPPLIER_GRANT], False)],
)
def test_the_supplier_block_is_for_office_staff_with_the_reveal(monkeypatch, staff, keys, expected):
    import types

    from app.services import contact_customer_scope, contact_field_reveal_service, field_access
    from app.services.chatbot import engine as engine_mod

    class _Db:
        def begin_nested(self):
            import contextlib

            return contextlib.nullcontext()

    monkeypatch.setattr(field_access, "resolve_contact_with_null_workspace_fallback", lambda db, **kw: "pk-1")
    monkeypatch.setattr(
        contact_customer_scope, "contact_customer_scope",
        lambda db, pk: types.SimpleNamespace(staff=staff, enforced=not staff, customer_ids=[]),
    )
    monkeypatch.setattr(contact_field_reveal_service, "granted_keys", lambda db, pk: list(keys))
    monkeypatch.setattr(engine_mod, "_may_see_salespeople", lambda db, pk: False)
    assert engine_mod._lookup_visibility(_Db(), "c-1", None)[3] is expected


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
    trig = {
        "tool": PO_TOOL,
        "semantic_input": {},
        "entities": [{"uuid": sid, "entity_type": "supplier", "code": "ZZTSUP-TY01"}],
    }
    out = fetch_mod.entity_ids_transformer({**trig, "access": {"attributes": [SUPPLIER_GRANT]}})
    assert out["supplier_ids"] == [sid]
    # The second refusal, below the resolver (the RESTRICTED_SORT_KEYS precedent).
    refused = fetch_mod.entity_ids_transformer({**trig, "access": {"attributes": [PLACED]}})
    assert "supplier_ids" not in refused
    assert refused["_diagnostics"]["refused"] == {"supplier_ids": [sid]}


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


def test_the_swap_rewrites_order_asks_too():
    v = {**_verdict("order", "supplier"), "asks": [{"domain": "order"}, {"domain": "incoming"}]}
    out = resolve_gate.supplier_ask_reads_purchase_orders(v)
    assert out["asks"] == [{"domain": "purchase_order"}, {"domain": "incoming"}]


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


# --------------------------------------------------------------------------- #
# prompts: new UNLABELLED versions only; the owner moves the label after the eval
# --------------------------------------------------------------------------- #


def _migration(name: str):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_span_edit_asks_meanings_names_the_supplier_and_reads_chinese_names_by_pinyin():
    """Crew console pass: the production span prompt (v1) asks for no meaning, so the edit adds it."""
    from app.services.ai_prompt_registry import PROMPT_KEYS
    from app.services.chatbot.head import span_extract

    sask = _migration("sask_0002_span_supplier")
    assert sask.MEANING_PARAGRAPH == span_extract.MEANING_PARAGRAPH, "the frozen copy matches the code"
    v1 = PROMPT_KEYS["chatbot_span_extractor"].fallback()
    out = sask.with_supplier_type(v1)
    lines = out.split("\n")
    at = next(i for i, ln in enumerate(lines) if ln.startswith("- customer:"))
    assert lines[at + 1] == sask.SUPPLIER_TYPE_LINE
    assert span_extract.MEANING_ASK in out, "the span model is asked for meanings"
    assert span_extract.span_schema(out) is span_extract.SCHEMA
    assert out.endswith(sask.NAME_MEANING_SENTENCE)
    assert sask.with_supplier_type(out) is None, "applied once"
    assert sask.with_supplier_type("no anchor here") is None


def test_the_parser_edit_goes_right_after_the_span_marker():
    from app.services.chatbot.head import lookup_lists as ll_mod

    sask = _migration("sask_0002_span_supplier")
    text = "head\n== LOOKUP SPANS ==\ntail"
    out = sask.with_supplier_line(text)
    assert out == f"head\n== LOOKUP SPANS ==\n{sask.PARSER_SUPPLIER_LINE}\ntail"
    assert ll_mod.spans_gate_on(out), "the span pass stays on"
    assert sask.with_supplier_line(out) is None
    assert sask.with_supplier_line("no marker") is None


def _seed_prompts(db) -> str:
    """Production span v1 and a production parser that runs the span pass; the parser label's version id."""
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion

    _migration("eem_0001_span_pass").seed_span_prompt(db)
    top = db.query(AIPromptVersion.version).filter(AIPromptVersion.name == "chatbot_semantic_parser").order_by(
        AIPromptVersion.version.desc()
    ).first()
    parser_row = AIPromptVersion(
        name="chatbot_semantic_parser", version=(int(top[0]) if top else 0) + 1, type="text",
        template="ZZT parser\n== LOOKUP SPANS ==\nrules", variables=["current_date"], config_json={"blocks_hash": "x"},
    )
    db.add(parser_row)
    db.flush()
    label = db.query(AIPromptLabel).filter(
        AIPromptLabel.name == "chatbot_semantic_parser", AIPromptLabel.label == "production"
    ).first()
    if label is None:
        db.add(AIPromptLabel(name="chatbot_semantic_parser", label="production", version_id=parser_row.id))
    else:
        label.version_id = parser_row.id
    db.flush()
    return parser_row.id


def _labels(db) -> dict[str, str]:
    from app.models.ai_prompt import AIPromptLabel

    return {
        r.name: str(r.version_id)
        for r in db.query(AIPromptLabel).filter(AIPromptLabel.label == "production")
        if r.name in ("chatbot_semantic_parser", "chatbot_span_extractor")
    }


def test_the_migration_publishes_a_paired_span_and_parser_version_unlabelled_once(session_factory):
    from app.models.ai_prompt import AIPromptVersion

    db = session_factory()
    _seed_prompts(db)
    labels = _labels(db)
    sask = _migration("sask_0002_span_supplier")
    span_v, parser_v = sask.publish(db)
    assert span_v is not None and parser_v is not None
    span_row = db.query(AIPromptVersion).filter(
        AIPromptVersion.name == "chatbot_span_extractor", AIPromptVersion.version == span_v
    ).one()
    parser_row = db.query(AIPromptVersion).filter(
        AIPromptVersion.name == "chatbot_semantic_parser", AIPromptVersion.version == parser_v
    ).one()
    assert sask.SUPPLIER_TYPE_LINE in span_row.template and sask.NAME_MEANING_SENTENCE in span_row.template
    assert sask.PARSER_SUPPLIER_LINE in parser_row.template and "== LOOKUP SPANS ==" in parser_row.template
    assert parser_row.config_json["span_prompt_version_id"] == str(span_row.id)
    assert parser_row.config_json["blocks_hash"] == "x", "the base version's config rides along"
    assert _labels(db) == labels, "no production label moves"
    count = db.query(AIPromptVersion).count()
    assert sask.publish(db) == (span_v, parser_v) and db.query(AIPromptVersion).count() == count


def test_a_console_parser_pin_runs_its_paired_span_prompt_on_a_dry_run_only(session_factory):
    from types import SimpleNamespace

    from app.services.chatbot import engine as engine_mod

    db = session_factory()
    _seed_prompts(db)
    sask = _migration("sask_0002_span_supplier")
    span_v, parser_v = sask.publish(db)
    from app.models.ai_prompt import AIPromptVersion

    parser_id = db.query(AIPromptVersion.id).filter(
        AIPromptVersion.name == "chatbot_semantic_parser", AIPromptVersion.version == parser_v
    ).scalar()
    paired = db.query(AIPromptVersion.config_json).filter(AIPromptVersion.id == parser_id).scalar()["span_prompt_version_id"]

    def env(overrides):
        return SimpleNamespace(model_extra={"prompt_overrides": overrides})

    pin = {"chatbot_semantic_parser": str(parser_id)}
    assert engine_mod._span_override(db, env(pin), dry_run=True) == paired
    assert engine_mod._span_override(db, env(pin), dry_run=False) is None, "a live turn never pins"
    own = {**pin, "chatbot_span_extractor": "span-own"}
    assert engine_mod._span_override(db, env(own), dry_run=True) == "span-own"
    assert engine_mod._span_override(db, env({}), dry_run=True) is None


def test_a_pick_from_the_supplier_roster_lists_that_suppliers_open_pos(session_factory, monkeypatch):
    """Hand-test step 4: "1" after "Which one do you mean?" filters by the supplier on line 1."""
    ids = _seed_suppliers(session_factory)
    twin = _seed_twin(session_factory)
    _seed_contact(session_factory, variables={})
    _make_staff(session_factory)
    asked, _ = _turn(session_factory, monkeypatch, _ask("taiyang", None), "outstanding PO for taiyang")
    assert "Which one do you mean?" in asked, asked
    first = next(ln for ln in asked.splitlines() if ln.startswith("1. "))
    expected = ids["ours"] if SUPPLIER in first else twin
    pick = _parser_output(
        message_type="answer", intent_hint=None, domain_hint=None, entities=[], reference_positions=[1],
    )
    _reply, captured = _turn(session_factory, monkeypatch, pick, "1")
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [expected], captured


# --------------------------------------------------------------------------- #
# Console pass 2 (crew, e04e8ebb9d): the three failures, red first
# --------------------------------------------------------------------------- #


def test_a_spaced_pinyin_meaning_does_not_reach_the_record_but_the_joined_one_does(session_factory):
    """The span model answered "tai yang"; the records keep "TAIYANG". Code scores spans, it does not guess
    a join, so the prompt must ask for the name as written in the records: one word per name word."""
    _seed_suppliers(session_factory)
    spaced = _resolve(session_factory, list_resolver.Span(NATIVE, "supplier", meaning="tai yang"))
    joined = _resolve(session_factory, list_resolver.Span(NATIVE, "supplier", meaning="Taiyang"))
    assert not (spaced.status == "resolved" and spaced.candidates[0].row.label == SUPPLIER)
    assert joined.status == "resolved" and joined.candidates[0].row.label == SUPPLIER


def test_the_span_prompt_asks_for_pinyin_joined_the_way_records_write_the_name():
    sask = _migration("sask_0002_span_supplier")
    sentence = sask.NAME_MEANING_SENTENCE
    assert "Taiyang" in sentence and "tai yang" in sentence, sentence
    assert "joined" in sentence or "one word" in sentence, sentence


def test_the_parser_line_says_several_equal_supplier_lines_are_a_question_not_a_pick():
    """Console pass 2 step 3: three Supplier candidates fitted "taiyang" equally and the parser picked one."""
    line = _migration("sask_0002_span_supplier").PARSER_SUPPLIER_LINE
    assert "several" in line and "canonical_code" in line, line
    assert "share" in line, "the shared name word is the token, so the resolver finds every supplier it names"


def test_the_native_name_read_as_the_shared_word_asks_which_supplier(session_factory, monkeypatch):
    """What the parser answers under the new line for "太阳" with several TAIYANG suppliers listed: hint
    supplier, canonical_code the shared word. The resolver finds every supplier it names and the turn asks."""
    _seed_suppliers(session_factory)
    _seed_twin(session_factory)
    _seed_contact(session_factory, variables={})
    _make_staff(session_factory)
    reply, captured = _turn(session_factory, monkeypatch, _ask(NATIVE, "TAIYANG"), OWNER_MESSAGE)
    # The roster question, in the asker's language (this message is Chinese: 您指的是哪一个？).
    lines = reply.splitlines()
    assert f"1. {SUPPLIER}" in lines or f"2. {SUPPLIER}" in lines, reply
    assert any(ln.endswith("ZZT TAIYANG SANITARY CO LTD") for ln in lines), reply
    assert not _po_calls(captured), captured


def test_republishing_never_stacks_a_second_supplier_line(session_factory, monkeypatch):
    """Crew republishes sask_0002 on a copy that already holds this migration's earlier parser version: the
    new version is built from the span-pass parser this migration did NOT publish."""
    from app.models.ai_prompt import AIPromptVersion

    from app.models.ai_prompt import AIPromptLabel

    db = session_factory()
    _seed_prompts(db)
    # As on the copy: production is a parser WITHOUT the span pass, a newer version has it.
    plain = AIPromptVersion(
        name="chatbot_semantic_parser", version=900001, type="text", template="ZZT plain parser",
        variables=["current_date"], config_json={},
    )
    db.add(plain)
    db.flush()
    db.query(AIPromptLabel).filter(
        AIPromptLabel.name == "chatbot_semantic_parser", AIPromptLabel.label == "production"
    ).one().version_id = plain.id
    db.flush()
    sask = _migration("sask_0002_span_supplier")
    sask.publish(db)
    monkeypatch.setattr(sask, "PARSER_SUPPLIER_LINE", "A changed supplier line.")
    monkeypatch.setattr(sask, "NAME_MEANING_SENTENCE", "A changed name sentence.")
    _span_v, parser_v = sask.publish(db)
    row = db.query(AIPromptVersion).filter(
        AIPromptVersion.name == "chatbot_semantic_parser", AIPromptVersion.version == parser_v
    ).one()
    assert "A changed supplier line." in row.template
    assert 'A "Supplier candidates" line' not in row.template, "the earlier line rode in from its own version"
    assert row.template.count("== LOOKUP SPANS ==") == 1
