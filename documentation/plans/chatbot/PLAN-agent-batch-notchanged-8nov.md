# PLAN: agent batch keeps the not-changed rows of the current request (AGENT-BATCH-NOTCHANGED)

Status: built, in review (small fix track: no migration, no auth/RBAC change, no new ingest surface)

## Problem

Follow-up to #2250. Crew live check, grant prompt P5 run 1 (`laneboard/scripts/2241-live.md`): on the pick
follow-up (`row 1: 300-F004, row 2 all`) the model sent only the 2 ready rows, so row 3 ("No Such Shop Sdn Bhd",
not changed on P4) disappeared from the Not changed table and the reply read "Rows from your table: 2 ready to
confirm." In #2241 the row was always kept (6/6). Cause: #2250's tool wording "Propose only the rows still open in
the CURRENT request" reads to the model as "drop the rows that were not changed".

## Fix

1. Code, deterministic: a table turn stores its not-changed rows (`batch_skipped`: row, reason, cells) next to
   `batch_waiting` on the turn response (`loop.py`). On the pick follow-up (the newest earlier table turn left rows
   waiting), `batch.propose` puts back every not-changed row of that turn whose row number the model did not send,
   with its earlier reason. The model never decides whether such a row is shown.
2. Tool wording: send EVERY row of the current request (ready, waiting and not changed); leave out only rows of a
   card the user already cancelled or confirmed.

## Tests (red first)

`sorento_crm_backend/tests/chatbot/agent/test_agent_batch_notchanged.py`: a 3-row request where row 3 is not
changed; the follow-up pick sends only rows 1 and 2; row 3 is still under Not changed with its reason and the
summary line counts it. A brand-new table (no waiting rows before it) inherits nothing.
