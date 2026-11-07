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
from typing import Any

from app.services.chatbot.agent import writes
from app.services.chatbot.agent.tools import ToolResult

BATCH = "crm_batch_propose"
MAX_ROWS = 50
PREVIEW_HEAD = "I will make these changes when you confirm:"
SKIPPED_HEAD = "Not changed:"
NEEDS_HEAD = "Needs your choice:"
PREVIEW_TAIL = "Reply yes to go ahead, or tell me what to change."
CHOICE_TAIL = "Reply with the account code(s) to use for each row above, or all, or tell me what to change."
MORE_NOTE = "more than 10 accounts match; give a longer name or the code"


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
                "waiting row (codes, or all) and do not repeat the table, then call this again with the chosen "
                "codes in customer_codes. Nothing changes until the user confirms. Call it again with corrected "
                "rows to replace the proposal."
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


def propose_rows(
    db, ctx, write: str, rows: list, *, seen_ids: set[str]
) -> tuple[list[dict], list[dict], list[dict]]:
    """(steps, skipped, waiting) for the rows, in input order. A skipped row: {"row", "reason", "cells"}. A waiting
    item (a row whose only problem is a customer name that fits several accounts; one per such name):
    {"row", "cells", "written", "company", "candidates", "more"}."""
    definition = writes.WRITES[write]
    steps: list[dict] = []
    skipped: list[dict] = []
    waiting: list[dict] = []
    keys: dict[Any, int] = {}
    for n, args in enumerate(rows, 1):
        key = definition.batch_key(args) if definition.batch_key is not None and isinstance(args, dict) else None
        if key is not None and key in keys:
            skipped.append({"row": n, "reason": f"Same as row {keys[key]}.", "cells": _cells(definition, args, None)})
            continue
        out, step = writes.propose_step(db, ctx, write, args, seen_ids=seen_ids)
        if step is None:
            choices = (out.data or {}).get("choices") if isinstance(out.data, dict) else None
            if choices:
                waiting += [{"row": n, "cells": _cells(definition, args, None), **c} for c in choices]
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


def propose(
    db, ctx, args: Any, steps: list[dict], *, seen_ids: set[str], skipped_out: list[dict] | None = None,
    waiting_out: list[dict] | None = None,
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
    new_steps, skipped, waiting = propose_rows(db, ctx, write, rows, seen_ids=seen_ids)
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
        "rows_total": len(rows), "rows_proposed": len(new_steps), "rows_skipped": len(skipped),
        "rows_waiting": len({w["row"] for w in waiting}),
    }
    if not new_steps:
        if waiting:
            return ToolResult(
                "invalid", data=data,
                message=(
                    "No row is ready. The user sees the tables of rows that need a choice and rows not changed. "
                    "Ask which account(s) to use for each waiting row (codes, or all); do not repeat the tables."
                ),
            )
        return ToolResult("invalid", data=data, message="No row can be changed; tell the user why, row by row.")
    return ToolResult(
        "proposed",
        data=data,
        message=(
            "Proposed, not done. The user sees the preview table and must confirm in a later message. "
            "Say in one line how many rows will change and how many are skipped or waiting; do not repeat the "
            "table. When needs_choice is not empty, ask which account(s) to use for each waiting row (codes, or all)."
        ),
    )


MAX_CELL_CHARS = 200


def _cell(value: Any) -> str:
    """A table cell: one line, no pipe, no markdown link brackets (a cell may hold the model's copy of the paste)."""
    text = writes._line(value).replace("|", "/").replace("[", "(").replace("]", ")")
    return (text if len(text) <= MAX_CELL_CHARS else f"{text[:MAX_CELL_CHARS]}...") or " "


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def preview_block(steps: list[dict], skipped: list[dict], waiting: list[dict] | tuple = ()) -> str:
    """The turn as tables built by code: the ready rows (row number from the pasted table), the rows that need a
    choice, then the skipped rows and why."""
    parts: list[str] = []
    if steps:
        headers = list(dict.fromkeys(k for s in steps for k in (s.get("cells") or {"Change": s.get("summary")})))
        body = [[s.get("row", n)] + [(s.get("cells") or {"Change": s.get("summary")}).get(h, "") for h in headers]
                for n, s in enumerate(steps, 1)]
        parts += [PREVIEW_HEAD, _table(["#", *headers], body)]
    if waiting:
        heads = list(dict.fromkeys(k for w in waiting for k in w.get("cells") or {}))
        rows: list[list[Any]] = []
        for w in waiting:
            cells = [(w.get("cells") or {}).get(h, "") for h in heads]
            for i, c in enumerate(w["candidates"]):
                first = i == 0
                rows.append([w["row"], *cells] if first else [w["row"], *[""] * len(heads)])
                rows[-1] += [w["written"] if first else "", f"{c['code']} {c['name']}"]
            if w.get("more"):
                rows.append([w["row"], *[""] * len(heads), "", MORE_NOTE])
        parts += [NEEDS_HEAD, _table(["#", *heads, "You wrote", "Account"], rows)]
    if skipped:
        heads = list(dict.fromkeys(k for s in skipped for k in s.get("cells") or {}))
        rows = [[s["row"]] + [(s.get("cells") or {}).get(h, "") for h in heads] + [s["reason"]] for s in skipped]
        parts += [SKIPPED_HEAD, _table(["#", *heads, "Why"], rows)]
    parts.append(PREVIEW_TAIL if steps else CHOICE_TAIL)
    return "\n\n".join(parts)
