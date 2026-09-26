# Samantha replay, before and after (issue #1262)

Plan: `../../PLAN-chatbot-samantha-slices-26sep.md`.

## Method (read this first)

This is NOT a live-parser console pass. The cloud lane has no LLM key and an empty database,
so the parser verdict for each turn is stubbed, and so are the shared resolver and the MCP
tool results (the same doubles `tests/chatbot/` uses). Everything after the parser is the real
code: `engine.run_turn`, `resolve_gate`, `turn/decide.py`, `turn/apply.py`, fetch, compose,
and the session read/write on Postgres. "Before" is origin/main `253dafaf1`; "after" is this
branch at `9935664f3`. The after run seeds a real company scope, the contact at profile tier
`office`, and an active brand `Sorento (SRT)` in the `brands` table, so brand resolution runs
through the live brand list, not a stub.

The live-parser pass is still owed: `sorento_crm_backend/tests/chatbot/console_cases/2026-09-26-samantha.yaml`,
run against a local lane backend on the prod copy with the new prompt version id (see the
file header).

## T2 / T3 "outstanding brand Sorento dealer Cheng Huat Sentul"

Before:

```
Which one do you mean?
1. Sorento (customer)
2. Sorento (transporter)
```

(Cheng Huat Sentul dropped from focus while the pick is open.)

After (turn 1 of the exchange; the scope question is the existing Contract 38 rule):

```
Product: all
Customer: all
Location: all
Order date: all
Brand: Sorento
Outstanding for which document?
1. Sales orders (not yet transferred to DO)
2. Delivery orders (not yet delivered)
3. Both
```

No customer pick and no kind pick. Answering "3" calls `crm_outstanding_report` with
`brand_ids` = Sorento's id and `customer_ids` = [Cheng Huat Sentul]
(`test_samantha_26sep_s9_brand_resolve.py`, two-turn test). Open item: the scope question's
own header prints `Customer: all` although the customer rides on the filters (see the PR).

## T6 "got eta" under the open outstanding offer

Before and after both print the incoming rows in this replay (the "0 products have incoming
stock." header needs the real predicate search, which the stub does not run; it is pinned by
`test_samantha_26sep_s6_incoming_header.py` at `envelope_of`). After: the outstanding offer is
closed by the domain switch (`test_samantha_26sep_s4_offer_topic.py`), so the next photo is its
own question.

## T7 / T9 photo, caption X5 / X4

Before:

```
Product: all
Customer: all
...
Outstanding for which document?
...
I could not find X5: M210-GM.
```

After:

```
Product: M210-GM
Customer: all
...
Outstanding for which document?
...
```

The code is no longer glued to the caption, and no "Error executing tool" text appears. The raw
INVALID_UUID leak itself is pinned by `test_samantha_26sep_s1_tool_error.py` and
`test_samantha_26sep_s2_uuid_only.py`.

## T10 photo X5 M210-GM, stock ask, staff

Before:

```
No stock found for X5: M210-GM.
I could not find X5: M210-GM.

Would you like me to escalate to warehouse team?
```

After:

```
No stock found for M210-GM.
Nothing on incoming stock either.
```
