# PLAN: a customer pick answer resumes the held sales ask (lane CHAT-CUSTOMER-PICK-RESUME)

Status: IN REVIEW (Opus reviewer READY at 1ae7b94d; owner data fix for the group ruled 25 Oct), small fix track (S: `report_ask.py`,
`gate._cust_base`, the resolve gate's name fill; no migration, no access change, no new ingest, no prompt change).

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
   the "[A/C I]" ledger and a customer hit on the "(PROJECT)" ledger, both in one customer group. `_cust_base` looks the
   group up on the suffix-stripped name, so the two land in two gate families, while the printed roster (full name) joins
   them into one line. Fix: the gate asks only when the roster PRINTS two or more lines (`printed_lines`, one
   `ledger_family_key` per representative's name, beside `len(bases) > 1` in `gate.py`). The gate's families are left as
   they are, because they decide which ledgers each printed line carries: a first cut that keyed `_cust_base` by the
   roster key (c05682bf) split the group's ungrouped "- [IBORN]" and inactive "(SHOWCASE)" ledgers into a line of their
   own (crew live check, 3 lines), against the owner's ruling below; reverted.
2. **A match with no name:** `_cust_base` fell back to the account code, the roster to the CRM name. Fix:
   `resolve_gate.name_unnamed_customers` fills `customers.customer_name` by uuid onto an unnamed customer match before the
   gate (after `_without_customer_rows`, so a hidden customer is never named), through the `customer_names` reader
   (`services.customer_names_reader`, passed by `turn_runtime.py` like `account_levels`; a failed read adds nothing).

Tests: O2 (case 1, the two prod shapes, red commit first), O1 (case 2), U5 (the name fill, unit). Kill: dropping
`len(printed_lines) > 1` fails O2; dropping the `customer_names` argument fails O1.

## Owner ruling on the group's ungrouped ledgers (25 Oct)
17:35: 300-F033 ("- [IBORN]") and the inactive 305-F001 count in the 300-F004 group. Neither has a customer group, so by
ruling (b) of 2 Oct (an ungrouped ledger is never joined by the name rule; `UNGROUPED_JOINS_NAME_MATCHED_GROUP` False) they
are a customer of their own, and they reached option 1 of the prod case only by resolver order (the gate's stripped-name
family, reviewer). Crew live check @1ae7b94d (b): "Dealer <customer> sanitary oct total sales", where no other customer
matches, asked between the group and "- [IBORN]". 18:4x, option (a) DATA: the office adds both ledgers to the group;
ruling (b) stays, no code rule.

Tests: O3 (the group, all four of its ledgers grouped, plus another customer: two lines, option 1 carries the four, the
pick reports them; red against c05682bf), O4 (only the group's ledgers match: no question, one report over the four; red at 26c2aec1 on the
ungrouped data, before the data fix was ruled), O5 (guard, ruling (b): with the two ledgers ungrouped
they stay their own line). Kill: `UNGROUPED_JOINS_NAME_MATCHED_GROUP` True fails exactly O5.
"water closet" read as a promotion is out of scope (separate lane).
