# PLAN: a customer pick answer resumes the held sales ask (lane CHAT-CUSTOMER-PICK-RESUME)

Status: IN PROGRESS (Build done, Review next), small fix track (S: `report_ask.py` + one engine line, no migration, no access
change, no new ingest, no prompt change).

## Why
Prod 25 Oct 10:02 (prompt v63, gpt-5.4-mini), and the owner again in the staff console: t1 "Dealer <customer> oct total sales"
-> "Which one do you mean? 1. ... (SRT, MCH) 2. ... (SRT)" (codes 300-F029, 300-F059). t2 "1" -> "I can't break sales down by
customer yet. I can show them by month, by year or by channel." Expected: the October Dealer total for 300-F029 (all its accounts).

The t2 parse: `business_query`, `order_status` sales_analysis, `group_by` "customer", `sales_channel` null, `entity_op` reuse,
`open_question_answer {mode pick, picked [1]}`. The open question: `customer_pick`, payload `{domain sales, status sales_report}`.

## Root cause (traced through the real engine, `tests/chatbot/test_chat_customer_pick_resume.py`)
1. `engine.py` runs `report_ask.by_capability` before grounding and APPLY. `group_by` customer is not in
   `CAN_DRAW["sales_analysis"]` (nor `["sales_report"]`, `report_ask.py:298-305`), so the pick turn is rerouted to
   `sales_ranking` (`capability_from` sales_analysis, `report_breakdown` true).
2. APPLY still answers the pick (`turn/apply.py` `_answer_pending`: focus.customers = the picked option, focus.status =
   the payload's sales_report), but the narrowing over a ranking verdict never marks the customer `just_picked`, so the lane
   receives no customer entity.
3. The lane's "staff sales_report with no subject -> company analysis" branch (`lanes/business/__init__.py` `run_fetch`)
   takes it, and that branch's axis guard refuses `group_by` customer (`_sales_analysis_axis_unsupported`).
Why `group_by` survives: nothing between the parser and `by_capability` reads the open question, so a pick's echo of the
roster's own kind ("picking a customer") is read as a breakdown axis.

## Rule (parser fields only, the engine seam before `by_capability`)
`report_ask.without_pick_axis(verdict, pending)`: when the open question is a `customer_pick` (or `product_pick`) and the
verdict picks a position (`open_question_answer.mode` pick with `picked`, or `reference_positions`), a `group_by` that names
the roster's own kind (customer / product) is the pick, not a breakdown: it is dropped. The held ask then resumes through
the existing pick path (status, channel and window off the focus; the picked option's uuids).

Unchanged: any other axis ("1 by month"), an "all" answer, no pick, any other open question (tier_pick, kind_pick, ...),
no open question.

Other pick kinds: `product_pick` is the same class (a `group_by` product on a product pick) and is covered by the same map.
`kind_pick` options mix kinds, so no single axis names it (left out). The sales company question is a `required_ask` slot,
already exempt from the axis check (`lanes/business/__init__.py`, "Crew re-verify E2").

## Tests (red first, real engine seam, v63 shapes)
`tests/chatbot/test_chat_customer_pick_resume.py`: P1 the prod t2 parse resumes the held report (one `crm_sales_report`,
the picked uuid, channel dealer, Oct window, no group_by, no refusal); P2 the same with `order_status` sales_report; P4 option
2 picks the second account. Guards: G1 the plain pick parse, G2 "1" with group_by month. Unit U1-U4 for the seam.
Kill: removing the engine call fails exactly P1, P2, P4.

## Owner add-on (25 Oct, in review with crew)
"Which one do you mean? 1. <one line>": a customer picker with one printed option. Suspected cause: the gate's ask decision
(`gate._cust_base` over the resolver's display name, account code when none) and the printed roster (`ledger_family_key`
over the CRM name) group by different names. Waiting on the t1 trace to confirm before fixing (crew-ask on the PR).
"water closet" read as a promotion is out of scope (separate lane).
