"""Proposals, confirm and cancel (AGENTIC-P3 plan sections 2 to 4).

A turn's write calls become one `chatbot.agent_actions` row (`proposed`). Confirming re-checks every
step before writing anything, claims the row atomically, then runs the steps in order and stops at the
first failure. The same functions serve the console buttons and the chat tools.
"""
from __future__ import annotations

import copy
import dataclasses
import logging
import re
import uuid
from dataclasses import dataclass
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
    entry_refused, changed, same_turn."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class ActionOutcome:
    action_id: str
    status: str  # executed | partial | rejected | cancelled
    reply_text: str
    steps: list[dict]  # [{"summary", "status": done|failed|skipped|proposed, "error"}]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def store_proposal(
    db, ctx, *, conversation_id: str, turn_id: str, steps: list[dict], action_id: str | None = None
) -> AgentAction:
    """The turn's steps as a `proposed` action. Older `proposed` actions of the contact expire."""
    now = _now()
    db.query(AgentAction).filter(
        AgentAction.contact_respond_id == ctx.contact_respond_id, AgentAction.status == "proposed"
    ).update({AgentAction.status: "expired"}, synchronize_session=False)
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
    db, contact_respond_id: str, *, now: datetime | None = None, user_id: str | None = None
) -> AgentAction | None:
    """The newest `proposed` action of the contact (of this linked user, when given), unless it has expired."""
    query = db.query(AgentAction).filter(
        AgentAction.contact_respond_id == contact_respond_id, AgentAction.status == "proposed"
    )
    if user_id is not None:
        query = query.filter(AgentAction.user_id == str(user_id))
    row = query.order_by(AgentAction.created_at.desc(), AgentAction.id.desc()).first()
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


def _out_steps(steps: list[dict]) -> list[dict]:
    return [
        {"summary": s.get("summary"), "status": s.get("status"), "error": scrub_ids(s.get("error")), "changes": s.get("changes") or []}
        for s in steps
    ]


# ------------------------------------------------------------------ confirm


def _recheck(db, ctx, step: dict) -> str | None:
    """Why this step may no longer run, or None. Reads the record again as the user."""
    definition = writes.WRITES.get(step["tool"])
    if definition is None:
        return "This change is no longer available."
    if not writes.holds(db, ctx.user_id, definition.user_permission):
        return "You no longer have permission for this change."
    if not writes.holds_ctx(db, ctx, definition.user_permission):
        return "You do not have permission for this change."
    try:
        now = writes.read_before_all(db, ctx, definition, step["args"])
    except Exception as exc:  # noqa: BLE001
        text = writes.error_text(exc)
        # A rule that now refuses (nothing left to change, a field no longer valid) means it moved on.
        return f"This changed since it was proposed: {text}" if getattr(exc, "status_code", 0) == 422 else text
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
        if s["status"] == "parked":
            tail = f" (commits at {writes._local_time(s.get('commit_at'))} unless cancelled)"
        if s.get("error"):
            tail = f" ({marks.get(s['status'], s['status'])}: {scrub_ids(s['error'])})"
        lines.append(f"{n}. {s['summary']}{tail}")
    head = {
        "executed": "Done. I made these changes:",
        "partial": "I made some of the changes and stopped at a failure:",
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
        (d := writes.WRITES.get(step.get("tool"))) is not None and writes.holds_ctx(db, ctx, d.user_permission)
        for step in action.steps or []
    )


def confirm(
    db, contact_respond_id: str, action_id: str, *, via: str, turn_id: str | None = None,
    now: datetime | None = None, operator_user_id: str | None = None,
) -> ActionOutcome:
    action = _load(db, contact_respond_id, action_id)
    if action.status != "proposed":
        raise ActionRefused("not_proposed")
    newest = (
        db.query(AgentAction)
        .filter(AgentAction.contact_respond_id == contact_respond_id, AgentAction.status == "proposed")
        .order_by(AgentAction.created_at.desc(), AgentAction.id.desc())
        .first()
    )
    if newest is not None and str(newest.id) != str(action.id):
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
    for step in steps:
        problem = _recheck(db, ctx, step)
        if problem:
            step["status"], step["error"] = "failed", problem
            for other in steps:
                if other is not step:
                    other["status"] = "skipped"
            return _finish(
                db, action, "rejected", steps, via=via, turn_id=turn_id, expect="proposed", decider=decider
            )

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
        if failed:
            step["status"] = "skipped"
            continue
        definition = writes.WRITES[step["tool"]]
        try:
            result = writes.run_as_user(
                db, ctx, lambda user: definition.execute(db, user, step["args"]), tool_name=step["tool"]
            )
            step.update(status="done", result_id=result.get("id"), after=result.get("after"), error=None)
            try:
                if definition.changes is not None:
                    step["changes"] = definition.changes(
                        step["args"], step.get("before") or {}, result.get("after") or {}, step.get("shown") or {}
                    )
            except Exception:  # noqa: BLE001 - the write is done; a missing summary must not undo it
                logger.warning("agent: building the change lines failed", exc_info=True)
            if result.get("parked"):
                # Deferred by the grace window: nothing is committed or sent until it lapses.
                step.update(status="parked", **result["parked"])
            if "unlinked_customer_ids" in result:
                step["unlinked_customer_ids"] = result["unlinked_customer_ids"]
        except Exception as exc:  # noqa: BLE001 - a route refusal stops the run
            db.rollback()
            if not isinstance(exc, writes.HTTPException):
                logger.warning("agent: action step failed", exc_info=True)
            step.update(status="failed", error=writes.error_text(exc))
            failed = True
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
    return ActionOutcome(str(action.id), status, _reply(status, steps), _out_steps(steps))


# ------------------------------------------------------------------ cancel


def cancel(db, contact_respond_id: str, action_id: str, *, operator_user_id: str | None = None) -> ActionOutcome:
    action = _load(db, contact_respond_id, action_id)
    if operator_user_id:
        # A console operator may cancel for the linked user only while that is still who the action is for,
        # and only when they could have confirmed at least one step themselves.
        try:
            ctx = build_context(db, contact_respond_id)
        except AgentRefused:
            raise ActionRefused("entry_refused")
        theirs = str(operator_user_id)
        may = theirs == str(ctx.user_id) or any(
            (d := writes.WRITES.get(step.get("tool"))) is not None and writes.holds(db, theirs, d.user_permission)
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
