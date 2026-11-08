"""`crm_batch_propose`: one generic tool that proposes a row write for every row of a pasted table
(AGENT-BULK-ACTIONS, PLAN-agent-bulk-actions-7nov.md).

Any `WriteDef` with `batchable=True` can be batched; a later wave adds a WriteDef, not a flow. Each row goes
through the write's own `propose_step` (its slug, its argument checks, its `read_before` as the user), so a row
that cannot apply is listed as skipped with its reason and never becomes a step. The rows that can apply become the
proposal's steps, each marked `batch`: confirm then runs every row in its own transaction (`actions.confirm`), so
one failed row never stops or half-writes another. Nothing is written here.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from app.services.chatbot.agent import writes
from app.services.chatbot.agent.tools import ToolResult

BATCH = "crm_batch_propose"
MAX_ROWS = 50
PREVIEW_HEAD = "I will make these changes when you confirm:"
SKIPPED_HEAD = "Not changed:"
NEEDS_HEAD = "Needs your choice:"
PREVIEW_TAIL = "Reply yes to go ahead, or tell me what to change."
CHOICE_TAIL = "Reply with the account code(s) for each row under Needs your choice, all, or skip."
TAG_CHOICE_TAIL = "Reply with the tag name(s) for each row under Needs your choice, all, or skip."
#: The arguments whose values are picks from a Needs your choice list (grant: account codes; tags: tag names).
PICK_ARGS = ("customer_codes", "tags_add", "tags_remove")
READY_NOW = " Or reply yes to confirm the ready rows now."
NOTHING_TAIL = "Nothing can change yet; fix the rows above and send the table again."
MORE_NOTE = "more than 10 accounts match; give a longer name or the code"
TAG_MORE_NOTE = "more than 10 tags match; give a longer name"


def batchable_writes(db, ctx) -> list[writes.WriteDef]:
    """The batchable writes this turn may propose (slug for the linked user and the console operator)."""
    return [w for w in writes.permitted_writes(db, ctx) if w.batchable]


def schema_for(db, ctx) -> dict | None:
    """The tool schema, or None when no batchable write is permitted. A row object carries the properties of every
    permitted batchable write; each row is checked against the chosen write's own schema."""
    defs = batchable_writes(db, ctx)
    if not defs:
        return None
    props: dict[str, Any] = {}
    for definition in defs:
        props.update(copy.deepcopy(definition.schema["function"]["parameters"].get("properties") or {}))
    props["row"] = {
        "type": "integer",
        "description": "The row's number in the pasted table; keep it when you re-propose.",
    }
    return {
        "type": "function",
        "function": {
            "name": BATCH,
            "description": (
                "Propose one change per row of a table the user pasted (any column order, English or Malay "
                "headers). `write` names the change; each row holds that change's arguments, copied from the "
                f"table. Up to {MAX_ROWS} rows. Rows that cannot apply are listed as skipped with the reason; the "
                "user sees one preview table and confirms once. A customer name that fits several accounts is not "
                "linked: the row waits and `needs_choice` lists its accounts; ask the user which account(s) per "
                "waiting row (codes, or all) and do not repeat the table. When the user picks accounts for waiting "
                "rows (codes; 'all' = every listed account of that row; 'skip' = leave the row out), call this again "
                "with the WHOLE table, every row's `row` kept and the picked codes in customer_codes (no "
                "customer_names for those rows). A tag name that is not exactly a tag waits the same way with the "
                "tags containing it; the picked tag names go in tags_add / tags_remove, the row's other tags kept. "
                "Nothing changes until the user confirms. Call it again with "
                "corrected rows to replace the proposal. Send EVERY row of the current request: ready, waiting and "
                "not changed alike, so the user sees the whole table. Leave out only a row of an earlier card the "
                "user already cancelled or confirmed (the history says 'Card cancelled' or 'Card confirmed'), "
                "unless the user's latest message asks for that row again; such a row comes back as skipped."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "write": {"type": "string", "enum": [d.name for d in defs]},
                    "rows": {"type": "array", "items": {"type": "object", "properties": props}},
                },
                "required": ["write", "rows"],
            },
        },
    }


def _cells(definition: writes.WriteDef, args: Any, shown: dict | None, summary: str = "") -> dict:
    if definition.preview is not None and isinstance(args, dict):
        return definition.preview(args, shown)
    return {"Change": summary} if shown is not None else {}


def _not_listed(args: dict, key: Any, previous: list[dict], user_text: str) -> str | None:
    """The skip reason when a row picks a code that neither the last table turn listed for this phone nor the user
    typed this turn; None when every code is allowed (or the row picks nothing)."""
    codes = [c for name in PICK_ARGS if isinstance(args.get(name), list) for c in args[name]]
    mine = [p for p in previous if key is not None and p.get("key") == key]
    if not mine or not codes:
        return None
    # A value the row resolved exactly last time (`kept`, tag rows) is the user's own, not a pick.
    listed = {" ".join(str(c).split()).lower() for p in mine for c in [*(p.get("codes") or []), *(p.get("kept") or [])]}
    typed = " ".join(str(user_text or "").split()).lower()
    for code in codes:
        said = " ".join(str(code).split())
        if said.lower() not in listed and not re.search(rf"(?<![0-9a-z]){re.escape(said.lower())}(?![0-9a-z])", typed):
            return f'"{said}" was not in the list for "{mine[0].get("written")}" (row {mine[0].get("row")}); pick from the list.'
    return None


CLOSED_CANCELLED = (
    "From your earlier cancelled table, so not proposed again; ask for it again (its phone or name) to include it."
)
CLOSED_DONE = "Already done on your earlier confirmed table."
_PHONE_RUN = re.compile(r"\+?\d[\d\s().-]{5,}\d")
_MATCH_DIGITS = 9


def _asked_again(args: dict, key: Any, user_text: str) -> bool:
    """Does the user's latest message name this row: its phone (the last 9 digits, any formatting, also inside a
    pasted list of numbers) or its name (whole words, any case)? Plain text, never the model's say-so."""
    raw = str(user_text or "")
    digits = re.sub(r"\D", "", str(key or ""))
    if len(digits) >= _MATCH_DIGITS:
        tail = digits[-_MATCH_DIGITS:]
        # Numbers on one line or one per line can run together here; a contained match still names the row.
        if any(tail in re.sub(r"\D", "", run) for run in _PHONE_RUN.findall(raw)):
            return True
    text = " ".join(raw.split()).lower()
    name = " ".join(str(args.get("name") or "").split()).lower()
    return len(name) >= 3 and re.search(rf"(?<![0-9a-z]){re.escape(name)}(?![0-9a-z])", text) is not None


def _closed_reason(write: str, args: dict, key: Any, closed: dict, user_text: str) -> str | None:
    """The skip reason for a row the user already decided on an earlier card of this conversation (cancelled, or
    done by a confirm), unless their latest message asks for it again; None when the row is open."""
    if not closed:
        return None
    from app.services.chatbot.agent.actions import row_identity

    ident = row_identity({"tool": write, "args": args})
    found = closed.get(ident) if ident is not None else None
    if found is None or _asked_again(args, key, user_text):
        return None
    return CLOSED_CANCELLED if found["status"] == "cancelled" else CLOSED_DONE


def propose_rows(
    db, ctx, write: str, rows: list, *, seen_ids: set[str], user_text: str = "",
    previous_waiting: list[dict] | None = None, closed: dict | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """(steps, skipped, waiting) for the rows, in input order. A skipped row: {"row", "reason", "cells"}. A waiting
    item (a row whose only problem is a customer name that fits several accounts; one per such name):
    {"row", "cells", "written", "company", "candidates", "more"}."""
    definition = writes.WRITES[write]
    steps: list[dict] = []
    skipped: list[dict] = []
    waiting: list[dict] = []
    keys: dict[Any, int] = {}
    def valid(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    numbers = [r["row"] for r in rows if isinstance(r, dict) and valid(r.get("row"))]
    use_given = len(numbers) == len(set(numbers))  # a repeated number makes every given number untrustworthy
    for position, args in enumerate(rows, 1):
        n = position
        if isinstance(args, dict):
            # The pasted table's own row number; it never reaches the write's argument check.
            args = dict(args)
            given = args.pop("row", None)
            if use_given and valid(given):
                n = given
        key = definition.batch_key(args) if definition.batch_key is not None and isinstance(args, dict) else None
        if key is not None and key in keys:
            skipped.append({"row": n, "reason": f"Same as row {keys[key]}.", "cells": _cells(definition, args, None)})
            continue
        if isinstance(args, dict):
            unlisted = _not_listed(args, key, previous_waiting or [], user_text) or _closed_reason(
                write, args, key, closed or {}, user_text
            )
            if unlisted:
                skipped.append({"row": n, "reason": unlisted, "cells": _cells(definition, args, None)})
                continue
        out, step = writes.propose_step(db, ctx, write, args, seen_ids=seen_ids)
        if step is None:
            choices = (out.data or {}).get("choices") if isinstance(out.data, dict) else None
            if choices:
                waiting += [{"row": n, "key": key, "cells": _cells(definition, args, None), **c} for c in choices]
                if key is not None:
                    keys[key] = n
                continue
            reason = out.message or "This row cannot be changed."
            skipped.append({"row": n, "reason": reason, "cells": _cells(definition, args, None)})
            continue
        if key is not None:
            keys[key] = n
        step.update(batch=True, row=n, cells=_cells(definition, args, step.get("shown") or {}, step["summary"]))
        steps.append(step)
    return steps, skipped, waiting


def carried_skips(
    steps: list[dict], skipped: list[dict], waiting: list[dict],
    previous_waiting: list[dict] | None, previous_skipped: list[dict] | None,
) -> list[dict]:
    """The not-changed rows of the earlier table turn that this call left out (AGENT-BATCH-NOTCHANGED). Only on the
    pick follow-up, i.e. that turn left rows waiting: the current request is still that table, so its not-changed
    rows stay listed with their earlier reason, whatever rows the model chose to send. A new table inherits none."""
    if not previous_waiting or not previous_skipped:
        return []
    sent = {s.get("row") for s in steps} | {s.get("row") for s in skipped} | {w.get("row") for w in waiting}
    return [
        {"row": s["row"], "reason": s["reason"], "cells": dict(s.get("cells") or {})}
        for s in previous_skipped
        if isinstance(s, dict) and s.get("row") not in sent and s.get("reason")
    ]


def propose(
    db, ctx, args: Any, steps: list[dict], *, seen_ids: set[str], skipped_out: list[dict] | None = None,
    waiting_out: list[dict] | None = None,
    user_text: str = "",
    previous_waiting: list[dict] | None = None,
    closed: dict | None = None,
    previous_skipped: list[dict] | None = None,
) -> ToolResult:
    """The loop's entry: check the call, then replace this turn's batch with the rows' steps. A batch stands alone:
    it is refused next to single changes of the same turn."""
    if not isinstance(args, dict):
        return ToolResult("invalid", message="Arguments must be an object of named values.")
    unknown = sorted(k for k in args if k not in ("write", "rows"))
    if unknown:
        return ToolResult("invalid", message=f"Unknown argument(s): {', '.join(map(str, unknown))}.")
    write, rows = args.get("write"), args.get("rows")
    definition = writes.WRITES.get(write) if isinstance(write, str) else None
    # A batched row gets no loop-set arguments (`_is_test`, `_user_text`), so a write that needs them never batches.
    if definition is None or not definition.batchable or definition.runs_as != "user" or write == writes.CREATE_IDEA:
        return ToolResult("invalid", message=f"{write} cannot be proposed for a table.")
    if definition.name not in {d.name for d in batchable_writes(db, ctx)}:
        return ToolResult("denied", message=f"{write} is outside this user's access.")
    if not isinstance(rows, list) or not rows:
        return ToolResult("invalid", message="rows must be a list of at least one row.")
    if len(rows) > MAX_ROWS:
        return ToolResult(
            "invalid", message=f"At most {MAX_ROWS} rows per confirmation; ask the user to split the table."
        )
    if any(not s.get("batch") for s in steps):
        return ToolResult("invalid", message="Propose the table on its own, not with other changes in the same turn.")
    new_steps, skipped, waiting = propose_rows(
        db, ctx, write, rows, seen_ids=seen_ids, user_text=user_text, previous_waiting=previous_waiting,
        closed=closed,
    )
    carried = carried_skips(new_steps, skipped, waiting, previous_waiting, previous_skipped)
    skipped += carried
    steps[:] = new_steps
    if skipped_out is not None:
        skipped_out[:] = skipped
    if waiting_out is not None:
        waiting_out[:] = waiting
    data = {
        "proposed": [{"row": s["row"], "summary": s["summary"]} for s in new_steps],
        "skipped": [{"row": s["row"], "reason": s["reason"]} for s in skipped],
        "needs_choice": [
            {k: w[k] for k in ("row", "written", "company", "candidates")} | ({"more": True} if w["more"] else {})
            for w in waiting
        ],
        # The counts the reply may say, so the number check finds them in this result.
        "rows_total": len(rows) + len(carried), "rows_proposed": len(new_steps), "rows_skipped": len(skipped),
        "rows_waiting": len({w["row"] for w in waiting}),
    }
    if not new_steps:
        if waiting:
            return ToolResult(
                "invalid", data=data,
                message=(
                    "No row is ready. The user sees the tables of rows that need a choice and rows not changed. "
                    "Ask which account(s) or tag(s) to use for each waiting row (codes or tag names, or all); do not "
                    "repeat the tables."
                ),
            )
        return ToolResult("invalid", data=data, message="No row can be changed; tell the user why, row by row.")
    return ToolResult(
        "proposed",
        data=data,
        message=(
            "Proposed, not done. The user sees the preview table and must confirm in a later message. "
            "Say in one line how many rows will change and how many are skipped or waiting; do not repeat the "
            "table. When needs_choice is not empty, ask which account(s) or tag(s) to use for each waiting row (codes or tag names, or all)."
        ),
    )


MAX_CELL_CHARS = 200


def _cell(value: Any, cap: bool = True) -> str:
    """A table cell: one line, no pipe, no markdown link brackets (a cell may hold the model's copy of the paste)."""
    text = writes._line(value).replace("|", "/").replace("[", "(").replace("]", ")")
    return (text if not cap or len(text) <= MAX_CELL_CHARS else f"{text[:MAX_CELL_CHARS]}...") or " "


def _table(headers: list[str], rows: list[list[Any]], uncapped: tuple[str, ...] = ()) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += [
        "| " + " | ".join(_cell(v, headers[i] not in uncapped) for i, v in enumerate(row)) + " |" for row in rows
    ]
    return "\n".join(lines)


def summary_line(steps: list[dict], skipped: list[dict], waiting: list[dict] | tuple = ()) -> str:
    """The reply's first line: how many distinct table rows are ready, need a choice, or were not changed."""
    counts = (
        (len({s.get("row") for s in steps}), "ready to confirm"),
        (len({w["row"] for w in waiting}), "need your choice"),
        (len({s["row"] for s in skipped}), "not changed"),
    )
    return "Rows from your table: " + ", ".join(f"{n} {word}" for n, word in counts if n) + "."


#: The cells every table starts with, whatever order a stored step's cells come back in (JSONB keeps no key order).
LEAD_CELLS = ("Phone", "Name")


def _heads(cells: list[dict]) -> list[str]:
    keys = list(dict.fromkeys(k for c in cells for k in c))
    return [k for k in LEAD_CELLS if k in keys] + [k for k in keys if k not in LEAD_CELLS]


def preview_block(steps: list[dict], skipped: list[dict], waiting: list[dict] | tuple = ()) -> str:
    """The turn as tables built by code: the ready rows (row number from the pasted table), the rows that need a
    choice, then the skipped rows and why."""
    parts: list[str] = []
    if steps:
        headers = _heads([s.get("cells") or {"Change": s.get("summary")} for s in steps])
        body = [[s.get("row", n)] + [(s.get("cells") or {"Change": s.get("summary")}).get(h, "") for h in headers]
                for n, s in enumerate(steps, 1)]
        parts += [PREVIEW_HEAD, _table(["#", *headers], body, uncapped=("Will change",))]
    tags = bool(waiting) and all(w.get("noun") == "tag" for w in waiting)
    if waiting:
        heads = _heads([w.get("cells") or {} for w in waiting])
        rows: list[list[Any]] = []
        for w in waiting:
            cells = [(w.get("cells") or {}).get(h, "") for h in heads]
            for i, c in enumerate(w["candidates"]):
                first = i == 0
                rows.append([w["row"], *cells] if first else [w["row"], *[""] * len(heads)])
                rows[-1] += [w["written"] if first else "", f"{c['code']} {c['name']}".strip()]
            if w.get("more"):
                rows.append([w["row"], *[""] * len(heads), "", MORE_NOTE if not tags else TAG_MORE_NOTE])
        parts += [NEEDS_HEAD, _table(["#", *heads, "You wrote", "Tag" if tags else "Account"], rows)]
    if skipped:
        heads = _heads([s.get("cells") or {} for s in skipped])
        rows = [[s["row"]] + [(s.get("cells") or {}).get(h, "") for h in heads] + [s["reason"]] for s in skipped]
        parts += [SKIPPED_HEAD, _table(["#", *heads, "Why"], rows)]
    if waiting:
        parts.append((TAG_CHOICE_TAIL if tags else CHOICE_TAIL) + (READY_NOW if steps else ""))
    else:
        parts.append(PREVIEW_TAIL if steps else NOTHING_TAIL)
    return "\n\n".join(parts)
