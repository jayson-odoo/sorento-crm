# PLAN: escalation quote fallback, SLA comment timestamps, stock question always routes to warehouse

Status: small fix track, building (lane `fix/chatbot-reply-quote-and-team`, worktree `sorento_crm-ticket-reply-team`)
UAC: `escalation-quote-title-and-stock-team-22sep-acceptance-criteria.md`
Owner rulings (22 Sep 2026): R1 drop the ` reply to:` suffix when the quoted message has neither text nor title; R6 a stock question is always suggested to the warehouse team, no rung override.

## Journey

Dealer quotes the bot's "Would you like me to escalate to purchasing team?" message and replies "Yes". Staff opens the ticket in the CRM drawer.

Today: header reads `Yes reply to: undefined`, the internal Respond.io note reads `routed to you at [object Object]`, and the ticket sits with the purchasing team although the dealer asked about stock.

After: header reads `Yes reply to: Would you like me to escalate...`, the note carries Malaysia-time timestamps, and the offer + assignment name the warehouse team.

## Defects (all in `sorento_crm_backend/`)

1. `app/services/chatbot/lanes/escalation.py:1245-1247` `_input_message` reads `replyTo.message.text` only. Respond.io delivers a quoted quick-reply message under `title`. `engine.py:321-323` already falls back to `title`.
2. `app/services/chatbot/lanes/escalation_services.py:105-107` `_sla_create` hands back `datetime` objects; `escalation.py:440-456` `_malaysia` calls `jsc.js_string(datetime)`, which renders `[object Object]`. Tests stub ISO strings so the path was never exercised.
3. `app/services/chatbot/lanes/business/answer.py:1120` `_CROSSDOMAIN_RUNG_TEAM = {"purchase_order": "purchasing"}` and `:1425-1444` `_apply_crossdomain_rung` rewrite `parser["routing"]["suggested_team"]` and `block["team"]` to `purchasing` whenever the PO rung answers a stock-origin ask. Parser prompt and `turn/policy_rows.py:141` already say inventory → warehouse.

## Fix

1. `_input_message`: quoted body = `text` if truthy else `title`; if neither is truthy, append nothing. Update the docstring (it currently documents the n8n parity choice).
2. `_sla_create`: return `initiated_at` / `due_at` / `due_at_resolution` as ISO-8601 strings (`.isoformat()` when the value is a `datetime`, else pass through). `_malaysia` unchanged.
3. Delete `_CROSSDOMAIN_RUNG_TEAM` and the override block in `_apply_crossdomain_rung`. The offer sentence and routing keep the question-origin team from `crossdomain_zeroset` (`answer.py:489`). Incoming-origin asks are unaffected (incoming → purchasing already).

## Tests (write first, red, then green)

Files: `tests/chatbot/test_s5_escalation_seams.py` (or a sibling), `tests/chatbot/test_crossdomain_ladder.py`.

- AC-EQ-1..3 quote fallback; AC-EQ-4 datetime comment; AC-EQ-5..7 team.
- Flip the five assertions that pin "purchasing wins": `test_crossdomain_ladder.py:217-238` (`TestAC921...`), `:390-398` (`test_rung_found`), `:757-769`, `:894-933` (incoming-origin PO-rung tests: check whether they assert the team; incoming-origin stays purchasing so they may need no change), `:1197-1212`.

## Out of scope

Frontend header rendering (lane `fix/sla-chat-panel-layout`), keep-assignee-on-resolve (lane `fix/sla-keep-assignee-on-resolve`).
