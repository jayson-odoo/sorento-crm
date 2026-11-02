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
from tests.chatbot.test_engine import CONTACT_ID, _parser_output
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


def test_a_po_domain_ask_for_a_supplier_filters_by_it(session_factory, monkeypatch):
    """"POs for supplier X" parsed straight into the purchase_order domain."""
    ids = _staff_world(session_factory)
    _reply, captured = _turn(
        session_factory, monkeypatch, _ask("taiyang", None, domain="purchase_order"), "POs for taiyang"
    )
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["ours"]], (_reply, captured)


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


def test_the_span_edit_asks_meanings_and_names_the_supplier_type():
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


@pytest.mark.parametrize("base", ["head\n== LOOKUP SPANS ==\ntail", "no years line here\n== LOOKUP SPANS ==\n"])
def test_the_parser_edit_rules_after_a_year_whatever_the_base_says_about_years(base):
    """Owner turn 1-3: 'after 2025' was read as from 1 January 2025. Round 4 (crew): the copy's production parser v189
    has no 'Years compared' line, so the sentence never landed. It now sits right after the supplier line, which every
    published version carries, once."""
    sask = _migration("sask_0002_span_supplier")
    out = sask.with_after_year(sask.with_supplier_line(base))
    assert out is not None and out.count(sask.AFTER_YEAR_SENTENCE) == 1
    assert f"{sask.PARSER_SUPPLIER_LINE}\n{sask.AFTER_YEAR_SENTENCE}" in out and "2026-01-01" in sask.AFTER_YEAR_SENTENCE
    assert sask.with_after_year(out) is None, "applied once"
    assert sask.with_after_year("no supplier line") is None


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
    assert parser_row.template.count(sask.AFTER_YEAR_SENTENCE) == 1, "fix round 3: the bounded-year rule is published"
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


# --------------------------------------------------------------------------- #
# Console pass 2 (crew, e04e8ebb9d): the three failures, red first
# --------------------------------------------------------------------------- #


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
    assert sask.SUPPLIER_ID_ASK not in row.template, "the earlier line rode in from its own version"
    assert row.template.count("== LOOKUP SPANS ==") == 1


def test_the_published_prompts_compare_no_names():
    """Owner ruling (1 Nov 2026, "match by meaning"): no example name, no shared-word rule; the parser answers
    with the row id, and the code constant and the migration's frozen copy agree."""
    from app.services.chatbot.head import parser as parser_mod

    sask = _migration("sask_0002_span_supplier")
    assert sask.SUPPLIER_ID_ASK == parser_mod.SUPPLIER_ID_ASK
    assert sask.PARSER_SUPPLIER_LINE.startswith(parser_mod.SUPPLIER_ID_ASK)
    for text in (sask.PARSER_SUPPLIER_LINE, sask.NAME_MEANING_SENTENCE, sask.SUPPLIER_TYPE_LINE):
        assert "aiyang" not in text.lower() and "share" not in text and "pinyin" not in text, text


# --------------------------------------------------------------------------- #
# The span flow, end to end (owner ruling: suppliers do exactly what customers do). The span model and the embedder
# are doubles: `near` is the set of texts the embedder puts on one axis (cosine 1), everything else is orthogonal.
# The parser double answers what the id rule asks: the id of the FIRST Supplier candidates line it is shown.
# --------------------------------------------------------------------------- #

#: A name written the way some suppliers spell the same words apart.
SPACED = "ZZT TAI YANG TRADING SDN BHD"
THIRD = "ZZT TAIYANG METAL CO LTD"


class _PickFirstSupplierId(list):
    """`capture_user_block` for `_run_turn`: sees the user block the parser was shown and writes the first Supplier
    line's id into the verdict, as the parser would under `SUPPLIER_ID_ASK`."""

    def __init__(self, qf: dict[str, Any]) -> None:
        super().__init__()
        self.qf = qf

    def append(self, block: str) -> None:  # type: ignore[override]
        super().append(block)
        import re

        section = block.split(ll.header("supplier"), 1)
        ids = re.findall(r"\[id: ([0-9a-f-]{36})\]", section[1]) if len(section) == 2 else []
        for e in self.qf.get("entities") or []:
            if e.get("hint") == "supplier":
                e["canonical_code"] = ids[0] if ids else None


def _seed_named(session_factory, name: str, code: str) -> str:
    from app.models.procurement import Supplier

    db = session_factory()
    row = Supplier(id=str(uuid.uuid4()), supplier_code=code, supplier_name=name, company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.commit()
    return row.id


def _span_turn(session_factory, monkeypatch, text_body: str, span: list_resolver.Span, near: set[str], *,
               qf: dict[str, Any] | None = None, attributes=STAFF_GRANTS, supplier_ids: bool = True):
    import functools

    from app.services import contact_field_reveal_service
    from app.services.chatbot.head import parser as parser_mod
    from app.services.chatbot.head import span_extract

    monkeypatch.setattr(
        parser_mod, "ParserConfig",
        functools.partial(parser_mod.ParserConfig, lookup_spans=True, supplier_ids=supplier_ids),
    )
    monkeypatch.setattr(span_extract, "resolve_config", lambda db, **kw: span_extract.SpanConfig(
        "sys", 1, "openai", "gpt-zz", "ZZ-key", "label"))
    monkeypatch.setattr(span_extract, "extract", lambda config, message: span_extract.SpanAnswer([span], {}, 1))
    monkeypatch.setattr(ll, "EMBED", meaning_embed({t.casefold() for t in near}))
    monkeypatch.setattr(contact_field_reveal_service, "granted_keys", lambda db, pk: list(attributes))
    qf = qf or _ask(span.text, None)
    seen = _PickFirstSupplierId(qf)
    result, captured = _run_turn(
        session_factory, monkeypatch, qf=qf, text_body=text_body,
        msg_id=f"ZZT-supplier-span-{uuid.uuid4().hex[:10]}", attributes=list(attributes), real_resolver=True,
        capture_user_block=seen,
    )
    return ((result.reply or {}).get("text") or ""), captured, seen


def _staff_world(session_factory) -> dict[str, Any]:
    from tests.chatbot._turn_helpers import make_office_access_type

    ids = _seed_suppliers(session_factory)
    _seed_contact(session_factory, variables={})
    _make_staff(session_factory)
    make_office_access_type(session_factory, CONTACT_ID)
    return ids


@pytest.mark.parametrize(
    "text_body,span",
    [
        (OWNER_MESSAGE, list_resolver.Span(NATIVE, "supplier", meaning="Taiyang")),  # the owner's message
        (OWNER_MESSAGE, list_resolver.Span(NATIVE, "supplier")),  # no meaning: the native span itself
        ("outstanding for tai yang", list_resolver.Span("tai yang", "supplier")),  # spaced romanisation
        ("outstanding for Taiyang", list_resolver.Span("Taiyang", "supplier")),
        ("outstanding for Taiyan", list_resolver.Span("Taiyan", "supplier")),  # a typo
        ("ada PO pembekal 太阳 ke", list_resolver.Span(NATIVE, "supplier", meaning="Taiyang")),  # Malay / Chinese mix
    ],
)
def test_one_supplier_by_meaning_lists_its_open_pos(session_factory, monkeypatch, text_body, span):
    """The span list places the phrase on the supplier BY ITS SCORES (meaning here: the embedder double puts the
    phrase, its meaning and the supplier on one axis); the parser answers with the line's id; the id binds."""
    ids = _staff_world(session_factory)
    near = {span.text, span.meaning or span.text, SUPPLIER}
    reply, captured, seen = _span_turn(session_factory, monkeypatch, text_body, span, near)
    assert seen and ll.header("supplier") in seen[-1], "the parser was shown the Supplier candidates"
    assert f"[id: {ids['ours']}]" in seen[-1], seen[-1]
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["ours"]], (reply, captured)
    assert not [n for n, _ in captured if n == "crm_report_ask"], captured


def test_a_spaced_supplier_name_is_reached_by_meaning(session_factory, monkeypatch):
    """A record written "TAI YANG" (two words) is the supplier "太阳" means when the embedder says so: no join rule."""
    _staff_world(session_factory)
    spaced = _seed_named(session_factory, SPACED, "ZZTSUP-TY07")
    # The native span alone: only the embedder places it (the romanised "Taiyang" would also name the TAIYANG
    # record by its word, two close suppliers, which is a question, see the three-supplier test).
    span = list_resolver.Span(NATIVE, "supplier")
    _reply, captured, _seen = _span_turn(session_factory, monkeypatch, OWNER_MESSAGE, span, {NATIVE, SPACED})
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [spaced], captured


def test_a_single_clear_supplier_binds_without_a_question(session_factory, monkeypatch):
    ids = _staff_world(session_factory)
    span = list_resolver.Span("jinbai", "supplier")
    reply, captured, _seen = _span_turn(session_factory, monkeypatch, "outstanding PO for jinbai", span, {"jinbai", OTHER})
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["other"]], (reply, captured)


def test_three_equal_suppliers_ask_from_the_scores_and_a_pick_lists_that_one(session_factory, monkeypatch):
    """Console pass 2: "taiyang" placed three suppliers equally and the parser bound one. The id binds the whole
    runner-up group, so the turn asks; "1" then lists the supplier on line 1. The parser still picked ONE id."""
    ids = _staff_world(session_factory)
    twin = _seed_twin(session_factory)
    third = _seed_named(session_factory, THIRD, "ZZTSUP-TY03")
    names = {
        f"{SUPPLIER} (ZZTSUP-TY01)": ids["ours"], "ZZT TAIYANG SANITARY CO LTD (ZZTSUP-TY02)": twin,
        f"{THIRD} (ZZTSUP-TY03)": third,
    }
    span = list_resolver.Span("taiyang", "supplier")
    reply, captured, seen = _span_turn(
        session_factory, monkeypatch, "outstanding PO for taiyang", span,
        {"taiyang", SUPPLIER, "ZZT TAIYANG SANITARY CO LTD", THIRD},
    )
    assert not _po_calls(captured), f"no PO list before the pick: {captured}"
    listed = [ln for ln in reply.splitlines() if ln[:1].isdigit()]
    assert sorted(ln.split(". ", 1)[1] for ln in listed) == sorted(names), reply
    first = listed[0].split(". ", 1)[1]
    pick = _parser_output(
        message_type="answer", intent_hint=None, domain_hint=None, entities=[], reference_positions=[1],
    )
    _r, captured, _s = _span_turn(session_factory, monkeypatch, "1", list_resolver.Span("1"), set(), qf=pick)
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [names[first]], captured
    assert not [n for n, _ in captured if n == "crm_report_ask"], "never the customer outstanding report"



def test_a_span_typed_customer_is_scored_against_the_supplier_list_too(session_factory, monkeypatch):
    """Console pass 3 step 1: the span model typed 太阳 `customer` (meaning "Tai Yang"). The type is a tie-break, never
    a filter: the supplier rows are scored and, when the scores place the span there, the supplier binds."""
    ids = _staff_world(session_factory)
    span = list_resolver.Span(NATIVE, "customer", meaning="Tai Yang")
    reply, captured, seen = _span_turn(
        session_factory, monkeypatch, OWNER_MESSAGE, span, {NATIVE, "Tai Yang", SUPPLIER},
        qf=_ask(NATIVE, None, hint="supplier"),
    )
    assert f"[id: {ids['ours']}]" in seen[-1], seen[-1]
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["ours"]], (reply, captured)


def test_a_customer_typed_span_resolves_to_a_supplier_row_when_only_the_supplier_scores(session_factory):
    _seed_suppliers(session_factory)
    rows = ll.load_rows(scoped(session_factory), include_suppliers=True)
    embed = meaning_embed({"tai yang", SUPPLIER.casefold()})
    res = list_resolver.resolve([list_resolver.Span(NATIVE, "customer", meaning="Tai Yang")], rows, embed=embed)[0]
    assert res.status == "resolved" and res.candidates[0].row.list_name == "supplier", (
        res.status, [(c.row.list_name, c.row.label) for c in res.candidates]
    )


def test_two_suppliers_with_one_name_are_two_lines_each_with_its_code(session_factory, monkeypatch):
    """Console pass 3 note a: "CO.,LTD" and "CO., LTD." were two companies on two lines nobody could tell apart, and
    two suppliers with the very same name shared one line. Every supplier is its own line, named with its code."""
    ids = _staff_world(session_factory)
    same = _seed_named(session_factory, SUPPLIER, "ZZTSUP-TY09")
    span = list_resolver.Span("taiyang", "supplier")
    reply, captured, _seen = _span_turn(
        session_factory, monkeypatch, "outstanding PO for taiyang", span, {"taiyang", SUPPLIER}
    )
    lines = [ln.split(". ", 1)[1] for ln in reply.splitlines() if ln[:1].isdigit()]
    assert sorted(lines) == sorted([f"{SUPPLIER} (ZZTSUP-TY01)", f"{SUPPLIER} (ZZTSUP-TY09)"]), reply
    assert not _po_calls(captured), captured
    assert same != ids["ours"]



class _MeasuredGemini:
    """An embedder reproducing crew's floor measurement (dev copy, gemini-embedding-001, 1 Nov 2026): the three
    TAIYANG suppliers score 0.665-0.669 against "太阳" and 0.696-0.699 against "tai yang"; the closest real negative,
    "water closet", scores 0.628 against an unrelated supplier. Every other text is orthogonal."""

    model = "gemini-embedding-001"

    def __init__(self, taiyang: list[str], unrelated: str) -> None:
        import math

        self.dim = 4096
        self.fixed: dict[str, list[float]] = {}
        for name in taiyang:
            self.fixed[name.casefold()] = self._axis(0)
        self.fixed[unrelated.casefold()] = self._axis(1)
        for phrase, axis, cos in (("太阳", 0, 0.667), ("tai yang", 0, 0.698), ("water closet", 1, 0.628)):
            v = [0.0] * self.dim
            v[axis], v[2] = cos, math.sqrt(1 - cos * cos)
            self.fixed[phrase] = v

    def _axis(self, i: int) -> list[float]:
        v = [0.0] * self.dim
        v[i] = 1.0
        return v

    def __call__(self, texts):
        import hashlib

        out = []
        for t in texts:
            v = self.fixed.get(t.casefold().strip())
            if v is None:
                v = self._axis(3 + int(hashlib.md5(t.encode()).hexdigest(), 16) % (self.dim - 3))
            out.append(v)
        return out


def test_the_measured_gemini_supplier_floor_places_the_owner_word_and_keeps_the_negative_out(session_factory):
    """Crew's table: at 0.75 every TAIYANG name phrase missed (console pass 3 step 1); at 0.65, 太阳 and "tai yang" ask
    among the three TAIYANG suppliers and "water closet" (0.628) stays out."""
    _seed_suppliers(session_factory)
    _seed_twin(session_factory)
    _seed_named(session_factory, THIRD, "ZZTSUP-TY03")
    unrelated = _seed_named(session_factory, "ZZT CERAMIC SANITARYWARE CO", "ZZTSUP-CR01")
    rows = ll.load_rows(scoped(session_factory), include_suppliers=True)
    embed = _MeasuredGemini([SUPPLIER, "ZZT TAIYANG SANITARY CO LTD", THIRD], "ZZT CERAMIC SANITARYWARE CO")
    for span in (list_resolver.Span(NATIVE, "customer"), list_resolver.Span(NATIVE, "customer", meaning="Tai Yang")):
        res = list_resolver.resolve([span], rows, embed=embed)[0]
        suppliers = sorted(c.row.label for c in res.candidates if c.row.list_name == "supplier")
        assert res.status == "ambiguous" and suppliers == sorted([SUPPLIER, "ZZT TAIYANG SANITARY CO LTD", THIRD]), (
            span, res.status, [(c.row.label, round(c.score, 3)) for c in res.candidates]
        )
    negative = list_resolver.resolve([list_resolver.Span("water closet")], rows, embed=embed)[0]
    assert not any(c.row.key == unrelated for c in negative.candidates), negative


# --------------------------------------------------------------------------- #
# Fix round on PR #2066 (owner hand test, console turn 52faa07d, 2 Nov 2026): an office-access
# staff contact whose chatbot_profile.tier is NULL. Staff for suppliers is the office ACCESS
# TYPE + the reveal, the Supplier list's own rule (`engine._may_see_suppliers`); and a supplier
# the turn names but cannot bind stops the fetch, never an unfiltered list.
# --------------------------------------------------------------------------- #

SUPPLIER_REFUSAL = "isn't under your account"
ORDER_TOOLS = ("crm_report_ask", "crm_outstanding_report", "crm_orders_list")


def _office_world(session_factory) -> dict[str, Any]:
    """The owner's contact: office access type, tier NULL (no `_make_staff`)."""
    from tests.chatbot._turn_helpers import make_office_access_type

    ids = _seed_suppliers(session_factory)
    _seed_contact(session_factory, variables={})
    make_office_access_type(session_factory, CONTACT_ID)
    return ids


def _fetch_calls(captured) -> list[tuple[str, dict[str, Any]]]:
    return [(n, a) for n, a in captured if n == PO_TOOL or n in ORDER_TOOLS or n.startswith("crm_order")]


def test_a_tier_null_office_contact_sees_the_supplier_and_its_open_pos(session_factory, monkeypatch):
    ids = _office_world(session_factory)
    span = list_resolver.Span("jinbai", "supplier")
    reply, captured, seen = _span_turn(
        session_factory, monkeypatch, "outstanding PO for jinbai", span, {"jinbai", OTHER}
    )
    assert seen and ll.header("supplier") in seen[-1], "the Supplier list is shown (office access type + reveal)"
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["other"]], (reply, captured)


def test_a_tier_null_office_contact_gets_the_picker_for_three_equal_suppliers(session_factory, monkeypatch):
    """Console turn 52faa07d: 'taiyang' placed three suppliers; the turn must ask, never list every PO."""
    _office_world(session_factory)
    _seed_twin(session_factory)
    _seed_named(session_factory, THIRD, "ZZTSUP-TY03")
    span = list_resolver.Span("taiyang", "supplier")
    reply, captured, _seen = _span_turn(
        session_factory, monkeypatch, "outstanding PO for taiyang", span,
        {"taiyang", SUPPLIER, "ZZT TAIYANG SANITARY CO LTD", THIRD},
        qf=_ask("taiyang", None, domain="purchase_order"),
    )
    assert not _fetch_calls(captured), f"no list before the pick: {captured}"
    assert len([ln for ln in reply.splitlines() if ln[:1].isdigit()]) == 3, reply


def test_a_tier_null_office_contact_order_outstanding_for_a_supplier_reads_its_pos(session_factory, monkeypatch):
    """The order path: 'outstanding' flips the domain to order (`turn_runtime` order_status rule); the supplier
    ask still becomes that supplier's open POs, never every customer's orders."""
    ids = _office_world(session_factory)
    qf = {**_ask("jinbai", None), "order_status": "outstanding"}
    span = list_resolver.Span("jinbai", "supplier")
    reply, captured, _seen = _span_turn(
        session_factory, monkeypatch, "outstanding for jinbai", span, {"jinbai", OTHER}, qf=qf
    )
    assert not [n for n, _ in _fetch_calls(captured) if n != PO_TOOL], f"never a customer order list: {captured}"
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["other"]], (reply, captured)


@pytest.mark.parametrize("domain", ["purchase_order", "order"])
def test_a_supplier_the_asker_may_not_see_stops_the_fetch(session_factory, monkeypatch, domain):
    """Office access type, no supplier reveal: the supplier word is dropped, so the turn refuses; it never runs the
    PO or order fetch with no supplier filter."""
    _office_world(session_factory)
    qf = {**_ask("taiyang", None, domain=domain), **({"order_status": "outstanding"} if domain == "order" else {})}
    reply, captured = _turn(session_factory, monkeypatch, qf, "outstanding for taiyang", attributes=(PLACED,))
    assert not _fetch_calls(captured), f"no unfiltered list: {captured}"
    assert SUPPLIER_REFUSAL in reply, reply
    assert SUPPLIER not in reply, reply


@pytest.mark.parametrize("domain", ["purchase_order", "order"])
def test_a_dealer_naming_a_supplier_is_refused_not_listed(session_factory, monkeypatch, domain):
    _seed_suppliers(session_factory)
    _seed_contact(session_factory, variables={})
    qf = {**_ask("taiyang", None, domain=domain), **({"order_status": "outstanding"} if domain == "order" else {})}
    reply, captured = _turn(
        session_factory, monkeypatch, qf, "outstanding for taiyang", attributes=("sales_orders.outstanding", PLACED)
    )
    assert not _fetch_calls(captured), f"no unfiltered list: {captured}"
    assert SUPPLIER_REFUSAL in reply, reply
    assert SUPPLIER not in reply, reply


@pytest.mark.parametrize("domain", ["purchase_order", "order"])
def test_a_supplier_word_nothing_binds_stops_the_fetch(session_factory, monkeypatch, domain):
    """Office staff with the reveal name a supplier no row matches: no unfiltered PO or order list."""
    _office_world(session_factory)
    qf = {**_ask("zzqqxx", None, domain=domain), **({"order_status": "outstanding"} if domain == "order" else {})}
    reply, captured = _turn(session_factory, monkeypatch, qf, "outstanding for zzqqxx")
    assert not [a for n, a in _fetch_calls(captured) if not (n == PO_TOOL and a.get("supplier_ids"))], (
        reply, captured
    )
    assert 'couldn\'t find a supplier called "zzqqxx"' in reply, reply


def test_a_stray_supplier_hint_on_a_stock_ask_never_refuses_the_turn(session_factory, monkeypatch):
    """The stop is for the lists a supplier filters (purchase_order, order, sales); a dealer's stock ask that the
    parser also hinted a supplier on drops the word, as before, and is answered."""
    _seed_suppliers(session_factory)
    _seed_contact(session_factory, variables={})
    qf = _parser_output(
        domain_hint="inventory", intent_hint="check_stock", order_status=None,
        entities=[
            {"raw": "taiyang", "hint": "supplier", "canonical_code": None, "current_message": True, "confident": True},
            {"raw": "basin", "hint": "product", "canonical_code": None, "current_message": True, "confident": True},
        ],
    )
    reply, _captured = _turn(session_factory, monkeypatch, qf, "stock basin taiyang", attributes=("sales_orders.outstanding",))
    assert SUPPLIER_REFUSAL not in reply, reply


# --------------------------------------------------------------------------- #
# Fix round 3 on PR #2066 (owner hand test on e93e1bb6, contact with no tier and an office access type).
# --------------------------------------------------------------------------- #


def _three_taiyang(session_factory, monkeypatch, text_body: str = "outstanding PO for taiyang", qf=None):
    ids = _office_world(session_factory)
    twin = _seed_twin(session_factory)
    third = _seed_named(session_factory, THIRD, "ZZTSUP-TY03")
    span = list_resolver.Span("taiyang", "supplier")
    reply, captured, _seen = _span_turn(
        session_factory, monkeypatch, text_body, span,
        {"taiyang", SUPPLIER, "ZZT TAIYANG SANITARY CO LTD", THIRD}, qf=qf,
    )
    assert not _po_calls(captured), f"no PO list before the pick: {captured}"
    return reply, {ids["ours"], twin, third}


@pytest.mark.parametrize("answer,positions", [("all", [1, 2, 3]), ("1 and 3", [1, 3]), ("everything", [1, 2, 3])])
def test_a_pick_of_several_suppliers_lists_every_picked_one(session_factory, monkeypatch, answer, positions):
    """Owner turn 3: 'all' over the three-supplier question listed ONE supplier. Every picked line is a supplier
    of the PO list."""
    reply, three = _three_taiyang(session_factory, monkeypatch)
    listed = {int(ln.split(". ", 1)[0]): ln.split(". ", 1)[1] for ln in reply.splitlines() if ln[:1].isdigit()}
    pick = _parser_output(
        message_type="answer", intent_hint=None, domain_hint=None, entities=[], reference_positions=positions,
    )
    _r, captured, _s = _span_turn(session_factory, monkeypatch, answer, list_resolver.Span(answer), set(), qf=pick)
    calls = _po_calls(captured)
    assert calls, (_r, captured)
    got = set(calls[0].get("supplier_ids") or [])
    assert len(got) == len(positions) and got <= three, (listed, calls[0].get("supplier_ids"), _r)


def test_the_owner_all_over_the_supplier_question_lists_all_three_and_names_each_in_the_header(
    session_factory, monkeypatch
):
    """Owner turn 3 (87fc44fc), v194's real emission for 'all': positions 1-3, `broaden_axis` supplier. The PO list
    carries all three suppliers, and the reply names each one with its code: two suppliers sharing one trading name
    are not merged into one name (`turn/compose` grouped them by the customer-account rule)."""
    _office_world(session_factory)
    twin_same = _seed_named(session_factory, SUPPLIER, "ZZTSUP-TY09")
    third = _seed_named(session_factory, THIRD, "ZZTSUP-TY03")
    span = list_resolver.Span("taiyang", "supplier")
    reply, captured, _seen = _span_turn(
        session_factory, monkeypatch, "outstanding PO for taiyang", span, {"taiyang", SUPPLIER, THIRD},
    )
    assert not _po_calls(captured), captured
    pick = _parser_output(
        message_type="answer", intent_hint="check_po", domain_hint="purchase_order", order_status="outstanding",
        entities=[], reference_positions=[1, 2, 3], broaden_axis="supplier", broaden_to="all",
        scope_intent="broaden", entity_op="reuse",
    )
    reply, captured, _s = _span_turn(session_factory, monkeypatch, "all", list_resolver.Span("all"), set(), qf=pick)
    calls = _po_calls(captured)
    assert calls and len(set(calls[0].get("supplier_ids") or [])) == 3, (reply, captured)


def _supplier_entity(name: str, code: str) -> dict[str, Any]:
    return {"entity_type": "supplier", "uuid": str(uuid.uuid4()), "canonical_code": f"{name} ({code})"}


def test_the_envelope_names_its_supplier_subjects_with_their_codes():
    from app.services.chatbot.turn.plan import FetchSpec
    from app.services.chatbot.turn_runtime import envelope_of

    entities = [
        {"entity_type": "product", "uuid": str(uuid.uuid4()), "canonical_code": "SRTW2600"},
        _supplier_entity(SUPPLIER, "400-X006"), _supplier_entity(SUPPLIER, "400-X008"),
    ]
    env = envelope_of(
        {"fetch": {"has_result": False}}, FetchSpec(domain="purchase_order", entities=[], filters={}, date_window=None),
        entities,
    )
    assert env["supplier_subjects"] == [f"{SUPPLIER} (400-X006)", f"{SUPPLIER} (400-X008)"], env
    # The section header reads the envelope as the composer does: every supplier whole, with its code.
    from types import SimpleNamespace

    from app.services.chatbot.turn.compose import _section_subjects

    assert _section_subjects(env, SimpleNamespace(focus=None)) == [
        "SRTW2600", f"{SUPPLIER} (400-X006)", f"{SUPPLIER} (400-X008)"
    ]


def test_the_header_keeps_two_suppliers_of_one_trading_name_apart_with_their_codes():
    """Owner turn 3 (87fc44fc): the header read 'SRTW2600, XIAMEN TAIYANG TECHNOLOGY CO.,LTD' for three suppliers: the
    customer-account rule folded two records of one name and dropped every code. A customer still folds."""
    from app.services.chatbot.turn.compose import _header_subjects

    a, b, c = f"{SUPPLIER} (400-X006)", f"{SUPPLIER} (400-X008)", "ZZT TAIYANG TECHNOLOGY CO., LTD. (400-X001)"
    assert _header_subjects(["SRTW2600", a, b, c], whole=[a, b, c]) == ["SRTW2600", a, b, c]
    ledgers = ["ZZT HARDWARE SDN BHD - [A/C I]", "ZZT HARDWARE SDN BHD - [A/C II]"]
    assert len(_header_subjects(ledgers, whole=[a])) == 1


def test_the_owner_supplier_ask_with_a_product_and_a_year_stays_on_purchase_orders(session_factory, monkeypatch):
    """Owner turn 4 (d1bdf144), v194's real emission: the span pass typed 太阳 `customer` and placed it on the three
    supplier rows; the parser returned the product alone, status outstanding, 2026. The supplier is not lost: the
    turn asks which supplier (never the order clarifier 'Undelivered orders or pending delivery?')."""
    from app.services.chatbot.lanes.business import report_ask

    _office_world(session_factory)
    _seed_twin(session_factory)
    _seed_named(session_factory, THIRD, "ZZTSUP-TY03")
    qf = _parser_output(
        domain_hint="purchase_order", intent_hint="check_po", order_status="outstanding", status="outstanding",
        date_filter_start="2026-01-01", date_filter_end="2026-12-31",
        entities=[{"raw": "SRTW2600", "hint": "product", "canonical_code": None, "current_message": True, "confident": True}],
    )
    span = list_resolver.Span(NATIVE, "customer")
    reply, captured, _seen = _span_turn(
        session_factory, monkeypatch, "outstaing for 太阳 for SRTW2600 in 2026", span,
        {NATIVE, SUPPLIER, "ZZT TAIYANG SANITARY CO LTD", THIRD}, qf=qf,
    )
    assert report_ask.KIND_QUESTION not in reply, reply
    assert not _fetch_calls(captured), f"no unfiltered list: {captured}"
    assert len([ln for ln in reply.splitlines() if ln[:1].isdigit()]) == 3, reply


def test_a_span_that_also_scores_a_customer_is_not_made_a_supplier():
    from app.services.chatbot import engine as engine_mod

    def _res(*lists):
        import types

        return types.SimpleNamespace(
            status="ambiguous", matched_by="text", span=list_resolver.Span("zz"),
            candidates=[types.SimpleNamespace(row=types.SimpleNamespace(list_name=n, key=f"k{i}")) for i, n in enumerate(lists)],
        )

    assert engine_mod._supplier_spans([_res("supplier", "supplier")]) == {"zz": "k0"}
    assert engine_mod._supplier_spans([_res("supplier", "customer")]) == {}


def test_the_po_list_date_line_names_the_expected_date():
    """Owner turn 3: the PO list filters the expected date, and its line read 订单日期 (Order date)."""
    from app.services.chatbot import turn_runtime

    window = {"date_filter_start": "2026-01-01", "date_filter_end": None}
    assert turn_runtime._date_line(window, PO_TOOL) == "Expected date: 01/01/2026"
    assert turn_runtime._date_line(window, "crm_outstanding_report") == "Order date: 01/01/2026"


def test_a_parser_without_the_supplier_id_line_never_turns_a_span_into_a_supplier(session_factory, monkeypatch):
    """Review round 3 (B1): a parser version that runs the span pass but lacks the supplier id line binds no supplier by
    id, so a span on suppliers adds none (it would only be refused as not found)."""
    _office_world(session_factory)
    qf = _parser_output(
        domain_hint="purchase_order", intent_hint="check_po", order_status="outstanding",
        entities=[{"raw": "SRTW2600", "hint": "product", "canonical_code": None, "current_message": True, "confident": True}],
    )
    span = list_resolver.Span(NATIVE, "customer")
    reply, _captured, _seen = _span_turn(
        session_factory, monkeypatch, "outstaing for 太阳 for SRTW2600", span, {NATIVE, SUPPLIER}, qf=qf,
        supplier_ids=False,
    )
    assert "couldn't find a supplier" not in reply, reply


def test_a_supplier_the_parser_already_bound_by_id_is_not_added_twice():
    import types

    from app.services.chatbot import engine as engine_mod

    prep = types.SimpleNamespace(supplier_spans={"太阳": "id-1"}, supplier_groups={"id-1": [("id-1", "A (X1)")]})
    verdict = {"entities": [{"raw": "Taiyang", "hint": "supplier", "canonical_code": "id-1", "current_message": True}]}
    assert engine_mod._with_span_suppliers(verdict, prep) is verdict


def test_a_counted_header_still_names_every_supplier():
    """Fix round 4 (crew console pass, 'extra' step 4): the PO header read '未找到 7 items 的 PO。' with no supplier named."""
    from app.services.chatbot.turn.compose import HEADER_SUBJECT_MAX, _header_codes

    a, b = f"{SUPPLIER} (400-X006)", f"{SUPPLIER} (400-X008)"
    products = [f"SRTW26{i:02d}" for i in range(HEADER_SUBJECT_MAX)]
    env = {"domain": "purchase_order", "supplier_subjects": [a, b]}
    assert _header_codes([*products, a, b], env) == f"{HEADER_SUBJECT_MAX} items, {a}, {b}"
    assert _header_codes(["SRTW2600", a], env) == f"SRTW2600, {a}"
    assert _header_codes(products + ["SRTW2699"], {"domain": "inventory"}) == f"{HEADER_SUBJECT_MAX + 1} products"


@pytest.mark.parametrize("hint,canonical", [("customer", None), ("supplier", None), ("supplier", "太阳")])
def test_the_owner_turn_1_misreads_still_ask_which_supplier(session_factory, monkeypatch, hint, canonical):
    """Fix round 4 (crew sweep: owner turn 1 x5 on v194, 2 of 5 asked): the parser named 太阳 as a CUSTOMER under the
    order/sales report, or as a supplier with no row id, though the span list placed 太阳 on the three supplier rows
    alone. The scores decide: the turn asks which supplier, never the order kind question or 'couldn't find'."""
    from app.services.chatbot.lanes.business import report_ask

    _office_world(session_factory)
    _seed_twin(session_factory)
    _seed_named(session_factory, THIRD, "ZZTSUP-TY03")
    qf = _parser_output(
        domain_hint="sales" if hint == "customer" else "purchase_order",
        intent_hint="check_sales" if hint == "customer" else "check_po",
        order_status="outstanding", status="outstanding", date_filter_start="2026-01-01",
        entities=[
            {"raw": "SRTW2600", "hint": "product", "canonical_code": None, "current_message": True, "confident": True},
            {"raw": NATIVE, "hint": hint, "canonical_code": canonical, "current_message": True, "confident": True},
        ],
    )
    span = list_resolver.Span(NATIVE, "supplier", meaning="Taiyang")
    reply, captured, _seen = _span_turn(
        session_factory, monkeypatch, "outstaing for 太阳 for SRTW2600 after 2025", span,
        {NATIVE, "Taiyang", SUPPLIER, "ZZT TAIYANG SANITARY CO LTD", THIRD}, qf=qf,
    )
    assert report_ask.KIND_QUESTION not in reply and "couldn't find a supplier" not in reply, reply
    assert not _fetch_calls(captured), f"no list before the pick: {captured}"
    assert len([ln for ln in reply.splitlines() if ln[:1].isdigit()]) == 3, reply


def test_both_over_three_suppliers_asks_again_and_lists_nothing(session_factory, monkeypatch):
    """Fix round 4 (crew sweep 'both-over-three'): 'both' names two options; over three it picks none of them, so the
    question stays open. v194 read it as every position and listed all three."""
    reply, _three = _three_taiyang(session_factory, monkeypatch)
    pick = _parser_output(
        message_type="answer", intent_hint=None, domain_hint=None, entities=[], reference_positions=[1, 2, 3],
    )
    again, captured, _s = _span_turn(session_factory, monkeypatch, "both", list_resolver.Span("both"), set(), qf=pick)
    assert not _po_calls(captured), (again, captured)
    assert len([ln for ln in again.splitlines() if ln[:1].isdigit()]) == 3, again
    one = _parser_output(message_type="answer", intent_hint=None, domain_hint=None, entities=[], reference_positions=[1])
    _r, captured, _s = _span_turn(session_factory, monkeypatch, "1", list_resolver.Span("1"), set(), qf=one)
    calls = _po_calls(captured)
    assert calls and len(calls[0].get("supplier_ids") or []) == 1, (_r, captured)


def test_a_non_answer_over_the_supplier_question_never_lists_without_a_supplier(session_factory, monkeypatch):
    """Round 3's hole: an aside over the open supplier question ran the PO list with the held, unsettled supplier
    word skipped (no `supplier_ids`). The question is asked again instead."""
    _three_taiyang(session_factory, monkeypatch)
    aside = _parser_output(
        message_type="business_query", intent_hint="check_po", domain_hint="purchase_order", entities=[],
        broaden_axis="all", broaden_to="all",
    )
    again, captured, _s = _span_turn(session_factory, monkeypatch, "all", list_resolver.Span("all"), set(), qf=aside)
    assert not [a for a in _po_calls(captured) if not a.get("supplier_ids")], (again, captured)


def _prep(spans: dict[str, str], groups: dict[str, list]):
    import types

    return types.SimpleNamespace(supplier_spans=spans, supplier_groups=groups)


@pytest.mark.parametrize("canonical", [None, "太阳", "not-an-id"])
def test_a_supplier_named_without_its_row_id_gets_the_span_id(canonical):
    """Review round 4 (B1): crew's 1 of 5 'couldn't find a supplier called 太阳': the parser hinted supplier with no
    row id. The span's best row id is put on it."""
    from app.services.chatbot import engine as engine_mod

    verdict = {"entities": [{"raw": "太阳", "hint": "supplier", "canonical_code": canonical, "current_message": True}]}
    out = engine_mod._with_span_suppliers(verdict, _prep({"太阳": "id-1"}, {"id-1": [("id-1", "A (X1)")]}))
    assert out["entities"] == [{"raw": "太阳", "hint": "supplier", "canonical_code": "id-1", "current_message": True}]


def test_a_supplier_already_carrying_a_grouped_id_is_kept_as_the_parser_picked_it():
    """Review round 4 (B2): the parser picked the second, near-tied supplier of the span's group; its pick stands."""
    from app.services.chatbot import engine as engine_mod

    groups = {"id-1": [("id-1", "A (X1)"), ("id-2", "A (X2)")], "id-2": [("id-1", "A (X1)"), ("id-2", "A (X2)")]}
    verdict = {"entities": [{"raw": "太阳", "hint": "supplier", "canonical_code": "id-2", "current_message": True}]}
    assert engine_mod._with_span_suppliers(verdict, _prep({"太阳": "id-1"}, groups)) is verdict


def test_a_name_that_is_also_a_customer_is_not_supplier_only_without_its_type():
    """Review round 4 (S4): the span model's type narrows the pool; a name shared by a customer and a supplier, typed
    `supplier`, reads supplier-only. Re-resolved with no type it scores both, so the parser's customer reading stands."""
    import types

    from app.services.chatbot import engine as engine_mod

    def _res(*lists):
        return types.SimpleNamespace(
            status="ambiguous", matched_by="text", span=list_resolver.Span("zz", "supplier"),
            candidates=[types.SimpleNamespace(row=types.SimpleNamespace(list_name=n, key=f"k{i}")) for i, n in enumerate(lists)],
        )

    typed = [_res("supplier")]
    assert engine_mod._supplier_spans(typed, untyped=lambda span: _res("customer", "supplier")) == {}
    assert engine_mod._supplier_spans(typed, untyped=lambda span: _res("supplier")) == {"zz": "k0"}


def test_a_follow_up_after_the_supplier_was_picked_is_not_asked_which_supplier_again(session_factory, monkeypatch):
    """Review round 4 (S3): the supplier roster stays open after its pick; a follow-up never re-asks it."""
    _three_taiyang(session_factory, monkeypatch)
    one = _parser_output(message_type="answer", intent_hint=None, domain_hint=None, entities=[], reference_positions=[1])
    _r, captured, _s = _span_turn(session_factory, monkeypatch, "1", list_resolver.Span("1"), set(), qf=one)
    assert _po_calls(captured), captured
    more = _parser_output(
        message_type="business_query", intent_hint="check_po", domain_hint="purchase_order", entities=[],
        date_filter_start="2026-03-01", date_filter_end="2026-03-31", entity_op="reuse",
    )
    reply, _c, _s = _span_turn(
        session_factory, monkeypatch, "and in March 2026?", list_resolver.Span("March 2026"), set(), qf=more
    )
    assert "Which one do you mean?" not in reply, reply


# --------------------------------------------------------------------------- #
# Fix round 5 (crew sweep at e1c37978, 48/50): a supplier code typed as a product code; 太阳 read as "Sun".
# --------------------------------------------------------------------------- #


def _sup_row(key: str, name: str, code: str):
    return ll.LookupRow("supplier", key, name, (name, code), homes=("label", "code"))


def test_a_code_span_that_is_a_suppliers_own_code_resolves_to_that_supplier():
    """Crew 'code-direct': "outstanding PO for 400-X008" - the span pass typed the code `product_code`, which the span
    list skips, so the supplier was never placed and the turn went to the order report."""
    rows = [_sup_row("s1", SUPPLIER, "400-X008"), _sup_row("s2", OTHER, "400-X001")]
    res = list_resolver.resolve([list_resolver.Span("400-X008", "product_code")], rows)[0]
    assert res.status == "resolved" and res.candidates[0].row.key == "s1", res
    assert list_resolver.resolve([list_resolver.Span("SRTW2600", "product_code")], rows)[0].status == "skipped"


def test_a_supplier_code_the_parser_hinted_as_a_product_reads_the_po_book(session_factory, monkeypatch):
    ids = _office_world(session_factory)
    qf = _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="outstanding", status="outstanding",
        entities=[{"raw": "ZZTSUP-JB02", "hint": "product", "canonical_code": None, "current_message": True, "confident": True}],
    )
    span = list_resolver.Span("ZZTSUP-JB02", "product_code")
    reply, captured, _seen = _span_turn(session_factory, monkeypatch, "outstanding PO for ZZTSUP-JB02", span, set(), qf=qf)
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["other"]], (reply, captured)


def test_a_span_read_by_a_wrong_meaning_still_shows_its_own_text_reading():
    """Crew 'owner-turn1-repeat-1': 太阳 typed brand, meaning "Sun", placed on Sun* rows; its own text scores the
    TAIYANG suppliers. Both readings reach the blocks; the supplier-only reading is a supplier span."""
    from app.services.chatbot import engine as engine_mod

    rows = [
        ll.LookupRow("brand", "b1", "SUN LIGHT", ("SUN LIGHT",), homes=("label",)),
        _sup_row("s1", SUPPLIER, "400-X006"), _sup_row("s2", THIRD, "400-X001"),
    ]
    embed = meaning_embed({NATIVE, SUPPLIER.casefold(), THIRD.casefold()})
    spans = [list_resolver.Span(NATIVE, "brand", meaning="Sun")]
    resolutions = list_resolver.resolve(spans, rows, embed=embed)
    assert resolutions[0].matched_by == "meaning" and resolutions[0].candidates[0].row.list_name == "brand"
    readings = list_resolver.text_readings(spans, resolutions, rows, embed=embed)
    assert {c.row.key for r in readings for c in r.candidates} == {"s1", "s2"}, readings
    spans_found = engine_mod._supplier_spans([*resolutions, *readings])
    assert set(spans_found) == {NATIVE}
    kinds = engine_mod._span_kinds([*resolutions, *readings])
    assert kinds[NATIVE] == frozenset({"supplier"}), "the gloss found as a word inside a brand name backs no hint"


@pytest.mark.parametrize("hint,expect", [("customer", "supplier"), ("brand", "brand")])
def test_a_hint_no_reading_backs_becomes_the_supplier_and_a_backed_hint_stands(hint, expect):
    import types

    from app.services.chatbot import engine as engine_mod

    prep = types.SimpleNamespace(
        supplier_spans={NATIVE: "s1"}, supplier_groups={"s1": [("s1", "A (X1)")]},
        span_kinds={NATIVE: frozenset({"brand", "supplier"})},
    )
    verdict = {"entities": [{"raw": NATIVE, "hint": hint, "canonical_code": None, "current_message": True}]}
    out = engine_mod._with_span_suppliers(verdict, prep)
    assert out["entities"][0]["hint"] == expect


def test_the_crew_sun_trace_asks_which_taiyang_supplier():
    """Crew trace 393eff8d: 太阳 typed brand, meaning "Sun"; "Sun" matched as a word inside SUN-named customers and one
    SUN supplier (partial 1.0); the parser hinted 太阳 customer. 太阳's own text scores the TAIYANG suppliers alone, and a
    gloss found only as a word inside longer names backs no hint, so 太阳 is the supplier with a TAIYANG id."""
    from app.services.chatbot import engine as engine_mod

    rows = [
        ll.LookupRow("customer", "c1", "ZZT SUN CREST TRANSPORT SDN BHD", ("ZZT SUN CREST TRANSPORT SDN BHD",), homes=("label",)),
        ll.LookupRow("customer", "c2", "ZZT CHONG SUN FAT HARDWARE", ("ZZT CHONG SUN FAT HARDWARE",), homes=("label",)),
        _sup_row("s9", "ZZT SUN CREST TRANSPORT SDN BHD", "400-S009"),
        _sup_row("s1", SUPPLIER, "400-X006"), _sup_row("s2", THIRD, "400-X001"),
    ]
    embed = meaning_embed({NATIVE, SUPPLIER.casefold(), THIRD.casefold()})
    spans = [list_resolver.Span(NATIVE, "brand", meaning="Sun")]
    resolutions = list_resolver.resolve(spans, rows, embed=embed)
    assert resolutions[0].matched_by == "meaning" and {c.signal for c in resolutions[0].candidates} == {"partial"}
    readings = list_resolver.text_readings(spans, resolutions, rows, embed=embed)
    import types

    prep = types.SimpleNamespace(
        supplier_spans=engine_mod._supplier_spans([*resolutions, *readings]),
        supplier_groups=engine_mod._supplier_groups([*resolutions, *readings]),
        span_kinds=engine_mod._span_kinds([*resolutions, *readings]),
    )
    verdict = {"entities": [{"raw": NATIVE, "hint": "customer", "canonical_code": None, "current_message": True}]}
    entity = engine_mod._with_span_suppliers(verdict, prep)["entities"][0]
    assert entity["hint"] == "supplier" and entity["canonical_code"] in {"s1", "s2"}, entity
    assert {k for k, _n in prep.supplier_groups[entity["canonical_code"]]} == {"s1", "s2"}


# --------------------------------------------------------------------------- #
# Fix round 6 (owner hand test, 2 Nov ~21:58): the RESOLVED party decides the side. "Outstandinf for orionis" listed
# purchase orders though Orionis is a customer; a customer is the sales side, a supplier the purchase side, a name on
# both sides (or none) is asked.
# --------------------------------------------------------------------------- #

ORIONIS = "ZZT ORIONIS TECHNOLOGY (M) SDN BHD"


def _seed_customer(session_factory, name: str) -> str:
    from app.models.order import Customer

    db = session_factory()
    row = Customer(id=str(uuid.uuid4()), customer_code=f"ZZT-C-{uuid.uuid4().hex[:6]}", customer_name=name,
                   company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.commit()
    return row.id


def _orionis_turn(session_factory, monkeypatch, hint: str, canonical: str | None, text: str = "Outstandinf for orionis"):
    qf = _parser_output(
        domain_hint="purchase_order" if hint == "supplier" else "order",
        intent_hint="check_po" if hint == "supplier" else "check_order",
        order_status="outstanding", status="outstanding",
        entities=[{"raw": "orionis", "hint": hint, "canonical_code": canonical, "current_message": True, "confident": True}],
    )
    span = list_resolver.Span("orionis", "customer")
    return _span_turn(session_factory, monkeypatch, text, span, {"orionis", ORIONIS.casefold()}, qf=qf)


def test_a_name_on_both_sides_is_asked_customer_or_supplier(session_factory, monkeypatch):
    """The owner's repro shape: 'orionis' names a customer AND a supplier of the same name; the parser bound the
    supplier. Neither side is assumed: the turn asks which, and lists nothing."""
    _office_world(session_factory)
    _seed_customer(session_factory, ORIONIS)
    sup = _seed_named(session_factory, ORIONIS, "ZZTSUP-OR01")
    reply, captured, _seen = _orionis_turn(session_factory, monkeypatch, "supplier", sup)
    assert not _fetch_calls(captured), (reply, captured)
    assert "(customer)" in reply and "(supplier)" in reply, reply


def test_a_customer_only_name_reads_the_sales_side_even_when_the_parser_said_supplier(session_factory, monkeypatch):
    """Orionis a customer only: the outstanding ask is the sales side (the outstanding report and its kind question),
    never purchase orders and never 'couldn't find a supplier'."""
    from app.services.chatbot.lanes.business import report_ask

    _office_world(session_factory)
    _seed_customer(session_factory, ORIONIS)
    reply, captured, _seen = _orionis_turn(session_factory, monkeypatch, "supplier", None)
    assert not _po_calls(captured), (reply, captured)
    assert "couldn't find a supplier" not in reply and "purchase order" not in reply.lower(), reply
    assert report_ask.KIND_QUESTION in reply or [n for n, _ in captured if n in ORDER_TOOLS], (reply, captured)


def test_a_supplier_only_name_reads_the_purchase_side_even_when_the_parser_said_customer(session_factory, monkeypatch):
    ids = _office_world(session_factory)
    qf = _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="outstanding", status="outstanding",
        entities=[{"raw": "jinbai", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}],
    )
    span = list_resolver.Span("jinbai", "customer")
    reply, captured, _seen = _span_turn(session_factory, monkeypatch, "outstanding for jinbai", span, {"jinbai", OTHER}, qf=qf)
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["other"]], (reply, captured)


@pytest.mark.parametrize("kinds,domain,expect", [
    ({"supplier"}, "order", "purchase_order"), ({"supplier"}, "sales", "purchase_order"),
    ({"customer"}, "purchase_order", "order"), ({"customer", "supplier"}, "order", None),
    (set(), "order", None), ({"customer"}, "order", None), ({"supplier"}, "inventory", None),
])
def test_the_resolved_party_decides_the_side(kinds, domain, expect):
    from app.services.chatbot.turn.apply import _side_of_the_parties

    entities = [{"raw": k, "hint": k, "current_message": True} for k in kinds]
    assert _side_of_the_parties(entities, {"domain_hint": domain}) == expect


@pytest.mark.parametrize("side", ["customer", "supplier"])
def test_the_owner_orionis_turn_after_a_supplier_thread_asks_and_the_pick_decides_the_side(
    session_factory, monkeypatch, side
):
    """Owner hand test 2 Nov (turn 67b179ee), after a PO thread for another supplier: the span pass typed 'orionis'
    product_code (skipped), the parser carried the PO subject and hinted supplier with no id. 'orionis' names a
    customer AND a supplier, so the turn asks which; the customer pick is the sales side (never a PO list), the
    supplier pick lists that supplier's POs."""
    from app.services.chatbot.lanes.business import report_ask

    ids = _office_world(session_factory)
    customer = _seed_customer(session_factory, f"{ORIONIS} (PROJECT)")
    sup = _seed_named(session_factory, ORIONIS, "ZZTSUP-OR01")
    _r, captured, _s = _span_turn(
        session_factory, monkeypatch, "outstanding PO for jinbai", list_resolver.Span("jinbai", "supplier"),
        {"jinbai", OTHER},
    )
    assert _po_calls(captured) and _po_calls(captured)[0].get("supplier_ids") == [ids["other"]]
    owner = _parser_output(
        domain_hint="purchase_order", intent_hint="check_po", order_status="outstanding", status="outstanding",
        document=["PO"], entity_op="replace_combine",
        entities=[{"raw": "orionis", "hint": "supplier", "canonical_code": None, "current_message": True, "confident": True}],
    )
    reply, captured, _s = _span_turn(
        session_factory, monkeypatch, "Outstandinf for orionis", list_resolver.Span("orionis", "product_code"), set(),
        qf=owner,
    )
    assert not _fetch_calls(captured), (reply, captured)
    lines = {ln.split(". ", 1)[1]: int(ln.split(". ", 1)[0]) for ln in reply.splitlines() if ln[:1].isdigit() and ". " in ln}
    position = next(p for label, p in lines.items() if f"({side})" in label)
    pick = _parser_output(
        message_type="answer", intent_hint=None, domain_hint=None, entities=[], reference_positions=[position],
    )
    reply, captured, _s = _span_turn(session_factory, monkeypatch, str(position), list_resolver.Span(str(position)), set(), qf=pick)
    if side == "supplier":
        calls = _po_calls(captured)
        assert calls and calls[0].get("supplier_ids") == [sup], (reply, captured)
    else:
        assert not _po_calls(captured), (reply, captured)
        assert report_ask.KIND_QUESTION in reply or [a for n, a in captured if n in ORDER_TOOLS], (reply, captured)
        assert customer


def test_a_word_the_resolver_retyped_to_a_supplier_moves_the_ask_to_the_purchase_side(session_factory, monkeypatch):
    """Crew trace 1b3b877b: the resolver's reconciliation retyped '400-X008' product -> supplier, and the ask stayed on
    the order side (no PO list). With no span reading at all, the reconciled kind alone decides the side."""
    ids = _office_world(session_factory)
    qf = _parser_output(
        domain_hint="purchase_order", intent_hint="check_po", order_status=None, status="outstanding", document=["PO"],
        entities=[{"raw": "ZZTSUP-JB02", "hint": "product", "canonical_code": None, "current_message": True, "confident": True}],
    )
    reply, captured, _seen = _span_turn(
        session_factory, monkeypatch, "outstanding PO for ZZTSUP-JB02", list_resolver.Span("for", "brand"), set(), qf=qf,
    )
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["other"]], (reply, captured)



# Review of rounds 5-6.


@pytest.mark.parametrize("hint", ["customer", "supplier"])
def test_an_exact_supplier_name_inside_a_longer_customer_name_is_still_asked(session_factory, monkeypatch, hint):
    """B1: 'ah hock' IS the supplier AH HOCK and sits inside the customer AH HOCK HARDWARE; the untyped read alone keeps
    only the exact row. Both names are the word's: asked, never assigned to one side (S1: whatever the parser's hint)."""
    _office_world(session_factory)
    _seed_customer(session_factory, "ZZT AH HOCK HARDWARE SDN BHD")
    _seed_named(session_factory, "ZZT AH HOCK", "ZZTSUP-AH01")
    qf = _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="outstanding", status="outstanding",
        entities=[{"raw": "zzt ah hock", "hint": hint, "canonical_code": None, "current_message": True, "confident": True}],
    )
    reply, captured, _seen = _span_turn(
        session_factory, monkeypatch, "outstanding for zzt ah hock", list_resolver.Span("zzt ah hock", "customer"),
        set(), qf=qf,
    )
    assert not _fetch_calls(captured), (reply, captured)
    assert "(customer)" in reply and "(supplier)" in reply, reply


def test_the_customer_pick_reaches_the_report_with_that_customer(session_factory, monkeypatch):
    """S4: the 'customer' pick over the orionis question settles THAT customer: the report ask that follows filters
    by its id."""
    _office_world(session_factory)
    customer = _seed_customer(session_factory, f"{ORIONIS} (PROJECT)")
    _seed_named(session_factory, ORIONIS, "ZZTSUP-OR01")
    owner = _parser_output(
        domain_hint="purchase_order", intent_hint="check_po", order_status="outstanding", status="outstanding",
        entities=[{"raw": "orionis", "hint": "supplier", "canonical_code": None, "current_message": True, "confident": True}],
    )
    reply, _c, _s = _span_turn(
        session_factory, monkeypatch, "Outstandinf for orionis", list_resolver.Span("orionis", "product_code"), set(),
        qf=owner,
    )
    position = next(int(ln.split(". ", 1)[0]) for ln in reply.splitlines() if "(customer)" in ln)
    pick = _parser_output(message_type="answer", intent_hint=None, domain_hint=None, entities=[], reference_positions=[position])
    reply, captured, _s = _span_turn(session_factory, monkeypatch, str(position), list_resolver.Span(str(position)), set(), qf=pick)
    basis = _parser_output(
        message_type="answer", intent_hint="check_order", domain_hint="order", order_status="outstanding",
        basis="pending_delivery", entities=[], reference_positions=[2],
    )
    if report_kind_asked := ("Undelivered orders or pending delivery?" in reply):
        reply, captured, _s = _span_turn(
            session_factory, monkeypatch, "Pending delivery", list_resolver.Span("Pending delivery"), set(), qf=basis,
        )
    asks = [a for n, a in captured if n in ORDER_TOOLS]
    assert asks and customer in (asks[0].get("customer_ids") or []), (report_kind_asked, reply, captured)


def test_a_meaning_placed_span_reaches_the_supplier_by_its_own_text_in_a_turn(session_factory, monkeypatch):
    """S4: the text reading is wired into the turn: 太阳 glossed "Sun" (a SUN-named customer matches the gloss as a word)
    still asks which TAIYANG supplier."""
    from app.services.chatbot.lanes.business import report_ask

    _office_world(session_factory)
    _seed_twin(session_factory)
    _seed_customer(session_factory, "ZZT SUN CREST TRANSPORT SDN BHD")
    qf = _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="outstanding", status="outstanding",
        entities=[{"raw": NATIVE, "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}],
    )
    span = list_resolver.Span(NATIVE, "brand", meaning="Sun")
    reply, captured, seen = _span_turn(
        session_factory, monkeypatch, "outstanding for 太阳", span, {NATIVE, SUPPLIER, "ZZT TAIYANG SANITARY CO LTD"}, qf=qf,
    )
    assert ll.header("supplier") in seen[-1], seen[-1]
    assert report_ask.KIND_QUESTION not in reply and not _fetch_calls(captured), (reply, captured)
    assert len([ln for ln in reply.splitlines() if ln[:1].isdigit()]) == 2, reply


def test_a_both_sides_word_naming_two_suppliers_never_binds_only_one(session_factory, monkeypatch):
    """Re-review B-new: two suppliers named ORIONIS and one customer; the supplier pick lists both suppliers (or asks
    which), never only the first."""
    _office_world(session_factory)
    _seed_customer(session_factory, f"{ORIONIS} (PROJECT)")
    s1 = _seed_named(session_factory, ORIONIS, "ZZTSUP-OR01")
    s2 = _seed_named(session_factory, ORIONIS, "ZZTSUP-OR02")
    owner = _parser_output(
        domain_hint="purchase_order", intent_hint="check_po", order_status="outstanding", status="outstanding",
        entities=[{"raw": "orionis", "hint": "supplier", "canonical_code": None, "current_message": True, "confident": True}],
    )
    reply, _c, _s = _span_turn(
        session_factory, monkeypatch, "Outstandinf for orionis", list_resolver.Span("orionis", "product_code"), set(),
        qf=owner,
    )
    position = next(int(ln.split(". ", 1)[0]) for ln in reply.splitlines() if "(supplier)" in ln)
    pick = _parser_output(message_type="answer", intent_hint=None, domain_hint=None, entities=[], reference_positions=[position])
    reply, captured, _s = _span_turn(session_factory, monkeypatch, str(position), list_resolver.Span(str(position)), set(), qf=pick)
    calls = _po_calls(captured)
    asked = len([ln for ln in reply.splitlines() if ln[:1].isdigit()]) >= 2
    assert (calls and set(calls[0].get("supplier_ids") or []) == {s1, s2}) or (asked and not calls), (reply, captured)


def test_a_kind_pick_drops_only_the_picked_word_from_the_other_party_kind():
    """Re-review S-a: the other party kind loses only the picked word; another held party stays."""
    from types import SimpleNamespace

    from app.services.chatbot.turn import apply as apply_mod
    from app.services.chatbot.turn.state import Focus

    focus = Focus()
    apply_mod._set_kind_field(focus, "supplier", [{"raw": "orionis", "uuid": "a"}, {"raw": "jinbai", "uuid": "b"}])
    held = apply_mod._kind_rows(focus, "supplier")
    assert [r["raw"] for r in held] == ["orionis", "jinbai"]
    apply_mod._drop_words(focus, "supplier", {"orionis"})
    assert [r["raw"] for r in apply_mod._kind_rows(focus, "supplier")] == ["jinbai"]
    assert SimpleNamespace
