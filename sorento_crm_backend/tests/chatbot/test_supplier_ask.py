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
from app.services.chatbot.lanes.business import report_ask
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
               qf: dict[str, Any] | None = None, attributes=STAFF_GRANTS, supplier_ids: bool = True, embed=None,
               party_side: bool = False):
    import functools

    from app.services import contact_field_reveal_service
    from app.services.chatbot.head import parser as parser_mod
    from app.services.chatbot.head import span_extract

    monkeypatch.setattr(
        parser_mod, "ParserConfig",
        functools.partial(parser_mod.ParserConfig, lookup_spans=True, supplier_ids=supplier_ids, party_side=party_side),
    )
    monkeypatch.setattr(span_extract, "resolve_config", lambda db, **kw: span_extract.SpanConfig(
        "sys", 1, "openai", "gpt-zz", "ZZ-key", "label"))
    monkeypatch.setattr(span_extract, "extract", lambda config, message: span_extract.SpanAnswer([span], {}, 1))
    monkeypatch.setattr(ll, "EMBED", embed or meaning_embed({t.casefold() for t in near}))
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


def test_two_suppliers_with_one_name_are_one_supplier_never_asked(session_factory, monkeypatch):
    """Console pass 3 note a (#2066) had "CO.,LTD" and "CO., LTD." as two companies on two lines, and two suppliers of
    the very same name on one line nobody could pick from; it ruled every supplier its own line with its code. Crew
    live check on #2120 (7 Nov, HANLIM TRADING SDN BHD 403-H007 + 400-H018) replaces that: records of one trading name
    are one supplier, keyed as customer ledgers are (`ledger_family_key`: brackets, punctuation and legal-form words
    ignored, so the note a pair is one supplier too). The PO list runs for every record and nothing is asked."""
    ids = _staff_world(session_factory)
    same = _seed_named(session_factory, SUPPLIER, "ZZTSUP-TY09")
    span = list_resolver.Span("taiyang", "supplier")
    reply, captured, _seen = _span_turn(
        session_factory, monkeypatch, "outstanding PO for taiyang", span, {"taiyang", SUPPLIER}
    )
    assert "Which one do you mean?" not in reply, reply
    calls = _po_calls(captured)
    assert calls and sorted(calls[0].get("supplier_ids") or []) == sorted([ids["ours"], same]), (reply, captured)



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
    if report_kind_asked := ("Sales order or delivery order?" in reply):
        reply, captured, _s = _span_turn(
            session_factory, monkeypatch, "Delivery order", list_resolver.Span("Delivery order"), set(), qf=basis,
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


# --------------------------------------------------------------------------- #
# Fix round 7 (crew sweep at 55545eb7): meaning hits came and went (金百川, 太阳); the supplier side was still held
# after the customer pick in the owner's flow.
# --------------------------------------------------------------------------- #


def test_one_uncached_row_no_longer_switches_meaning_off_for_the_whole_turn(monkeypatch):
    """Crew turns 2d4e8d65 (fail) / 7e4a5d65 (pass): the same span, meaning hits only on some sends. One row text not
    yet in the vector cache made `usable_embedder` spelling-only for every span of the turn. Cached rows keep their
    meaning; the uncached row scores none and no row is embedded on the turn."""
    import numpy as np

    asked: list[list[str]] = []

    def request(chunk):
        asked.append(list(chunk))
        return [[1.0, 0.0, 0.0] if "jinbaichuan" in t.casefold() or t == "Jin Bai Chuan" else [0.0, 1.0, 0.0] for t in chunk]

    ll._cache.clear()
    embed = ll._vector_embedder("gemini-embedding-001", request, 10)
    cached = _sup_row("s1", "ZZT CHAOZHOU JINBAICHUAN SANITARY", "400-J001")
    fresh = ll.LookupRow("customer", "c1", "ZZT NEW CUSTOMER TODAY", ("ZZT NEW CUSTOMER TODAY",), homes=("label",))
    embed(list(cached.texts))
    asked.clear()
    monkeypatch.setattr(ll, "TURN_EMBED_GAP", 0)  # a gap too large for the turn: the cached rows only
    usable = ll.usable_embedder([cached, fresh], embed)
    assert usable is not None and usable is not embed
    m = usable.matrix(ll.row_texts([cached, fresh]))
    assert m.shape[0] == len(ll.row_texts([cached, fresh])) and float(np.abs(m).sum()) > 0
    res = list_resolver.resolve([list_resolver.Span("金百川", "customer", meaning="Jin Bai Chuan")], [cached, fresh], embed=usable)[0]
    assert res.status == "resolved" and res.candidates[0].row.key == "s1", res
    assert all("ZZT NEW CUSTOMER TODAY" not in c for c in asked), "no row is embedded on the turn"



def test_a_small_gap_of_uncached_rows_is_embedded_on_the_turn_and_meaning_stays_full(monkeypatch):
    """Fix round 7: a few uncached row texts (a new customer) are embedded on the turn, within the embedder's own
    budget, so every row keeps its meaning."""
    ll._cache.clear()
    embed = ll._vector_embedder("gemini-embedding-001", lambda chunk: [[1.0, 0.0] for _ in chunk], 10)
    rows = [_sup_row("s1", "ZZT CHAOZHOU JINBAICHUAN SANITARY", "400-J001")]
    assert ll.usable_embedder(rows, embed) is embed
    assert embed.is_cached(ll.row_texts(rows))
    assert ll.cached_share(rows, embed) == f"{len(ll.row_texts(rows))}/{len(ll.row_texts(rows))}"


@pytest.mark.parametrize("echo,current", [(None, False), ("supplier", False), ("customer", False), ("supplier", True), ("customer", True)])
def test_after_a_supplier_po_thread_the_customer_pick_reaches_that_customers_do_report(
    session_factory, monkeypatch, echo, current
):
    """Crew sweep at 55545eb7 (turns c73ee10c, 55775513, 34b1a786): after a PO thread, the customer pick over
    "orionis" left orionis held as a supplier (and the thread's PO document), so "Pending delivery" ran the report
    for every customer or answered "Couldn't find orionis (supplier)". The pick drops the supplier side for the rest
    of the thread: the report is that customer's."""
    _office_world(session_factory)
    customer = _seed_customer(session_factory, f"{ORIONIS} (PROJECT)")
    _seed_named(session_factory, ORIONIS, "ZZTSUP-OR01")
    _span_turn(session_factory, monkeypatch, "outstanding PO for jinbai", list_resolver.Span("jinbai", "supplier"), {"jinbai", OTHER})
    owner = _parser_output(
        domain_hint="purchase_order", intent_hint="check_po", order_status="outstanding", status="outstanding",
        document=["PO"], entity_op="replace_combine",
        entities=[{"raw": "orionis", "hint": "supplier", "canonical_code": None, "current_message": True, "confident": True}],
    )
    reply, _c, _s = _span_turn(
        session_factory, monkeypatch, "Outstandinf for orionis", list_resolver.Span("orionis", "product_code"), set(), qf=owner,
    )
    position = next(int(ln.split(". ", 1)[0]) for ln in reply.splitlines() if "(customer)" in ln)
    # The parser may echo the asked word beside the pick, with either hint (v195 does on some sends).
    echoed = [{"raw": "orionis", "hint": echo, "canonical_code": None, "current_message": current, "confident": True}] if echo else []
    pick = _parser_output(
        message_type="answer", intent_hint="check_po", domain_hint="purchase_order", document=["PO"], entities=echoed,
        reference_positions=[position], status="outstanding", order_status="outstanding", entity_op="reuse",
    )
    reply, _c, _s = _span_turn(session_factory, monkeypatch, str(position), list_resolver.Span(str(position)), set(), qf=pick)
    basis = _parser_output(
        message_type="answer", intent_hint="check_order", domain_hint="order", order_status="outstanding",
        status="outstanding", basis="pending_delivery", entities=echoed, reference_positions=[2], entity_op="reuse",
    )
    reply, captured, _s = _span_turn(
        session_factory, monkeypatch, "Delivery order", list_resolver.Span("Delivery order"), set(), qf=basis,
    )
    asks = [a for n, a in captured if n in ORDER_TOOLS]
    assert asks and asks[0].get("customer_ids") == [customer], (reply, captured)
    assert "(supplier)" not in reply, reply



def test_the_customer_pick_drops_the_held_supplier_row_by_its_id_whatever_its_name():
    """Crew turn c73ee10c: the supplier row held on the asking turn carried the resolver's name (not 'orionis') and id
    42b950b5; matched by the word alone it stayed, and the next turn read orionis as a supplier again."""
    from app.services.chatbot.turn import apply as apply_mod
    from app.services.chatbot.turn.state import Focus

    focus = Focus()
    held = {"raw": ORIONIS, "uuid": "42b950b5-0000-0000-0000-000000000000", "canonical_code": ORIONIS}
    other = {"raw": "jinbai", "uuid": "11111111-0000-0000-0000-000000000000"}
    apply_mod._set_kind_field(focus, "supplier", [held, other])
    apply_mod._drop_words(focus, "supplier", {"orionis"}, {"42b950b5-0000-0000-0000-000000000000"})
    assert [r["raw"] for r in apply_mod._kind_rows(focus, "supplier")] == ["jinbai"]



def test_a_customer_kind_pick_on_the_purchase_side_moves_to_sales_and_drops_the_po_document():
    from app.services.chatbot.turn import apply as apply_mod
    from app.services.chatbot.turn.state import Focus

    assert apply_mod._side_of_the_parties([{"hint": "customer", "current_message": True}], {"domain_hint": "purchase_order"}) == "order"
    focus = Focus()
    focus.document = ["PO", "SO"]
    apply_mod._documents_of_the_side(focus, "order")
    assert focus.document == ["SO"]
    focus.document = ["PO"]
    apply_mod._documents_of_the_side(focus, "purchase_order")
    assert focus.document == ["PO"]


# Fix round 8: crew's exact v195 emissions at edf38ba5 (pick turns f733c7c5 / 3e907f1b / 236c70fb, "Pending delivery"
# turns fe876b64 / 5f7b1567 / 37efd0f3 / ef59bc58 / 066890a3).

#: The owner's contact's reveals (office staff: the outstanding AND sales report reveals beside the supplier ones).
OWNER_GRANTS = (*STAFF_GRANTS, "sales_orders.sales_report")

_PICK_EMISSION = dict(
    message_type="business_query", intent_hint="check_order", domain_hint="order", order_status="outstanding",
    status="outstanding", document=[], entity_op="replace_combine", reference_positions=[1],
    open_question_answer={"mode": "pick", "items": [], "picked": [1], "qty_for_all": None}, reference_target="dym",
)
_PEND_EMISSIONS = {
    "empty-DO": dict(entities=[], document=["DO"], order_status="outstanding", status="outstanding"),
    "empty-nodoc": dict(entities=[], document=[], order_status="outstanding", status="outstanding"),
    "carried-do_outstanding": dict(
        entities=[{"raw": "orionis", "hint": "customer", "canonical_code": None, "current_message": False, "confident": True}],
        document=["DO"], order_status="do_outstanding", status="do_outstanding",
    ),
}


@pytest.mark.parametrize("thread", [False, True])
@pytest.mark.parametrize("pend", sorted(_PEND_EMISSIONS))
def test_crews_emissions_customer_pick_then_pending_delivery_is_that_customers_do_report(
    session_factory, monkeypatch, thread, pend
):
    _office_world(session_factory)
    customer = _seed_customer(session_factory, f"{ORIONIS} (PROJECT)")
    _seed_named(session_factory, ORIONIS, "ZZTSUP-OR01")
    if thread:
        _span_turn(session_factory, monkeypatch, "outstanding PO for jinbai", list_resolver.Span("jinbai", "supplier"), {"jinbai", OTHER})
    owner = _parser_output(
        domain_hint="purchase_order", intent_hint="check_po", order_status="outstanding", status="outstanding",
        entities=[{"raw": "orionis", "hint": "supplier", "canonical_code": None, "current_message": True, "confident": True}],
    )
    reply, _c, _s = _span_turn(
        session_factory, monkeypatch, "Outstandinf for orionis", list_resolver.Span("orionis", "product_code"), set(), qf=owner,
    )
    position = next(int(ln.split(". ", 1)[0]) for ln in reply.splitlines() if "(customer)" in ln)
    pick = _parser_output(**{**_PICK_EMISSION, "reference_positions": [position],
        "open_question_answer": {"mode": "pick", "items": [], "picked": [position], "qty_for_all": None},
        "entities": [{"raw": "orionis", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}]})
    reply, _c, _s = _span_turn(session_factory, monkeypatch, str(position), list_resolver.Span(str(position)), set(), qf=pick)
    assert "Sales order or delivery order?" in reply, reply
    pend_qf = _parser_output(
        message_type="business_query", intent_hint="check_order", domain_hint="order", entity_op="reuse",
        reference_positions=[2], open_question_answer={"mode": "pick", "items": [], "picked": [2], "qty_for_all": None},
        reference_target="dym", domain_in_message=True, **_PEND_EMISSIONS[pend],
    )
    reply, captured, _s = _span_turn(
        session_factory, monkeypatch, "Delivery order", list_resolver.Span("Delivery order"), set(), qf=pend_qf,
        attributes=OWNER_GRANTS,
    )
    asks = [a for n, a in captured if n in ORDER_TOOLS]
    assert asks and asks[0].get("customer_ids") == [customer], (reply, captured)
    assert "(supplier)" not in reply, reply


@pytest.mark.parametrize("pend", sorted(_PEND_EMISSIONS))
def test_baseline_a_typed_customer_then_pending_delivery_is_that_customers_do_report(session_factory, monkeypatch, pend):
    """The same 'Pending delivery' emissions after a plain customer ask (no supplier anywhere): the baseline the kind
    pick must match."""
    _office_world(session_factory)
    customer = _seed_customer(session_factory, f"{ORIONIS} (PROJECT)")
    ask = _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="outstanding", status="outstanding",
        entities=[{"raw": "orionis", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}],
    )
    reply, _c, _s = _span_turn(
        session_factory, monkeypatch, "Outstanding order for orionis", list_resolver.Span("orionis", "customer"),
        {"orionis", ORIONIS.casefold()}, qf=ask,
    )
    assert "Sales order or delivery order?" in reply, reply
    pend_qf = _parser_output(
        message_type="business_query", intent_hint="check_order", domain_hint="order", entity_op="reuse",
        reference_positions=[2], open_question_answer={"mode": "pick", "items": [], "picked": [2], "qty_for_all": None},
        reference_target="dym", domain_in_message=True, **_PEND_EMISSIONS[pend],
    )
    reply, captured, _s = _span_turn(
        session_factory, monkeypatch, "Delivery order", list_resolver.Span("Delivery order"), set(), qf=pend_qf,
        attributes=OWNER_GRANTS,
    )
    asks = [a for n, a in captured if n in ORDER_TOOLS]
    assert asks and asks[0].get("customer_ids") == [customer], (reply, captured)


@pytest.mark.parametrize("current", [True, False])
def test_both_over_three_with_the_parser_echoing_two_options_still_asks_again(session_factory, monkeypatch, current):
    """Crew turns a058af76 / dcf048aa / 5f0c3d6c (and 10d8d75c, the echo carried): v195 answered 'both' over the three
    supplier lines with picked [1, 2] AND the two lines as supplier entities. The PO list ran for two of three, or, with
    the echo carried, the turn fell to an order list with no supplier. The question is asked again; nothing is listed."""
    _three_taiyang(session_factory, monkeypatch)
    echo = [
        {"raw": f"{SUPPLIER} (ZZTSUP-TY01)", "hint": "supplier", "canonical_code": "ZZTSUP-TY01", "current_message": current, "confident": True},
        {"raw": "ZZT TAIYANG SANITARY CO LTD (ZZTSUP-TY02)", "hint": "supplier", "canonical_code": "ZZTSUP-TY02", "current_message": current, "confident": True},
    ]
    both = _parser_output(
        message_type="business_query", intent_hint="check_po", domain_hint="purchase_order", entities=echo,
        reference_positions=[1, 2], open_question_answer={"mode": "pick", "items": [], "picked": [1, 2], "qty_for_all": None},
    )
    again, captured, _s = _span_turn(session_factory, monkeypatch, "both", list_resolver.Span("both"), set(), qf=both)
    assert not _fetch_calls(captured), (again, captured)
    assert len([ln for ln in again.splitlines() if ln[:1].isdigit()]) == 3, again


def test_a_new_span_sentence_republishes_the_span_and_re_pairs_the_same_parser_text(session_factory, monkeypatch):
    """Fix round 8 (金百川 'meaning' null 7/12): the span version gains one sentence (a non-Latin span always carries a
    meaning). The parser text is unchanged, so its version is kept and re-paired to the new span version, which the
    console pin then runs."""
    from app.models.ai_prompt import AIPromptVersion

    db = session_factory()
    _seed_prompts(db)
    sask = _migration("sask_0002_span_supplier")
    assert "never null" in sask.NAME_MEANING_SENTENCE
    span_v, parser_v = sask.publish(db)
    monkeypatch.setattr(sask, "NAME_MEANING_SENTENCE", sask.NAME_MEANING_SENTENCE + " ZZT newer wording.")
    span_v2, parser_v2 = sask.publish(db)
    assert span_v2 != span_v and parser_v2 == parser_v, "a new span version, the same parser version"
    span_row = db.query(AIPromptVersion).filter(AIPromptVersion.name == "chatbot_span_extractor", AIPromptVersion.version == span_v2).one()
    parser_row = db.query(AIPromptVersion).filter(AIPromptVersion.name == "chatbot_semantic_parser", AIPromptVersion.version == parser_v).one()
    db.refresh(parser_row)
    assert parser_row.config_json["span_prompt_version_id"] == str(span_row.id)


def test_a_fresh_process_reads_the_stored_vectors_on_the_turn_before_falling_back(monkeypatch):
    """Fix round 8: a large gap (a fresh process) loads the stored vectors first (one SELECT, no provider call)."""
    ll._cache.clear()
    calls: list[int] = []
    embed = ll._vector_embedder("gemini-embedding-001", lambda chunk: calls.append(len(chunk)) or [[1.0, 0.0] for _ in chunk], 10)
    rows = [ll.LookupRow("customer", f"c{i}", f"ZZT CUSTOMER {i}", (f"ZZT CUSTOMER {i}",), homes=("label",)) for i in range(80)]

    def load_stored(texts):
        embed(list(texts))  # stands in for the stored vectors arriving in the cache
        return len(texts)

    monkeypatch.setattr(embed, "load_stored", load_stored, raising=False)
    assert ll.usable_embedder(rows, embed) is embed
    calls.clear()
    monkeypatch.setattr(embed, "load_stored", lambda texts: (_ for _ in ()).throw(RuntimeError("db down")), raising=False)
    ll._cache.clear()
    usable = ll.usable_embedder(rows, embed)
    assert usable is not embed and not calls, "a failed load falls back to the cached rows; no row is embedded"


# --------------------------------------------------------------------------- #
# Fix round 9 (crew re-check at c5333b37): a supplier-scoped turn never reaches a list tool without a supplier filter.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("tool", sorted(fetch_mod.SUPPLIER_GUARDED_TOOLS))
def test_the_tool_boundary_refuses_a_list_without_the_supplier_of_a_supplier_scoped_turn(tool):
    trigger = {
        "tool": tool, "entities": [], "contact_id": "c-1",
        "semantic_input": {"supplier_scope": {"line": "Which one do you mean?"}},
    }
    with pytest.raises(fetch_mod.SupplierScopeViolation) as refused:
        fetch_mod.entity_ids_transformer(trigger, space_id=None)
    assert refused.value.line == "Which one do you mean?"
    fetch_mod.entity_ids_transformer({**trigger, "semantic_input": {}}, space_id=None)  # no scope: as before


def test_a_scoped_po_list_with_its_supplier_passes_the_guard():
    sid = str(uuid.uuid4())
    trigger = {
        "tool": PO_TOOL, "contact_id": "c-1", "semantic_input": {"supplier_scope": {"line": "x"}},
        "access": {"attributes": [SUPPLIER_GRANT]},
        "entities": [{"entity_type": "supplier", "uuid": sid, "canonical_code": "ZZTSUP-TY01"}],
    }
    assert fetch_mod.entity_ids_transformer(trigger, space_id=None).get("supplier_ids") == [sid]


@pytest.mark.parametrize("aside", ["broaden", "order-flip", "bare"])
def test_an_answer_over_the_supplier_question_never_lists_without_a_supplier(session_factory, monkeypatch, aside):
    """Crew turns 4cfda57c / 872cb7a6 (全部 listed every customer's orders) and 10d8d75c: whatever the parser read the
    answer as, the turn either lists the picked suppliers or asks again; never a list with no supplier."""
    _three_taiyang(session_factory, monkeypatch)
    qf = {
        "broaden": _parser_output(message_type="business_query", intent_hint="check_po", domain_hint="purchase_order",
                                  entities=[], broaden_axis="all", broaden_to="all", scope_intent="broaden"),
        "order-flip": _parser_output(message_type="business_query", intent_hint="check_order", domain_hint="order",
                                     order_status="outstanding", status="outstanding", entities=[]),
        "bare": _parser_output(message_type="answer", intent_hint=None, domain_hint=None, entities=[]),
    }[aside]
    reply, captured, _s = _span_turn(session_factory, monkeypatch, "全部", list_resolver.Span("全部"), set(), qf=qf)
    lists = [(n, a) for n, a in captured if n in fetch_mod.SUPPLIER_GUARDED_TOOLS]
    assert not [a for _n, a in lists if not a.get("supplier_ids")], (reply, captured)


def test_an_unknown_supplier_word_never_lists_the_po_book(session_factory, monkeypatch):
    """Crew turn 4ff1d7b8: 'outstanding PO for zzqqxx supplier' once listed the PO book with no supplier filter."""
    _office_world(session_factory)
    qf = _parser_output(
        domain_hint="purchase_order", intent_hint="check_po", order_status=None,
        entities=[{"raw": "zzqqxx", "hint": "supplier", "canonical_code": None, "current_message": True, "confident": True}],
    )
    reply, captured, _s = _span_turn(
        session_factory, monkeypatch, "outstanding PO for zzqqxx supplier", list_resolver.Span("zzqqxx", "supplier"), set(), qf=qf,
    )
    assert not [a for n, a in captured if n in fetch_mod.SUPPLIER_GUARDED_TOOLS and not a.get("supplier_ids")], (reply, captured)


def test_crews_all_emission_over_the_supplier_question_lists_the_three_suppliers_pos(session_factory, monkeypatch):
    """Crew turns 4cfda57c / 872cb7a6: 全部 parsed as picked [1, 2, 3] with domain purchase_order, status outstanding
    (flipped to order) and the message's own domain; the order list ran for every customer. The picked suppliers decide
    the side: their open POs."""
    _reply, three = _three_taiyang(session_factory, monkeypatch)
    qf = _parser_output(
        message_type="business_query", intent_hint="check_po", domain_hint="purchase_order", order_status="outstanding",
        status="outstanding", document=["PO"], entity_op="reuse", entities=[], reference_positions=[1, 2, 3],
        open_question_answer={"mode": "pick", "items": [], "picked": [1, 2, 3], "qty_for_all": None},
        broaden_axis="supplier", broaden_to="all", domain_in_message=True,
    )
    reply, captured, _s = _span_turn(session_factory, monkeypatch, "全部", list_resolver.Span("全部"), set(), qf=qf)
    assert not [n for n, _a in captured if n in fetch_mod.SUPPLIER_GUARDED_TOOLS and n != PO_TOOL], (reply, captured)
    calls = _po_calls(captured)
    assert calls and set(calls[0].get("supplier_ids") or []) == three, (reply, captured)


def test_crews_step3_customer_pick_with_po_document_asks_the_kind_on_the_sales_side(session_factory, monkeypatch):
    """Crew turns 1f34fcce / 027619e3 / 03df31ef: the customer pick came back with domain purchase_order and document
    PO; the reply was 'Could not find purchase order for customer orionis'. The PO document is the purchase thread's."""
    _office_world(session_factory)
    _seed_customer(session_factory, f"{ORIONIS} (PROJECT)")
    _seed_named(session_factory, ORIONIS, "ZZTSUP-OR01")
    owner = _parser_output(
        domain_hint="purchase_order", intent_hint="check_po", order_status="outstanding", status="outstanding",
        entities=[{"raw": "orionis", "hint": "supplier", "canonical_code": None, "current_message": True, "confident": True}],
    )
    reply, _c, _s = _span_turn(
        session_factory, monkeypatch, "Outstandinf for orionis", list_resolver.Span("orionis", "product_code"), set(), qf=owner,
    )
    position = next(int(ln.split(". ", 1)[0]) for ln in reply.splitlines() if "(customer)" in ln)
    pick = _parser_output(
        message_type="business_query", intent_hint="check_po", domain_hint="purchase_order", status=None, order_status=None,
        document=["PO"], entity_op="replace_combine", reference_positions=[position],
        open_question_answer={"mode": "pick", "items": [], "picked": [position], "qty_for_all": None},
        entities=[{"raw": "orionis", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}],
    )
    reply, _c, _s = _span_turn(
        session_factory, monkeypatch, str(position), list_resolver.Span(str(position)), set(), qf=pick, attributes=OWNER_GRANTS,
    )
    assert "Sales order or delivery order?" in reply, reply


def test_crews_unknown_supplier_with_no_parser_entity_never_lists_the_po_book(session_factory, monkeypatch):
    """Crew turn 4ff1d7b8: no parser entity at all; only the span pass typed 'zzqqxx' a supplier. The PO book ran with
    no filter."""
    _office_world(session_factory)
    qf = _parser_output(domain_hint="purchase_order", intent_hint="check_po", order_status=None, document=["PO"], entities=[])
    reply, captured, _s = _span_turn(
        session_factory, monkeypatch, "outstanding PO for zzqqxx supplier", list_resolver.Span("zzqqxx", "supplier"), set(), qf=qf,
    )
    assert not [a for n, a in captured if n in fetch_mod.SUPPLIER_GUARDED_TOOLS and not a.get("supplier_ids")], (reply, captured)


def test_a_hintless_entity_never_breaks_the_resolver_request():
    """Crew turn 36f11957: '太阳的' with hint null reached `allowed_entity_types` as None and the resolver request failed."""
    assert resolve_gate._allowed_entity_types({}, [{"raw": "太阳的", "hint": None}, {"raw": "x", "hint": "supplier"}]) == ["supplier"]


# --------------------------------------------------------------------------- #
# Follow-up to #2066 (crew re-check at 8b759db7): 金百川 read "Kim Pak Chuan" placed KIM HOH HARDWARE (403-K032) ALONE
# at exactly the supplier meaning floor; the turn listed KIM HOH's POs (turns ed977e5f, c5ffe95e). A lone row that only
# just reaches the floor is never the answer: the turn asks among the near rows, or finds nothing.
# --------------------------------------------------------------------------- #

KIM_HOH = "ZZT KIM HOH HARDWARE"
KIM_SENG = "ZZT KIM SENG TRADING"
JINBAICHUAN = "ZZT JINBAICHUAN SANITARY CO LTD"
KIM_READING = "Kim Pak Chuan"


class _CosineEmbed:
    """`cos[phrase][text]` is the cosine the phrase scores against that row text; every other text is orthogonal.
    `model` None is a plain callable (the OpenAI floors)."""

    def __init__(self, cos: dict[str, dict[str, float]], model: str | None = None) -> None:
        import math

        if model:
            self.model = model
        self.dim = 4096
        texts = sorted({t.casefold() for row in cos.values() for t in row})
        self.axis = {t: i for i, t in enumerate(texts)}
        self.fixed: dict[str, list[float]] = {t: self._unit(i) for t, i in self.axis.items()}
        rest = len(texts)
        for phrase, row in cos.items():
            v = [0.0] * self.dim
            for t, c in row.items():
                v[self.axis[t.casefold()]] = c
            v[rest] = math.sqrt(max(0.0, 1 - sum(c * c for c in row.values())))
            self.fixed[phrase.casefold()] = v

    def _unit(self, i: int) -> list[float]:
        v = [0.0] * self.dim
        v[i] = 1.0
        return v

    def __call__(self, texts):
        import hashlib

        out = []
        for t in texts:
            v = self.fixed.get(t.casefold().strip())
            if v is None:
                v = self._unit(len(self.axis) + 1 + int(hashlib.md5(t.encode()).hexdigest(), 16) % (self.dim - len(self.axis) - 1))
            out.append(v)
        return out


def _kim_rows():
    return [
        _sup_row("s-kh", KIM_HOH, "403-K032"), _sup_row("s-ks", KIM_SENG, "403-K040"),
        _sup_row("s-jb", JINBAICHUAN, "403-J011"),
    ]


def test_a_lone_supplier_at_the_meaning_floor_is_asked_among_its_near_rows():
    """Crew's emission: KIM HOH at exactly the gemini supplier floor (0.65), alone over it; KIM SENG just under."""
    embed = _CosineEmbed({KIM_READING: {KIM_HOH: 0.651, KIM_SENG: 0.62}}, model="gemini-embedding-001")
    res = list_resolver.resolve([list_resolver.Span(NATIVE_JBC, "customer", meaning=KIM_READING)], _kim_rows(), embed=embed)[0]
    assert res.status == "ambiguous", res
    assert [c.row.key for c in res.candidates] == ["s-kh", "s-ks"], res


def test_a_lone_supplier_at_the_meaning_floor_with_nothing_near_is_not_found():
    embed = _CosineEmbed({KIM_READING: {KIM_HOH: 0.651}}, model="gemini-embedding-001")
    res = list_resolver.resolve([list_resolver.Span(NATIVE_JBC, "customer", meaning=KIM_READING)], _kim_rows(), embed=embed)[0]
    assert res.status == "unresolved" and not res.candidates, res


@pytest.mark.parametrize("cos", [0.67, 0.69])
def test_a_lone_supplier_clearly_over_the_floor_still_binds(cos):
    """The true reading's hits scored 0.687-0.692 (crew turn 659346ce): a clear lone match stays the answer."""
    embed = _CosineEmbed({"Jin Bai Chuan": {JINBAICHUAN: cos, KIM_SENG: 0.62}}, model="gemini-embedding-001")
    res = list_resolver.resolve([list_resolver.Span(NATIVE_JBC, "customer", meaning="Jin Bai Chuan")], _kim_rows(), embed=embed)[0]
    assert res.status == "resolved" and res.candidates[0].row.key == "s-jb", res


@pytest.mark.parametrize("typed", ["kim hoh", "kimhoh hardware"])
def test_a_lone_spelling_match_is_untouched_by_the_weak_meaning_rule(typed):
    """"kimhoh hardware" spells KIM HOH alone at 0.636, under the floor plus the margin: only meaning is judged weak."""
    embed = _CosineEmbed({}, model="gemini-embedding-001")  # the 0.65 floor, no meaning hits
    res = list_resolver.resolve([list_resolver.Span(typed, "supplier")], _kim_rows(), embed=embed)[0]
    assert res.status == "resolved" and res.candidates[0].row.key == "s-kh", res


def test_a_lone_customer_at_its_meaning_floor_is_unchanged():
    """Only the supplier list is measured near a wrong row; a customer's lone meaning match keeps resolving."""
    rows = [ll.LookupRow("customer", "c1", "ZZT HARBOUR TILES", ("ZZT HARBOUR TILES",), homes=("label",))]
    embed = _CosineEmbed({"port tiles": {"ZZT HARBOUR TILES": 0.75}}, model="gemini-embedding-001")
    res = list_resolver.resolve([list_resolver.Span("port tiles", "customer")], rows, embed=embed)[0]
    assert res.status == "resolved", res


NATIVE_JBC = "金百川"


def test_crews_kim_pak_chuan_turn_never_lists_the_lone_floor_suppliers_pos(session_factory, monkeypatch):
    """Crew turns ed977e5f / c5ffe95e end to end: "Outstanding for 金百川", the span pass reads it "Kim Pak Chuan", which
    scores KIM HOH alone at the floor. The turn asks which supplier (KIM HOH beside KIM SENG) and lists nothing."""
    _staff_world(session_factory)
    kh = _seed_named(session_factory, KIM_HOH, "ZZTSUP-KH32")
    ks = _seed_named(session_factory, KIM_SENG, "ZZTSUP-KS40")
    floor = list_resolver._meaning_floor(_CosineEmbed({}), "supplier")
    embed = _CosineEmbed({KIM_READING: {KIM_HOH: floor + 0.001, KIM_SENG: floor - 0.03}})
    span = list_resolver.Span(NATIVE_JBC, "customer", meaning=KIM_READING)
    reply, captured, _seen = _span_turn(
        session_factory, monkeypatch, "Outstanding for 金百川", span, set(), qf=_ask(NATIVE_JBC, None), embed=embed,
    )
    assert not [a for n, a in captured if n == PO_TOOL and a.get("supplier_ids") == [kh]], (reply, captured)
    assert KIM_HOH in reply and KIM_SENG in reply, reply
    assert not _po_calls(captured), captured
    assert ks


def test_crews_kim_pak_chuan_turn_with_nothing_near_never_lists_that_supplier(session_factory, monkeypatch):
    _staff_world(session_factory)
    kh = _seed_named(session_factory, KIM_HOH, "ZZTSUP-KH32")
    floor = list_resolver._meaning_floor(_CosineEmbed({}), "supplier")
    embed = _CosineEmbed({KIM_READING: {KIM_HOH: floor + 0.001}})
    span = list_resolver.Span(NATIVE_JBC, "customer", meaning=KIM_READING)
    reply, captured, _seen = _span_turn(
        session_factory, monkeypatch, "Outstanding for 金百川", span, set(), qf=_ask(NATIVE_JBC, None), embed=embed,
    )
    assert not [a for n, a in captured if n == PO_TOOL and kh in (a.get("supplier_ids") or [])], (reply, captured)
    assert not [a for n, a in captured if n in fetch_mod.SUPPLIER_GUARDED_TOOLS and not a.get("supplier_ids")], (reply, captured)


# --------------------------------------------------------------------------- #
# Owner ruling, 3 Nov 2026 (prod, after #2066 went live): "it keeps asking me to choose fullshun customer or supplier,
# it is so clear that sales is talking about customer". The PARSER reads the side of a both-sides name from the whole
# turn (`party_side`, behind `parser.PARTY_SIDE_LINE`); code reads no word of the message (owner rule, 28 Oct). Only
# "unclear" (or a prompt without the line) asks.
# --------------------------------------------------------------------------- #

FULLSHUN = "ZZT FULLSHUN HARDWARE SDN BHD"


def test_the_party_side_line_turns_the_schema_key_on_and_only_then():
    from app.services.chatbot.head import parser as parser_mod

    base = parser_mod._base_schema(parser_mod.ParserConfig("x", 1, "openai", "m", "k"))
    assert "party_side" not in base["properties"] and "party_side" not in base["required"]
    on = parser_mod._base_schema(parser_mod.ParserConfig("x", 1, "openai", "m", "k", party_side=True))
    assert on["properties"]["party_side"] == {"type": ["string", "null"], "enum": ["customer", "supplier", "unclear", None]}
    assert on["required"][-1] == "party_side"
    assert parser_mod.with_party_side(base)["properties"].keys() - base["properties"].keys() == {"party_side"}


def test_no_word_list_decides_the_side_in_code():
    """Owner rule 28 Oct (#1947): meaning comes from the parser. The engine keeps no side word list or message read."""
    from app.services.chatbot import engine as engine_mod

    assert not hasattr(engine_mod, "_party_side")
    assert not [n for n in dir(engine_mod) if n.endswith("_SIDE_WORDS") or n.endswith("_PARTY_WORDS")]


@pytest.mark.parametrize("side,expect", [("customer", "customer"), ("supplier", "supplier")])
def test_a_side_keeps_only_that_party_kind_of_a_both_sides_word(side, expect):
    from app.services.chatbot.turn.reconcile import apply_reconciliation

    entities = [{"raw": "fullshun", "hint": "supplier", "canonical_code": "sup-id", "current_message": True}]
    hits = {"fullshun": {"customer": 1, "supplier": 1}}
    asked = apply_reconciliation(entities, hits, exact={"fullshun": {}})
    assert asked.kind_pick_options and {o["entity_type"] for o in asked.kind_pick_options} == {"customer", "supplier"}
    sided = apply_reconciliation(entities, hits, exact={"fullshun": {}}, side=side)
    assert sided.kind_pick_options is None, sided.kind_pick_options
    assert sided.entities[0]["hint"] == expect
    if expect == "customer":
        assert sided.entities[0]["canonical_code"] is None, "a supplier's row id never binds the customer"


def _fullshun_world(session_factory) -> dict[str, Any]:
    ids = _office_world(session_factory)
    ids["fs_customer"] = _seed_customer(session_factory, FULLSHUN)
    ids["fs_supplier"] = _seed_named(session_factory, FULLSHUN, "ZZTSUP-FS01")
    return ids


def _fullshun_turn(session_factory, monkeypatch, text: str, hint: str, canonical: str | None, *, flag: bool = True,
                   **parse):
    qf = _parser_output(
        entities=[{"raw": "fullshun", "hint": hint, "canonical_code": canonical, "current_message": True, "confident": True}],
        **parse,
    )
    return _span_turn(
        session_factory, monkeypatch, text, list_resolver.Span("fullshun", hint), {"fullshun", FULLSHUN.casefold()},
        qf=qf, attributes=OWNER_GRANTS, party_side=flag,
    )


#: The sales side's own next question for these asks (the kind, the basis, the period).
_SALES_SIDE_REPLIES = (report_ask.KIND_QUESTION, "Invoiced, delivered, ordered or outstanding?", "Which period")

_SALES_ASKS = {
    "delivery for fullshun": dict(
        domain_hint="order", intent_hint="check_order", order_status=None, document=["DO"], party_side="customer",
    ),
    "dealer fullshun oct sale": dict(party_side="customer",
        domain_hint="sales", intent_hint="sales_report", status="sales_report", order_status=None, date_mode="range", date_filter_start="2026-10-01", date_filter_end="2026-10-31",
    ),
    "customer fullshun only": dict(
        domain_hint="sales", intent_hint="sales_report", status="sales_report", order_status=None, party_side="customer",
    ),
    "Outstanding order for fullshun": dict(
        domain_hint="order", intent_hint="check_order", order_status="outstanding", status="outstanding",
        party_side="customer",
    ),
}


@pytest.mark.parametrize("hint", ["customer", "supplier"])
@pytest.mark.parametrize("text", sorted(_SALES_ASKS))
def test_owners_prod_sales_asks_over_a_both_sides_name_are_the_customer_never_asked(
    session_factory, monkeypatch, text, hint
):
    """Prod 3 Nov: "delivery for hanlim", "dealer fullshun oct sale", "customer fullshun only" were each asked
    "fullshun (customer) / fullshun (supplier)". A sales question is the customer's: no question, no PO list."""
    ids = _fullshun_world(session_factory)
    canonical = ids["fs_supplier"] if hint == "supplier" else None
    reply, captured, _seen = _fullshun_turn(session_factory, monkeypatch, text, hint, canonical, **_SALES_ASKS[text])
    assert "(supplier)" not in reply and "Which one do you mean?" not in reply, reply
    assert any(q in reply for q in _SALES_SIDE_REPLIES), reply  # the sales side's own next step, never an empty turn
    assert not _po_calls(captured), (reply, captured)
    party = [a for n, a in captured if n in fetch_mod.SUPPLIER_GUARDED_TOOLS]
    assert all(ids["fs_supplier"] not in (a.get("supplier_ids") or []) for a in party), (reply, captured)
    assert all(a.get("customer_ids") == [ids["fs_customer"]] for a in party if n_party(a)), (reply, captured)


def n_party(args: dict[str, Any]) -> bool:
    return bool(args.get("customer_ids") or args.get("supplier_ids"))


_PURCHASE_ASKS = {
    "PO for fullshun": dict(
        domain_hint="purchase_order", intent_hint="check_po", order_status=None, document=["PO"], party_side="supplier",
    ),
    "fullshun PO outstanding": dict(
        domain_hint="purchase_order", intent_hint="check_po", order_status=None, status="outstanding", document=["PO"],
        party_side="supplier",
    ),
    "supplier fullshun outstanding": dict(
        domain_hint="order", intent_hint="check_order", order_status="outstanding", status="outstanding",
        party_side="supplier",
    ),
}


@pytest.mark.parametrize("hint", ["customer", "supplier"])
@pytest.mark.parametrize("text", sorted(_PURCHASE_ASKS))
def test_a_purchase_ask_over_a_both_sides_name_is_the_supplier_never_asked(session_factory, monkeypatch, text, hint):
    ids = _fullshun_world(session_factory)
    canonical = ids["fs_supplier"] if hint == "supplier" else None
    reply, captured, _seen = _fullshun_turn(session_factory, monkeypatch, text, hint, canonical, **_PURCHASE_ASKS[text])
    assert "(customer)" not in reply and "Which one do you mean?" not in reply, reply
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["fs_supplier"]], (reply, captured)
    assert not calls[0].get("customer_ids"), calls


@pytest.mark.parametrize("hint", ["customer", "supplier"])
def test_a_both_sides_name_with_no_side_word_is_still_asked(session_factory, monkeypatch, hint):
    """The #2066 rule stands where the message names no side ("Outstandinf for orionis"): asked, nothing listed."""
    ids = _fullshun_world(session_factory)
    canonical = ids["fs_supplier"] if hint == "supplier" else None
    reply, captured, _seen = _fullshun_turn(
        session_factory, monkeypatch, "Outstandinf for fullshun", hint, canonical,
        domain_hint="order", intent_hint="check_order", order_status="outstanding", status="outstanding",
        party_side="unclear",
    )
    assert "(customer)" in reply and "(supplier)" in reply, reply
    assert not _fetch_calls(captured), (reply, captured)


@pytest.mark.parametrize("said", ["customer", "supplier"])
def test_a_party_side_from_a_prompt_without_the_line_is_ignored_and_the_name_asked(session_factory, monkeypatch, said):
    """Production today: no text carries `PARTY_SIDE_LINE`, so a stray key never decides; the #2066 question stands."""
    ids = _fullshun_world(session_factory)
    reply, captured, _seen = _fullshun_turn(
        session_factory, monkeypatch, "delivery for fullshun", "supplier", ids["fs_supplier"], flag=False,
        domain_hint="order", intent_hint="check_order", order_status=None, document=["DO"], party_side=said,
    )
    assert "(customer)" in reply and "(supplier)" in reply, reply
    assert not _fetch_calls(captured), (reply, captured)


@pytest.mark.parametrize("hint", ["customer", "supplier"])
def test_an_outstanding_order_ask_over_a_both_sides_name_reports_that_customer(session_factory, monkeypatch, hint):
    """End to end: "Outstanding order for fullshun" asks the sales side's kind question (never customer or supplier),
    and "Pending delivery" is the customer's DO report, filtered by that customer's id."""
    ids = _fullshun_world(session_factory)
    canonical = ids["fs_supplier"] if hint == "supplier" else None
    reply, captured, _s = _fullshun_turn(
        session_factory, monkeypatch, "Outstanding order for fullshun", hint, canonical,
        **_SALES_ASKS["Outstanding order for fullshun"],
    )
    assert report_ask.KIND_QUESTION in reply, reply
    pend_qf = _parser_output(
        message_type="business_query", intent_hint="check_order", domain_hint="order", entity_op="reuse",
        reference_positions=[2], open_question_answer={"mode": "pick", "items": [], "picked": [2], "qty_for_all": None},
        reference_target="dym", domain_in_message=True, **_PEND_EMISSIONS["empty-DO"],
    )
    reply, captured, _s = _span_turn(
        session_factory, monkeypatch, "Pending delivery", list_resolver.Span("Pending delivery"), set(), qf=pend_qf,
        attributes=OWNER_GRANTS,
    )
    asks = [a for n, a in captured if n in ORDER_TOOLS]
    assert asks and asks[0].get("customer_ids") == [ids["fs_customer"]], (reply, captured)
    assert not _po_calls(captured), captured


@pytest.mark.parametrize("hint", ["customer", "supplier"])
def test_a_delivery_ask_over_a_both_sides_name_names_the_customer(session_factory, monkeypatch, hint):
    """Prod "delivery for hanlim": the sales side's period question names the customer, never "couldn't find a
    supplier" (the round-9 guard counted the span model's supplier type as the subject)."""
    ids = _fullshun_world(session_factory)
    canonical = ids["fs_supplier"] if hint == "supplier" else None
    reply, _c, _s = _fullshun_turn(
        session_factory, monkeypatch, "delivery for fullshun", hint, canonical, **_SALES_ASKS["delivery for fullshun"],
    )
    assert FULLSHUN in reply and "couldn't find" not in reply, reply


def _parser_config_for(session_factory, monkeypatch, template: str):
    """`test_eem_category_pick._config_for` over a parser with no other label (the session DB keeps earlier rows)."""
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
    from app.services.chatbot.head import parser as parser_mod
    from tests.chatbot.test_eem_category_pick import _config_for

    db = session_factory()
    db.query(AIPromptLabel).filter(AIPromptLabel.name == parser_mod.PROMPT_KEY).delete()
    db.query(AIPromptVersion).filter(AIPromptVersion.name == parser_mod.PROMPT_KEY).delete()
    db.commit()
    db.close()
    from app.services import ai_prompt_registry
    from app.services import chatbot_prompt_vars as pv

    ai_prompt_registry.bust_cache()
    pv.clear_cache()
    return _config_for(session_factory, monkeypatch, template)


@pytest.mark.parametrize("gate", ["", "== CLOSED LISTS ==\n"])
def test_a_prompt_with_the_party_side_line_offers_the_key_on_both_schema_paths(session_factory, monkeypatch, gate):
    from app.services.chatbot.head import parser as parser_mod
    on = _parser_config_for(session_factory, monkeypatch, "Rules {{current_date}}.\n" + gate + parser_mod.PARTY_SIDE_LINE + "\n")
    assert on.party_side is True
    schema = on.json_schema or parser_mod._base_schema(on)
    assert schema["properties"]["party_side"]["enum"] == ["customer", "supplier", "unclear", None], schema["properties"].keys()
    assert "party_side" in schema["required"]


def test_a_prompt_without_the_party_side_line_has_no_key(session_factory, monkeypatch):
    from app.services.chatbot.head import parser as parser_mod
    off = _parser_config_for(session_factory, monkeypatch, "Rules {{current_date}}.\n== CLOSED LISTS ==\n")
    assert off.party_side is False
    assert "party_side" not in (off.json_schema or parser_mod._base_schema(off))["properties"]


# --------------------------------------------------------------------------- #
# SUPPLIER-PARTY-SIDE (owner, 5 Nov 2026, prod on parser v202 / label v71): "delivery to hanlim" still replied "Which
# one do you mean? 1. hanlim (customer) 2. hanlim (supplier)" because #2120's code was not on main while the prompt
# already carried its PARTY_SIDE section. The parser's party_side decides; only a message naming no side asks.
# --------------------------------------------------------------------------- #

HANLIM = "ZZT HANLIM ENTERPRISE SDN BHD"


def _party_side_section(name: str) -> str:
    """The PARTY_SIDE section as published in the prod text (md5 d29c1983 carries it verbatim), from its PROMPT doc
    wherever the plan currently lives (plans/ or plans/_archive/)."""
    import pathlib

    docs = pathlib.Path(__file__).resolve().parents[3] / "documentation" / "plans"
    found = sorted(docs.glob(f"**/chatbot/{name}"))
    assert found, f"{name} not under {docs}"
    text = found[0].read_text(encoding="utf-8")
    return text.split("```text\n", 1)[1].split("```", 1)[0]


def test_the_prod_party_side_section_carries_the_line_the_code_keys_on():
    """The section v202 published (PROMPT-party-side-3nov.md Edit 1, 1315 bytes, md5 9fcfa92c) turns the key on."""
    import hashlib

    from app.services.chatbot.head import parser as parser_mod

    section = _party_side_section("PROMPT-party-side-3nov.md")
    assert hashlib.md5(section.encode("utf-8")).hexdigest() == "9fcfa92c8b6045279b8889734c0fe4d8"
    assert section.splitlines()[0] == parser_mod.PARTY_SIDE_LINE
    for side in parser_mod.PARTY_SIDES:
        assert f'"{side}"' in section, side


def _hanlim_world(session_factory) -> dict[str, Any]:
    ids = _office_world(session_factory)
    ids["hl_customer"] = _seed_customer(session_factory, HANLIM)
    ids["hl_supplier"] = _seed_named(session_factory, HANLIM, "ZZTSUP-HL01")
    return ids


def _hanlim_turn(session_factory, monkeypatch, text: str, hint: str, canonical: str | None, **parse):
    qf = _parser_output(
        entities=[{"raw": "hanlim", "hint": hint, "canonical_code": canonical, "current_message": True, "confident": True}],
        **parse,
    )
    return _span_turn(
        session_factory, monkeypatch, text, list_resolver.Span("hanlim", hint), {"hanlim", HANLIM.casefold()},
        qf=qf, attributes=OWNER_GRANTS, party_side=True,
    )


@pytest.mark.parametrize("hint", ["customer", "supplier"])
def test_delivery_to_hanlim_is_the_customer_never_asked(session_factory, monkeypatch, hint):
    ids = _hanlim_world(session_factory)
    canonical = ids["hl_supplier"] if hint == "supplier" else None
    reply, captured, _seen = _hanlim_turn(
        session_factory, monkeypatch, "delivery to hanlim", hint, canonical,
        domain_hint="order", intent_hint="check_order", order_status=None, document=["DO"], party_side="customer",
    )
    assert "Which one do you mean?" not in reply and "(supplier)" not in reply, reply
    assert HANLIM in reply and "couldn't find" not in reply, reply
    assert not _po_calls(captured), (reply, captured)
    party = [a for n, a in captured if n in fetch_mod.SUPPLIER_GUARDED_TOOLS and n_party(a)]
    assert all(a.get("customer_ids") == [ids["hl_customer"]] for a in party), (reply, captured)


@pytest.mark.parametrize("hint", ["customer", "supplier"])
def test_po_from_hanlim_is_the_supplier_never_asked(session_factory, monkeypatch, hint):
    ids = _hanlim_world(session_factory)
    canonical = ids["hl_supplier"] if hint == "supplier" else None
    reply, captured, _seen = _hanlim_turn(
        session_factory, monkeypatch, "PO from hanlim", hint, canonical,
        domain_hint="purchase_order", intent_hint="check_po", order_status=None, document=["PO"], party_side="supplier",
    )
    assert "Which one do you mean?" not in reply and "(customer)" not in reply, reply
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["hl_supplier"]], (reply, captured)
    assert not calls[0].get("customer_ids"), calls


@pytest.mark.parametrize("said", ["unclear", None])
@pytest.mark.parametrize("hint", ["customer", "supplier"])
def test_hanlim_alone_is_still_asked(session_factory, monkeypatch, hint, said):
    ids = _hanlim_world(session_factory)
    canonical = ids["hl_supplier"] if hint == "supplier" else None
    reply, captured, _seen = _hanlim_turn(
        session_factory, monkeypatch, "hanlim", hint, canonical,
        domain_hint="order", intent_hint="check_order", order_status=None, party_side=said,
    )
    assert "(customer)" in reply and "(supplier)" in reply, reply
    assert not _fetch_calls(captured), (reply, captured)


def test_a_customer_side_never_keeps_a_supplier_row_id_the_parser_put_on_a_customer_hint():
    """Review nit (#2120): the model put a Supplier candidate's id on a customer-hinted both-sides entity."""
    from types import SimpleNamespace

    from app.services.chatbot.engine import _both_side_words

    prep = SimpleNamespace(
        party_suppliers={"hanlim": "sup-1"}, supplier_groups={"sup-1": [("sup-1", "HANLIM")]}, message=None,
    )
    verdict = {"party_side": "customer", "entities": [
        {"raw": "hanlim", "hint": "customer", "canonical_code": "sup-1", "current_message": True},
    ]}
    out = _both_side_words(verdict, prep)["entities"][0]
    assert out["hint"] == "customer" and out["canonical_code"] is None, out
    kept = _both_side_words({**verdict, "entities": [{**verdict["entities"][0], "canonical_code": "cus-9"}]}, prep)
    assert kept["entities"][0]["canonical_code"] == "cus-9", kept


def test_a_weak_lone_supplier_offers_each_row_once():
    """Review nit (#2120): one supplier with two texts near the span is one option, never two."""
    from types import SimpleNamespace

    from app.services.chatbot.head.lookup_lists import LookupRow

    rows = [
        LookupRow("supplier", "s1", "S1", ("kim pak",)), LookupRow("supplier", "s1", "S1", ("kim pak chuan",)),
        LookupRow("supplier", "s2", "S2", ("kim hoh",)),
    ]
    span = list_resolver.Span("kim pak chuan", "supplier")
    meaning = {("supplier", 0): {span.text: 0.66}, ("supplier", 1): {span.text: 0.64}, ("supplier", 2): {span.text: 0.62}}
    best = list_resolver.Candidate(rows[0], 0.66, "meaning")
    res = list_resolver._weak_alone(
        span, best, {"supplier": {"meaning": 0.65}}, {"supplier": SimpleNamespace(rows=rows)}, meaning,
    )
    assert res.status == "ambiguous" and [c.row.key for c in res.candidates] == ["s1", "s2"], res
    assert res.candidates[0].score == 0.66, res
    alone = list_resolver._weak_alone(
        span, best, {"supplier": {"meaning": 0.65}}, {"supplier": SimpleNamespace(rows=rows[:2])},
        {k: v for k, v in meaning.items() if k[1] < 2},
    )
    assert alone.status == "unresolved", alone


# --------------------------------------------------------------------------- #
# SUPPLIER-PARTY-SIDE crew live check (7 Nov 2026, db7ec534, parser v74 md5 d29c1983): HANLIM TRADING SDN BHD is a
# customer AND two supplier records (403-H007, 400-H018). "PO for hanlim" read party_side=supplier and then asked
# "Which one do you mean?" over the two supplier records of one name. Records of one name are one supplier, as ledgers
# of one trading name are one customer (`chatbot_entity_kinds.family_grouping`, migration
# `sfam_0001_supplier_ledger_family`): the PO list runs for both, never asked.
# --------------------------------------------------------------------------- #

HANLIM_TRADING = "HANLIM TRADING SDN BHD"


def _hanlim_trading_world(session_factory) -> dict[str, Any]:
    ids = _office_world(session_factory)
    ids["hl_customer"] = _seed_customer(session_factory, HANLIM_TRADING)
    ids["hl_sup_a"] = _seed_named(session_factory, HANLIM_TRADING, "403-H007")
    ids["hl_sup_b"] = _seed_named(session_factory, HANLIM_TRADING, "400-H018")
    return ids


def _hanlim_trading_turn(session_factory, monkeypatch, text: str, hint: str, **parse):
    qf = _parser_output(
        entities=[{"raw": "hanlim", "hint": hint, "canonical_code": None, "current_message": True, "confident": True}],
        **parse,
    )
    return _span_turn(
        session_factory, monkeypatch, text, list_resolver.Span("hanlim", hint), {"hanlim", HANLIM_TRADING.casefold()},
        qf=qf, attributes=OWNER_GRANTS, party_side=True,
    )


_PO_ASK = dict(domain_hint="purchase_order", intent_hint="check_po", order_status=None, document=["PO"])
_OUTSTANDING_PO_AS_ORDER = dict(domain_hint="order", intent_hint="check_order", order_status="outstanding", document=[])


@pytest.mark.parametrize(
    "text,hint,parse",
    [
        ("PO for hanlim", "supplier", _PO_ASK),
        ("PO for hanlim", "customer", _PO_ASK),
        # Live run 3: party_side supplier, the entity hinted customer, the order domain's outstanding read.
        ("outstanding PO hanlim", "customer", _OUTSTANDING_PO_AS_ORDER),
        ("outstanding PO hanlim", "supplier", {**_PO_ASK, "order_status": "outstanding"}),
    ],
)
def test_po_for_a_supplier_of_two_records_of_one_name_lists_both_never_asked(
    session_factory, monkeypatch, text, hint, parse
):
    ids = _hanlim_trading_world(session_factory)
    reply, captured, _seen = _hanlim_trading_turn(session_factory, monkeypatch, text, hint, party_side="supplier", **parse)
    assert "Which one do you mean?" not in reply and "(customer)" not in reply, reply
    calls = _po_calls(captured)
    assert calls and sorted(calls[0].get("supplier_ids") or []) == sorted([ids["hl_sup_a"], ids["hl_sup_b"]]), (
        reply, captured,
    )
    assert not calls[0].get("customer_ids"), calls


def test_delivery_to_hanlim_trading_is_the_customer_never_asked(session_factory, monkeypatch):
    ids = _hanlim_trading_world(session_factory)
    reply, captured, _seen = _hanlim_trading_turn(
        session_factory, monkeypatch, "delivery to hanlim", "customer", party_side="customer",
        domain_hint="order", intent_hint="check_order", order_status=None, document=["DO"],
    )
    assert "Which one do you mean?" not in reply and "(supplier)" not in reply, reply
    assert HANLIM_TRADING in reply, reply
    assert not _po_calls(captured), (reply, captured)
    party = [a for n, a in captured if n in fetch_mod.SUPPLIER_GUARDED_TOOLS and n_party(a)]
    assert all(a.get("customer_ids") == [ids["hl_customer"]] for a in party), (reply, captured)


@pytest.mark.parametrize("said", ["unclear", None])
def test_bare_hanlim_trading_is_asked_customer_or_supplier_once(session_factory, monkeypatch, said):
    """Owner, 5 Nov: ask only when nothing in the message names a side. A bare name names none."""
    _hanlim_trading_world(session_factory)
    reply, captured, _seen = _hanlim_trading_turn(
        session_factory, monkeypatch, "hanlim", "customer", party_side=said,
        domain_hint="order", intent_hint="check_order", order_status=None,
    )
    assert "(customer)" in reply and "(supplier)" in reply, reply
    assert reply.count("(supplier)") == 1, reply
    assert not _fetch_calls(captured), (reply, captured)


def test_the_supplier_kind_groups_records_of_one_name():
    """The seed fallback and the migration agree: supplier records of one name are one family."""
    from app.services.chatbot.turn import policy_rows

    assert policy_rows.SUPPLIER_KIND_ROW["family_grouping"] == "ledger_family"


def test_a_customer_group_never_merges_two_suppliers_of_different_names():
    """Reviewer follow-up (#2120): the supplier family is the supplier's own trading name. A customer group that
    happens to list both names (customer rows of the same names) never makes two different suppliers one choice."""
    from app.services import ledger_family as lf
    from app.services.chatbot.turn import narrow
    from app.services.chatbot.turn.state import Focus, Profile

    rows = [
        {"uuid": str(uuid.uuid4()), "name": name, "canonical_code": name, "raw": name, "entity_type": "supplier"}
        for name in ("ZZT ALPHA SDN BHD", "ZZT BETA SDN BHD")
    ]
    focus = Focus(extra={"supplier": [{"raw": "zzt", "hint": "supplier", "current_message": True}]})
    with lf.customer_groups({"ZZT ALPHA SDN BHD": "ZZT GROUP", "ZZT BETA SDN BHD": "ZZT GROUP"}):
        outcome = narrow.decide(
            kind="supplier", policy_value="optional_filter", focus=focus, profile=Profile(),
            resolved_candidates=rows, family_grouping="ledger_family",
        )
    assert outcome.ask_kind == "supplier_pick", outcome
    assert sorted(o["label"] for o in outcome.ask_options) == ["ZZT ALPHA SDN BHD", "ZZT BETA SDN BHD"], outcome


# --------------------------------------------------------------------------- #
# SUPPLIER-PARTY-SIDE crew live re-run at 8b26ef80 (7 Nov 2026, dev copy sorento_prod_1104, parser v74 md5 d29c1983,
# gemini-3.5-flash-lite, 3 runs each): HANLIM is 7 customer ledgers and 2 supplier records. With party_side supplier and
# the word hinted customer, `apply.reconciled` was empty on all 6 PO turns: the untyped party read placed no single row,
# so nothing bound a supplier. Run 1 (span typed supplier) answered "Could not find purchase order for customer hanlim";
# runs 2 and 3 read the whole PO book with no supplier filter. The parser objects below are the live ones.
# --------------------------------------------------------------------------- #

HANLIM_LEDGERS = (
    HANLIM_TRADING, f"{HANLIM_TRADING} [A/C II]", "HANLIM ENTERPRISE", "HANLIM HARDWARE SDN BHD", "HANLIM (JB) SDN BHD",
    "HANLIM BUILDERS", "HANLIM TILES",
)
_LIVE_PO = dict(domain_hint="purchase_order", intent_hint="check_po", order_status=None, document=["PO"])
_LIVE_OUTSTANDING_PO = dict(domain_hint="order", intent_hint="check_po", order_status="outstanding", document=["PO"])


def _live_hanlim_world(session_factory) -> dict[str, Any]:
    ids = _office_world(session_factory)
    ids["ledgers"] = [_seed_customer(session_factory, name) for name in HANLIM_LEDGERS]
    ids["hl_sup_a"] = _seed_named(session_factory, HANLIM_TRADING, "403-H007")
    ids["hl_sup_b"] = _seed_named(session_factory, HANLIM_TRADING, "400-H018")
    return ids


def _live_turn(session_factory, monkeypatch, text: str, word: str, span_type: str | None, **parse):
    qf = _parser_output(
        entities=[{"raw": word, "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}],
        **parse,
    )
    near = {word, *(n.casefold() for n in HANLIM_LEDGERS)}
    return _span_turn(
        session_factory, monkeypatch, text, list_resolver.Span(word, span_type), near,
        qf=qf, attributes=OWNER_GRANTS, party_side=True,
    )


@pytest.mark.parametrize("span_type", ["customer", None, "supplier"])
@pytest.mark.parametrize(
    "text,parse",
    [
        ("PO for hanlim", _LIVE_PO),
        ("outstanding PO hanlim", _LIVE_OUTSTANDING_PO),  # live r1 / r3
        ("outstanding PO hanlim", {**_LIVE_PO, "order_status": "outstanding"}),  # live r2
    ],
)
def test_the_supplier_side_binds_the_supplier_over_many_customer_ledgers(
    session_factory, monkeypatch, text, parse, span_type
):
    ids = _live_hanlim_world(session_factory)
    reply, captured, _seen = _live_turn(
        session_factory, monkeypatch, text, "hanlim", span_type, party_side="supplier", **parse
    )
    assert "Which one do you mean?" not in reply and "for customer" not in reply, reply
    calls = _po_calls(captured)
    assert calls and sorted(calls[0].get("supplier_ids") or []) == sorted([ids["hl_sup_a"], ids["hl_sup_b"]]), (
        reply, captured,
    )
    assert not [n for n, a in captured if a.get("customer_ids")], captured


@pytest.mark.parametrize("said", ["supplier", "unclear", None])
@pytest.mark.parametrize("parse", [_LIVE_PO, {**_LIVE_PO, "order_status": "outstanding"}])
def test_the_po_book_never_lists_without_a_supplier_for_a_named_party(session_factory, monkeypatch, parse, said):
    """Crew rule B (7 Nov, live runs 2 and 3 read the whole PO book): with a party named, the PO tool never runs
    without supplier_ids. A word only a customer row places is "couldn't find a supplier", never the whole book."""
    ids = _live_hanlim_world(session_factory)
    only_customer = _seed_customer(session_factory, "ZZT QQCUST SDN BHD")
    reply, captured, _seen = _live_turn(
        session_factory, monkeypatch, "PO for qqcust", "qqcust", "customer", party_side=said, **parse
    )
    assert not [a for a in _po_calls(captured) if not a.get("supplier_ids")], (reply, captured)
    if said == "supplier":
        assert "couldn't find a supplier" in reply.lower() and "qqcust" in reply, reply
    assert only_customer not in str(captured) and ids["hl_sup_a"] not in str(captured), captured


def test_a_named_party_scopes_the_po_book_alone():
    """Crew rule B: a customer-hinted party of this message, and no supplier, scopes the PO book (only): an unfiltered
    PO list is refused with "couldn't find a supplier"; the customer's own lists run as before."""
    from types import SimpleNamespace

    from app.services.chatbot.engine import _supplier_scope

    verdict = {"entities": [{"raw": "hanlim", "hint": "customer", "current_message": True}]}
    state = SimpleNamespace(pending=None, focus=SimpleNamespace(extra={}))
    scope = _supplier_scope(state, state, verdict, ["purchase_order"], True)
    assert scope is not None and scope["tools"] == [PO_TOOL] and '"hanlim"' in scope["line"], scope
    trigger = {"tool": PO_TOOL, "entities": [], "contact_id": "c-1", "semantic_input": {"supplier_scope": scope}}
    with pytest.raises(fetch_mod.SupplierScopeViolation):
        fetch_mod.entity_ids_transformer(trigger, space_id=None)
    fetch_mod.entity_ids_transformer({**trigger, "tool": "crm_outstanding_report"}, space_id=None)  # customer side runs
    assert _supplier_scope(state, state, {"entities": []}, ["purchase_order"], True) is None
    assert _supplier_scope(state, state, verdict, ["purchase_order"], False) is None


def test_a_named_party_scopes_the_po_book_on_a_report_ask_turn_too():
    """Review S3 (#2120): a turn that also carries a report object keeps the PO book's guard."""
    from types import SimpleNamespace

    from app.services.chatbot.engine import _supplier_scope

    verdict = {
        "report_ask": {"company": None},
        "entities": [{"raw": "hanlim", "hint": "customer", "current_message": True}],
    }
    state = SimpleNamespace(pending=None, focus=SimpleNamespace(extra={}))
    scope = _supplier_scope(state, state, verdict, ["purchase_order"], True)
    assert scope is not None and scope["tools"] == [PO_TOOL], scope


def test_the_supplier_side_never_binds_a_name_the_report_object_holds():
    """Review S1 (#2120): REPORT-FILTER-ALL's rule holds on a supplier-side turn: a name the kept report object holds
    is never bound as a supplier."""
    from app.services.chatbot.engine import _SpanPrep, _side_suppliers
    from app.services.chatbot.head.lookup_lists import LookupRow

    prep = _SpanPrep.__new__(_SpanPrep)
    prep.supplier_ids, prep.message = True, "sorento PO"
    prep.rows = [LookupRow("supplier", "s2", "SORENTO KITCHEN SUPPLY", ("sorento kitchen supply",))]
    prep.supplier_groups = {"s9": [("s9", "NEAR (S9)")]}
    entity = {"raw": "Sorento", "hint": "customer", "canonical_code": None, "current_message": True}
    trace = SimpleNamespaceTrace()
    out = _side_suppliers({"party_side": "supplier", "entities": [entity]}, prep, trace, frozenset({"sorento"}))
    assert out["entities"][0] == entity, out
    kept = _side_suppliers({"party_side": "supplier", "entities": [entity]}, prep, trace)
    assert kept["entities"][0]["hint"] == "supplier" and kept["entities"][0]["canonical_code"] == "s2", kept
    prep.supplier_groups["s2"] = [("s2", "SORENTO KITCHEN SUPPLY (X)"), ("s7", "SORENTA (Y)")]
    _side_suppliers({"party_side": "supplier", "entities": [entity]}, prep, trace)
    assert ("s7", "SORENTA (Y)") in prep.supplier_groups["s2"], "the span pass's close rows are merged, never dropped"


class SimpleNamespaceTrace:
    def add(self, *_args, **_kwargs) -> None:
        return None


# --------------------------------------------------------------------------- #
# SUPPLIER-PARTY-SIDE crew live re-run 2 at 73e1c41a (7 Nov): whenever the parser hinted the word customer, the supplier
# never bound. (2) runs 2+3 "Could not find purchase order for customer hanlim"; (3) x3 stayed on the order domain
# ("Sales order or delivery order?"). Reproduced here with the span pass giving no supplier rows (`supplier_ids=False`):
# the side is the parser's top-level party_side (A2), a purchase order ask on the supplier side is the purchase_order
# domain whatever domain_hint says (A3), and a supplier-side miss never says "customer" (A4). Parser fields only.
# --------------------------------------------------------------------------- #


def _round2_turn(session_factory, monkeypatch, text: str, word: str, *, supplier_ids: bool, **parse):
    qf = _parser_output(
        entities=[{"raw": word, "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}],
        party_side="supplier", **parse,
    )
    return _span_turn(
        session_factory, monkeypatch, text, list_resolver.Span(word, "customer"), {word},
        qf=qf, attributes=OWNER_GRANTS, party_side=True, supplier_ids=supplier_ids,
    )


@pytest.mark.parametrize("supplier_ids", [True, False])
@pytest.mark.parametrize(
    "text,parse",
    [("PO for hanlim", _LIVE_PO), ("outstanding PO hanlim", _LIVE_OUTSTANDING_PO), ("PO for hanlim", _LIVE_OUTSTANDING_PO)],
)
def test_party_side_supplier_binds_the_supplier_whatever_the_hint(session_factory, monkeypatch, text, parse, supplier_ids):
    ids = _live_hanlim_world(session_factory)
    reply, captured, _seen = _round2_turn(session_factory, monkeypatch, text, "hanlim", supplier_ids=supplier_ids, **parse)
    assert "customer" not in reply.lower() and "Which one do you mean?" not in reply, reply
    calls = _po_calls(captured)
    assert calls and sorted(calls[0].get("supplier_ids") or []) == sorted([ids["hl_sup_a"], ids["hl_sup_b"]]), (
        reply, captured,
    )


@pytest.mark.parametrize("supplier_ids", [True, False])
@pytest.mark.parametrize("parse", [_LIVE_PO, _LIVE_OUTSTANDING_PO])
def test_a_supplier_side_miss_names_a_supplier_never_a_customer(session_factory, monkeypatch, parse, supplier_ids):
    _live_hanlim_world(session_factory)
    _seed_customer(session_factory, "ZZT QQCUST SDN BHD")
    reply, captured, _seen = _round2_turn(
        session_factory, monkeypatch, "outstanding PO qqcust", "qqcust", supplier_ids=supplier_ids, **parse
    )
    assert reply == 'Sorry, I couldn\'t find a supplier called "qqcust".', reply
    assert not [n for n, _a in captured], captured
