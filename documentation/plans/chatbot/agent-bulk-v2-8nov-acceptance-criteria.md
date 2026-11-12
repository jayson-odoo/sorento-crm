# UAC: Agent bulk actions v2 (AGENT-BULK-V2)

Plan: `PLAN-agent-bulk-v2-8nov.md`. Crew answers on the card (8 Nov): Q1 (a) list candidates, the owner picks, "all"
is one choice, never auto-link; Q3 (a) Confirm the ready rows now, waiting rows listed and left out; Q4 (b)
accounts only, no customer-group candidate (the dev DB groups are name-seeded by `cust_group_0001`, not office-made, and
miss accounts, so a group candidate would be name matching by the back door); Q5 next wave = contact tags. Q2 (a), owner 8 Nov ~10:40 "Ok for all rec": the owner picks by chat reply
("row 1: 300-F004, row 2 all, row 3 skip"); the agent re-proposes the whole table into a new Confirm card; no buttons
(V16-V21).

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
| V6b | The same written name exists in BOTH companies (a dealer with accounts in Sorento and Mocha) | only the row's company's accounts are candidates; the other company's are never listed or linked (03) |
| V7 | No account anywhere in the user's companies contains the cell | skipped: "No customer named \"X\" in your companies" (04) |
| V8 | A row with several problems (bad phone AND unknown customer AND unknown access word) | skipped once, with EVERY reason, in the order phone, access, company, customer (05) |
| V9 | A row with a hard problem (bad phone, unknown access) AND an ambiguous customer | skipped (not waiting), reasons include "\"X\" fits N accounts" (05) |
| V10 | A table where some rows are ready and some need a choice | the Confirm card holds ONLY the ready rows; the waiting rows are listed under "Needs your choice" with their candidates and are not steps (06) |
| V11 | A table where NO row is ready (all waiting or skipped) | the reply still ends with the code-built table (Needs your choice and/or Not changed); no Confirm card, no `agent_actions` row (07) |
| V12 | Any batch preview | one code-built block, parts in order: Ready table (if any), "Needs your choice" table (if any), "Not changed" table (if any) (06, 07) |
| V13 | The batch tool result the model reads | carries `needs_choice: [{row, written, company, candidates: [{code, name}]}]` and counts `rows_waiting`, so the model can ask which account; its counts back the reply's numbers (08) |
| V14 | A reply that says a row's customer was not found, after a batch call | accepted without a repair round (a batch skip backs the not-found wording) (09) |
| V15 | Every rule above | permission, audit and per-row confirm of #2226 unchanged (B1, B2, B12-B17 still green) |
| V16 | Turn 1 left rows waiting; the owner replies with a code per row ("row 1: F-1, row 2: H-2") | the agent re-proposes the whole table with those codes; ONE new Confirm card holds the picked rows (and any rows ready before); the earlier card, if any, is expired (10) |
| V17 | The owner replies "row 2 all" | row 2 links every account LISTED for it (not more than the 10 shown) (10) |
| V18 | The owner replies "row 3 skip", or skips row 1 | that row is left out; every other row keeps the row number of the pasted table in the preview (batch rows carry `row`, the table's row number) (11) |
| V19 | A re-proposed row picks a code that was neither listed for that row last turn nor typed in the owner's message this turn | the row is skipped: `"CODE" was not in the list for "X" (row N); pick from the list` (never linked) (11) |
| V20 | A code the owner typed in this turn's message, listed or not (e.g. a fresh table with the code in the Customer column) | accepted as an explicit link (11) |
| V21 | A table turn that leaves rows waiting, with or without ready rows | the waiting rows (row, phone, written name, listed codes) are kept on the turn (`response.batch_waiting`) and read by the next batch call of the same conversation; only the immediately previous table turn counts (12) |

Crew live x3 on 722d5e86 (8 Nov, gemini-3.6-flash, 18 turns): behaviour right 18/18; reply shape and cost fix round
(V22-V26).

| # | Given / When | Then |
|---|---|---|
| V22 | A table turn whose code-built block is shown (ready, waiting or skipped rows) | the reply is ONE code-built sentence of counts ("Rows from your table: N ready to confirm, N need your choice, N not changed.", zero parts left out) then the code-built tables; the model's own text is never shown, so no model copy of the tables and no candidate codes in prose (13) |
| V23 | Same turn | the model's final answer is accepted without the answer check (its text is replaced), so no repair round is spent (13) |
| V24 | A not-found claim after a batch call that quotes the term (`Customer named "X"`) or repeats the code's own reason (`No customer named "X" in your companies.`) | backed (no repair round) for a term the batch skipped as "No customer ..."; a term the batch never refused that way stays unbacked (14) |
| V25 | The closing line | any row waits: "Reply with the account code(s) for each row under Needs your choice, all, or skip." (plus " Or reply yes to confirm the ready rows now." when rows are ready); no row waits and rows are ready: "Reply yes to go ahead, or tell me what to change."; nothing ready or waiting: "Nothing can change yet; fix the rows above and send the table again." (14) |
| V26 | Every preview table | columns start "#", "Phone", "Name"; the ready table's "Will change" cell is never cut (all entries shown) (15) |
