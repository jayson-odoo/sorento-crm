# Samantha replay, before and after (issue #1262)

Plan: `../../PLAN-chatbot-samantha-slices-26sep.md`.

## Method (read this first)

This is NOT a live-parser console pass. The cloud lane has no LLM key and an empty database,
so the parser verdict for each turn is stubbed, and so are the shared resolver and the MCP
tool results (the same doubles `tests/chatbot/` uses). Everything after the parser is the real
code: `engine.run_turn`, `resolve_gate`, `turn/decide.py`, `turn/apply.py`, fetch, compose,
and the session read/write on Postgres.

"After" was regenerated in fix lane round 2 (reviewer finding S4) at this branch's head after
the origin/main merge (`f2392887`), as ONE conversation for one contact, turn after turn. The
run seeds:

- a real company scope and the contact at profile tier `office`;
- an active brand `Sorento (SRT)` in `brands`, so brand resolution runs through the live list;
- a real `customers` row `CHENG HUAT SENTUL`, so the report and scope-question headers read
  the name back from the table. The first version of this document seeded no customer row,
  which is why it printed `Customer: all`. That was a replay artifact, not a product defect.
- the products `SRTBF 11502`, `SRTBF 11503` and `M210-GM`.

The stubbed report returns a rendered body with the list offer (so T5 runs under an open
offer, as in the real chat); stock and incoming return no rows.

"Before" is unchanged from the first version of this document (origin/main `253dafaf1`) and
was not re-run.

The live-parser pass is still owed: `sorento_crm_backend/tests/chatbot/console_cases/2026-09-26-samantha.yaml`,
run against a local lane backend on the prod copy with the new prompt version id (see the
file header). It now carries T5 (reviewer finding S2).

## T2 / T3 "outstanding brand Sorento dealer Cheng Huat Sentul"

Before:

```
Which one do you mean?
1. Sorento (customer)
2. Sorento (transporter)
```

(Cheng Huat Sentul dropped from focus while the pick is open.)

After, turn 1 (the scope question is the existing Contract 38 rule; no tool call yet):

```
Product: all
Customer: CHENG HUAT SENTUL
Location: all
Order date: all
Brand: Sorento
Outstanding for which document?
1. Sales orders (not yet transferred to DO)
2. Delivery orders (not yet delivered)
3. Both
```

No customer pick and no kind pick. Answering "3" calls `crm_outstanding_report` with
`customer_ids` = [CHENG HUAT SENTUL] and `brand_ids` = [Sorento], `scope: both`.

## T5 photo list "SRTBF 11502 x3 / SRTBF 11503 x4" under the open offer

After (parser verdict stubbed with `domain_hint: null`, `domain_in_message: false`):

```
Product: SRTBF 11502, SRTBF 11503
Customer: CHENG HUAT SENTUL
Location: all
Order date: all
Brand: Sorento
...
```

Tool call: `crm_outstanding_report` with `product_codes` = both codes, the carried customer
and the carried brand. The live parser's `domain_hint` on this turn is what the console case
pins (S2): an `inventory` or `incoming` hint here would make it a new ask.

## T6 "got eta" under the open outstanding offer

The offer closes on the domain switch (`test_samantha_26sep_s4_offer_topic.py`), and no
"0 products have incoming stock." header prints (`test_samantha_26sep_s6_incoming_header.py`).

After:

```
Could not find incoming.
```

Tool call: `crm_incoming_stock_list` with NO product filter. The domain switch drops the
closed offer's whole subject (`turn/apply.py::_drop_question_subject`), products included, so
"got eta" is not asked about the two products the customer just sent. Found while
regenerating this document and reported on the PR as a new finding. This round does not
fix it.

## T7 photo "X5 / M210-GM" (incoming)

Before:

```
Product: all
Customer: all
...
Outstanding for which document?
...
I could not find X5: M210-GM.
```

After (T6 closed the offer, so this is its own incoming ask):

```
Here's what you want:
• product: M210-GM (x5)

But no incoming matched these.
No incoming and no stock for M210-GM.
```

The code is no longer glued to the caption, the parser's quantity prints beside the code
(S1), no "Error executing tool" text appears, and there is no escalation offer (profile tier
office, slice 11).

## T10 photo "X5 / M210-GM", stock ask, staff

Before:

```
No stock found for X5: M210-GM.
I could not find X5: M210-GM.

Would you like me to escalate to warehouse team?
```

After:

```
Here's what you want:
• product: M210-GM (x5)

But no inventory matched these.
No stock and no incoming for M210-GM.
```
