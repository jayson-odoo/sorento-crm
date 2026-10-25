"""The `log_opportunity` lane: a salesperson logs a sales opportunity in chat (SALES-TARGET-CHAT s2).

`documentation/plans/sales/PLAN-sales-opportunity-chat-25oct.md`, "Chat lane". The parser reads,
the code applies (RS-9): the turn is this lane's when the parser says `order_status
"log_opportunity"`, when it declares an answer to this lane's open field question, or when it
answers this lane's read-back with a yes, a no or a cancel. Nothing here reads the message text.

* Collect: the four fields (customer, title, amount, close date) ride a `required_fields` slot
  (`OPPORTUNITY_ASK`, stated to the parser as the turn's `Open question:`), asked one per turn
  in that order. A declared answer fills only the field asked; a fresh "log_opportunity" turn
  takes every field it names.
* Customer: the customer entity's raw words go to `crm_sales_opportunity_customer_options` (the
  salesperson's own customers): one item settles it, several are a numbered pick, `blocked`
  ends the flow, none is a prospect.
* Confirm: all four known -> the read-back and a yes/no pending (`OPPORTUNITY_CONFIRM_KIND`)
  carrying the values. YES calls `crm_sales_opportunity_log` (a dry run sends `dry_run`), NO or
  cancel says "Not saved.", another ask drops it (the engine).

Both tools are called HERE, at `call_opportunity_tool`, never through the business lane's
read-only allow-list (`fetch.call_tool`, LESSONS-LEARNT 155): the write is not a read.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from app.services.chatbot import jsc
from app.services.chatbot import required_fields as rf
from app.services.chatbot.turn import pending as turn_pending

logger = logging.getLogger(__name__)

STATUS = "log_opportunity"
BRANCH_KIND = "log_opportunity"
OPTIONS_TOOL = "crm_sales_opportunity_customer_options"
LOG_TOOL = "crm_sales_opportunity_log"
ASK_NAME = "opportunity"
CONFIRM_KIND = turn_pending.OPPORTUNITY_CONFIRM_KIND

NOT_SALESPERSON = "Logging an opportunity is for salespeople only."
NOT_ENABLED = "Logging an opportunity is not enabled for your account."
NOT_YOURS = "That customer is not one of yours."
COULD_NOT_SAVE = "I couldn't save that. Nothing was recorded."
NOT_SAVED = "Not saved."
TEST_RUN = "Test run: nothing was saved."

#: The route codes the lane words as "not enabled" (403 on either route).
_NOT_ENABLED_CODES = frozenset({"not_a_salesperson", "opportunity_not_enabled"})


def _never(_db: Any, _word: str, _extras: dict[str, Any]) -> rf.Resolved:
    # The lane settles every field itself and hands `collect` a `Resolved`; a raw word never reaches here.
    return rf.Resolved("unknown")


#: The four fields, in the order they are asked. The questions are the plan's own.
OPPORTUNITY_ASK = rf.register(rf.AskType(
    name=ASK_NAME,
    fields=(
        rf.FieldSpec(name="customer", noun="customer", question="Which customer is it for?", resolve=_never,
                     allow_all=False, pick_head="Which account?"),
        rf.FieldSpec(name="title", noun="title", question="What is the opportunity? A short title, please.",
                     resolve=_never, allow_all=False),
        rf.FieldSpec(name="amount", noun="amount", question="What is the expected amount in RM?", resolve=_never,
                     allow_all=False),
        rf.FieldSpec(name="close_date", noun="close date", question="When do you expect it to close?",
                     resolve=_never, allow_all=False),
    ),
    reroute={"message_type": "business_query", "intent_hint": "check_order", "domain_hint": "order",
             "order_status": STATUS},
    cancelled=NOT_SAVED,
    give_up=NOT_SAVED,
    answered_by_parser=True,
))


def call_opportunity_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call one of the lane's two tools through the MCP client (the ideate seam's shape).

    A SEAM: tests patch this one name. The tool's MCP content text is decoded here; a refused
    route comes back as the HTTP error body (`code`, `status_code`), which `_refusal` words."""
    from app.services.ai_assistant_service import MCPRuntimeClient
    from app.services.ai_assistant_service import settings as ai_settings

    client = MCPRuntimeClient(
        ai_settings.ai_assistant_mcp_url,
        timeout_seconds=ai_settings.ai_assistant_mcp_timeout_seconds,
    )
    raw = client.call_tool(tool_name, dict(arguments))
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        raise RuntimeError(f"{tool_name} returned a non-JSON payload: {str(raw)[:200]}")
    if not isinstance(decoded, dict):
        raise RuntimeError(f"{tool_name} returned {type(decoded).__name__}, expected an object")
    return decoded


# --------------------------------------------------------------------------- #
# Who may log (the route's gate decides again; this is the lane's no-call refusal)
# --------------------------------------------------------------------------- #


def is_salesperson(db: Any, contact_respond_id: Any, space_id: Any) -> bool:
    """A salesperson by the one asker rule, not revoked (the route's gate, steps 2 and 3)."""
    from app.services.contact_asker import classify
    from app.services.field_access import resolve_contact_with_null_workspace_fallback
    from app.services.sales.target_chat_scope import _user_revoked

    if not contact_respond_id or not str(contact_respond_id).strip():
        return False
    contact_id = resolve_contact_with_null_workspace_fallback(
        db, contact_id=str(contact_respond_id).strip(), space_id=(str(space_id).strip() or None) if space_id else None
    )
    if not contact_id:
        return False
    return classify(db, str(contact_id)) == "salesperson" and not _user_revoked(db, str(contact_id))


# --------------------------------------------------------------------------- #
# Does this turn belong to the lane
# --------------------------------------------------------------------------- #


def _status(verdict: Mapping[str, Any]) -> str:
    return jsc.js_string(verdict.get("order_status") or "").strip()


def _mode(verdict: Mapping[str, Any]) -> Any:
    answer = verdict.get("open_question_answer")
    return answer.get("mode") if isinstance(answer, dict) else None


def own_slot(open_ask: Any) -> dict[str, Any] | None:
    return open_ask if isinstance(open_ask, dict) and open_ask.get("ask") == ASK_NAME else None


def own_pending(pending: Any) -> Any:
    return pending if getattr(pending, "kind", None) == CONFIRM_KIND else None


def _bare_yes_no(verdict: Mapping[str, Any]) -> bool | None:
    """The parser's yes / no to the read-back: its declared answer, else `is_affirmative` on a
    turn that asks nothing of its own (no status, no entity)."""
    mode = _mode(verdict)
    if mode == "yes":
        return True
    if mode in ("no", "cancel"):
        return False
    if mode is None and not _status(verdict) and not verdict.get("entities"):
        flag = verdict.get("is_affirmative")
        if isinstance(flag, bool):
            return flag
    return None


def takes_turn(verdict: Mapping[str, Any], open_ask: Any, pending: Any) -> bool:
    if _status(verdict) == STATUS:
        return True
    if own_pending(pending) is not None and _bare_yes_no(verdict) is not None:
        return True
    return own_slot(open_ask) is not None and _mode(verdict) in rf.ANSWER_MODES


# --------------------------------------------------------------------------- #
# Values
# --------------------------------------------------------------------------- #


def _money(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return amount.quantize(Decimal("0.01")) if amount.is_finite() and amount > 0 else None


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value).strip()[:10]) if value else None
    except ValueError:
        return None


def _rm(value: Any) -> str:
    return f"RM {Decimal(str(value)):,.2f}"


def _day(value: date, *, year: bool = True) -> str:
    return f"{value.day} {value.strftime('%b')}" + (f" {value.year}" if year else "")


def _customer_label(item: Mapping[str, Any]) -> str:
    name = jsc.js_string(item.get("name") or "").strip()
    label = jsc.js_string(item.get("label") or "").strip()
    return f"{name} [{label}]" if label and label != name else name


def _customer_words(verdict: Mapping[str, Any]) -> str | None:
    for entity in verdict.get("entities") or []:
        if (
            isinstance(entity, dict)
            and entity.get("hint") == "customer"
            and entity.get("current_message") is not False
            and jsc.js_string(entity.get("raw") or "").strip()
        ):
            return jsc.js_string(entity["raw"]).strip()
    return None


def _positions(verdict: Mapping[str, Any]) -> list[int]:
    answer = verdict.get("open_question_answer") if isinstance(verdict.get("open_question_answer"), dict) else {}
    raw = list(answer.get("picked") or []) or list(verdict.get("reference_positions") or [])
    return [p for p in raw if isinstance(p, int) and not isinstance(p, bool)]


def _error_line(result: Any) -> str | None:
    """The lane's words for a refused route (the HTTP error body), None for a success."""
    if not isinstance(result, dict):
        return COULD_NOT_SAVE
    status = result.get("status_code")
    if not (isinstance(status, int) and status >= 400) and not result.get("http_error"):
        return None
    detail = result.get("detail") if isinstance(result.get("detail"), dict) else {}
    code = jsc.js_string(result.get("code") or detail.get("code") or "")
    if status == 403 and code in _NOT_ENABLED_CODES:
        return NOT_ENABLED
    if code == "CUSTOMER_NOT_YOURS":
        return NOT_YOURS
    return COULD_NOT_SAVE


def _call(tool_name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    try:
        result = call_opportunity_tool(tool_name, arguments)
    except Exception:  # noqa: BLE001 - never a raw error to the customer
        logger.warning("chatbot opportunity lane: %s failed", tool_name, exc_info=True)
        return None, COULD_NOT_SAVE
    line = _error_line(result)
    return (None, line) if line else (result, None)


# --------------------------------------------------------------------------- #
# The turn
# --------------------------------------------------------------------------- #


@dataclass
class LaneReply:
    text: str
    #: The open field question for the next message (a `required_fields` slot), or None.
    slot: dict[str, Any] | None = None
    #: The read-back's yes/no pending, or None.
    pending: Any = None
    #: Which tools the lane called, for the trace.
    called: tuple[str, ...] = ()


def _read_back(values: Mapping[str, Any], *, asked_at_turn: int | None) -> LaneReply:
    customer = values["customer"]["value"]
    who = (
        f"Prospect: {customer['prospect_name']}"
        if customer.get("prospect_name")
        else f"Customer: {_customer_label(customer)}"
    )
    lines = [
        "Save this opportunity?",
        who,
        f"Title: {values['title']['value']}",
        f"Amount: {_rm(values['amount']['value'])}",
        f"Close by: {_day(date.fromisoformat(values['close_date']['value']))}",
        "Reply YES to save.",
    ]
    confirm = turn_pending.ask(
        CONFIRM_KIND,
        [{"position": 1, "label": "Yes", "code": "YES"}],
        expects="yes_no",
        asked_at_turn=asked_at_turn,
        payload={"values": dict(values)},
    )
    return LaneReply(text="\n".join(lines), pending=confirm)


def _save(values: Mapping[str, Any], *, contact_respond_id: Any, space_id: Any, dry_run: bool) -> LaneReply:
    customer = values["customer"]["value"]
    args: dict[str, Any] = {
        "contact_id": jsc.js_string(contact_respond_id),
        "space_id": jsc.js_string(space_id),
        "title": values["title"]["value"],
        "expected_amount": values["amount"]["value"],
        "expected_close_date": values["close_date"]["value"],
    }
    if customer.get("customer_id"):
        args["customer_id"] = customer["customer_id"]
    else:
        args["prospect_name"] = customer.get("prospect_name")
    if dry_run:
        # A string: the tool's body params are strings (the route reads it as a bool).
        args["dry_run"] = "true"
    result, line = _call(LOG_TOOL, args)
    if line:
        return LaneReply(text=line, called=(LOG_TOOL,))
    if dry_run or result.get("dry_run") is True:
        return LaneReply(text=TEST_RUN, called=(LOG_TOOL,))
    lines = [f"Saved {result.get('opportunity_no')}, stage {result.get('stage') or 'New'}."]
    pipeline = result.get("pipeline") if isinstance(result.get("pipeline"), dict) else None
    end = _date((pipeline or {}).get("target_end_date"))
    if pipeline and end is not None and pipeline.get("pipeline_value") is not None:
        lines.append(f"Open opportunities closing by {_day(end, year=False)}: {_rm(pipeline['pipeline_value'])}.")
    return LaneReply(text="\n".join(lines), called=(LOG_TOOL,))


def run(
    verdict: Mapping[str, Any],
    *,
    open_ask: Any,
    pending: Any,
    salesperson: bool,
    contact_respond_id: Any,
    space_id: Any,
    dry_run: bool,
    turn_no: int | None,
) -> LaneReply:
    """One opportunity turn. Pure but for the two tool calls at the seam."""
    if not salesperson:
        return LaneReply(text=NOT_SALESPERSON)
    confirm = own_pending(pending)
    slot = own_slot(open_ask)
    status = _status(verdict)
    mode = _mode(verdict)

    if confirm is not None and status != STATUS:
        values = dict(confirm.payload.get("values") or {})
        if _bare_yes_no(verdict) is True and len(values) == len(OPPORTUNITY_ASK.fields):
            return _save(values, contact_respond_id=contact_respond_id, space_id=space_id, dry_run=dry_run)
        return LaneReply(text=NOT_SAVED)
    if mode == "cancel" or (mode == "no" and confirm is not None):
        return LaneReply(text=NOT_SAVED)

    if confirm is not None:
        values: dict[str, Any] = dict(confirm.payload.get("values") or {})
    elif slot is not None:
        values = dict(slot.get("values") or {})
    else:
        values = {}
    asking = jsc.js_string(slot.get("asking") or "") if slot is not None else ""
    answering = slot is not None and mode in rf.ANSWER_MODES

    def wanted(name: str) -> bool:
        # A declared answer to the open question fills only the field it asked.
        return not answering or asking == name

    opp = verdict.get("opportunity") if isinstance(verdict.get("opportunity"), dict) else {}
    title = jsc.js_string(opp.get("title") or "").strip()
    if title and wanted("title"):
        values["title"] = {"value": title, "label": title}
    amount = _money(opp.get("amount_rm"))
    if amount is not None and wanted("amount"):
        values["amount"] = {"value": str(amount), "label": _rm(amount)}
    close = _date(opp.get("close_date"))
    if close is not None and wanted("close_date"):
        values["close_date"] = {"value": close.isoformat(), "label": _day(close)}

    called: list[str] = []
    ambiguous: rf.Resolved | None = None
    options = list(slot.get("options") or []) if slot is not None and asking == "customer" else []
    picked = next((p for p in _positions(verdict) if 1 <= p <= len(options)), None) if options else None
    words = _customer_words(verdict) if wanted("customer") else None
    if picked is not None:
        value, label = options[picked - 1]
        values["customer"] = {"value": value, "label": label}
    elif words:
        result, line = _call(OPTIONS_TOOL, {
            "contact_id": jsc.js_string(contact_respond_id), "space_id": jsc.js_string(space_id), "q": words,
        })
        called.append(OPTIONS_TOOL)
        if line:
            return LaneReply(text=line, called=tuple(called))
        items = [i for i in result.get("items") or [] if isinstance(i, dict) and i.get("customer_id")]
        if len(items) == 1:
            item = {k: items[0].get(k) for k in ("customer_id", "code", "name", "label")}
            values["customer"] = {"value": item, "label": _customer_label(item)}
        elif len(items) > 1:
            values.pop("customer", None)
            ambiguous = rf.Resolved("ambiguous", options=tuple(
                ({k: i.get(k) for k in ("customer_id", "code", "name", "label")}, _customer_label(i)) for i in items
            ))
        elif result.get("blocked") is True:
            return LaneReply(text=NOT_YOURS, called=tuple(called))
        else:
            values["customer"] = {"value": {"prospect_name": words}, "label": words}

    outcome = rf.collect(
        None, OPPORTUNITY_ASK, given={"customer": ambiguous} if ambiguous else {}, slot={"values": values},
    )
    if not outcome.done:
        return LaneReply(text=outcome.reply or "", slot=outcome.slot, called=tuple(called))
    reply = _read_back(outcome.values, asked_at_turn=turn_no)
    reply.called = tuple(called)
    return reply
