# UAC: REPORT-UNIFY

Status: Draft (pending the owner's card answers). Plan: `PLAN-report-unify-27oct.md`.

## Engine (slice 1)

- **AC-RU-1.** `GET /order-management/report-ask?spec=trap_type:p_trap&category_ids=<WC>` returns only products whose
  `trap_type` is P-trap. The total equals the sum of those products' rows.
- **AC-RU-2.** A spec set with more than 50 products is answered whole. There is no 50-id cap on a spec, because it
  resolves server-side.
- **AC-RU-3.** A numeric spec (`length:250mm`) matches exactly after unit normalisation. 200 mm and unstated lengths
  are excluded.
- **AC-RU-4.** A spec that matches no product returns zero rows with `status=no_products`, never the unfiltered set.
- **AC-RU-5.** A spec key hidden from the contact is not applied and is echoed under
  `not_applied: [{filter: "spec", reason: "hidden"}]`.
- **AC-RU-6.** `group_by=spec:trap_type` returns one row per value plus "Not stated". The rows sum to the ungrouped
  total. Top N cuts after the fold.
- **AC-RU-7.** On every basis (invoiced after the #1916 rebase, delivered, ordered, outstanding), the total equals the
  sum by product, which equals the sum by spec key, for a seeded chain.
- **AC-RU-8.** Outstanding answers carry qty and RM, where RM = `line_total` x open / ordered.
- **AC-RU-9.** The echo carries the spec labels from the registry ("Trap type: P-trap").

## Chatbot (slice 2)

- **AC-RU-10.** A sales total naming a customer, product, agent, brand or category calls `crm_report_ask` with no
  grouping. `crm_sales_report` is not called (Q1).
- **AC-RU-11.** Any outstanding ask calls `crm_report_ask` with `basis=outstanding`. `crm_outstanding_report` is not
  called (Q1, Q2).
- **AC-RU-12.** "by month" / "by channel" / "by sales agent" / "by customer" asks call `crm_report_ask` with that
  grouping. No "I can't break sales down by X" reply remains (P5, P9).
- **AC-RU-13.** A parsed spec entity becomes a `spec` param and the header names it. The generic "need a filter" gate
  never replaces a report answer (H1).
- **AC-RU-14.** A filter that cannot be applied prints `Not applied: <filter> (<reason>)` under the header. When it
  was the only subject, the bot asks instead (Q4, P11).
- **AC-RU-15.** A product named this turn replaces the carried subject's products (P4).
- **AC-RU-16.** The standing rulings still hold:
  - one question for missing period + measure + basis, with Invoiced first and never defaulted;
  - "by X" keeps the filters;
  - the Sales report switch;
  - "my ..." from an ungranted salesperson = own customers, "Limited to: your customers".
- **AC-RU-17.** The retired tools are gone from the policy rows, the MCP catalog and the analytics connector (Q1).

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
