"""CHAT-STATE r7 v2 LAST-REFERENT (red): quote first, an open how-many outranks a newer list,
list rows (promotion / file / order) are pickable by number only when no question is open.

Owner 20 Oct ~07:55 (v1 "newest wins" withdrawn). UAC: chat-state-last-referent-r7-acceptance-criteria.md.
Audit row 6 shape: how-many for MKS9505-GM-HC asked (turn 1), dealer asks promotions, the bot lists two
promotion flyers (turn 3), dealer sends "1" (turn 4).

Real shapes used (AC-R7-9):
  * promotion item: MCP presenter `_promotions` (sorento_crm_mcp/sorento_crm_mcp/presenters.py:1051-1064)
    plus the planned top-level "id" (`_Builder.item(entity_id=...)`, presenters.py:287/:329);
    engine section = `Section(domain="promotion", figures=[item])` (turn/compose.py:49-54);
  * the quote: respond.io `message.replyTo` {id, sender.source, message.text} read by
    engine._reply_to_message_id / _quoted_context (engine.py:1186-1190, 1236-1238), resolved by
    quoted.resolve_quoted_turn (quoted.py:64-132) through ChatHistory(outgoing).chatbot_turn_id -> ChatbotTurn.trace
    "state" event {focus, open_question, turn_no};
  * the fetch: lanes/business/fetch.TYPE_TO_PARAM (promotion -> promotion_ids, order -> order_ids,
    attachment -> attachment_ids) via entity_ids_transformer.

Seams assumed: a stored `Focus.last_list` row carries `shown_at_turn`, `entity_type`, `uuid` (the row id);
`tail.last_list_after` takes a turn-number parameter; the State returned by `engine._quoted_context` carries
that the turn is a quoted reply (also when the quoted turn is the newest one and nothing differs from live).
"""
from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from app.models.chat_history import ChatHistory
from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot.turn import chat_state
from app.services.chatbot.turn import question as question_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.compose import Answer, Section
from app.services.chatbot.turn.pending import ask
from app.services.chatbot.turn.state import Focus, State, focus_to_wire
from tests._pg_fixture import blank_session
from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict
from tests.chatbot.test_engine import stub_access  # noqa: F401 - fixture used by name

DOMAINS = ["inventory", "incoming", "order", "sales", "product_attachment", "promotion"]
KINDS = ["product", "customer", "brand", "promotion", "attachment", "order"]
BRANDS = ["SORENTO", "MOCHA"]
CONTACT = "900000077"
CODE = "MKS9505-GM-HC"
FILE_1, FILE_2 = "Raya Promo A3.pdf", "Merdeka Promo A4.pdf"
PID_1, PID_2 = str(uuid.uuid5(uuid.NAMESPACE_URL, "zzt-r7/promo1")), str(uuid.uuid5(uuid.NAMESPACE_URL, "zzt-r7/promo2"))
HOWMANY_ID, FLYERS_ID = "ZZT-MID-HOWMANY", "ZZT-MID-FLYERS"


# ------------------------------------------------------------------------------------- shapes
def _promo_figure(name: str, pid: str | None) -> dict[str, Any]:
    item = {
        "title": name,
        "fields": [
            {"key": "company_name", "label": "Company", "value": "SORENTO"},
            {"label": "Promotion", "value": name},
            {"label": "Start Date", "value": "2026-10-01"},
            {"label": "End Date", "value": "2026-10-31"},
        ],
        "flags": {"expired": False},
    }
    if pid:
        item["id"] = pid
    return item


def _rows(kind: str, ids: tuple[str, str], names: tuple[str, str], shown_at: int) -> list[dict[str, Any]]:
    return [
        {"position": i, "label": n, "entity_type": kind, "uuid": u, "shown_at_turn": shown_at}
        for i, (n, u) in enumerate(zip(names, ids), 1)
    ]


def _promo_rows(shown_at: int) -> list[dict[str, Any]]:
    return _rows("promotion", (PID_1, PID_2), (FILE_1, FILE_2), shown_at)


def _owed_task(touched: int = 1):
    return ht.stock_task([(CODE, None)], opened_at_turn=touched, touched_at_turn=touched)


def _state(*, last_list=None, pending=None, tasks=(), products=(), turn_no=4, path=True) -> State:
    focus = Focus(products=ht.product_rows(*products), tasks=tuple(tasks), domains=["inventory"], last_list=last_list)
    return State(focus=focus, pending=pending, turn_no=turn_no, state_path=path)


def _op(op: str, position: int | None = None) -> dict[str, Any]:
    return {"op": op, "axis": None, "position": position}


def _open_question(state: State):
    return question_mod.open_question(state.pending, state.focus.tasks)


def _turn(state: State, v: dict[str, Any], monkeypatch):
    """The engine's order: the state applier (when the parser emitted ops), then the turn APPLY."""
    out_state, applied = state, None
    if v.get("state_changes") is not None:
        ran: list[int] = []
        real = chat_state.apply_changes

        def counted(*a, **k):
            ran.append(1)
            return real(*a, **k)

        monkeypatch.setattr(chat_state, "apply_changes", counted)
        applied = chat_state.apply_changes(
            state, v, open_question=_open_question(state), domains=DOMAINS, kinds=KINDS, brands=BRANDS,
            positions_read_elsewhere=False,
        )
        assert ran, "apply_changes never ran: the state path was not exercised"  # AC-R7-9
        out_state, v = applied.state, applied.verdict
    out_state, plan = apply(out_state, v, build_policy())
    return applied, out_state, v, plan


def _picked(v: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [e for e in v.get("entities") or [] if isinstance(e, dict) and e.get("hint") == kind]


def _stock_answered_with_one(out_state: State, v: dict[str, Any], plan) -> bool:
    if v.get("demand_qty") == 1 or "bare_number_is_the_quantity" in plan.trace.rules_fired:
        return True
    return any(s.value == 1 for t in out_state.focus.tasks or () if t.kind == "stock_qty" for s in t.slots)


# ------------------------------------------------------------------------- quote harness (real replyTo)
@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _stored_turn(db, *, reply: str, message_id: str, focus: Focus, turn_no: int, age_s: int):
    created = datetime.now(tz=timezone.utc) - timedelta(seconds=age_s)
    row = ChatbotTurn(
        id=str(uuid.uuid4()), contact_respond_id=CONTACT, message_id=f"ZZT-IN-{uuid.uuid4().hex[:8]}", envelope={},
        is_test=False, status="done", response={"reply": {"text": reply}},
        trace=[{"kind": "state", "focus": focus_to_wire(focus), "open_question": None, "turn_no": turn_no}],
        created_at=created, finished_at=created + timedelta(seconds=3),
    )
    db.add(row)
    db.add(ChatHistory(
        channel="whatsapp", contact_id=CONTACT, phone_number="+60160000577", message=reply,
        sent_at=(created + timedelta(seconds=3)).replace(tzinfo=None), type="outgoing", message_id=message_id,
        chatbot_turn_id=row.id,
    ))
    db.commit()


def _quote_envelope(reply_to_id: str, text: str):
    # respond.io webhook body as carried on the envelope: message.replyTo.{id, sender.source, message.text}
    return SimpleNamespace(message={"message": {"messageId": "ZZT-IN-NOW", "replyTo": {
        "id": reply_to_id, "sender": {"source": "workflow"}, "message": {"text": text}}}})


def _quoted(db, state_in: State, reply_to_id: str, text: str) -> State:
    from app.services.chatbot import engine

    out, _facts = engine._quoted_context(
        db, _quote_envelope(reply_to_id, text), contact_respond_id=CONTACT, dry_run=False, state_in=state_in,
        remembered_before={"focus": focus_to_wire(state_in.focus), "open_question": None},
    )
    return out


def _audit_row_6(db) -> State:
    """Turn 1 how-many; turn 3 flyer list; the live state at turn 4 is the flyer turn's."""
    asked = Focus(products=ht.product_rows(CODE), tasks=(_owed_task(1),), domains=["inventory"])
    _stored_turn(db, reply=f"How many units of {CODE}?", message_id=HOWMANY_ID, focus=asked, turn_no=1, age_s=300)
    listed = Focus(products=ht.product_rows(CODE), tasks=(_owed_task(1),), domains=["inventory", "promotion"],
                   last_list=_promo_rows(3))
    _stored_turn(db, reply=f"1. {FILE_1}\n2. {FILE_2}", message_id=FLYERS_ID, focus=listed, turn_no=3, age_s=100)
    return State(focus=listed, turn_no=4, state_path=True)


# --------------------------------------------------------------- AC-R7-1 no quote: today's rule (guard)
def test_r7_1_guard_no_quote_a_one_after_the_flyer_list_is_the_quantity(monkeypatch):
    state = _state(last_list=_promo_rows(3), tasks=(_owed_task(1),), products=(CODE,))
    v = verdict(reference_positions=[1], entities=[])
    _a, out_state, v, plan = _turn(state, v, monkeypatch)
    assert v.get("demand_qty") == 1, "the open how-many keeps the bare 1"
    assert not _picked(v, "promotion"), "no flyer may be picked without a quote"


# ------------------------------------------------------------- AC-R7-2 quote of the flyer list
def test_r7_2_quoting_the_flyer_list_picks_flyer_1_by_id_and_leaves_the_task(db, monkeypatch):
    from app.services.chatbot.lanes.business import fetch

    state = _quoted(db, _audit_row_6(db), FLYERS_ID, f"1. {FILE_1}\n2. {FILE_2}")
    v = verdict(reference_positions=[1], entities=[], state_changes=[_op("pick", 1)])
    applied, out_state, v, plan = _turn(state, v, monkeypatch)
    assert applied.valid, applied.log.get("rejected")
    promos = _picked(v, "promotion")
    assert [e.get("uuid") for e in promos] == [PID_1], ("flyer 1 must be picked by its id", promos)
    args = fetch.entity_ids_transformer({"entities": [{"entity_type": "promotion", "uuid": promos[0]["uuid"], "code": FILE_1}]})
    assert args["promotion_ids"] == [PID_1]
    assert not _stock_answered_with_one(out_state, v, plan), "the how-many must not take the 1"
    held = [t for t in out_state.focus.tasks if t.kind == "stock_qty"]
    assert held and all(s.value is None for t in held for s in t.slots)


# ------------------------------------------------------------- AC-R7-3 quote of the how-many
def test_r7_3_guard_quoting_the_how_many_a_one_is_the_quantity(db, monkeypatch):
    state = _quoted(db, _audit_row_6(db), HOWMANY_ID, f"How many units of {CODE}?")
    v = verdict(reference_positions=[1], entities=[])
    _a, out_state, v, plan = _turn(state, v, monkeypatch)
    assert v.get("demand_qty") == 1, "the quoted how-many decides: 1 is the quantity"
    assert not _picked(v, "promotion")


# --------------------------------------------------------------------- AC-R7-4 nothing open
ROW_KINDS = [
    ("promotion", "promotion", (FILE_1, FILE_2)),
    ("attachment", "attachment", ("Brochure A.pdf", "Brochure B.pdf")),
    ("order", "order", ("SO417636", "SO417637")),
]


@pytest.mark.parametrize("kind,bucket,names", ROW_KINDS, ids=[k[0] for k in ROW_KINDS])
def test_r7_4_nothing_open_a_two_picks_row_2_by_its_id(monkeypatch, kind, bucket, names):
    ids = (str(uuid.uuid4()), str(uuid.uuid4()))
    state = _state(last_list=_rows(kind, ids, names, 3), turn_no=4)
    v = verdict(reference_positions=[2], entities=[], state_changes=[_op("pick", 2)])
    applied, out_state, v, _plan = _turn(state, v, monkeypatch)
    assert applied.valid is True, applied.log.get("rejected")
    assert [e.get("uuid") for e in _picked(v, kind)] == [ids[1]], ("row 2 by its id", _picked(v, kind))
    held = [r.get("uuid") for r in out_state.focus.extra.get(bucket) or [] if isinstance(r, dict)]
    assert held == [ids[1]], (f"{kind} id must land on the {bucket} axis", held)


# ------------------------------------------------------- AC-R7-5 a question open, no quote
def _roster(asked_at: int):
    options = [
        {"position": 1, "label": "Acme Trading", "code": "C0001", "name": "Acme Trading", "entity_type": "customer", "payload": {}},
        {"position": 2, "label": "Beta Bhd", "code": "C0002", "name": "Beta Bhd", "entity_type": "customer", "payload": {}},
    ]
    return ask("customer_pick", options, asked_at_turn=asked_at)


def test_r7_5_guard_how_many_open_a_flyer_row_is_not_pickable_the_number_is_the_quantity(monkeypatch):
    state = _state(last_list=_promo_rows(3), tasks=(_owed_task(1),), products=(CODE,))
    _a, out_state, v, plan = _turn(state, verdict(reference_positions=[2], entities=[]), monkeypatch)
    assert v.get("demand_qty") == 2 and not _picked(v, "promotion")


@pytest.mark.parametrize("kind,bucket,names", ROW_KINDS, ids=[k[0] for k in ROW_KINDS])
def test_r7_5_guard_a_roster_open_the_number_answers_the_roster_not_the_list(monkeypatch, kind, bucket, names):
    ids = (str(uuid.uuid4()), str(uuid.uuid4()))
    state = _state(last_list=_rows(kind, ids, names, 4), pending=_roster(asked_at=2), turn_no=5)
    applied, _s, v, _p = _turn(state, verdict(reference_positions=[1], entities=[], state_changes=[_op("pick", 1)]), monkeypatch)
    assert (v.get("open_question_answer") or {}).get("picked") == [1], "the roster takes the number"
    assert not _picked(v, kind), "no list row may be picked while the roster is open"


@pytest.mark.parametrize("kind,bucket,names", ROW_KINDS, ids=[k[0] for k in ROW_KINDS])
def test_r7_5_a_pick_op_on_a_list_row_while_a_roster_is_open_is_refused_not_guessed(monkeypatch, kind, bucket, names):
    # position 3 exists only in the list (the roster has two options): it must not be picked.
    ids = (str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))
    rows = _rows(kind, ids[:2], names, 4) + [
        {"position": 3, "label": "third", "entity_type": kind, "uuid": ids[2], "shown_at_turn": 4}
    ]
    state = _state(last_list=rows, pending=_roster(asked_at=2), turn_no=5)
    applied = chat_state.apply_changes(
        state, verdict(reference_positions=[3], entities=[], state_changes=[_op("pick", 3)]),
        open_question=_open_question(state), domains=DOMAINS, kinds=KINDS, brands=BRANDS, positions_read_elsewhere=False,
    )
    assert applied.valid is False and not _picked(applied.verdict, kind)


# ---------------------------------------------------------------------------- AC-R7-6 keys
def _list_after(previous, *, question=None, sections=None, turn_no: int, need_turn: bool = True):
    from app.services.chatbot.turn.tail import last_list_after

    kwargs: dict[str, Any] = {"question": question, "sections": sections if sections is not None else []}
    turn_params = [p for p in inspect.signature(last_list_after).parameters if "turn" in p]
    if turn_params:
        kwargs[turn_params[0]] = turn_no
    elif need_turn:
        pytest.fail("tail.last_list_after takes no turn number: the list cannot be stamped shown_at_turn")
    return last_list_after(previous, **kwargs)


def test_r7_6_a_promotion_row_carries_kind_promotion_and_the_promotion_id():
    section = Section(domain="promotion", figures=[_promo_figure(FILE_1, PID_1), _promo_figure(FILE_2, PID_2)])
    rows = _list_after(None, sections=[section], turn_no=3, need_turn=False)
    assert [(r.get("entity_type"), r.get("uuid")) for r in rows] == [("promotion", PID_1), ("promotion", PID_2)]


def test_r7_6_a_file_row_carries_its_attachment_id():
    aid = str(uuid.uuid4())
    section = Section(domain="product_attachment", figures=[], files=[
        {"id": aid, "url": "http://cdn/x/A.pdf", "filename": "A.pdf", "mimeType": "application/pdf"},
    ])
    rows = _list_after(None, sections=[section], turn_no=3, need_turn=False)
    assert [(r.get("entity_type"), r.get("uuid")) for r in rows or []] == [("attachment", aid)]


def test_r7_6_an_order_row_carries_its_order_id():
    oid = str(uuid.uuid4())
    fig = {"id": oid, "title": "SO417636", "fields": [{"key": "order_number", "label": "Order Number", "value": "SO417636"}]}
    rows = _list_after(None, sections=[Section(domain="order", figures=[fig])], turn_no=3, need_turn=False)
    assert [(r.get("entity_type"), r.get("uuid")) for r in rows or []] == [("order", oid)]


@pytest.mark.parametrize("kind", ["promotion", "attachment", "order"])
def test_r7_6_guard_a_row_with_no_id_is_never_picked(monkeypatch, kind):
    rows = [{"position": 1, "label": "something", "entity_type": kind, "shown_at_turn": 3}]
    applied, *_ = _turn(_state(last_list=rows, turn_no=4), verdict(state_changes=[_op("pick", 1)]), monkeypatch)
    assert applied.valid is False and applied.log["rejected"]


def test_r7_6_guard_the_row_id_is_never_printed_in_the_state_block():
    state = _state(last_list=_promo_rows(3), turn_no=4)
    text = chat_state.render(chat_state.view(state, None)) or ""
    assert PID_1 not in text and PID_2 not in text and FILE_1 in text


# ---------------------------------------------------------------------------- AC-R7-7 stamp
def _stamps(rows) -> set:
    return {r.get("shown_at_turn") for r in rows or []}


def test_r7_7_a_list_carries_the_turn_that_showed_it():
    section = Section(domain="promotion", figures=[_promo_figure(FILE_1, PID_1), _promo_figure(FILE_2, PID_2)])
    assert _stamps(_list_after(_promo_rows(2), sections=[section], turn_no=5)) == {5}


def test_r7_7_a_turn_showing_nothing_keeps_the_list_and_its_stamp():
    old = _promo_rows(2)
    rows = _list_after(old, sections=[Section(domain="inventory", figures=[])], turn_no=6)
    assert rows == old and _stamps(rows) == {2}


def test_r7_7_a_questions_options_keep_the_questions_turn_on_every_pass():
    q = ask("customer_pick", _roster(2).options, asked_at_turn=2)
    first = _list_after(None, question=q, turn_no=2)
    again = _list_after(None, question=q, turn_no=5)
    assert first == again and _stamps(again) == {2}, ("same input must give the same focus", _stamps(again))


# ------------------------------------------------------------------------------ AC-R7-8 state off
def test_r7_8_guard_state_off_records_no_list():
    from app.services.chatbot.turn import tail

    state = _state(last_list=None, path=False, turn_no=3)
    answer = Answer(sections=[Section(domain="promotion", figures=[_promo_figure(FILE_1, PID_1), _promo_figure(FILE_2, PID_2)])])
    assert "last_list" not in tail.session_payload(state, answer, SimpleNamespace())["focus"]


def test_r7_8_guard_state_off_the_legacy_bare_number_rule_is_unchanged():
    state = _state(last_list=_promo_rows(3), tasks=(_owed_task(1),), products=(CODE,), path=False)
    v = verdict(reference_positions=[1], entities=[])
    _out, plan = apply(state, v, build_policy())
    assert v.get("demand_qty") == 1 and "bare_number_is_the_quantity" in plan.trace.rules_fired


# =============================================================================================
# AC-R7-2, live shape: what the PARSER READS when the dealer quotes the flyer-list turn.
# The parser decides from its input; if the input still carries the held how-many it reads "1" as
# demand_qty and the held task takes it. Through the real `engine.run_turn` (EngineConsole: real engine,
# real quote resolution, stubbed parser + stock tool; `console.last_block` is the exact user block the parser
# got). The held product is ELP3754 (a code the console seeds) standing in for MKS9505-GM-HC.
# =============================================================================================
HELD = "ELP3754"
FLYER_TEXT = f"1. {FILE_1}\n2. {FILE_2}"
LIST_TURN = 3


def _with_state_block(monkeypatch):
    import dataclasses

    from app.services.chatbot.head import parser as parser_mod

    real = parser_mod.resolve_config

    def with_state(db, *, current_date, override_version_id=None):
        return dataclasses.replace(real(db, current_date=current_date, override_version_id=override_version_id), state_block=True)

    monkeypatch.setattr(parser_mod, "resolve_config", with_state)


def _audit_console(session_factory, monkeypatch, stub_access, phone):
    from tests.chatbot.test_quoted_reply_engine import (
        _console, _focus_wire, _live_c, _store_asked, _store_turn, _task_wire, ask_text,
    )
    from tests.chatbot._r9_engine_console import stock, product

    c = _console(session_factory, monkeypatch, stub_access, phone)
    _with_state_block(monkeypatch)
    _store_asked(c, HELD, turn_no=1, age_s=900)  # the how-many turn
    listed = _focus_wire(c, HELD, [_task_wire(c, HELD)])
    listed["last_list"] = _promo_rows(LIST_TURN)
    _store_turn(c, reply_text=FLYER_TEXT, focus=listed, turn_no=LIST_TURN, age_s=800)  # the flyer-list turn
    assert c.say(f"check stock {HELD}", stock(product(HELD))) == ask_text(HELD)  # live: the how-many is open
    c.state["focus"]["last_list"] = _promo_rows(LIST_TURN)  # live: the flyer list is stored too
    return c


def _lines(block: str, *prefixes: str) -> list[str]:
    return [ln for ln in block.splitlines() if ln.startswith(prefixes)]


def test_r7_2_live_a_quote_of_the_list_turn_hides_the_held_how_many_from_the_parser_input(
    session_factory, monkeypatch, stub_access
):
    from tests.chatbot.test_quoted_reply_engine import reply, say_quoted

    c = _audit_console(session_factory, monkeypatch, stub_access, "+60900000771")
    say_quoted(c, "1", reply(reference_positions=[1], entities=[]), quote=FLYER_TEXT)
    block = c.last_block
    # State block on: the how-many reaches the parser as the State block's `open question` object and the
    # `pending task: the open question` line (the Open task / Open question lines are folded into it, context.py:394).
    assert not _lines(block, "Open task:", "Open question:")
    oq = _lines(block, "- open question:")
    assert not any("quantities" in ln or HELD in ln for ln in oq), ("the held how-many is still the open question", oq)
    assert "pending task: the open question" not in block, "the State block still prints the how-many as THE open question"
    # Held is not hidden: the quantities object (owed [1]) must not reach the parser at all, or it reads "1" as demand_qty.
    assert '"kind": "quantities"' not in block and '"owed"' not in block, (
        "the quantities / how-many object is still in the parser input", _lines(block, "- pending task:")
    )


def test_r7_2_live_a_quote_of_the_list_turn_shows_the_flyer_list_as_the_open_list(
    session_factory, monkeypatch, stub_access
):
    from tests.chatbot.test_quoted_reply_engine import reply, say_quoted

    c = _audit_console(session_factory, monkeypatch, stub_access, "+60900000772")
    say_quoted(c, "1", reply(reference_positions=[1], entities=[]), quote=FLYER_TEXT)
    last = _lines(c.last_block, "- last list")
    assert last and FILE_1 in last[0] and FILE_2 in last[0], ("the State block must list the flyers", last)
    assert "- open question: none" in c.last_block or "- open question: {" not in c.last_block


def test_r7_2_live_guard_no_quote_the_how_many_object_is_in_the_parser_input(session_factory, monkeypatch, stub_access):
    from tests.chatbot._r9_engine_console import reply

    c = _audit_console(session_factory, monkeypatch, stub_access, "+60900000773")
    c.say("1", reply(demand_qty=1, entities=[]))
    assert any("quantities" in ln and HELD in ln for ln in _lines(c.last_block, "- open question:")), c.last_block
    assert "pending task: the open question" in c.last_block


def test_r7_3_live_guard_a_quote_of_the_how_many_turn_keeps_the_how_many_object(session_factory, monkeypatch, stub_access):
    from tests.chatbot.test_quoted_reply_engine import ask_text, reply, say_quoted

    c = _audit_console(session_factory, monkeypatch, stub_access, "+60900000774")
    say_quoted(c, "1", reply(demand_qty=1, entities=[]), quote=ask_text(HELD))
    assert any("quantities" in ln and HELD in ln for ln in _lines(c.last_block, "- open question:")), c.last_block
    assert "pending task: the open question" in c.last_block


def test_r7_2_live_apply_a_quote_of_the_list_turn_with_a_bare_demand_qty_does_not_fill_the_held_task(
    session_factory, monkeypatch, stub_access
):
    # The parser read "1" as demand_qty (no entity, no positions). NOTE: if the parser input no longer shows the
    # how-many this reading should not occur; this pins the apply side for the case it still does (see report).
    from tests.chatbot.test_quoted_reply_engine import _answered, _open_task_labels, reply, say_quoted

    c = _audit_console(session_factory, monkeypatch, stub_access, "+60900000775")
    text = say_quoted(c, "1", reply(demand_qty=1, entities=[]), quote=FLYER_TEXT)
    assert text != _answered(HELD, 1), ("the held task took the bare 1 under a quote of the list turn", text)
    assert _open_task_labels(c) == [HELD], "the stock task must stay open and unanswered"
