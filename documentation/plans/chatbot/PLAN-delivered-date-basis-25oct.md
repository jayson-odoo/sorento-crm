# PLAN: DELIVERED-DATE-BASIS (25 Oct 2026)

Status: Build done, in review (PR #1854). Track: standard (size L after Q0 (b)), no migration.

Owner ruling 25 Oct 2026 ~16:35: every DELIVERED sales measure buckets by the delivery order (DO) date, through one
shared function. Q0 ruled ~17:00: (b) (behaviour card `delivered-date-basis-behaviour-card.md`). Ordered and
outstanding keep their own basis. Q1 to Q6 are built on the recommendations as small switches; crew confirms them with
the owner on the hand test.

## The rule (one definition: `app/services/reports/datasets/delivery_order_lines.py`)

One row per delivery event, built per run (`_events`):

| Event | Rows | Date | Qty | Amount | Channel / agent |
|---|---|---|---|---|---|
| linked | live DO line that resolves to an SO line (line link, else the first line of its product on the SO the header or the doc number names) | DO date | DO line qty, no cap | DO line total (Q6, `LINKED_AMOUNT_FROM_DO`); an old-system line pro-rated (review S1) | the SO's |
| residual | live SO line, `least(qty_delivered, qty_ordered)` minus what DOs explain of it (its own linked lines, plus its share, in `line_no` order, of DO lines that name only its SO and product: review B1), when > 0 | SO line date (`required_date`, else SO `order_date`) | that rest | SO line pro-rata | the SO's |
| unlinked | live AutoCount DO line (`source_book` set) with no SO line | DO date | DO line qty | DO line total | the SO the header / doc number names, else none (Q1) |

Left out: old-system DO lines (`source_book` NULL) with no SO line (their SO's delivered qty is the residual; their
stored totals repeat the DOC total, so they are no line amount); consignment SOs (AC-CONSIGN-CRM); cancelled, deleted,
undated and `REP...` DOs (AC-SR-20). The #1401 DOC split is retired with the rows it priced.

## Surfaces moved onto it

| Surface | Change | File |
|---|---|---|
| Report ask delivered (rankings, totals, drill, refine, compare; chatbot `crm_report_ask`) | catalogue points at the shared definition | `services/reports/ask.py` (`_SALES_DEFINITIONS`) |
| Agent fill rate note on a delivered ranking (Q3 a) | `ask.delivered_fill_rate` over the same rows, every ranking filter applied | `ask.py`, `api/v1/order_management/report_ask.py` |
| Chatbot sales report (`crm_sales_report`) | same definition; residual rows list as "(no delivery order)" | `services/sales_report_delivered.py` |
| Yearly comparison screen + `crm_sales_analysis`, Basis Delivered | `datasets_by` basis delivered -> `YEARLY_DATASET`; note "by delivery order date" | `definitions/sales_yearly.py`, `datasets/sales_order_lines.py:note` |
| Legacy `GET /order-management/top-selling` delivered (Q5 a) | `_top_selling_delivered`, the engine over the definition | `services/sales_report_service.py` |
| Targets achievement (Q4 a) | unchanged (already DO-dated, its own cap and credit rules) | `services/sales/achievement_service.py` |

Engine change: a `DateBasis.expr` may be a function of the run (`engine.py` context build), and a Yearly split block
shares its parent's per-run cache (`engine._blocks`).

## Switches (owner to confirm on the hand test)

- Q1 a: an event with no SO is in no channel, silently (`channel_condition`).
- Q2 a: "orders" counts DOs, a residual its SO (`ORDERS_COUNT_DELIVERY_ORDERS`).
- Q3 a: fill rate over the delivered rows (`ask.delivered_fill_rate`).
- Q4 a: targets untouched.
- Q5 a: top selling delivered moved.
- Q6 a: a DO-linked delivery is worth the DO line total (`LINKED_AMOUNT_FROM_DO`).

## Tests

`tests/test_delivered_date_basis.py` (red first): DO date filing, no-SO lines with no channel, agent through the line /
doc link, ranking == sales report (3 periods x 3 channels), orders = DOs, ordered unchanged, partial delivery across
months, Yearly by DO month and its note, fill rate on DO date, "(no delivery order)" row, top selling delivered and its
detail, Q6 amount. Rewritten to the ruling, each citing it: report-ask catalogue (4 Oct direction superseded for
delivered), Yearly AC-S1-3 (ordered keeps G1), finance detail title and note, brand-scope sales report / top selling
totals, DBR debtor fallback, sales report dataset meta; seven legacy DOC split tests killed (the rows they priced no
longer count).

## Performance (measured 25 Oct 2026, 300k synthetic DO lines, 100k SO lines)

Delivered ask: 7.5 s first cut -> 1.4 s for a year of 174k delivered lines, 0.6 s with a product filter; ordered 0.07 s.
After review B1 (a DO naming only its SO is shared over that SO's lines of the product): 1.75 s and 1.1 s, on data
where EVERY DO line links by doc number only (prod Sep: 28% by line link). The more lines carry their own link, the
smaller the shared pool.
The floor is summing every DO line once per run to find what each SO line already has delivered. Trigger for more:
a prod delivered ask over ~1 s. Then (in order) the link lane DO-SO-LINK-SURFACE (#1855) filling
`order_lines.sales_order_line_id` takes the header / doc-number resolution off the hot path, and a per-SO-line
"explained qty" column maintained by the DO ingest removes the full scan.

## Depends on

DO-SO-LINK-SURFACE (#1855): the link chain needs the backfill's links; a DO line that resolves to no SO line is
unlinked (AutoCount) or out (old-system).
