# Behaviour card: REPORT-OUTSTANDING-SUMMARY (29 Oct 2026)

Status: Answered (owner 29 Oct). Q1 (a) with access-aware kinds and unpaid never offered; Q2 default group-bys, the user's own axes and filters win; Q3 ok; access (a) the pre-#1922 split. See the plan.

## The regression

#1922 REPORT-UNIFY moved every outstanding ask onto `crm_report_ask` (owner rule 27 Oct: one shared report
service). That path prints ONE total for an outstanding kind (`presenters._report_ask`, the `not group_by`
branch), so the summary the old `crm_outstanding_report` printed is gone: counts, the quantity lines, the date
range, By location, By customer (or By product), and the DO list offer.

Pre-#1922 path: `lanes/business/__init__.py:2208` (on 98773e5a^) picked `crm_outstanding_report`;
`outstanding_report_service.outstanding_report` built `do_by_location` / `do_by_customer` / `do_by_product`
(R13: a product subject gets By customer, a customer subject gets By product, both named gets neither);
`presenters._outstanding_do_block` / `_outstanding_so_block` printed them, then `Reply 1 for the delivery
order list.` (`presenters._outstanding_report`).

Main today: `report_ask.by_capability` routes the ask to `crm_report_ask` via `as_outstanding`; no kind ->
`KIND_QUESTION` (`report_ask.py:225`, options `KIND_OPTIONS`); after the kind, one total only; the list offer
exists only for undelivered SO (`fetch.py` `_SO_LIST_OFFER`).

## The fix (one engine, no old tool)

The route `GET /order-management/report-ask` adds a `summary` block to the body when ALL hold:
basis is `outstanding` or `pending_delivery`, no `group_by`, no `compare_to`, and the ask names a product or a
customer (the old tool's "needs a subject" rule). Every figure in it is `reports.ask.run_ask` over the SAME
definition and filters as the total (grouped by location, by customer or product, by document for the count,
by day for the date range), so the summary and the total cannot disagree. The MCP presenter prints it in the
old shape. Pending delivery arms "Reply 1 for the delivery order list." (the held frame grouped by delivery
order), as undelivered orders already arm the sales order list.

Data note: this sandbox has no dev or prod data (crew rule: no shared DB). The cases below are the prod turn
from the brief plus seeded test data; the figures are illustrative and masked.

## Cases (before = main 6011ba76, after = this lane)

### C1 (prod turn #b6e9, 26 Oct 09:28): "Srt5733 stock and outstanding"

Pre-#1922 reply (outstanding half; stock block unchanged):

```
Product: SRT5733-xx
Customer: all
Location: all
Order date: all
*Delivery order outstanding*
Delivery orders: 3
DO qty: 40
Delivered: 0
Outstanding: 40
DO date range: 02/10/2026 to 20/10/2026
*_By location_*
WH-A: 30 (O/S: 30)
WH-B: 10 (O/S: 10)
*_By customer_*
<Customer A>: 25 (O/S: 25)
<Customer B>: 15 (O/S: 15)

Reply 1 for the delivery order list.
```

Main today: stock block, then `Undelivered orders, pending delivery or unpaid invoices?`; on "pending
delivery":

```
Pending delivery
Product: SRT5733-xx
Period: all dates
Total RM 1,234.00, 40 pcs
```

After (on "pending delivery", Q1 a):

```
Pending delivery
Product: SRT5733-xx
Period: all dates
Delivery orders: 3
DO qty: 40
Delivered: 0
Outstanding: 40 pcs, RM 1,234.00
DO date range: 02/10/2026 to 20/10/2026
*_By location_*
WH-A: 30 (O/S: 30)
WH-B: 10 (O/S: 10)
*_By customer_*
<Customer A>: 25 (O/S: 25)
<Customer B>: 15 (O/S: 15)

Reply 1 for the delivery order list.
```

### C2: "<Customer A> outstanding" -> kind "undelivered orders"

Main: `Undelivered orders / Customer: <Customer A> / Period: all dates / Total RM 9,800.00, 120 pcs` + SO list offer.

After:

```
Undelivered orders
Customer: <Customer A>
Period: all dates
Sales orders: 4
Ordered: 300
Transferred to DO: 180
Outstanding: 120 pcs, RM 9,800.00
Order date range: 05/08/2026 to 21/10/2026
*_By location_*
WH-A: 300 (O/S: 120)
*_By product_*
<Product 1>: 200 (O/S: 80)
<Product 2>: 100 (O/S: 40)

Reply 1 for the sales order list.
```

### C3: "SRT5733 outstanding for <Customer A>" (both named) -> By location only (R13).

### C4: "outstanding" with no subject -> kind asked, then the one total, unchanged (no subject, no summary).

### C5: unpaid invoices -> unchanged (per document: no location, no product).

## Questions (recommendations)

- **Q1. A product outstanding ask: default to pending delivery (as the prod turn did) or keep asking the kind?**
  (a) keep asking the kind, then print the summary; (b) default a product or customer ask to pending delivery.
  **Rec (a):** owner ruling 27 Oct Q2 ("ask which outstanding, never default", recorded in
  `CARD-report-unify-27oct.md` status line and `PLAN-report-unify-27oct.md` Q12 "An outstanding kind is never
  inferred"). The memory note on sales basis is about sales, but the outstanding ruling says the same. Pre-#1922
  also asked (SO / DO / both) whenever the contact held the SO reveal; the prod turn defaulted only because that
  contact did not. The regression the owner named is the shape, which (a) restores.
- **Q2. Summary shape per kind.**
  - Undelivered SO: Sales orders, Ordered, Transferred to DO, Outstanding (qty + RM), Order date range, By
    location, By customer / By product, SO list offer.
  - Pending delivery DO: Delivery orders, DO qty, Delivered, Outstanding (qty + RM), DO date range, By location,
    By customer / By product, DO list offer.
  - Unpaid: unchanged single total (a document has no location or product).
  **Rec:** as listed; the line names are the pre-#1922 ones, the only addition is RM on the Outstanding line
  (#1922 Q1: outstanding gains RM).
- **Q3. Which asks get the summary?** **Rec:** an outstanding kind naming a product or a customer, the old
  tool's two subjects. A brand alone was a filter there, not a subject, so it stays the total, as does an ask
  with no subject.
