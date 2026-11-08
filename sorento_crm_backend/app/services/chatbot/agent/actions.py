"""Proposals, confirm and cancel (AGENTIC-P3 plan sections 2 to 4).

A turn's write calls become one `chatbot.agent_actions` row (`proposed`). Confirming re-checks every
step before writing anything, claims the row atomically, then runs the steps in order and stops at the
first failure. The same functions serve the console buttons and the chat tools.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from app.models.chatbot_agent import AgentAction
from app.services.chatbot.agent import writes
from app.services.chatbot.agent.access import AgentRefused, build_context

logger = logging.getLogger(__name__)

_UUID_TEXT = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)


def scrub_ids(text: str | None) -> str | None:
    """A step error as a person reads it: no id in it."""
    return None if text is None else " ".join(_UUID_TEXT.sub("", text).split())


ACTION_TTL_MINUTES = 10
MAX_STEPS = 20


class ActionRefused(Exception):
    """Nothing was written. `reason` is one of not_found, not_newest, expired, not_proposed,
    entry_refused, changed, same_turn; a withdraw adds not_waiting and applied."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class ActionOutcome:
    action_id: str
    status: str  # executed | partial | rejected | cancelled
    reply_text: str
    steps: list[dict]  # [{"summary", "status": done|failed|skipped|proposed, "error"}]
    #: The notes of the steps that ran (a link, a waiting window), for the reply to repeat in code.
    notes: list[str] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_test_action(action) -> bool:
    """A console proposal: its steps carry the loop's `_is_test` (dealer writes, ideas)."""
    return any(bool((s.get("args") or {}).get("_is_test")) for s in (action.steps or []))


def _is_contact_action(action) -> bool:
    """A contact principal's own proposal (no user, AGENTIC-WA-W2)."""
    return str(action.user_id or "") == ""


def _decidable_here(action, *, via: str, operator_user_id: str | None) -> bool:
    """A contact's LIVE proposal is decided only from its own WhatsApp turn, a TEST one only from the console
    (owner W2-Q3 (a)): a staff confirm can never run a dealer's live write, nor a dealer's yes a console test."""
    if not _is_contact_action(action):
        return True
    live_channel = via == "chat" and not operator_user_id
    return is_test_action(action) != live_channel


def expire_proposed(db, contact_respond_id: str, *, test: bool | None = None) -> None:
    """Every `proposed` action of the contact becomes `expired` (nobody decided it). With `test`, only the
    contact's own proposals of that kind (a console test leaves a live WhatsApp proposal alone). Does not commit."""
    query = db.query(AgentAction).filter(
        AgentAction.contact_respond_id == contact_respond_id, AgentAction.status == "proposed"
    )
    if test is not None:
        ids = [str(r.id) for r in query.filter(AgentAction.user_id == "").all() if is_test_action(r) == test]
        query = query.filter(AgentAction.id.in_(ids)) if ids else query.filter(AgentAction.id.is_(None))
    query.update({AgentAction.status: "expired"}, synchronize_session=False)


def expire_previous(db, ctx, steps: list[dict], *, test: bool = False) -> None:
    """A new proposal (or a table turn with no ready row) replaces the contact's older `proposed` actions. A contact
    turn expires only its own kind (test or live); `test` is used when there are no steps to read it from."""
    if str(ctx.user_id or "") == "":
        expire_proposed(
            db, ctx.contact_respond_id, test=any(bool((s.get("args") or {}).get("_is_test")) for s in steps) if steps else test
        )
    else:
        expire_proposed(db, ctx.contact_respond_id)


def store_proposal(
    db, ctx, *, conversation_id: str, turn_id: str, steps: list[dict], action_id: str | None = None
) -> AgentAction:
    """The turn's steps as a `proposed` action. Older `proposed` actions of the contact expire."""
    now = _now()
    expire_previous(db, ctx, steps)
    row = AgentAction(
        id=action_id or str(uuid.uuid4()),
        conversation_id=conversation_id,
        turn_id=turn_id,
        contact_respond_id=ctx.contact_respond_id,
        user_id=ctx.user_id,
        status="proposed",
        steps=[dict(s, status="proposed") for s in steps],
        created_at=now,
    )
    db.add(row)
    db.commit()
    return row


def _expires_at(action: AgentAction) -> datetime:
    return action.created_at + timedelta(minutes=ACTION_TTL_MINUTES)


def pending_action(
    db, contact_respond_id: str, *, now: datetime | None = None, user_id: str | None = None,
    test: bool | None = None,
) -> AgentAction | None:
    """The newest `proposed` action of the contact (of this linked user, when given), unless it has expired.
    With `test`, only a proposal of that kind (console test or live), so the two never answer each other."""
    query = db.query(AgentAction).filter(
        AgentAction.contact_respond_id == contact_respond_id, AgentAction.status == "proposed"
    )
    if user_id is not None:
        query = query.filter(AgentAction.user_id == str(user_id))
    query = query.order_by(AgentAction.created_at.desc(), AgentAction.id.desc())
    if test is None:
        row = query.first()
    else:
        row = next((r for r in query.limit(25).all() if is_test_action(r) == test), None)
    if row is None or _expires_at(row) < (now or _now()):
        return None
    return row


def pending_dict(action: AgentAction) -> dict:
    """The proposal as the API and the turn result carry it."""
    return {
        "id": str(action.id),
        "turn_id": str(action.turn_id),
        "lines": proposal_lines(action),
        "expires_at": _expires_at(action).isoformat(),
    }


def proposal_lines(action: AgentAction) -> list[str]:
    return [str(s.get("summary") or "") for s in action.steps or []]


def waiting_of(step: dict) -> dict | None:
    """A done step whose form action is parked in its grace window: when it applies, for the console's
    Withdraw countdown. None for every other step."""
    after = step.get("after") or {}
    if step.get("status") != "done" or not after.get("deferred"):
        return None
    try:
        # The form-action stamps are naive UTC.
        due = datetime.fromisoformat(str(after.get("commit_at"))).replace(tzinfo=None)
    except ValueError:
        return None
    if due <= datetime.now(timezone.utc).replace(tzinfo=None):
        return None
    return {"commit_at": after.get("commit_at"), "window_seconds": after.get("window_seconds")}


def step_out(step: dict, *, default_status: str | None = None) -> dict:
    """One step as the API carries it: no ids, no internals."""
    return {
        "summary": step.get("summary"), "status": step.get("status") or default_status,
        "error": scrub_ids(step.get("error")), "changes": step.get("changes") or [], "waiting": waiting_of(step),
    }


def _out_steps(steps: list[dict]) -> list[dict]:
    return [step_out(s) for s in steps]


# ------------------------------------------------------------------ confirm


def _recheck(db, ctx, step: dict) -> str | None:
    """Why this step may no longer run, or None. Reads the record again as the user."""
    definition = writes.write_def(step["tool"])
    # A panel-only change confirmed from a thread that is not a panel thread (AGENTIC-UNIFY PR 4, AC-0).
    if definition is None or writes.panel_closed(step["tool"]):
        return "This change is no longer available."
    if definition.runs_as == "contact":
        from app.services.chatbot.agent import portal_writes

        if not portal_writes.may_use(db, ctx, definition.name):
            return "This change is no longer available to you."
    elif not writes.holds(db, ctx.user_id, definition.user_permission):
        return "You no longer have permission for this change."
    if not writes.holds_ctx(db, ctx, definition.user_permission):
        return "You do not have permission for this change."
    try:
        now = writes.read_before_all(db, ctx, definition, step["args"])
    except Exception as exc:  # noqa: BLE001
        text = writes.error_text(exc)
        # A rule that now refuses (nothing left to change, a field no longer valid) means it moved on.
        return f"This changed since it was proposed: {text}" if getattr(exc, "status_code", 0) in (409, 422) else text
    before = step.get("before") or {}
    for field in before:
        if now.get(field) != before[field]:
            return f"The {field.replace('_', ' ')} changed since this was proposed."
    return None


def _reply(status: str, steps: list[dict]) -> str:
    if status == "cancelled":
        return "Cancelled. Nothing was changed."
    marks = {"done": "done", "failed": "failed", "skipped": "not run"}
    lines = []
    for n, s in enumerate(steps, 1):
        tail = "" if status == "executed" else f" ({marks.get(s['status'], s['status'])})"
        if s.get("error"):
            tail = f" ({marks.get(s['status'], s['status'])}: {scrub_ids(s['error'])})"
        note = f" {s['note']}" if s.get("note") else ""
        lines.append(f"{n}. {s['summary']}{tail}{note}")
    head = {
        "executed": "Done. I made these changes:",
        "partial": (
            "I made some of the changes; the rows marked failed were not changed:" if steps and all(s.get("batch") for s in steps)
            else "I made some of the changes and stopped at a failure:"
        ),
        "rejected": "Nothing was changed:",
    }[status]
    return head + "\n" + "\n".join(lines)


def _load(db, contact_respond_id: str, action_id: str) -> AgentAction:
    try:
        uuid.UUID(str(action_id))
    except ValueError:
        raise ActionRefused("not_found")
    row = db.get(AgentAction, str(action_id))
    if row is None or row.contact_respond_id != contact_respond_id:
        raise ActionRefused("not_found")
    return row


def operator_may_decide(db, ctx, action: AgentAction) -> bool:
    """Does the console operator (if any) hold the slug of every step of this action?"""
    return all(
        (d := writes.write_def(step.get("tool"))) is not None
        # A dealer write needs no slug, and the console decides only a console TEST of one (owner W2-Q3 (a)).
        and (
            # The dealer's own turn decides its live write; a console operator only a console test of one.
            bool((step.get("args") or {}).get("_is_test")) == bool(getattr(ctx, "operator_user_id", None))
            if d.runs_as == "contact"
            else writes.holds_ctx(db, ctx, d.user_permission)
        )
        for step in action.steps or []
    )


def confirm(
    db, contact_respond_id: str, action_id: str, *, via: str, turn_id: str | None = None,
    now: datetime | None = None, operator_user_id: str | None = None,
) -> ActionOutcome:
    action = _load(db, contact_respond_id, action_id)
    if action.status != "proposed":
        raise ActionRefused("not_proposed")
    if not _decidable_here(action, via=via, operator_user_id=operator_user_id):
        raise ActionRefused("entry_refused")
    if _is_contact_action(action):
        # Newest among the contact's own proposals of the same kind (test or live).
        newest = next(
            (
                r for r in db.query(AgentAction)
                .filter(AgentAction.contact_respond_id == contact_respond_id, AgentAction.status == "proposed",
                        AgentAction.user_id == "")
                .order_by(AgentAction.created_at.desc(), AgentAction.id.desc())
                .limit(25)
                .all()
                if is_test_action(r) == is_test_action(action)
            ),
            None,
        )
    else:
        newest = (
            db.query(AgentAction)
            .filter(AgentAction.contact_respond_id == contact_respond_id, AgentAction.status == "proposed")
            .order_by(AgentAction.created_at.desc(), AgentAction.id.desc())
            .first()
        )
    if newest is None or str(newest.id) != str(action.id):
        raise ActionRefused("not_newest")
    if _expires_at(action) < (now or _now()):
        raise ActionRefused("expired")
    if via == "chat" and turn_id is not None and str(turn_id) == str(action.turn_id):
        raise ActionRefused("same_turn")
    try:
        ctx = build_context(db, contact_respond_id)
    except AgentRefused:
        raise ActionRefused("entry_refused")
    if str(ctx.user_id) != str(action.user_id):
        raise ActionRefused("entry_refused")
    if operator_user_id and str(operator_user_id) != str(ctx.user_id):
        ctx = dataclasses.replace(ctx, operator_user_id=str(operator_user_id))
    decider = str(operator_user_id or action.user_id)

    steps = copy.deepcopy(action.steps or [])
    # A table's rows (AGENT-BULK-ACTIONS) are independent: a row that no longer applies fails alone, the rest run.
    batch = bool(steps) and all(s.get("batch") for s in steps)
    for step in steps:
        problem = _recheck(db, ctx, step)
        if problem and batch:
            step["status"], step["error"] = "failed", problem
            db.rollback()  # a refused re-read must not leave the session aborted for the next row
            continue
        if problem:
            step["status"], step["error"] = "failed", problem
            for other in steps:
                if other is not step:
                    other["status"] = "skipped"
            return _finish(
                db, action, "rejected", steps, via=via, turn_id=turn_id, expect="proposed", decider=decider
            )
    if batch and all(s.get("status") == "failed" for s in steps):
        return _finish(db, action, "rejected", steps, via=via, turn_id=turn_id, expect="proposed", decider=decider)

    claimed = db.execute(
        update(AgentAction)
        .where(AgentAction.id == action.id, AgentAction.status == "proposed")
        .values(
            status="executing", via=via, confirm_turn_id=turn_id, decided_at=_now(), decided_by_user_id=decider
        )
    ).rowcount
    db.commit()
    if not claimed:
        raise ActionRefused("not_proposed")

    failed = False
    for step in steps:
        if batch and step.get("status") == "failed":
            continue  # its re-check refused it; nothing of this row runs
        if failed and not batch:
            step["status"] = "skipped"
            continue
        definition = writes.write_def(step["tool"])
        try:
            if definition.execute_takes_before:
                run = lambda who: definition.execute(db, who, step["args"], step.get("before") or {})  # noqa: E731
            else:
                run = lambda who: definition.execute(db, who, step["args"])  # noqa: E731
            if definition.runs_as == "contact":
                from app.services.chatbot.agent import portal_writes

                result = portal_writes.run_as_contact(db, ctx, run, tool_name=step["tool"])
            else:
                result = writes.run_as_user(db, ctx, run, tool_name=step["tool"])
            step.update(status="done", result_id=result.get("id"), after=result.get("after"), error=None)
            try:
                if definition.changes is not None:
                    step["changes"] = definition.changes(
                        step["args"], step.get("before") or {}, result.get("after") or {}, step.get("shown") or {}
                    )
            except Exception:  # noqa: BLE001 - the write is done; a missing summary must not undo it
                logger.warning("agent: building the change lines failed", exc_info=True)
            if "unlinked_customer_ids" in result:
                step["unlinked_customer_ids"] = result["unlinked_customer_ids"]
            if result.get("note"):
                step["note"] = result["note"]
        except Exception as exc:  # noqa: BLE001 - a route refusal stops the run
            db.rollback()
            if not isinstance(exc, writes.HTTPException):
                logger.warning("agent: action step failed", exc_info=True)
            step.update(status="failed", error=writes.error_text(exc))
            failed = True
    if batch:
        done = any(s.get("status") == "done" for s in steps)
        failed = any(s.get("status") == "failed" for s in steps)
        status = "executed" if not failed else ("partial" if done else "rejected")
    else:
        status = "partial" if failed else "executed"
    return _finish(db, action, status, steps, via=via, turn_id=turn_id, expect="executing")


def _finish(
    db, action, status: str, steps: list[dict], *, via, turn_id, expect: str, decider: str | None = None
) -> ActionOutcome:
    values = {"status": status, "steps": steps, "finished_at": _now()}
    if expect == "proposed":
        values.update(via=via, confirm_turn_id=turn_id, decided_at=_now(), decided_by_user_id=decider)
    changed = db.execute(
        update(AgentAction).where(AgentAction.id == action.id, AgentAction.status == expect).values(**values)
    ).rowcount
    db.commit()
    if not changed:
        raise ActionRefused("not_proposed")
    # Only a write that opts in (`note_in_reply`) has its note repeated in a chat reply.
    notes = [
        s["note"] for s in steps
        if s.get("status") == "done" and s.get("note")
        and getattr(writes.write_def(s.get("tool")), "note_in_reply", False)
    ]
    return ActionOutcome(str(action.id), status, _reply(status, steps), _out_steps(steps), notes)


# ------------------------------------------------------------------ cancel


def cancel(db, contact_respond_id: str, action_id: str, *, operator_user_id: str | None = None) -> ActionOutcome:
    action = _load(db, contact_respond_id, action_id)
    if not _decidable_here(action, via="console" if operator_user_id else "chat", operator_user_id=operator_user_id):
        raise ActionRefused("entry_refused")
    if not operator_user_id:
        # The chat path: only the linked user whose action it is (a contact principal has no user).
        try:
            ctx = build_context(db, contact_respond_id)
        except AgentRefused:
            raise ActionRefused("entry_refused")
        if str(ctx.user_id) != str(action.user_id):
            raise ActionRefused("entry_refused")
    if operator_user_id:
        # A console operator may cancel for the linked user only while that is still who the action is for,
        # and only when they could have confirmed at least one step themselves.
        try:
            ctx = build_context(db, contact_respond_id)
        except AgentRefused:
            raise ActionRefused("entry_refused")
        theirs = str(operator_user_id)
        may = theirs == str(ctx.user_id) or any(
            (d := writes.write_def(step.get("tool"))) is not None and writes.holds(db, theirs, d.user_permission)
            for step in action.steps or []
        )
        if str(ctx.user_id) != str(action.user_id) or not may:
            raise ActionRefused("entry_refused")
    changed = db.execute(
        update(AgentAction)
        .where(AgentAction.id == action.id, AgentAction.status == "proposed")
        .values(
            status="cancelled", decided_at=_now(), finished_at=_now(),
            decided_by_user_id=str(operator_user_id or action.user_id),
        )
    ).rowcount
    db.commit()
    if not changed:
        raise ActionRefused("not_proposed")
    db.refresh(action)
    return ActionOutcome(str(action.id), "cancelled", _reply("cancelled", []), _out_steps(action.steps or []))


# ------------------------------------------------------------------ withdraw (inside the grace window)

WITHDRAWN_REPLY = "Withdrawn. Nothing was changed and nobody was told."


def withdraw(
    db, contact_respond_id: str, action_id: str, index: int, *, operator_user_id: str | None = None
) -> ActionOutcome:
    """Withdraw one parked step through the system's form-action cancel, as the linked user who started it.
    The cancel has no slug (nothing has happened yet); a console operator may withdraw only what they could
    have confirmed, as `cancel` rules."""
    from app.api.v1.sla.form_actions import cancel_form_action

    action = _load(db, contact_respond_id, action_id)
    steps = copy.deepcopy(action.steps or [])
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(steps):
        raise ActionRefused("not_found")
    step = steps[index]
    after = step.get("after") or {}
    if waiting_of(step) is None or not after.get("pending_action_id"):
        raise ActionRefused("not_waiting")
    try:
        ctx = build_context(db, contact_respond_id)
    except AgentRefused:
        raise ActionRefused("entry_refused")
    definition = writes.WRITES.get(step.get("tool"))
    theirs = str(operator_user_id or ctx.user_id)
    may = theirs == str(ctx.user_id) or (definition is not None and writes.holds(db, theirs, definition.user_permission))
    if str(ctx.user_id) != str(action.user_id) or not may:
        raise ActionRefused("entry_refused")
    if operator_user_id and str(operator_user_id) != str(ctx.user_id):
        ctx = dataclasses.replace(ctx, operator_user_id=str(operator_user_id))
    try:
        def run(user: dict) -> None:
            writes._module_open(user, db, "sla")  # the cancel route's router guard
            cancel_form_action(action_id=str(after["pending_action_id"]), current_user=user, db=db)

        writes.run_as_user(db, ctx, run, tool_name=step.get("tool"))
    except writes.HTTPException as exc:
        db.rollback()
        if exc.status_code == 409 and "already been applied" in writes.error_text(exc):
            raise ActionRefused("applied")
        raise ActionRefused("entry_refused" if exc.status_code in (403, 409) else "not_waiting")
    step["status"] = "withdrawn"
    step["changes"] = [dict(c, after="Withdrawn") for c in step.get("changes") or []]
    db.execute(update(AgentAction).where(AgentAction.id == action.id).values(steps=steps))
    db.commit()
    return ActionOutcome(str(action.id), action.status, WITHDRAWN_REPLY, _out_steps(steps))


def actions_by_turn(db, turn_ids: list[str], user_id: str) -> dict[str, list[dict]]:
    """This user's actions per proposing turn, as they stand now (so a reload still shows what was done)."""
    from app.models.user import User

    if not turn_ids:
        return {}
    found = (
        db.query(AgentAction)
        .filter(AgentAction.turn_id.in_(turn_ids), AgentAction.user_id == str(user_id))
        .order_by(AgentAction.created_at, AgentAction.id)
        .all()
    )
    names = {
        str(i): n
        for i, n in db.query(User.id, User.name).filter(
            User.id.in_({a.decided_by_user_id for a in found if a.decided_by_user_id})
        )
    } if found else {}
    out: dict[str, list[dict]] = {}
    for a in found:
        out.setdefault(str(a.turn_id), []).append(
            {
                "id": str(a.id),
                # A proposal nobody decided in time reads Expired, whatever the row still says.
                "status": "expired" if a.status == "proposed" and _expires_at(a) < _now() else a.status,
                "decided_at": a.decided_at,
                "decided_by_name": names.get(str(a.decided_by_user_id)) if a.decided_by_user_id else None,
                "steps": [step_out(st, default_status="proposed") for st in a.steps or []],
            }
        )
    return out


# ------------------------------------------------------------------ decided cards (AGENT-DECIDED-CARDS)

#: An action the user decided: a cancel, or a confirm that ran (whatever each step's outcome).
DECIDED = ("cancelled", "executed", "partial", "rejected")
_STEP_MARKS = {"done": "done", "failed": "failed", "skipped": "not run", "withdrawn": "withdrawn"}


#: Argument keys that only echo the table and never change what a row asks for.
_ECHO_KEYS = frozenset({"access_as_written"})


def _canonical(value):
    """A value compared across cards: text trimmed, whitespace collapsed and lowercased; a list order-free."""
    if isinstance(value, str):
        return " ".join(value.split()).lower()
    if isinstance(value, (list, tuple, set)):
        return sorted((_canonical(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True, default=str))
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    return value


def row_identity(step: dict) -> tuple | None:
    """Which table row a step is, across cards: the write, its `batch_key` (a grant's phone) and what it asks for
    (every argument, compared without case, spacing or list order), so the same person asked for something else
    is a different row. None for a write that never batches."""
    definition = writes.write_def(step.get("tool"))
    args = step.get("args") if isinstance(step.get("args"), dict) else {}
    if definition is None or not definition.batchable:
        return None
    key = definition.batch_key(args) if definition.batch_key is not None else None
    plain = {k: v for k, v in args.items() if not str(k).startswith("_") and k not in _ECHO_KEYS and k != "row"}
    return (definition.name, key, json.dumps(_canonical(plain), sort_keys=True, ensure_ascii=False, default=str))


def closed_rows(db, contact_respond_id: str, conversation_id: str) -> dict[tuple, dict]:
    """The table rows of this conversation the user already decided, by `row_identity`: {"status": "cancelled" |
    "done", "args"}. The newest card holding a row speaks for it, so a row the user asked for again (a newer card
    proposed it) is open again; a step that failed or did not run stays open."""
    out: dict[tuple, dict] = {}
    rows = (
        db.query(AgentAction)
        .filter(
            AgentAction.contact_respond_id == str(contact_respond_id),  # the indexed column; same rows
            AgentAction.conversation_id == str(conversation_id),
        )
        .order_by(AgentAction.created_at, AgentAction.id)
        .all()
    )
    for action in rows:
        for step in action.steps or []:
            ident = row_identity(step)
            if ident is None:
                continue
            closed = None
            if action.status == "cancelled" or step.get("status") == "withdrawn":
                closed = "cancelled"
            elif action.status in DECIDED and step.get("status") == "done":
                closed = "done"
            if closed is None:
                out.pop(ident, None)
            else:
                out[ident] = {"status": closed, "args": dict(step.get("args") or {})}
    return out


def decision_note(action: AgentAction) -> str | None:
    """The fact the model reads after the turn that proposed `action`, once the user decided it (a panel Cancel or
    Confirm is not a chat turn, so the history would not say it otherwise). None while undecided."""
    steps = action.steps or []
    if action.status not in DECIDED or not steps:
        return None
    if action.status == "cancelled":
        rows = "; ".join(f"{n}. {writes._line(s.get('summary'))}" for n, s in enumerate(steps, 1))
        return (
            f"[Card cancelled by the user: nothing was changed. Its rows were: {rows}. These rows are closed: never "
            "propose them again unless the user's latest message asks for them again.]"
        )
    rows = "; ".join(
        f"{n}. {writes._line(s.get('summary'))} ({_STEP_MARKS.get(s.get('status'), s.get('status'))})"
        for n, s in enumerate(steps, 1)
    )
    head = (
        "Card confirmed by the user, but nothing ran" if action.status == "rejected" else "Card confirmed by the user"
    )
    return (
        f"[{head}. Rows: {rows}. Done rows are finished: never propose them again; a row marked failed or not run "
        "may be proposed again only if the user asks.]"
    )
