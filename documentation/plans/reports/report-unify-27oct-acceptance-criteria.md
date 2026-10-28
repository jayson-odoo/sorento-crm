# UAC: REPORT-UNIFY

Status: Agreed (owner answers 27 Oct ~19:15). Plan: `PLAN-report-unify-27oct.md`.

## Engine (slice 1)

- **AC-RU-1.** `GET /order-management/report-ask?spec=trap_type:p_trap&category_ids=<WC>` returns only products whose
  `trap_type` is P-trap. The total equals the sum of those products' rows.
- **AC-RU-2.** A spec set with more than 50 products is answered whole. There is no 50-id cap on a spec, because it
  resolves server-side.
- **AC-RU-3.** A numeric spec (`length:250` or `length:250mm` on an `mm` key) matches the stored number exactly. 200
  and unstated lengths are excluded. A value in another unit (`length:25cm`) is echoed under `not_applied`
  (reason `unit`), and so is an unknown key (reason `unknown_spec`).
- **AC-RU-4.** A spec that matches no product returns zero rows with `status=no_products`, never the unfiltered set.
- **AC-RU-5.** A spec key hidden from the contact is not applied and is echoed under
  `not_applied: [{filter: "spec", reason: "hidden"}]`.
- **AC-RU-6.** `group_by=spec:trap_type` returns one row per value plus "Not stated". The rows sum to the ungrouped
  total. Top N cuts after the fold.
- **AC-RU-7.** On every basis (invoiced after the #1916 rebase, delivered, ordered, outstanding), the total equals the
  sum by product, which equals the sum by spec key, for a seeded chain.
- **AC-RU-8.** Basis `outstanding` (undelivered order qty) carries qty and RM, where RM = `line_total` x open /
  ordered.
- **AC-RU-8a.** Basis `pending_delivery` counts only lines of DOs that are not delivered. A fully delivered DO
  appears in no row and no total. The total equals the sum by customer, which equals the sum by product.
- **AC-RU-8b.** Basis `unpaid` sums `billing_documents.outstanding` > 0 of posted, uncancelled documents by
  customer / agent / month.
  - A product, brand, category, spec, location or channel filter is echoed under `not_applied` with reason
    `per_document`, and the total is still returned.
- **AC-RU-8c.** On every outstanding basis, an absent period means all dates. A named period filters the SO / DO /
  document date.
- **AC-RU-9.** The echo carries the spec labels from the registry ("Trap type: P-trap").

- **AC-RU-9a** (owner Q6, 27 Oct 22:52). The reveal a contact needs depends on the basis:
  - the outstanding kinds need the Outstanding reveal and no Sales report reveal;
  - the sales bases still need Sales report;
  - a contact with Outstanding only that asks a sales basis gets the existing refusal;
  - a linked contact's outstanding / unpaid figures are forced to its own customers.

## Chatbot (slice 2)

- **AC-RU-10.** A sales total naming a customer, product, agent, brand or category calls `crm_report_ask` with no
  grouping. `crm_sales_report` is not called (Q1).
- **AC-RU-11.** An outstanding ask that does not say which kind is asked "Undelivered orders, pending delivery or
  unpaid invoices?". It is never defaulted, and it is folded into the one question with anything else missing
  (Q2).
  - The answer calls `crm_report_ask` with `basis=outstanding` / `pending_delivery` / `unpaid`.
  - `crm_outstanding_report` is never called (Q1).
  - A message that names the kind ("unpaid invoices", "not delivered yet", "outstanding SO") is not asked.
- **AC-RU-12.** "by month" / "by channel" / "by sales agent" / "by customer" asks call `crm_report_ask` with that
  grouping. No "I can't break sales down by X" reply remains (P5, P9).
- **AC-RU-13.** A parsed spec entity becomes a `spec` param and the header names it. The generic "need a filter" gate
  never replaces a report answer (H1).
- **AC-RU-14.** A filter that cannot be applied prints `Not applied: <filter> (<reason>)` under the header. When it
  was the only subject, the bot asks instead (Q4, P11).
- **AC-RU-15.** A product named this turn replaces the carried subject's products (P4).
- **AC-RU-16.** The standing rulings still hold:
  - one question for missing period + measure + basis, with Invoiced first and never defaulted. This includes a
    sales TOTAL, with or without a subject (owner 27 Oct ~23:35, lane SALES-TOTAL-ASK on main);
  - "by X" keeps the filters;
  - the Sales report switch;
  - "my ..." from an ungranted salesperson = own customers, "Limited to: your customers".
- **AC-RU-17.** The retired tools are gone from the policy rows, the MCP catalog and the analytics connector (Q1).

- **AC-RU-17a** (owner 28 Oct 09:30). An undelivered-orders answer (basis `outstanding`) ends with "Reply 1 for the
  sales order list". Replying 1 lists the open sales orders behind that figure: the same basis, filters, company and
  period, grouped by sales order, with their open qty and RM summing to the figure. Pending delivery and unpaid get
  no such offer.
- **AC-RU-17b** (owner 28 Oct 08:40). A contact without a linked customer sees all figures, on totals and rankings
  alike. A contact with a linked customer sees only that customer's figures. "My ..." from a live salesperson stays
  its own book.
  Outstanding kinds keep Q6: a salesperson without the Outstanding reveal stays on its own book there.
  (Owner 28 Oct 10:15) That includes product and category rankings: REPORT-SMART R1 retires for a contact with no
  linked customer, staff or not; a linked contact stays on its customers.

## Span binding (slice 3)

- **AC-RU-18.** "mch" bound by the span pass to brand MOCHA reaches the report as the MOCHA brand id (H2).
- **AC-RU-19.** "sales agent yu ..." never offers customers. Several agent matches mean "Which sales agent?" with
  agents only. The answer's header names the agent (H3, H4).
- **AC-RU-20.** H3 and H4 give the same figure for the same agent, product and period.
- **AC-RU-21.** A category word ("kitchen sink") never triggers a customer pick (P6).
- **AC-RU-22.** Every agent matched by the span pass for "yu" reaches the parser: no cap cuts an exact match.

## Eval

- **AC-RU-23.** On the eval set (the owner's 4 messages, P1-P12, the parser gold set), every message's header carries
  each named filter or a Not-applied line, with the asked grouping. The parser gold set shows no regression against
  main.
