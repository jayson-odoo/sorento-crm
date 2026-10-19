# CHAT-STATE: the one explicit conversation state the parser is shown and answers.
#
# `view` / `render` state the focus, the open question, the last list and the pending task
# as a fixed four line block. `apply_changes` validates the parser's `state_changes` and
# carries the prior state accordingly (CARRY only: what this message names is still
# written by `apply._focus_rules`). Pure: no I/O, no word of the customer's message is
# ever read here; an op carries no value, the value is the parse's own existing field.
from __future__ import annotations

import copy
import json
from datetime import date
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from app.services.chatbot.turn import question as question_mod
from app.services.chatbot.turn import task as task_mod
from app.services.chatbot.turn.pending import ESCALATION_OFFER_KINDS
from app.services.chatbot.turn.pending import ask as pending_ask
from app.services.chatbot.turn.pending import option_entities
from app.services.chatbot.turn.state import Focus, State, Subject

OPS: tuple[str, ...] = (
    "keep", "new_subject", "set", "clear", "pick", "answer", "switch_domain", "close_question",
)

#: The fixed axes; every `policy.kinds` kind is an axis too.
FIXED_AXES: tuple[str, ...] = (
    "product", "customer", "warehouse", "brand", "tier", "channel", "period", "status", "document", "sort", "quantity",
)

#: Subject keys the State block prints that only a `clear` can act on.
CLEAR_ONLY_AXES: tuple[str, ...] = ("domain", "report", "relation")

#: Owner ruling 16 Oct 2026 ~23:00 (R16): a follow-up keeps the held period; a new subject keeps
#: it too unless the parser says `skip` / `clear` / `set` for the period. The one spot.
NEW_SUBJECT_KEEPS_PERIOD = True

#: R15: what an `unclear` held slot does when the held entity's type cannot settle it. "ask"
#: raises one real-name question; "assume" applies the slot. Storage is undecided (owner), so
#: the default sits behind one function.
UNCLEAR_SLOT_DEFAULT = "ask"

#: R15: the held entity's registry kind settles an unclear customer slot: a customer (debtor)
#: means delivery. A supplier kind does not exist in `chatbot_entity_kinds` today.
KIND_DOMAIN: dict[str, str] = {"customer": "order"}

#: The slots the parser states per message.
SLOT_AXES: tuple[str, ...] = ("customer", "period")
SLOT_OPS: tuple[str, ...] = ("keep", "skip", "clear", "unclear")

#: The question this module raises for an unclear period (a Pending kind of its own).
PERIOD_ASK = "period_ask"
CUSTOMER_ASK = "held_customer_ask"
_SLOT_ASKS = (PERIOD_ASK, CUSTOMER_ASK)


def unclear_slot_default() -> str:
    return UNCLEAR_SLOT_DEFAULT

#: Axes tied to the domain they were asked in; a domain switch drops them.
_DOMAIN_BOUND = (
    "status", "document", "sort", "sales_channel", "top_selling", "sales_ranking_frame", "low_stock", "set_page",
)

#: Keys that are machine identity, never printed.
_HIDDEN_KEYS = frozenset({"uuid", "uuids", "id", "key", "payload"})



# --------------------------------------------------------------------------- #
# view / render
# --------------------------------------------------------------------------- #


def _is_key(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        UUID(value.strip())
    except ValueError:
        return False
    return True


def _clean(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return None if not text or _is_key(text) else text


def _plain(value: Any) -> Any:
    """A copy with machine identity (keys, uuid-shaped strings) taken out."""
    if isinstance(value, dict):
        return {
            k: _plain(v) for k, v in value.items()
            if k not in _HIDDEN_KEYS and not _is_key(v) and _plain(v) not in (None, "", [], {})
        }
    if isinstance(value, (list, tuple)):
        return [p for p in (_plain(v) for v in value if not _is_key(v)) if p not in (None, "", [], {})]
    return value


def _names(rows: Any, *order: str) -> list[str]:
    out: list[str] = []
    for row in rows or ():
        if isinstance(row, dict):
            text = next((t for t in (_clean(row.get(k)) for k in order) if t), None)
        else:
            text = _clean(row)
        if text and text not in out:
            out.append(text)
    return out


def _products(rows: Any) -> list[str]:
    out: list[str] = []
    for row in rows or ():
        name = next(iter(_names([row], "canonical_code", "raw", "name")), None)
        if not name:
            continue
        qty = row.get("quantity") if isinstance(row, dict) else None
        out.append(f"{name} x{qty:g}" if isinstance(qty, (int, float)) and not isinstance(qty, bool) else name)
    return out


def _pairs(slot: Any) -> str | None:
    """A report slot as `key value` pairs, scalars only, machine identity left out."""
    if not isinstance(slot, dict):
        return None
    parts = []
    for key, value in _plain(slot).items():
        if isinstance(value, (list, tuple)):
            value = ",".join(str(v) for v in value if isinstance(v, (str, int, float)))
        if isinstance(value, (str, int, float, bool)) and value != "":
            parts.append(f"{key} {value}")
    return ", ".join(parts) or None


def _subject(focus: Focus) -> dict[str, Any]:
    out: dict[str, Any] = {
        "domain": _names([{"d": d} for d in focus.domains or ()], "d"),
        "customer": _names(focus.customers, "name", "raw", "canonical_code"),
        "product": _products(focus.products),
        "warehouse": _names(focus.warehouse, "name", "raw", "canonical_code"),
        "brand": _names(focus.brands),
        "tier": _names(focus.tier),
        "channel": _clean(focus.sales_channel),
        "period": [
            t for t in (_clean((focus.date_window or {}).get(k)) for k in ("start", "end")) if t
        ] if isinstance(focus.date_window, dict) else [],
        "status": _clean(focus.status),
        "document": _names(focus.document),
        "sort": [
            t for t in (_clean((focus.sort or {}).get(k)) for k in ("by", "dir")) if t
        ] if isinstance(focus.sort, dict) else [],
        "report": [
            f"{label} {pairs}".strip()
            for label, pairs in (
                ("top_selling", _pairs(focus.top_selling)),
                ("sales_ranking_frame", _pairs(focus.sales_ranking_frame)),
                ("low_stock", _pairs(focus.low_stock)),
            )
            if pairs or (label == "top_selling" and focus.status == "top_selling")
        ],
        "relation": _clean(focus.relation),
    }
    for kind, rows in sorted((focus.extra or {}).items()):
        names = _names(rows, "name", "raw", "canonical_code")
        if names and kind not in out:
            out[kind] = names
    return {k: v for k, v in out.items() if v}


def _list_item(row: dict[str, Any]) -> dict[str, Any] | None:
    position = row.get("position")
    if not isinstance(position, int) or isinstance(position, bool):
        return None
    item: dict[str, Any] = {"position": position}
    code, label = _clean(row.get("code")), _clean(row.get("label"))
    if code:
        item["code"] = code
    if label and label != code:
        item["label"] = label
    return item


def _same_list(items: list[dict[str, Any]], oq: dict[str, Any] | None) -> bool:
    options = (oq or {}).get("options")
    if not options:
        return False
    def key(row: dict[str, Any]) -> tuple[Any, Any]:
        return row.get("position"), row.get("code") or row.get("label")
    return {key(i) for i in items} == {key(o) for o in options if isinstance(o, dict)}


#: The `offer` value of a roster that carries a stamped hand-over offer.
HAND_OVER_OFFER = "hand_over"


def _offer_just_made(pending: Any, turn_no: int | None) -> bool:
    """An answered roster whose LAST reply offered the hand-over: the stamp (the miss path's
    own turn; a roster without one shows no offer) is the turn before this
    one. A fresh roster, or a flag left by an earlier turn, is not an offer."""
    payload = getattr(pending, "payload", None) or {}
    if not payload.get("escalate_offered") or not payload.get("answered_positions"):
        return False
    stamp = payload.get("offered_at_turn")
    return isinstance(stamp, int) and isinstance(turn_no, int) and stamp == turn_no - 1


def _open_question(focus: Focus, oq: dict[str, Any] | None, pending: Any = None, turn_no: int | None = None) -> dict[str, Any] | None:
    obj = _plain(oq) if oq else {}
    if obj and pending is not None and getattr(pending, "kind", None) in ESCALATION_OFFER_KINDS:
        # A hand-over offer states its kind and the team it would go to (a name, never an id),
        # so a yes or a no can be read as accepting or declining it.
        obj["offer"] = pending.kind
        team = _clean(getattr(pending, "team", None))
        if team:
            obj["hand_over_to"] = team.replace("_", " ")
    elif obj and pending is not None and _offer_just_made(pending, turn_no):
        # An answered roster the reply followed with a hand-over offer (contract 36 keeps the
        # roster stored, stamped): the open question is that offer, not a pick still owed.
        obj["offer"] = HAND_OVER_OFFER
        obj["owed"] = ["yes_no"]
        team = _clean(getattr(pending, "team", None))
        if team:
            obj["hand_over_to"] = team.replace("_", " ")
    extras: dict[str, Any] = {}
    if focus.set_clarify:
        extras["clarify"] = _plain(focus.set_clarify)
    if _offered_brands(focus):
        extras["other_brands"] = _plain(_offered_brands(focus))
    asked = (focus.top_selling or {}).get("asked") if isinstance(focus.top_selling, dict) else None
    if asked:
        extras["asked"] = _plain(asked)
    extras = {k: v for k, v in extras.items() if v}
    if not obj and not extras:
        return None
    if not obj:
        obj = {"kind": question_mod.FREE, "owed": ["answer"]}
    return {**obj, **extras}


def view(state: State, open_question: dict[str, Any] | None) -> dict[str, Any]:
    """The state as one plain, key-free dict: what the parser is shown and what the trace logs."""
    focus = state.focus
    oq = _open_question(focus, open_question, state.pending, state.turn_no)
    items = [i for i in (_list_item(r) for r in (focus.last_list or []) if isinstance(r, dict)) if i]
    stock_is_question = question_mod.is_the_stock_question(open_question)
    task = None if stock_is_question else task_mod.open_question(focus.tasks)
    return {
        "subject": _subject(focus),
        "open_question": oq,
        "last_list": items or None,
        "last_list_is_question": bool(items) and _same_list(items, oq) and (oq or {}).get("offer") != HAND_OVER_OFFER,
        "task": _plain(task) if task else None,
        "task_is_question": stock_is_question,
    }


def _list_text(items: list[dict[str, Any]]) -> str:
    return "; ".join(
        " ".join(str(p) for p in (i["position"], i.get("code"), i.get("label")) if p is not None)
        for i in items
    )


def _subject_text(subject: dict[str, Any]) -> str:
    parts = []
    for key, value in subject.items():
        if key == "period" and value:
            value = [" to ".join(value)]
        elif key == "sort":
            value = [" ".join(value)]
        joined = ', '.join(value) if isinstance(value, list) else value
        # The held domain is the domain that was answered last.
        parts.append(f"domain {joined} (answered)" if key == "domain" else f"{key} {joined}")
    return "; ".join(parts)


def render(v: dict[str, Any]) -> str | None:
    """The fixed four line block, or None when the state is empty (nothing is added)."""
    if not (v["subject"] or v["open_question"] or v["last_list"] or v["task"] or v["task_is_question"]):
        return None
    subject = f"- subject: {_subject_text(v['subject'])}" if v["subject"] else "- subject: none"
    oq = v["open_question"]
    question = "- open question: " + (json.dumps(oq, ensure_ascii=False) if oq else "none")
    items = v["last_list"]
    if not items:
        last = "- last list: none"
    else:
        domain = ", ".join(v["subject"].get("domain") or [])
        head = f"- last list ({domain + ', ' if domain else ''}{len(items)}): "
        last = head + ("the open question's options" if v["last_list_is_question"] else _list_text(items))
    if v["task_is_question"]:
        task = "- pending task: the open question"
    elif v["task"]:
        task = "- pending task: " + json.dumps(v["task"], ensure_ascii=False)
    else:
        task = "- pending task: none"
    return "\n".join(["State:", subject, question, last, task])


# --------------------------------------------------------------------------- #
# apply_changes
# --------------------------------------------------------------------------- #


@dataclass
class Applied:
    valid: bool
    state: State
    verdict: dict[str, Any]
    log: dict[str, Any]


def _entities(verdict: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in (verdict.get("entities") or []) if isinstance(e, dict)]


def _named_kinds(verdict: dict[str, Any]) -> set[str]:
    return {
        str(e.get("hint")) for e in _entities(verdict)
        if e.get("hint") and e.get("current_message") is not False
    }


def _has_field(verdict: dict[str, Any], axis: str) -> bool:
    """Does this message's own parse carry a value for the axis (one value, one place)?"""
    if axis == "tier":
        return bool(verdict.get("access_levels")) or "tier" in _named_kinds(verdict)
    if axis == "channel":
        return bool(verdict.get("sales_channel"))
    if axis == "period":
        return any(verdict.get(k) for k in ("date_mode", "date_filter_start", "date_filter_end"))
    if axis == "status":
        return any(verdict.get(k) for k in ("status", "order_status"))
    if axis == "document":
        return bool(verdict.get("document"))
    if axis == "sort":
        return bool(verdict.get("sort_by") or verdict.get("sort_dir"))
    if axis == "quantity":
        return verdict.get("demand_qty") is not None or any(e.get("quantity") is not None for e in _entities(verdict))
    return axis in _named_kinds(verdict)


def _message_domains(verdict: dict[str, Any]) -> list[str]:
    asks = [a.get("domain") for a in (verdict.get("asks") or []) if isinstance(a, dict) and a.get("domain")]
    if asks:
        return asks
    return [verdict["domain_hint"]] if verdict.get("domain_hint") else []


def _held_quantity(focus: Focus) -> tuple[dict[str, Any], Any]:
    """The quantity of an answered stock check, per product code, and the one quantity all
    of them share (None when they differ or none was answered)."""
    by_code: dict[str, Any] = {}
    for task in focus.tasks or ():
        if getattr(task, "kind", None) == "stock_qty" and getattr(task, "status", None) == task_mod.ANSWERED:
            for slot in task.slots:
                if isinstance(slot.value, (int, float)) and not isinstance(slot.value, bool):
                    by_code[str(slot.label).casefold()] = slot.value
    for row in focus.products:
        if isinstance(row, dict) and row.get("quantity") is not None:
            by_code.setdefault(str(row.get("canonical_code") or row.get("raw") or "").casefold(), row["quantity"])
    values = set(by_code.values())
    return by_code, (next(iter(values)) if len(values) == 1 else None)


#: The verdict key carrying the held quantities that reach this turn's stock fetch.
CARRIED_QUANTITY_KEY = "_carried_quantity"


def carry_onto_family(verdict: dict[str, Any], codes: list[str]) -> dict[str, Any]:
    """A refine of the same held subject landing on several family codes: the one held
    quantity rides onto each (owner: "don't re-ask what the user gave"). No-op when
    `apply_changes` carried no shared quantity."""
    carry = verdict.get(CARRIED_QUANTITY_KEY)
    if not isinstance(carry, dict) or carry.get("shared") is None:
        return verdict
    by_code = {**(carry.get("by_code") or {}), **{str(c).casefold(): carry["shared"] for c in codes}}
    return {**verdict, CARRIED_QUANTITY_KEY: {**carry, "by_code": by_code}}


def _clear_axis(focus: Focus, axis: str) -> None:
    if axis == "channel":
        focus.sales_channel = None
    elif axis == "period":
        focus.date_window = None
    elif axis == "status":
        focus.status = None
    elif axis == "document":
        focus.document = []
    elif axis == "domain":
        focus.domains = []
    elif axis == "report":
        focus.top_selling = focus.sales_ranking_frame = focus.low_stock = None
    elif axis == "relation":
        focus.relation = None
    elif axis == "sort":
        focus.sort = None
    elif axis == "tier":
        focus.tier = []
    elif axis == "brand":
        focus.brands = []
    elif axis == "quantity":
        for row in focus.products:
            row.pop("quantity", None)
        # The answered check's quantity goes with it.
        focus.tasks = tuple(
            t for t in focus.tasks or ()
            if not (getattr(t, "kind", None) == "stock_qty" and getattr(t, "status", None) == task_mod.ANSWERED)
        )
    elif axis in ("product", "customer", "warehouse"):
        setattr(focus, {"product": "products", "customer": "customers", "warehouse": "warehouse"}[axis], [])
    else:
        focus.extra.pop(axis, None)


def _write_set(focus: Focus, axis: str, verdict: dict[str, Any]) -> None:
    """The scalar axes a `set` writes onto the focus; entity axes are written by the
    existing kind rules from the parse's entities."""
    if axis in ("category", "product_type"):
        # The class is ONE axis held in two buckets: a newly set class replaces both.
        _clear_axis(focus, "category")
        _clear_axis(focus, "product_type")
    elif axis in ("product", "customer", "warehouse", "brand") or axis in (focus.extra or {}):
        # The stated entities replace the held value of this axis; the kind rules write them.
        _clear_axis(focus, axis)
    elif axis == "channel":
        focus.sales_channel = verdict.get("sales_channel")
    elif axis == "sort":
        focus.sort = {k: verdict.get(f"sort_{k}") for k in ("by", "dir") if verdict.get(f"sort_{k}")}
    elif axis == "status":
        focus.status = verdict.get("status") or verdict.get("order_status") or focus.status
    elif axis == "document":
        focus.document = list(verdict.get("document") or [])
    elif axis == "period":
        window = {k: verdict.get(f"date_filter_{k}") for k in ("start", "end") if verdict.get(f"date_filter_{k}")}
        if window:
            focus.date_window = window
    elif axis == "tier":
        if verdict.get("access_levels"):
            focus.tier = [t for t in verdict["access_levels"] if isinstance(t, str)]


def _drop_domain_bound(focus: Focus) -> None:
    # The held period is not domain bound (R16): it carries across a switch unless the parser
    # says `skip` / `clear` period.
    for name in _DOMAIN_BOUND:
        setattr(focus, name, [] if name == "document" else None)


def _reject(
    state: State, verdict: dict[str, Any], log: dict[str, Any], reasons: list[dict[str, Any]], brands: list[Any]
) -> Applied:
    """An invalid change set changes nothing: the State is the input's, every held axis stays
    held, and what this message typed is said on its axis (the same Subject a `keep` gives)."""
    log["rejected"] = reasons
    out = {k: v for k, v in verdict.items() if k != "state_changes"}
    subject = _build_subject(state, state.focus, out, brands, None)
    log["subject"] = subject_wire(subject)
    return Applied(False, replace(state, subject=subject), out, log)


def _brand_words(brands: list[Any]) -> set[str]:
    """The registry's brand names and codes, folded; rows may be plain strings or
    `{brand_name, brand_code}` dicts."""
    words: set[str] = set()
    for brand in brands or ():
        values = [brand] if isinstance(brand, str) else [brand.get("brand_name"), brand.get("brand_code")] if isinstance(brand, dict) else []
        words.update(str(v).strip().casefold() for v in values if v)
    return words


def _held(focus: Focus, axis: str) -> bool:
    """Does the focus hold anything on this axis (a `clear` of nothing is invalid)?"""
    if axis == "customer":
        return bool(focus.customers)
    if axis == "period":
        return bool(focus.date_window)
    if axis == "channel":
        return bool(focus.sales_channel)
    if axis == "status":
        return bool(focus.status)
    if axis == "document":
        return bool(focus.document)
    if axis == "domain":
        return bool(focus.domains)
    if axis == "report":
        return bool(focus.top_selling or focus.sales_ranking_frame or focus.low_stock)
    if axis == "relation":
        return bool(focus.relation)
    if axis == "sort":
        return bool(focus.sort)
    if axis == "tier":
        return bool(focus.tier)
    if axis == "brand":
        return bool(focus.brands)
    if axis == "quantity":
        return any(isinstance(r, dict) and r.get("quantity") is not None for r in focus.products) or bool(
            _held_quantity(focus)[0]
        )
    if axis == "product":
        return bool(focus.products)
    if axis == "warehouse":
        return bool(focus.warehouse)
    return bool((focus.extra or {}).get(axis))


def _day(value: Any) -> str | None:
    try:
        return date.fromisoformat(str(value)).strftime("%d/%m/%Y")
    except ValueError:
        return _clean(value)


def _window_label(window: dict[str, Any]) -> str:
    bounds = [d for d in (_day(window.get("start")), _day(window.get("end"))) if d]
    return " to ".join(bounds) or "the same period"


def _period_ask(state: State, window: dict[str, Any], domain: str | None) -> Any:
    options = [
        {"position": 1, "label": _window_label(window), "entity_type": "period", "payload": {"window": dict(window)}},
        {"position": 2, "label": "Another period", "entity_type": "period", "payload": {"window": None}},
    ]
    return pending_ask(
        PERIOD_ASK, options, asked_at_turn=state.turn_no, expects="pick",
        payload={"domain": domain, "slot": "period"},
    )


def _customer_ask(state: State, rows: list[dict[str, Any]], domain: str | None) -> Any:
    name = next(iter(_names(rows, "name", "raw", "canonical_code")), None) or "The same customer"
    options = [
        {"position": 1, "label": name, "entity_type": "customer", "payload": {"keep": True}},
        {"position": 2, "label": "All customers", "entity_type": "customer", "payload": {"keep": False}},
    ]
    return pending_ask(
        CUSTOMER_ASK, options, asked_at_turn=state.turn_no, expects="pick",
        payload={"domain": domain, "slot": "customer"},
    )


def _hand_over(state: State) -> Any:
    option = {
        "position": 1, "label": "Customer service", "entity_type": "team",
        "payload": {"team": "customer_service", "agent": None, "brand_code": None},
    }
    return pending_ask(
        "team_pick", [option], team="customer_service", expects="yes_no", asked_at_turn=state.turn_no,
        payload={"agent": None, "brand_code": None},
    )


def _offered_brands(focus: Focus) -> list[Any]:
    """The brands the last set answer offered. The writer stores the offer at
    `set_page["set_key"]["other_brands"]` (`turn_runtime`, the set page writer)."""
    page = focus.set_page if isinstance(focus.set_page, dict) else {}
    key = page.get("set_key")
    return list(key.get("other_brands") or []) if isinstance(key, dict) else []


def offered_brand_picks(state: State, verdict: dict[str, Any], brands: list[Any] | None = None) -> list[str]:
    """Every offered brand the parser's own brand entities name, in order. An entity's code or
    raw is compared to the offer's registry values (a code maps through `brands` to its name
    first); no word of the message is read."""
    offered = {
        str(o.get("brand") or "").strip().casefold(): str(o.get("brand") or "").strip()
        for o in _offered_brands(state.focus)
        if isinstance(o, dict)
    }
    offered.pop("", None)
    if not offered:
        return []
    # The set's own brand is pickable beside an offered one ("sorento and cabana" over a
    # Sorento set that offers Cabana).
    own = ((state.focus.set_page or {}).get("set_key") or {}).get("brand")
    if isinstance(own, str) and own.strip():
        offered.setdefault(own.strip().casefold(), own.strip())
    name_of_code = {
        str(b.get("brand_code")).strip().casefold(): str(b.get("brand_name")).strip().casefold()
        for b in brands or ()
        if isinstance(b, dict) and b.get("brand_code") and b.get("brand_name")
    }
    picks: list[str] = []
    for e in _entities(verdict):
        if e.get("hint") != "brand" or e.get("current_message") is False:
            continue
        for value in (e.get("canonical_code"), e.get("raw")):
            key = str(value or "").strip().casefold()
            hit = offered.get(key) or offered.get(name_of_code.get(key, ""))
            if hit:
                if hit not in picks:
                    picks.append(hit)
                break
    return picks


def narrow_held_to_brands(state: State, wanted: list[str], brand_of: dict[str, str]) -> State:
    """The state with the held products (and the slots a task still collects for them) kept
    only where `brand_of[uuid]` is one of `wanted` (the union); a row whose brand is unknown
    goes with the rest. Nothing held, or nothing of those brands held: unchanged."""
    want = {w.strip().casefold() for w in wanted}
    keep = lambda row: brand_of.get(str(row.get("uuid") or ""), "").strip().casefold() in want  # noqa: E731
    rows = [r for r in state.focus.products if isinstance(r, dict)]
    kept = [r for r in rows if keep(r)]
    if not rows or not kept:
        return state
    return _held_narrowed(state, kept)


def _held_narrowed(state: State, kept: list[dict[str, Any]]) -> State:
    """The State with only the `kept` held product rows, the slots a task still collects
    narrowed with them, and the Subject's held products read again off that focus (AC-S1-8:
    a later change to the State rebuilds the Subject here, so it never goes stale)."""
    keys = {str(r.get("uuid")) for r in kept if r.get("uuid")}
    tasks = tuple(
        replace(t, slots=tuple(sl for sl in t.slots if str(sl.key) in keys)) if t.slots else t
        for t in state.focus.tasks or ()
    )
    focus = replace(state.focus, products=kept, tasks=tasks)
    subject = state.subject
    if subject is not None and subject.provenance.get("product") == "held":
        ids = tuple(str(r["uuid"]) for r in kept if r.get("uuid") and r.get("described_set") is not True)
        tokens = tuple(t for t in (_token_row(r) for r in kept if not r.get("uuid")) if t)
        provenance = dict(subject.provenance)
        if not (ids or tokens or any(r.get("uuid") for r in kept)):
            provenance.pop("product")
        source = "ids" if ids else "unresolved" if tokens else "predicate" if subject.predicate else "unresolved"
        subject = replace(subject, source=source, product_ids=ids, product_tokens=tokens, provenance=provenance)
    return replace(state, focus=focus, subject=subject)


def pick_offered_brands(
    state: State, verdict: dict[str, Any], picked: list[str], brand_of: dict[str, str]
) -> tuple[State, dict[str, Any]]:
    """R4-A through the Subject (AC-S3-4): brands picked off the last answer's offer, with
    `brand_of` the brand of each held product (read by the engine). Every named brand the held
    set holds, and the held rows are the whole set: the held products narrow to the union of
    those brands, the Subject with them. Otherwise (a named brand the held set lacks, or a set
    longer than its held rows) one re-run of the offered set with every named brand
    (`set_brand_chosen`), the message's own words off the verdict."""
    from app.services.chatbot.turn_runtime import SET_BRAND_KEY

    held_keys = [str(r["uuid"]) for r in held_products(state)]
    held_brands = {v.strip().casefold() for v in brand_of.values()}
    hits = [b for b in picked if b.casefold() in held_brands]
    total = int(((state.focus.set_page or {}).get("set_key") or {}).get("total") or 0)
    if hits and len(hits) == len(picked) and not total > len(held_keys):
        return narrow_held_to_brands(state, hits, brand_of), verdict
    return state, {
        **verdict,
        SET_BRAND_KEY: list(picked),
        "entities": [
            e for e in verdict.get("entities") or [] if not (isinstance(e, dict) and e.get("current_message") is True)
        ],
        "reference_positions": [],
    }


def class_set_over_held(state: State) -> list[dict[str, Any]]:
    """The class rows a refine `set` over held explicit products (lead decision, S3): the engine
    reads which held products are members of that class. Empty when the rule does not apply."""
    subject = state.subject
    if (
        subject is None or state.state_led != "refine" or subject.provenance.get("class") != "said"
        or subject.provenance.get("product") != "held" or not subject.product_ids
    ):
        return []
    return list(subject.predicate.get("class") or [])


def keep_class_members(state: State, members: set[str]) -> State:
    """Lead decision S3 (card R1; membership read from the data): a `set` on the class axis is a
    refine over the held explicit products. The members of the said class stay the subject;
    the others drop, and with none left the subject is the class predicate with the other held
    axes kept. A described set's members and a held token are not explicit products here."""
    rows = [r for r in state.focus.products if isinstance(r, dict)]
    kept = [r for r in rows if not (r.get("uuid") and r.get("described_set") is not True) or str(r["uuid"]) in members]
    return state if len(kept) == len(rows) else _held_narrowed(state, kept)


def held_products(state: State, *, for_family: bool = False) -> list[dict[str, Any]]:
    """The focus rows the Subject holds as its products (its held ids and a described set's
    members): what the held-family narrowing and the scheme index read on the state path. None
    when the product axis is not held (said, or dropped by `new_subject` / a class set over
    other classes). The held-family narrowing (`for_family`) never runs when the class axis
    was said: a message naming its own class is about that class (AC-S3-3)."""
    subject = state.subject
    if subject is None or subject.provenance.get("product") != "held":
        return []
    if for_family and subject.provenance.get("class") == "said":
        return []
    keys = set(subject.product_ids)
    return [
        r for r in state.focus.products
        if isinstance(r, dict) and r.get("uuid") and (str(r["uuid"]) in keys or r.get("described_set") is True)
    ]


def held_family_landed(state: State, verdict: dict[str, Any], matched: list[str]) -> tuple[State, dict[str, Any]]:
    """SPEC-OVER-HELD on the state path (AC-S3-4): the family members a said spec landed on are
    the held subject now (tokens keyed by their codes, placed by the settle step), and the one
    held quantity rides onto each (R3-A, `carry_onto_family`)."""
    subject = state.subject
    if subject is None or not matched:
        return state, verdict
    tokens = tuple({"value": c, "key": c, "hint": "product"} for c in dict.fromkeys(matched))
    subject = replace(
        subject, source="unresolved", product_ids=(), product_tokens=tokens,
        provenance={**subject.provenance, "product": "held"},
    )
    return replace(state, subject=subject), carry_onto_family(verdict, matched)


def _focus_questions(focus: Focus) -> bool:
    """A question the focus itself holds for one turn: a clarify, the other-brands offer, a
    top selling question."""
    return bool(
        focus.set_clarify
        or _offered_brands(focus)
        or (isinstance(focus.top_selling, dict) and focus.top_selling.get("asked"))
    )


def _pickable(row: dict[str, Any]) -> bool:
    # A stored row names its kind; only product rows are pickable (a row written before the
    # kind was stored has none and reads as a product).
    return bool(row.get("code")) and row.get("entity_type", "product") == "product"


def set_aside(state: State, slots: dict[str, str]) -> State:
    """The slots the parser said `skip` for, taken off the focus for this turn and kept on
    the state so the tail can put them back. The stored focus never loses them."""
    aside: dict[str, Any] = {}
    focus = copy.deepcopy(state.focus)
    if slots.get("customer") == "skip" and focus.customers:
        aside["customers"], focus.customers = focus.customers, []
    if slots.get("period") == "skip" and focus.date_window:
        aside["date_window"], focus.date_window = focus.date_window, None
    return replace(state, focus=focus, held_aside=aside) if aside else state


def restored(state: State) -> State:
    """The state with the set-aside slots back on the focus (unless the turn wrote its own)."""
    aside = getattr(state, "held_aside", None)
    if not aside:
        return state
    focus = copy.deepcopy(state.focus)
    if aside.get("customers") and not focus.customers:
        focus.customers = aside["customers"]
    if aside.get("date_window") and not focus.date_window:
        focus.date_window = aside["date_window"]
    return replace(state, focus=focus, held_aside=None)


_CLASS_HINTS = ("category", "product_type")
_SUBJECT_AXIS = {"brand": "brand", "category": "class", "product_type": "class", "specification": "spec"}
_PREDICATE_AXES = ("brand", "class", "spec")
#: The fields a typed predicate row keeps from its entity, so the fetch can hand the row to the
#: resolver as it was said or held (a grounded spec keeps its registry key and value).
_ROW_FIELDS = ("uuid", "canonical_code", "spec_key", "spec_value", "spec_unit", "spec_label", "spec_words", "spec_known")


def _typed_row(entity: dict[str, Any], hint: str) -> dict[str, Any] | None:
    """One typed predicate row (AC-S1-7): the word as said or held, its registry key (the uuid,
    else the code; None for a bare word), the kind, and the entity's own grounding fields."""
    value = str(entity.get("raw") or entity.get("canonical_code") or "").strip()
    if not value:
        return None
    row: dict[str, Any] = {"value": value, "key": entity.get("uuid") or entity.get("canonical_code") or None, "hint": hint}
    row.update({k: entity[k] for k in _ROW_FIELDS if entity.get(k) is not None})
    return row


def _held_rows(focus: Focus) -> dict[str, list[dict[str, Any]]]:
    """The predicate axes the focus holds, as typed rows."""
    extra = focus.extra or {}
    return {
        "brand": [{"value": b.strip(), "key": b.strip(), "hint": "brand"} for b in focus.brands if isinstance(b, str) and b.strip()],
        "class": [r for h in _CLASS_HINTS for r in (_typed_row(x, h) for x in extra.get(h) or [] if isinstance(x, dict)) if r],
        "spec": [r for r in (_typed_row(x, "specification") for x in extra.get("specification") or [] if isinstance(x, dict)) if r],
    }


def _token_row(entity: dict[str, Any]) -> dict[str, Any] | None:
    """A named product with no key yet, keyed by its code (AC-S1-10)."""
    code = str(entity.get("canonical_code") or entity.get("raw") or "").strip()
    return {"value": str(entity.get("raw") or code).strip(), "key": code, "hint": "product"} if code else None


def _build_subject(
    state: State, focus: Focus, out: dict[str, Any], brands: list[Any], led: str | None
) -> Subject:
    """The Subject of this turn, before anything is resolved (AC-S1-9, card R1 / R4 / R5): the
    focus the ops left (held), with what this message types `said` on its own axis (`offer`
    when the brand is one the last answer offered). The op decides the OTHER held axes: a
    refine (`set` / `clear` / a list pick), an `answer` and a change set the applier rejected
    (`led` None) keep every held axis the message did not fill; a plain `keep` (`led` "keep"
    here) changes nothing, so a value typed on an axis the State holds stays held (one on an
    empty axis is said); a `new_subject` (`led` "new_ask") drops every held axis, the product
    axis included. A held product with no key stays as a token keyed by its code (AC-S1-10);
    a said one is `unresolved` until `settle_subject` reads what the resolver placed. `scope`
    and `hidden` stay empty."""
    said_rows = [e for e in _entities(out) if e.get("current_message") is not False]
    said: dict[str, list[dict[str, Any]]] = {}
    for e in said_rows:
        axis = _SUBJECT_AXIS.get(str(e.get("hint") or ""))
        row = _typed_row(e, str(e.get("hint"))) if axis else None
        if row:
            said.setdefault(axis, []).append(row)
    fresh = led == "new_ask"
    held = {axis: [] for axis in _PREDICATE_AXES} if fresh else _held_rows(focus)
    kept_aside: tuple[dict[str, Any], ...] = ()
    if led == "keep":
        # `keep` changes nothing: a value typed on an axis the State holds is not a change. The
        # words set aside are recorded, so the fetch drops exactly those and nothing a later
        # step adds (a clarify answer's chosen type, review round 3).
        kept_aside = tuple(r for axis, rows in said.items() if held[axis] for r in rows)
        said = {axis: rows for axis, rows in said.items() if not held[axis]}
    offered = bool(offered_brand_picks(state, out, brands))
    predicate: dict[str, list[dict[str, Any]]] = {}
    provenance: dict[str, str] = {}
    for axis in _PREDICATE_AXES:
        rows, how = (said[axis], "offer" if axis == "brand" and offered else "said") if axis in said else (held[axis], "held")
        unique = list({(r["value"].casefold(), r.get("key")): r for r in rows}.values())
        if unique:
            predicate[axis], provenance[axis] = unique, how

    said_products = [e for e in said_rows if e.get("hint") == "product"]
    if said_products:
        provenance["product"] = "said"
        said_ids = tuple(dict.fromkeys(str(e["uuid"]) for e in said_products if e.get("uuid")))
        tokens = tuple(t for t in (_token_row(e) for e in said_products if not e.get("uuid")) if t)
        return Subject(source="ids" if said_ids else "unresolved", product_ids=said_ids, product_tokens=tokens,
                       predicate=predicate, provenance=provenance, kept_aside=kept_aside)
    rows = [] if fresh else [r for r in focus.products if isinstance(r, dict)]
    members = [r for r in rows if r.get("uuid") and r.get("described_set") is True]
    ids = tuple(str(r["uuid"]) for r in rows if r.get("uuid") and r.get("described_set") is not True)
    tokens = tuple(t for t in (_token_row(r) for r in rows if not r.get("uuid")) if t)
    if ids or tokens:
        # `ids` means explicit keys; a token-only Subject is unresolved until settled (AC-S1-12).
        provenance["product"] = "held"
        return Subject(source="ids" if ids else "unresolved", product_ids=ids, product_tokens=tokens,
                       predicate=predicate, provenance=provenance, kept_aside=kept_aside)
    if predicate:
        if members:
            provenance["product"] = "held"
        return Subject(source="predicate", predicate=predicate, provenance=provenance, kept_aside=kept_aside)
    return Subject(source="unresolved", kept_aside=kept_aside)


def settle_subject(
    state: State, subject: Subject | None, *, unplaced_tokens: Any = None, log: dict[str, Any] | None = None
) -> State:
    """AC-S1-8 / AC-S1-11: the ONE settle step, run by the engine after the resolver (and its
    re-entry into APPLY) on the State that re-entry left. A product token the resolver placed
    carries its key on the focus now (a said one on this turn's own row, a held one on the row of
    its code): `source` is `ids` with those keys. A token it could not place (its own
    `unplaced_tokens`) is kept in `unplaced`; only when nothing was placed is the Subject
    `unresolved`. A token the resolver never saw leaves the source as the applier set it. The
    predicate and every provenance stay as `apply_changes` decided; the trace logs the settled
    Subject."""
    from app.services.chatbot.turn.state import token_key

    if subject is None:
        return state
    settled = subject
    said = subject.provenance.get("product") == "said"
    if said or subject.product_tokens:
        missed = {token_key(k) for k in (unplaced_tokens or {})} | {token_key(v) for v in (unplaced_tokens or {}).values()}
        held_codes = {token_key(t["key"]) for t in subject.product_tokens} if not said else set()
        placed = tuple(dict.fromkeys([*subject.product_ids, *(
            str(r["uuid"]) for r in state.focus.products
            if isinstance(r, dict) and r.get("uuid") and (
                (said and r.get("current_message") is not False)
                or token_key(r.get("canonical_code")) in held_codes or token_key(r.get("raw")) in held_codes
            )
        )]))
        unplaced = tuple(t for t in subject.product_tokens if token_key(t["key"]) in missed or token_key(t["value"]) in missed)
        source = "ids" if placed else "unresolved" if unplaced else subject.source
        settled = replace(subject, source=source, product_ids=placed, unplaced=unplaced)
    if log is not None:
        log["subject"] = subject_wire(settled)
    return replace(state, subject=settled)


def subject_wire(subject: Subject) -> dict[str, Any]:
    """The Subject as the trace's JSON dict (same field names). A row prints as its value: the
    trace is read by people, and the keys ride on the Subject itself."""
    return {
        "source": subject.source,
        "product_ids": list(subject.product_ids),
        "product_tokens": [t.get("value") for t in subject.product_tokens],
        "unplaced": [t.get("value") for t in subject.unplaced],
        "kept_aside": [t.get("value") for t in subject.kept_aside],
        "predicate": {k: [r.get("value") for r in v] for k, v in subject.predicate.items()},
        "scope": sorted(subject.scope),
        "hidden": sorted(subject.hidden),
        "provenance": dict(subject.provenance),
    }


SUBJECT_KINDS = frozenset({"brand", "category", "product_type", "specification"})


def _held_entity(row: dict[str, Any]) -> dict[str, Any]:
    """A held predicate row as the carried entity the resolver reads (`current_message: false`)."""
    entity: dict[str, Any] = {
        "raw": row["value"], "hint": row.get("hint"), "canonical_code": row.get("canonical_code") or row["value"],
        "current_message": False, "confident": True,
    }
    entity.update({k: row[k] for k in _ROW_FIELDS if k not in ("canonical_code",) and row.get(k) is not None})
    return entity


def _bare_word(row: dict[str, Any]) -> bool:
    """A held row that could only become a `scope_terms` entry: no uuid, and for a spec no
    registry key (`turn_runtime._is_a_bare_class_word`, read off the typed row)."""
    return not row.get("uuid") and (row.get("hint") in _CLASS_HINTS or not row.get("spec_key"))


def fetch_entities(
    subject: Subject, parse_output: dict[str, Any], focus: Focus, *, unsettled_only: bool
) -> dict[str, Any]:
    """The ONE State-to-fetch mapping: the resolver / fetch input of a turn on the state path.

    What this message typed is its own entities, as they stand after grounding. What is HELD
    is read off the Subject alone: a predicate axis whose provenance is `held` rides as its
    typed rows (a said or offered axis is the message's own words, never the held value
    beside it); the held products are the Subject's own ids and tokens. On a FETCH turn a
    settled product is already in the plan and a bare class word beside it never rides (the
    STALE-EXTRA-CARRY rule, read off the Subject's source). The State's other held slots
    (customer, warehouse, document type, order) ride per axis: a kind this message typed
    replaces the held one, every other held row is kept, as the ops left the focus."""
    from app.services.chatbot import turn_runtime

    # The words a `keep` set aside (typed on a held axis, recorded by the applier) were not a
    # change: the held rows answer for that axis and exactly those words do not ride. Nothing
    # else is dropped, whatever step added it.
    aside = {
        (_SUBJECT_AXIS.get(str(r.get("hint") or "")), str(r.get("value") or "").strip().casefold())
        for r in subject.kept_aside
    }
    stated = [e for e in parse_output.get("entities") or [] if isinstance(e, dict)]
    own = [
        e for e in stated
        if not (e.get("current_message") is not False and (
            _SUBJECT_AXIS.get(str(e.get("hint") or "")), str(e.get("raw") or e.get("canonical_code") or "").strip().casefold()
        ) in aside)
    ]
    typed = {str(e.get("hint") or "").strip().lower() for e in own if e.get("current_message") is not False}
    product_scoped = unsettled_only and bool(subject.product_ids or subject.product_tokens) and (
        subject.provenance.get("product") == "held"
    )
    # A said product is the fetch's subject: the held predicate stays on the Subject as context
    # and never gates or widens the lookup of what was said.
    by_ids = subject.provenance.get("product") == "said"
    held: list[dict[str, Any]] = [
        _held_entity(row)
        for axis in _PREDICATE_AXES if subject.provenance.get(axis) == "held" and not by_ids
        for row in subject.predicate.get(axis) or ()
        if not (product_scoped and axis != "brand" and _bare_word(row))
    ]
    # The held products are the Subject's ids (or a described set's members); the focus only
    # lends each id its code, so a roster prints a code and never a key.
    ids = set(subject.product_ids) if subject.provenance.get("product") == "held" else set()
    held_products = [
        r for r in focus.products
        if isinstance(r, dict) and subject.provenance.get("product") == "held"
        and (str(r.get("uuid")) in ids or r.get("described_set") is True)
    ]
    settled_passed_over = unsettled_only and bool(held_products)
    if not unsettled_only:
        held += turn_runtime.focus_entities(Focus(products=held_products))[0]
    scheme_pick = bool(parse_output.get("closed_lists")) and any(e.get("listed") == "cert_scheme" for e in own)
    if subject.provenance.get("product") == "held" and not scheme_pick:
        # A held product with no key is a token every turn hands over until the resolver places
        # it (AC-S1-10); a listed scheme pick does not answer an open product pick. A token the
        # verdict already names (a held family's members) is not handed over twice.
        from app.services.chatbot.turn.state import token_key

        named = {token_key(e.get("canonical_code") or e.get("raw")) for e in own if e.get("hint") == "product"}
        held += [
            {"raw": t["value"], "hint": "product", "canonical_code": t["key"], "current_message": False, "confident": True}
            for t in subject.product_tokens
            if token_key(t["key"]) not in named
        ]
    held += turn_runtime.focus_entities(
        focus, unsettled_only=unsettled_only, skip_kinds=SUBJECT_KINDS | {"product"} | typed, scheme_pick=scheme_pick,
    )[0]
    out = dict(parse_output)
    if settled_passed_over and not any(how in ("said", "offer") for how in subject.provenance.values()):
        # Nothing of the subject was said: the ask is about the held settled products the plan
        # already carries, so no `require` leg (`resolve_gate.resolve_entity_body`).
        out[turn_runtime.SUBJECT_SETTLED_KEY] = True
    if held or len(own) != len(stated):
        out["entities"] = [*held, *own]
    return out


def apply_changes(
    state: State,
    verdict: dict[str, Any],
    *,
    open_question: dict[str, Any] | None,
    domains: list[str],
    kinds: list[str],
    brands: list[Any],
    positions_read_elsewhere: bool,
) -> Applied:
    """Validate the parser's `state_changes` and carry the prior state by them.

    Returns the new `State` (with `state_led` set) and the verdict with `state_changes`
    popped; an invalid change returns the inputs unchanged with the reasons in the log.
    `log["slots"]` is the stance stated per held slot, `{axis: op}`."""
    changes = verdict.get("state_changes")
    shown = view(state, open_question)
    log: dict[str, Any] = {
        "shown": render(shown),
        "before": shown,
        "changes": copy.deepcopy(changes),
        "rejected": [],
        "slots": {},
    }
    if log["shown"] is None:
        # Nothing shown, nothing to carry: a first ask runs exactly as it does without the key.
        out = {k: v for k, v in verdict.items() if k != "state_changes"}
        subject = _build_subject(state, state.focus, out, brands, None)
        log["subject"] = subject_wire(subject)
        return Applied(True, replace(state, subject=subject), out, log)
    if isinstance(changes, list) and not changes:
        # Nothing declared (a retyped code, a bare re-ask): the state is not led, but the held
        # quantity still joins by the product's own code at the fetch; nothing else moves.
        rejected = _reject(state, verdict, log, [{"op": None, "reason": "no changes declared"}], brands)
        by_code, _shared = _held_quantity(state.focus)
        if by_code and verdict.get("demand_qty") is None:
            # Own-code join only: a turn the parser could not call a refine spreads nothing.
            rejected.verdict[CARRIED_QUANTITY_KEY] = {"by_code": dict(by_code), "shared": None}
        return rejected
    if not isinstance(changes, list):
        return _reject(state, verdict, log, [{"op": None, "reason": "no changes declared"}], brands)

    axes = set(FIXED_AXES) | set(kinds) | set(CLEAR_ONLY_AXES) | {k for k, v in (state.focus.extra or {}).items() if v}
    focus = copy.deepcopy(state.focus)
    # A carried customer row with no code and no key names nothing: it is not carried.
    focus.customers = [
        c for c in focus.customers
        if not isinstance(c, dict) or c.get("uuid") or c.get("uuids") or c.get("canonical_code") or c.get("raw") or c.get("name")
    ]
    # The same op stated twice (several `set product`) is one op.
    seen_ops: list[Any] = []
    deduped = []
    for c in changes:
        key = json.dumps(c, sort_keys=True, default=str)
        if key not in seen_ops:
            seen_ops.append(key)
            deduped.append(c)
    changes = deduped
    ignored: list[dict[str, Any]] = []
    ops = [c.get("op") if isinstance(c, dict) else None for c in changes]
    rejected: list[dict[str, Any]] = []

    def fail(op: Any, reason: str) -> None:
        rejected.append({"op": op, "reason": reason})

    # A `keep` that names no slot (no axis, "null", or any other axis) is a plain keep.
    plain_keeps = sum(
        1 for c in changes if isinstance(c, dict) and c.get("op") == "keep" and c.get("axis") not in SLOT_AXES
    )
    if plain_keeps + ops.count("new_subject") > 1:
        fail("keep", "keep and new_subject are exclusive")
    seen_axes: set[str] = set()
    set_axes: list[str] = []
    slots: dict[str, str] = {}
    picks: list[int] = []
    ignored_ops = 0
    # A set the parse backs with a value wins over a slot op on the same axis; a period the
    # message states replaces the held one with or without a `set` (R16).
    declared_sets = {
        c.get("axis") for c in changes
        if isinstance(c, dict) and c.get("op") == "set" and c.get("axis") in axes and _has_field(verdict, c["axis"])
    }
    states_period = _has_field(verdict, "period")
    for change in changes:
        op = change.get("op") if isinstance(change, dict) else None
        axis, position = (change.get("axis"), change.get("position")) if isinstance(change, dict) else (None, None)
        if op in ("keep", "skip", "unclear") and axis in SLOT_AXES and (
            axis in declared_sets or (axis == "period" and states_period)
        ):
            # The stated value is the change; the slot op is logged, not rejected.
            ignored.append({"axis": axis, "reason": f"{op} {axis} dropped: the message states its own"})
        elif op not in OPS and op not in SLOT_OPS:
            fail(op, "unknown op")
        elif op == "keep" and axis not in SLOT_AXES:
            pass
        elif op in ("set", "clear") or (op in SLOT_OPS and axis is not None) or op == "skip" or op == "unclear":
            if op in ("skip", "unclear", "keep") and axis not in SLOT_AXES:
                fail(op, f"{op} takes customer or period, not {axis}")
            elif axis not in axes:
                fail(op, f"unknown axis {axis}")
            elif axis in seen_axes:
                fail(op, f"axis {axis} repeated")
            elif op == "clear" and not _held(focus, axis):
                ignored.append({"axis": axis, "reason": f"nothing held for {axis}"})
                ignored_ops += 1
            else:
                seen_axes.add(axis)
                if op == "set":
                    if not _has_field(verdict, axis):
                        # A set the parse carries no value for changes nothing; the rest applies.
                        ignored.append({"axis": axis, "reason": f"no value for {axis} in the parse"})
                        ignored_ops += 1
                    else:
                        set_axes.append(axis)
                elif axis in SLOT_AXES:
                    slots[axis] = op
        elif op == "pick":
            if not isinstance(position, int) or isinstance(position, bool):
                fail(op, "pick needs a position")
            else:
                picks.append(position)
        elif op == "answer":
            mode = (verdict.get("open_question_answer") or {}).get("mode")
            if open_question is None and not _focus_questions(focus):
                fail(op, "no open question to answer")
            elif mode is None and not offered_brand_picks(state, verdict, brands):
                # The parser's own brand entity naming an offered brand IS the answer to the offer.
                fail(op, "no answer declared")
        elif op == "switch_domain":
            target = _message_domains(verdict)
            if not target or any(d not in domains for d in target):
                fail(op, "no known domain in the parse")

    if ignored_ops and ignored_ops == len(changes):
        # Every part was a no-op: there is no change to apply.
        for item in ignored:
            fail("set", item["reason"])

    if brands and "brand" in set_axes:
        known = _brand_words(brands)
        for e in _entities(verdict):
            if e.get("hint") == "brand" and e.get("current_message") is not False:
                if not ({str(e.get("canonical_code") or "").casefold(), str(e.get("raw") or "").casefold()} & known):
                    fail("set", f"unknown brand {e.get('canonical_code') or e.get('raw')}")

    options = {
        o.get("position"): o for o in (open_question or {}).get("options") or [] if isinstance(o, dict)
    }
    rows = {r.get("position"): r for r in (focus.last_list or []) if isinstance(r, dict)}
    roster_picks: list[int] = []
    data_picks: list[dict[str, Any]] = []
    for position in picks:
        if position in options:
            roster_picks.append(position)
        elif position in rows and _pickable(rows[position]):
            data_picks.append(rows[position])
        else:
            fail("pick", f"position {position} is not a pickable item of the list")

    if rejected:
        return _reject(state, verdict, log, rejected, brands)

    # ---- carry, on the copy, keyed off the ops ----
    pending = state.pending
    asked_before = getattr(state.pending, "kind", None) in _SLOT_ASKS
    out = {k: v for k, v in verdict.items() if k != "state_changes"}
    if states_period and "period" not in set_axes and slots.get("period") not in ("skip", "clear"):
        set_axes.append("period")
    slot_pick = None
    if asked_before and roster_picks:
        slot_pick, roster_picks = roster_picks[0], []
    if slots.get("customer") == "unclear":
        # R15: the held entity's registry kind settles it, before any switch is computed; a
        # customer means delivery, and this wins over the parse's own domain and asks.
        mapped = [KIND_DOMAIN.get(str(row.get("hint"))) for row in focus.customers if isinstance(row, dict)]
        if mapped and all(mapped):
            out["domain_hint"] = mapped[0]
            out["asks"] = []
    new_subject = "new_subject" in ops
    if new_subject:
        window = focus.date_window if NEW_SUBJECT_KEEPS_PERIOD else None
        focus = Focus(
            customers=focus.customers, tier=focus.tier, brands=focus.brands,
            tasks=focus.tasks, last_list=focus.last_list, date_window=window,
        )
        pending = None
    switch_to = _message_domains(out)
    held = list(focus.domains or [])
    if "switch_domain" in ops or (held and switch_to and not any(d in held for d in switch_to)):
        held_values = {
            "channel": ("sales_channel", focus.sales_channel),
            "status": ("status", focus.status),
            "document": ("document", focus.document),
            "sort": ("sort_by", (focus.sort or {}).get("by")),
        }
        _drop_domain_bound(focus)
        if switch_to:
            focus.domains = list(switch_to)
        # A parse field that merely restates a value just dropped does not bring it back
        # (value comparison only; a different value or an explicit `set` still applies).
        for axis_name, (field, value) in held_values.items():
            if value and axis_name not in set_axes and out.get(field) == value:
                out[field] = [] if field == "document" else None
                if field == "sort_by":
                    out["sort_dir"] = None
    for change in changes:
        axis = change.get("axis")
        if change["op"] == "clear":
            _clear_axis(focus, axis)
        elif change["op"] == "set" and axis in set_axes:
            _write_set(focus, axis, verdict)
    if "period" in set_axes and "period" not in declared_sets:
        _write_set(focus, "period", verdict)

    slot_ask = None
    period_answer = (
        ("answer" in ops or slot_pick is not None) and pending is not None and asked_before
    )
    answering = ("answer" in ops or bool(roster_picks)) and not period_answer
    if period_answer:
        # The answer fills only the period slot; nothing else of the state moves.
        declared = verdict.get(question_mod.ANSWER_KEY) or {}
        chosen = slot_pick if slot_pick is not None else (
            declared.get("picked") or verdict.get(question_mod.POSITIONS_KEY) or [None]
        )[0]
        option = next((o for o in pending.options if o.get("position") == chosen), None)
        if option is not None and pending.kind == PERIOD_ASK:
            focus.date_window = (option.get("payload") or {}).get("window")
        elif option is not None and not (option.get("payload") or {}).get("keep"):
            focus.customers = []
        pending = None
        out[question_mod.ANSWER_KEY] = dict(question_mod.NO_ANSWER)
        out[question_mod.POSITIONS_KEY] = []
    elif not answering:
        out, _ = question_mod.without_phantom_answer(
            out, open_question=None, positions_read_elsewhere=positions_read_elsewhere, focus_has_product=False
        )
    if roster_picks:
        out[question_mod.ANSWER_KEY] = {
            **question_mod.NO_ANSWER,
            "mode": "pick",
            "picked": list(roster_picks),
            "qty_for_all": (verdict.get(question_mod.ANSWER_KEY) or {}).get("qty_for_all"),
        }
        out[question_mod.POSITIONS_KEY] = list(roster_picks)
    if "close_question" in ops:
        if question_mod.is_the_stock_question(open_question):
            # Only an owed quantities question is cancelled, and only by a lone close that
            # names nothing of its own: a close with an entity this message states is a new ask.
            names_own = any(e.get("current_message") is not False for e in _entities(out))
            if open_question.get("kind") == question_mod.QUANTITIES and set(ops) == {"close_question"} and not names_own:
                out[question_mod.ANSWER_KEY] = {**question_mod.NO_ANSWER, "mode": "cancel"}
        elif open_question is not None:
            pending, focus.required_ask = None, None
        focus.set_clarify = None
        if isinstance(focus.top_selling, dict) and "asked" in focus.top_selling:
            focus.top_selling = {k: v for k, v in focus.top_selling.items() if k != "asked"}
        if _offered_brands(focus):
            key = {k: v for k, v in focus.set_page["set_key"].items() if k != "other_brands"}
            focus.set_page = {**focus.set_page, "set_key": key}
    if slots.get("customer") == "unclear" and focus.customers and unclear_slot_default() == "ask":
        mapped = [KIND_DOMAIN.get(str(row.get("hint"))) for row in focus.customers if isinstance(row, dict)]
        if not (mapped and all(mapped)):
            # The type cannot settle it (R11): ask once, real names; a second one hands over.
            if asked_before:
                slot_ask, pending = _hand_over(state), None
            else:
                slot_ask = _customer_ask(state, focus.customers, (switch_to or focus.domains or [None])[0])
    if slots.get("period") == "unclear" and focus.date_window and unclear_slot_default() == "ask":
        if asked_before:
            slot_ask, pending = _hand_over(state), None
        else:
            slot_ask = _period_ask(state, focus.date_window, (switch_to or focus.domains or [None])[0])
    held_products = list(state.focus.products)
    # Values come from the parse as stated; a restated held row (current_message false) goes.
    dropped_entities = [{"kind": e.get("hint")} for e in _entities(out) if e.get("current_message") is False]
    entities = [copy.deepcopy(e) for e in _entities(out) if e.get("current_message") is not False]
    # The quantity of the answered check (or of the held row) carries onto the refined, kept
    # or swapped item when the message states none; a stated quantity wins.
    qty_by_code, shared_qty = _held_quantity(state.focus)
    qty_open = out.get("demand_qty") is None and not new_subject and not (
        any(c.get("op") == "clear" and c.get("axis") == "quantity" for c in changes if isinstance(c, dict))
    )
    if qty_open and qty_by_code:
        # What the stock fetch joins by the product's own code (`turn_runtime._carried_quantities`,
        # its last source); `shared` rides onto the family codes a refine lands on
        # (`carry_onto_family`). The decision is made here and nowhere else.
        out[CARRIED_QUANTITY_KEY] = {"by_code": dict(qty_by_code), "shared": shared_qty}
    if shared_qty is not None and qty_open:
        mine = [e for e in entities if e.get("hint") == "product"]
        # Only an explicit one-for-one swap moves the quantity to another code.
        if "product" in set_axes and len(held_products) == 1 and len(mine) == 1 and mine[0].get("quantity") is None:
            mine[0]["quantity"] = shared_qty
        for row in focus.products:
            if isinstance(row, dict) and row.get("quantity") is None:
                filled = qty_by_code.get(str(row.get("canonical_code") or row.get("raw") or "").casefold())
                if filled is not None:
                    row["quantity"] = filled
    picked_kinds = {"product" for _ in data_picks}
    if pending is not None or state.pending is not None:
        for position in roster_picks:
            option = next((o for o in (state.pending.options if state.pending else []) if o.get("position") == position), None)
            if option and option.get("entity_type"):
                picked_kinds.add(str(option["entity_type"]))
    if picked_kinds:
        # A pick consumes the name it points at: a typed entity of the picked kind that no
        # `set` claims is not a second subject.
        kept_entities = []
        for e in entities:
            if e.get("hint") in picked_kinds and e.get("hint") not in set_axes:
                dropped_entities.append({"kind": e.get("hint")})
            else:
                kept_entities.append(e)
        entities = kept_entities
    for row in data_picks:
        # The code only: a stored key is never trusted, the resolver settles the code fresh
        # under the contact's current scope.
        entities.extend(option_entities({k: v for k, v in row.items() if k not in ("uuid", "uuids")}))
    if data_picks:
        out[question_mod.POSITIONS_KEY] = []
    named_products = {
        str(c).casefold() for e in entities if e.get("hint") == "product"
        for c in (e.get("canonical_code"), e.get("raw")) if c
    }
    if named_products:
        # Card R4: a new subject is only what this message names. An open task whose
        # products have all left the subject closes with them.
        focus.tasks = tuple(
            t for t in focus.tasks or ()
            if not (t.status == task_mod.OPEN and t.slots
                    and not any(str(sl.label).casefold() in named_products for sl in t.slots))
        )
    out["entities"] = entities

    led = (
        "answer" if answering
        else "new_ask" if new_subject
        else "refine" if (set_axes or "clear" in ops or data_picks or period_answer)
        else "carry"
    )
    log["rejected"] = []
    log["slots"] = slots
    log["ignored"] = ignored
    log["dropped_entities"] = dropped_entities
    subject = _build_subject(state, focus, out, brands, "keep" if led == "carry" and plain_keeps else led)
    log["subject"] = subject_wire(subject)
    return Applied(
        True, replace(state, focus=focus, pending=pending, state_led=led, slot_ask=slot_ask, subject=subject), out, log
    )
