# UAC: escalation quote fallback, SLA comment timestamps, stock team

Plan: `PLAN-escalation-quote-title-and-stock-team-22sep.md`

## Quoted message in `source_message_text`

- AC-EQ-1 Customer message "Yes" quoting a message with `text` "Would you like me to escalate?" → `source_message_text` is `Yes reply to: Would you like me to escalate?`.
- AC-EQ-2 Same, quoted message carries only `title` (quick-reply shape) → `Yes reply to: <title>`.
- AC-EQ-3 Quoted message has neither text nor title (image with no caption) → `source_message_text` is exactly `Yes`; the string `undefined` never appears.

## Internal SLA comment

- AC-EQ-4 `_sla_create` given a tracking row whose `initiated_at` / `due_at` / `due_at_resolution` are `datetime` values → the comment reads `routed to you at 2026-09-22 14:34:00` (Asia/Kuala_Lumpur), and `[object Object]` never appears in any of the three lines.

## Suggested team for a stock question (domain_hint = inventory)

- AC-EQ-5 Stock row(s) qty 0 at every location, incoming empty, PO placed → offer sentence says `escalate to warehouse team?` and `parser["routing"]["suggested_team"] == "warehouse"`; `block["team"] == "warehouse"`.
- AC-EQ-6 No stock, no incoming, PO placed → same as AC-EQ-5.
- AC-EQ-7 No stock, incoming found, no PO → warehouse (unchanged behaviour, pinned).
- AC-EQ-8 No stock, no incoming, no PO → warehouse (unchanged, pinned).
- AC-EQ-9 Incoming-origin ask (domain_hint = incoming) that climbs to the PO rung → still `purchasing` (regression guard: the fix must not touch incoming-origin routing).
- AC-EQ-10 The PO "placed" line is still rendered when the PO rung answers (only the team word changes).
