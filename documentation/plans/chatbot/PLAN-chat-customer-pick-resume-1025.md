# PLAN: a customer pick answer resumes the held sales ask (lane CHAT-CUSTOMER-PICK-RESUME)

Status: IN REVIEW (reviewer READY on the pick fix; add-on re-review on the final head), small fix track (S: `report_ask.py` + one engine line, no migration, no access
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

## Owner add-on: a "picker" of one printed line (25 Oct)
"Dealer <customer> sanitary oct total sales for water closet" -> "Which one do you mean? 1. <one line>". The gate decides to
ask on its own family count (`gate._cust_base`), and the printed roster is rebuilt with another key (`narrow.customer_options`
-> `ledger_family_key` over the full name it prints). Two ways they disagreed, both fixed so the ask count is the printed count:

1. **Both matches named, one customer group (the prod case, crew trace afd7779e on the prod clone):** a debtor-name hit on
   the "[A/C I]" ledger (display customer_name "... SDN BHD [A/C I]") and a customer hit on the "(PROJECT)" ledger, both
   in one customer group. `_cust_base` looked the group up on the SUFFIX-STRIPPED name ("... SDN BHD"), which no ledger
   carries, so `customer_group_of` (exact full name, `ledger_family.py`) missed and the row got "<key> (NO GROUP)", while
   the "(PROJECT)" row got the group key: two gate families, one printed line. Fix: `_cust_base` IS the roster's key,
   `ledger_family_key(_display_name(match) or canonical_code)` (`gate.py`); the gate's own regex copy of the name rule and
   its stripped group lookup are gone.
2. **A match with no name:** `_cust_base` fell back to the account code, the roster to the CRM name. Fix:
   `resolve_gate.name_unnamed_customers` fills `customers.customer_name` by uuid onto an unnamed customer match before the
   gate (after `_without_customer_rows`, so a hidden customer is never named), through the `customer_names` reader
   (`services.customer_names_reader`, passed by `turn_runtime.py` like `account_levels`; a failed read adds nothing).

Tests: O2 (case 1, the two prod shapes, red commit first), O1 (case 2), U5 (the name fill, unit). Kill: `_cust_base` back to
the stripped lookup fails O2; dropping the `customer_names` argument fails O1.

Owner note (no change): option 1 of "Dealer fullshun oct total sales" is the whole FULLSHUN SANITARYWARE group across SRT and
MCH (9 accounts), and that includes the ungrouped "- [IBORN]" ledger (name rule) and the inactive "(SHOWCASE)" one.
"water closet" read as a promotion is out of scope (separate lane).
