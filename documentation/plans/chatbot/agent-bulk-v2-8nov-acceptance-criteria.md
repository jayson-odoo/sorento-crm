# UAC: Agent bulk actions v2 (AGENT-BULK-V2)

Plan: `PLAN-agent-bulk-v2-8nov.md`. Crew answers on the card (8 Nov): Q1 (a) list candidates, the owner picks, "all"
is one choice, never auto-link; Q3 (a) Confirm the ready rows now, waiting rows listed and left out; Q4 group
candidate only if the data shows such groups (pending); Q5 next wave = contact tags. Q2 (how the owner picks: chat
reply vs buttons) is with the owner; V12+ are written after that answer.

Tests: `sorento_crm_backend/tests/chatbot/agent/test_agent_bulk_v2.py` (test number in brackets).
#2226's UAC (`agent-bulk-actions-7nov-acceptance-criteria.md`, B1-B17) still holds except where a row below replaces it.

| # | Given / When | Then |
|---|---|---|
| V1 | A customer cell equal to one account's code, or one account's full name, in the row's company | linked as today (B6 unchanged) (01) |
| V2 | A customer cell that is neither, but is contained (case and spaces aside) in the names of 2+ active accounts of the row's company inside the user's companies (e.g. "Dealer H" -> 3 MCH accounts) | the row is NOT proposed and NOT skipped: it is "needs your choice", carrying the candidates (code + full name, ordered by code); nothing is linked (02) |
| V3 | The same with exactly ONE containing account | still "needs your choice" with that one candidate (never auto-linked: explicit links only) (02) |
| V4 | More than 10 accounts contain the cell | 10 candidates listed, plus "more than 10 accounts match; give a longer name or the code" (03) |
| V5 | Containing accounts that are inactive, of another company the row does not name, or outside the user's companies | never listed as candidates (03) |
| V6 | No account of the row's company contains the cell, but an account of the other company does | skipped: "\"X\" is a Mocha customer, but the row's company is Sorento" (names the company, lists no account) (04) |
| V7 | No account anywhere in the user's companies contains the cell | skipped: "No customer named \"X\" in your companies" (04) |
| V8 | A row with several problems (bad phone AND unknown customer AND unknown access word) | skipped once, with EVERY reason, in the order phone, access, company, customer (05) |
| V9 | A row with a hard problem (bad phone, unknown access) AND an ambiguous customer | skipped (not waiting), reasons include "\"X\" fits N accounts" (05) |
| V10 | A table where some rows are ready and some need a choice | the Confirm card holds ONLY the ready rows; the waiting rows are listed under "Needs your choice" with their candidates and are not steps (06) |
| V11 | A table where NO row is ready (all waiting or skipped) | the reply still ends with the code-built table (Needs your choice and/or Not changed); no Confirm card, no `agent_actions` row (07) |
| V12 | Any batch preview | one code-built block, parts in order: Ready table (if any), "Needs your choice" table (if any), "Not changed" table (if any) (06, 07) |
| V13 | The batch tool result the model reads | carries `needs_choice: [{row, written, company, candidates: [{code, name}]}]` and counts `rows_waiting`, so the model can ask which account; its counts back the reply's numbers (08) |
| V14 | A reply that says a row's customer was not found, after a batch call | accepted without a repair round (a batch skip backs the not-found wording) (09) |
| V15 | Every rule above | permission, audit and per-row confirm of #2226 unchanged (B1, B2, B12-B17 still green) |
