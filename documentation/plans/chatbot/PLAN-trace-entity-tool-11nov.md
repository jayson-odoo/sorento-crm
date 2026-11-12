# PLAN: TRACE-ENTITY-TOOL - every chatbot turn trace shows the matched entity and the tool used

Status: in review, PR #2344 (small fix track: under ~300 lines, no migration, no auth/RBAC, no new ingest surface)

## Why

Owner, 11 Nov 2026, on turn #8322 (business_query lane, message "srtwc286", stock check): "why does
it not tell about the entity matched and the tool used".

## Findings

- The business lane writes the real tool event `{name, args, envelope, ms}`, then
  `turn/fetch.py::_fetch_one` writes a bare `{"domain": ...}` tool event after it. The drawer
  readers (`trace_detail._tool`, `_looked_up`) take the LAST tool event, so the drawer shows "Tool: -".
- Product codes resolved by `resolve_kinds` (in-process `/system/references/resolve`) are never
  written to the trace; "Index match" reads only `closed_lists_index` events (index mode only).
- Ran after / Next show "Not recorded" when a turn simply has no neighbour.

## Build

1. One rule for every reader: the tool shown is the last tool event WITH a name
   (`trace_mod.named_tool_event`). The fetch step's bare event stays (analytics counts domains) but
   is no longer picked as "the tool".
2. A `resolve` trace event after `resolve_kinds`: per typed word, matched codes (cap 10, "+N more"),
   match tier, and unplaced words. Rendered as "Entity match" in the drawer. Span pass labels code
   spans "sent to the code lookup", not "skipped".
3. Ran after / Next: "First message in this conversation" / "No later message yet".

## Tests (red first)

- trace_detail picks the named tool when a bare domain event follows it.
- resolve event rendered as entity match rows (cap + "+N more").
- span pass wording; drawer neighbour wording (vitest).
