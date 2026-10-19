"""CHAT-STATE round 6, S3 (red): held-family narrowing, the scheme index and the class decisions
read the parser's OPS, not entity-hint heuristics (UAC AC-S3-1..3; plan ARCHITECTURE item 4).

#1755's own definitions of R6-3 (NAMES-OWN-CLASS-AT-EVERY-SEAM) and R6-4 (a type-only follow-up
keeps the held product) are not in this tree's docs or tests (grep of documentation/plans and
tests/chatbot finds only the round 6 plan/UAC); the semantics below are taken from the UAC lines:
  * R6-4 / AC-S3-2: a follow-up that asks only for a file type or a type word keeps the held
    product; no empty described set runs. The op (`keep`, or `set` on the attachment type) says so.
  * R6-3 / AC-S3-3: a message whose ops make a class its subject (`new_subject`, or `set` on the
    class axis) is about that class: held-family narrowing does not run, the scheme index does not
    index the held products, an open task does not resume over the old products.
Lead decision, 20 Oct, CHAT-STATE r6 S3 (class membership comes from the data): `new_subject` means
the message is about the new class. A `set` on the class axis is a REFINE: held explicit products
that ARE members of that class stay the subject; held products of another class drop, and the
subject becomes the class predicate with the other held axes (brand / spec) kept.

Driven as in the closed-lists suites (`closed_lists` gate, dry-run mock emissions carrying
`state_changes`, so the state path is on); a counter proves `apply_changes` ran every turn.
"""
from __future__ import annotations

import json

import pytest

from app.models.chatbot_turn import ChatbotTurn
from tests.chatbot._family_code_seed import seed_rows
from tests.chatbot.test_chat_state_r3a_fetch_quantity import _family_turn, _fetched, _reply
from tests.chatbot.test_chat_state_seam import _op
from tests.chatbot.test_closed_lists_scheme_index import (  # noqa: F401 - fixtures used by name
    CODE, PRODUCT, _file_ask, _file_fetches, _message, _scheme, _seed,
)
from tests.chatbot.test_engine import _parser_output, seeded, stub_access  # noqa: F401
from tests.chatbot.test_chat_state_r4_held_family_code import (
    COLOUR_REG, SRTWC286_ROWS, DECOYS, TRAP_REG, _spec, _verdict,
)


@pytest.fixture()
def applied(monkeypatch):
    """Counts `apply_changes` calls: a turn that never reached the state path fails loudly."""
    from app.services.chatbot.turn import chat_state

    real, ran = chat_state.apply_changes, []

    def counted(*a, **k):
        ran.append(1)
        return real(*a, **k)

    monkeypatch.setattr(chat_state, "apply_changes", counted)
    return ran


def _turns(session_factory, stub_access, monkeypatch, turns):
    """The scheme suite's multi-turn driver with the State prompt on (`state_block`), so the
    parser's `state_changes` reach the applier."""
    from app.services.ai_assistant_service import MCPRuntimeClient
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.head import parser as parser_mod
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests.chatbot.test_engine import _envelope

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(system_prompt="stub", prompt_version=1, provider="openai", model="m",
                                       api_key="k", closed_lists=True, state_block=True)

    queue = [v for _t, v in turns]
    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: queue.pop(0))
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(MCPRuntimeClient, "call_tool",
                        lambda self, name, args: calls.append((name, args)) or json.dumps({"ok": True, "items": []}))
    stub_access()
    out = []
    for n, (text, _v) in enumerate(turns):
        calls.clear()
        out.append((engine_mod.run_turn(_envelope(message=_message(text, n)), session_factory=session_factory), list(calls)))
    return out


def _trace_text(session_factory, out) -> str:
    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == out.turn_id).first()
    return json.dumps(row.trace or [], default=str)


def _ent(raw: str, hint: str, **extra):
    return {"raw": raw, "hint": hint, "canonical_code": None, "current_message": True, "confident": True, **extra}


def _stock_first():
    return _parser_output(intent_hint="check_stock", domain_hint="inventory", user_goal="stock", entities=[PRODUCT],
                          state_changes=[_op("set", "product")])


# --------------------------------------------------------------------------- AC-S3-2 (R6-4)
def _cert_type():
    """The listed file type the seeded product holds ("ZZT Certification"), as the closed lists pick it."""
    return {"raw": "certificate", "hint": "attachment_type", "canonical_code": "ZZT Certification",
            "listed_item": "ZZT Certification", "current_message": True, "confident": True}


TYPE_ONLY = [("en", "the certificate?"), ("bm", "sijil dia?"), ("zh", "那个证书呢")]


@pytest.mark.parametrize("message", [m for _i, m in TYPE_ONLY], ids=[i for i, _m in TYPE_ONLY])
@pytest.mark.parametrize("ops,entities", [
    ([_op("keep")], lambda: [_cert_type()]),
    ([_op("set", "attachment_type")], lambda: [_cert_type()]),
], ids=["keep-with-a-type-word", "set-attachment-type"])
def test_r6_s3_a_type_only_follow_up_keeps_the_held_product(session_factory, seeded, stub_access, monkeypatch, applied,
                                                            message, ops, entities):
    ids = _seed(session_factory)
    ask = _file_ask(*entities())
    ask["state_changes"] = ops
    (_r1, _c1), (_r2, calls) = _turns(session_factory, stub_access, monkeypatch, [(CODE, _stock_first()), (message, ask)])
    assert len(applied) >= 2, "the state path did not run"
    fetches = _file_fetches(calls)
    assert fetches and fetches[0].get("product_ids") == [ids["product"]], ("the held product was dropped", calls)


# --------------------------------------------------------------------------- AC-S3-3 (R6-3)
CLASS_OPS = [([_op("new_subject")], "new_subject"), ([_op("set", "category")], "set-category")]


def _label_class(session_factory, ids, label="Water Closet"):
    """The held product's category carries the class label the data decides membership by."""
    from sqlalchemy import text

    db = session_factory()
    db.execute(text("UPDATE product_categories SET class_label = :l WHERE id = "
                    "(SELECT category_id FROM products WHERE id = :p)"), {"l": label, "p": ids["product"]})
    db.commit()


def _scheme_turn(session_factory, stub_access, monkeypatch, class_word, ops, ids_label="Water Closet"):
    ids = _seed(session_factory)
    _label_class(session_factory, ids, ids_label)
    ask = _file_ask(_ent(class_word, "category"), _scheme("zzpps", "ZZPPS"))
    ask["state_changes"] = ops
    (_r1, _c1), (_r2, calls) = _turns(session_factory, stub_access, monkeypatch,
                                      [(CODE, _stock_first()), (f"zzpps certificate {class_word}", ask)])
    return ids, _file_fetches(calls), calls


def test_r6_s3_new_subject_naming_a_class_is_not_about_the_held_products_scheme_seam(
    session_factory, seeded, stub_access, monkeypatch, applied
):
    ids, fetches, calls = _scheme_turn(session_factory, stub_access, monkeypatch, "water closet", [_op("new_subject")])
    assert len(applied) >= 2
    assert all(f.get("product_ids") != [ids["product"]] for f in fetches), ("the held product was indexed", calls)


def test_r6_s3_a_class_set_over_a_held_member_of_that_class_is_a_refine_and_keeps_it(
    session_factory, seeded, stub_access, monkeypatch, applied
):
    ids, fetches, calls = _scheme_turn(session_factory, stub_access, monkeypatch, "water closet", [_op("set", "category")])
    assert len(applied) >= 2
    assert fetches and fetches[0].get("product_ids") == [ids["product"]], ("the held member was dropped", calls)


def test_r6_s3_a_class_set_over_a_held_product_of_another_class_drops_it(
    session_factory, seeded, stub_access, monkeypatch, applied
):
    ids, fetches, calls = _scheme_turn(session_factory, stub_access, monkeypatch, "basin", [_op("set", "category")])
    assert len(applied) >= 2
    assert all(f.get("product_ids") != [ids["product"]] for f in fetches), ("the held WC was indexed for a basin ask", calls)


@pytest.mark.parametrize("ops", [c[0] for c in CLASS_OPS], ids=[c[1] for c in CLASS_OPS])
def test_r6_s3_a_message_naming_its_own_class_does_not_narrow_the_held_family(
    session_factory, seeded, stub_access, monkeypatch, applied, ops
):
    ids = seed_rows(session_factory, SRTWC286_ROWS + DECOYS, registry=TRAP_REG)
    v = _verdict(_spec("p trap", "trap_type", "p_trap"))
    v["entities"] = [_ent("water closet", "category"), *v["entities"]]
    v["state_changes"] = [*ops, _op("set", "specification")]
    out, calls = _family_turn(session_factory, stub_access, monkeypatch, "p trap water closets", ids, "SRTWC286-SH", 10, v)
    assert applied, "the state path did not run"
    assert '"held_family"' not in _trace_text(session_factory, out), "held-family narrowing ran over a message naming its class"
    assert _fetched(calls) != {ids["SRTWC286-SH-P"], ids["SRTWC286-SH-NEW-P"]}, calls


@pytest.mark.parametrize("ops", [c[0] for c in CLASS_OPS], ids=[c[1] for c in CLASS_OPS])
def test_r6_s3_a_message_naming_its_own_class_does_not_resume_the_open_task(
    session_factory, seeded, stub_access, monkeypatch, applied, ops
):
    ids = seed_rows(session_factory, SRTWC286_ROWS, registry=TRAP_REG)
    v = _parser_output(intent_hint="check_stock", domain_hint="inventory", user_goal="basin",
                       entities=[_ent("basin", "category")], state_changes=ops)
    out, calls = _family_turn(session_factory, stub_access, monkeypatch, "basins please", ids, "SRTWC286-SH", 10, v)
    assert applied
    assert "task_resumed" not in _trace_text(session_factory, out)
    assert not _fetched(calls) & set(ids.values()), ("the old products were fetched for a new class", calls)


# --------------------------------------------------------------------------- AC-S3-1
def test_r6_s3_a_spec_set_over_held_products_narrows_the_held_family(session_factory, seeded, stub_access, monkeypatch, applied):
    ids = seed_rows(session_factory, SRTWC286_ROWS + DECOYS, registry=TRAP_REG)
    v = _verdict(_spec("p trap", "trap_type", "p_trap"))
    v["state_changes"] = [_op("set", "specification")]
    out, calls = _family_turn(session_factory, stub_access, monkeypatch, "How about p trap", ids, "SRTWC286-SH", 10, v)
    assert applied
    assert _fetched(calls) == {ids["SRTWC286-SH-P"], ids["SRTWC286-SH-NEW-P"]}, (calls, _reply(out))


@pytest.mark.parametrize("message", ["how about p trap", "ada p trap tak", "有P trap的吗"])
def test_r6_s3_the_same_spec_under_new_subject_does_not_narrow_the_held_family(
    session_factory, seeded, stub_access, monkeypatch, applied, message
):
    ids = seed_rows(session_factory, SRTWC286_ROWS + DECOYS, registry=TRAP_REG)
    v = _verdict(_spec("p trap", "trap_type", "p_trap"))
    v["state_changes"] = [_op("new_subject")]
    out, calls = _family_turn(session_factory, stub_access, monkeypatch, message, ids, "SRTWC286-SH", 10, v)
    assert applied
    assert '"held_family"' not in _trace_text(session_factory, out), "held-family narrowing ran under new_subject"
    assert _fetched(calls) != {ids["SRTWC286-SH-P"], ids["SRTWC286-SH-NEW-P"]}, calls


# --------------------------------------------------------------------------- static
def test_r6_s3_names_own_class_is_deleted_from_its_seams():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot"
    for rel in ("turn/task.py", "head/scheme_index.py", "head/held_family.py", "engine.py"):
        assert "names_own_class" not in (root / rel).read_text(), f"{rel} still reads names_own_class"


# --------------------------------------------------------------------------- review round 4 (lead decision):
# a class SAID this message over held explicit products filters them by class membership WHATEVER the op.
SAID_CLASS_OPS = [
    ([_op("keep")], "keep"),
    ([_op("answer")], "answer"),
    ([_op("set", "no_such_axis")], "reject"),
]


def _scheme_with_ops(session_factory, stub_access, monkeypatch, class_word, ops):
    ids = _seed(session_factory)
    _label_class(session_factory, ids, "Water Closet")
    ask = _file_ask(_ent(class_word, "category"), _scheme("zzpps", "ZZPPS"))
    ask["state_changes"] = ops
    if ops[0]["op"] == "answer":
        ask["open_question_answer"] = {"mode": "value", "picked": [], "items": [], "qty_for_all": None}
    (_r1, _c1), (_r2, calls) = _turns(session_factory, stub_access, monkeypatch,
                                      [(CODE, _stock_first()), (f"zzpps certificate {class_word}", ask)])
    return ids, _file_fetches(calls), calls


@pytest.mark.parametrize("ops", [c[0] for c in SAID_CLASS_OPS], ids=[c[1] for c in SAID_CLASS_OPS])
def test_r6_s3_a_said_class_the_held_product_is_not_in_does_not_index_it_whatever_the_op(
    session_factory, seeded, stub_access, monkeypatch, applied, ops
):
    ids, fetches, calls = _scheme_with_ops(session_factory, stub_access, monkeypatch, "basin", ops)
    assert all(f.get("product_ids") != [ids["product"]] for f in fetches), ("the held WC was indexed for a basin ask", calls)


@pytest.mark.parametrize("ops", [c[0] for c in SAID_CLASS_OPS], ids=[c[1] for c in SAID_CLASS_OPS])
def test_r6_s3_a_said_class_the_held_product_is_a_member_of_still_indexes_it(
    session_factory, seeded, stub_access, monkeypatch, applied, ops
):
    ids, fetches, calls = _scheme_with_ops(session_factory, stub_access, monkeypatch, "water closet", ops)
    assert fetches and fetches[0].get("product_ids") == [ids["product"]], ("the held member was dropped", calls)


# --------------------------------------------------------------------------- kept_aside after grounding
def test_r6_s3_a_word_set_aside_under_keep_stays_set_aside_after_grounding_rewrites_it():
    from app.services.chatbot.turn import chat_state
    from app.services.chatbot.turn.state import Focus, State

    held = {"raw": "Wash Basin", "canonical_code": None, "hint": "product_type", "current_message": False, "confident": True}
    focus = Focus(domains=["inventory"], extra={"product_type": [held]})
    typed = {"raw": "washbasin", "hint": "product_type", "canonical_code": "wash_basin", "current_message": True, "confident": True}
    out = chat_state.apply_changes(State(focus=focus, turn_no=3), {"state_changes": [_op("keep")], "entities": [typed],
                                   "domain_hint": "inventory", "intent_hint": "check_stock"},
                                   open_question=None, domains=["inventory"], kinds=["product_type"], brands=[],
                                   positions_read_elsewhere=False)
    assert out.valid, out.log
    # grounding (head/grounding.py ~806 / ~819) replaces the typed name with the listed / canonical one
    from app.services.chatbot.turn.chat_state import KEPT_ASIDE

    assert all(KEPT_ASIDE not in e for e in (typed,)), "the applier mutated its INPUT verdict's entity"
    applied_entity = out.verdict["entities"][0]
    grounded = {**applied_entity, "raw": "Wash Basin", "canonical_code": None}
    ents = chat_state.fetch_entities(out.state.subject, {"entities": [grounded]}, out.state.focus, unsettled_only=False)["entities"]
    riding = [e for e in ents if e.get("current_message") is not False and e.get("hint") == "product_type"]
    assert not riding, ("the keep's word rode along after grounding rewrote it", riding)


# --------------------------------------------------------------------------- _class_members: unknown keeps the held set
def test_r6_s3_a_said_class_that_resolves_to_no_category_keeps_the_held_set(session_factory):
    from app.models.base import set_company_scope
    from app.services.chatbot.engine import _class_members
    from app.services.company_scope import DEFAULT_COMPANY_ID

    ids = seed_rows(session_factory, [("ZZTCM-A", "ZZTCMA", "trap_type", "s_trap")], registry=TRAP_REG)
    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    held = [ids["ZZTCM-A"]]
    assert _class_members(db, [{"value": "zzqxunknownclassword", "key": None, "hint": "category"}], held) == set(held)


def test_r6_s3_a_class_row_whose_key_resolves_when_its_value_does_not_uses_the_key(session_factory):
    from app.models.base import set_company_scope
    from app.services.chatbot.engine import _class_members
    from app.services.company_scope import DEFAULT_COMPANY_ID

    wc = seed_rows(session_factory, [("ZZTCM-W", "ZZTCMW", "trap_type", "s_trap")], registry=TRAP_REG, class_label="Water Closet")
    basin = seed_rows(session_factory, [("ZZTCM-B", "ZZTCMB", "trap_type", "s_trap")], class_label="Basin")
    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    held = [wc["ZZTCM-W"], basin["ZZTCM-B"]]
    row = {"value": "zzqxunknownclassword", "key": "Water Closet", "hint": "category", "canonical_code": "Water Closet"}
    assert _class_members(db, [row], held) == {wc["ZZTCM-W"]}


# --------------------------------------------------------------------------- held_family_landed: Subject and focus agree
def test_r6_s3_after_a_held_family_landing_the_next_fetch_holds_only_the_matched_members():
    from app.services.chatbot.turn import chat_state
    from app.services.chatbot.turn.state import Focus, State

    old = [{"raw": f"OLD{i}", "canonical_code": f"OLD{i}", "hint": "product", "uuid": f"0000000{i}-0000-0000-0000-000000000000",
            "described_set": True, "current_message": False} for i in range(2)]
    focus = Focus(products=old, domains=["inventory"])
    state = State(focus=focus, turn_no=3)
    out = chat_state.apply_changes(state, {"state_changes": [_op("keep")], "entities": [], "domain_hint": "inventory",
                                           "intent_hint": "check_stock"}, open_question=None, domains=["inventory"],
                                   kinds=["product"], brands=[], positions_read_elsewhere=False)
    assert out.valid, out.log
    landed, verdict2 = chat_state.held_family_landed(out.state, out.verdict, ["SRTWC286-SH-P", "SRTWC286-SH-NEW-P"])
    ents = chat_state.fetch_entities(landed.subject, {"entities": []}, landed.focus, unsettled_only=False)["entities"]
    codes = {str(e.get("canonical_code") or e.get("raw")) for e in ents if e.get("hint") == "product"}
    assert codes == {"SRTWC286-SH-P", "SRTWC286-SH-NEW-P"}, ("old described_set rows ride beside the matched tokens", codes)


# --------------------------------------------------------------------------- review round 5
def _keep_applied():
    from app.services.chatbot.turn import chat_state
    from app.services.chatbot.turn.state import Focus, State

    held = {"raw": "Wash Basin", "canonical_code": None, "hint": "product_type", "current_message": False, "confident": True}
    typed = {"raw": "washbasin", "hint": "product_type", "canonical_code": "wash_basin", "current_message": True, "confident": True}
    inp = {"state_changes": [_op("keep")], "entities": [typed], "domain_hint": "inventory", "intent_hint": "check_stock"}
    out = chat_state.apply_changes(State(focus=Focus(domains=["inventory"], extra={"product_type": [held]}), turn_no=3), inp,
                                   open_question=None, domains=["inventory"], kinds=["product_type"], brands=[],
                                   positions_read_elsewhere=False)
    assert out.valid, out.log
    return inp, out


def test_r6_s3_the_applier_never_mutates_its_input_verdict():
    from app.services.chatbot.turn.chat_state import KEPT_ASIDE

    inp, out = _keep_applied()
    assert not any(KEPT_ASIDE in e for e in inp["entities"]), ("input entity marked in place", inp["entities"])


def test_r6_s3_no_internal_mark_reaches_the_stored_clarify_session():
    from app.services.chatbot import turn_runtime
    from app.services.chatbot.turn.chat_state import KEPT_ASIDE

    _inp, out = _keep_applied()
    carried = turn_runtime.set_clarify_carry(out.verdict, {"unknown_values": [{"said": "zz", "known": ["a", "b"]}]}, None)
    assert carried and carried["ask"]["entities"], carried
    assert not any(KEPT_ASIDE in e for e in carried["ask"]["entities"]), ("the mark leaks into the session", carried)
    assert KEPT_ASIDE not in json.dumps(out.state.focus.__dict__, default=str)


def test_r6_s3_after_a_held_family_landing_the_open_stock_task_points_only_at_the_matched_members():
    from app.services.chatbot.turn import chat_state, task as task_mod
    from app.services.chatbot.turn.state import Focus, State

    rows = [{"raw": f"OLD{i}", "canonical_code": f"OLD{i}", "hint": "product", "uuid": f"0000000{i}-0000-0000-0000-000000000000",
             "current_message": False} for i in range(2)]
    task = task_mod.Task(kind="stock_qty", domain="inventory", status=task_mod.OPEN,
                         slots=tuple(task_mod.Slot(r["uuid"], r["canonical_code"], None) for r in rows))
    out = chat_state.apply_changes(State(focus=Focus(products=rows, domains=["inventory"], tasks=(task,)), turn_no=3),
                                   {"state_changes": [_op("keep")], "entities": [], "domain_hint": "inventory",
                                    "intent_hint": "check_stock"}, open_question=None, domains=["inventory"],
                                   kinds=["product"], brands=[], positions_read_elsewhere=False)
    assert out.valid, out.log
    matched = ["SRTWC286-SH-P", "SRTWC286-SH-NEW-P"]
    landed, _v = chat_state.held_family_landed(out.state, out.verdict, matched)
    labels = {sl.label for t in landed.focus.tasks for sl in t.slots}
    assert labels <= set(matched), ("the open task still points at the old held products", labels)
