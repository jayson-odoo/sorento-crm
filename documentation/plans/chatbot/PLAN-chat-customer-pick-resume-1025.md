# PLAN: a customer pick answer resumes the held sales ask (lane CHAT-CUSTOMER-PICK-RESUME)

Status: IN PROGRESS (Plan), small fix track (S: backend chatbot only, no migration, no access change, no new ingest, no prompt change).

## Why
Prod 25 Oct 10:02 (prompt v63): t1 "Dealer <customer> oct total sales" -> the bot asks which customer (two options,
codes 300-F029 and 300-F059). t2 "1" -> "I can't break sales down by customer yet. I can show them by month, by year or
by channel." Expected: the October Dealer total for 300-F029.

The parser reads t2 as `open_question_answer {mode pick, picked [1]}` but also sets `group_by` "customer" and drops
`sales_channel`. A pure pick turn's axis fields must not survive into the resumed ask.

## Root cause / fix
(filled in below once traced)
