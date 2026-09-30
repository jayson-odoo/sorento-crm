# PLAN: chatbot empty "choose who to route to" list + phantom open_question_answer pick

Status: in progress, small fix track (no migration, no auth change, no new ingest surface)
Lane: CHATBOT-EMPTY-ROUTE-PICK, branch `claude/chatbot-empty-route-pick-x5e9ad`, base `origin/main`
UAC: `chatbot-empty-route-pick-acceptance-criteria.md` (alongside)

## Owner repro (30 Sep 2026, Chatbot Console, contact Fanny Ng, prompt v37)

User: "Zhin heng delivered on 23/9". Bot:

```
Customer: Zhin heng / Product: all products / Dates: 23/09/2026

Please choose who to route to (reply with the number):

If you have no preference, just reply 'yes' and we'll assign automatically.
No orders matched these.
```

Parser: `business_query` / `check_order` / document `["DO"]` / `delivered` / date 2026-09-23,
entity `{raw "Zhin heng", hint customer, canonical_code null}`, routing
`customer_service` / `order_enquiries`, and `open_question_answer {"mode":"pick","items":[],
"picked":[1]}` while no open question was pending.

## Findings (file:line on this branch)

Filled in as the lane proceeds; the PR's `crew-done` comment carries the final version.

## Slices

1. Regression tests (red first) for the phantom pick drop and the empty picker.
2. Engine: drop `open_question_answer` and `reference_positions` when the turn has no open
   question (`turn/question.open_question(pending, tasks)` is None).
3. Order list R6 reply: when the routing picker's options are taken out, take the picker's
   header and its "reply 'yes'" close out with them; never render a picker with zero rows.
4. Report on the unresolved-customer path and the prompt version question.
