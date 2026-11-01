# SALES-ACCOUNT-TYPE acceptance criteria

Plan: `PLAN-sales-account-type-1nov.md`.

**Draft.** The behaviour card's open question decides how a number maps. The ACs below hold under either answer; the ones that
depend on it are written after the answer, before any test.

## Journey

A sales manager holds AutoCount's "Sorento sales report by account" and asks for one agent's sales on one numbered account, "account
type 4". They get that account's sales. They can split the same sales by account type, or combine an account with a brand. A bare
brand word stays the item brand. The AI panel and the Sales & outstanding screen read the same figures.

Decisions the user makes: only what they ask. Nothing about the account is configured.

## PR 1: filter and split on the shared report ask

The route is `GET /api/v1/order-management/report-ask`. The bases are invoiced, delivered, ordered, outstanding, pending_delivery,
unpaid. The label is "Account type".

- **AT-1 [BE]** A filter on one account returns only that account's sales on invoiced, a credit note negative.
- **AT-2 [BE]** AT-1 holds on each of the five other bases.
- **AT-3 [BE]** The agent code's suffix never decides the account: a customer of account 4 under an agent code ending `III` counts
  under account 4.
- **AT-4 [BE]** On all six bases the split returns one row per account plus a row for customers with none, `group_label` "Account
  type", and the rows add up to the unfiltered total.
- **AT-5 [BE]** The filter ANDs with the others: brand CABANA on account 3 returns only those lines.
- **AT-6 [BE]** An unknown number returns `status: refused`, with a message that says so and lists the account types, no rows
  and no total.
- **AT-7 [BE]** An empty filter value is 422 `empty_filter`; more than 50 values is 422 `too_many_values`.
- **AT-8 [BE]** A customer-scoped contact (dealer) naming the filter or the split is 403 `report_dimension_not_allowed`.
- **AT-9 [BE]** Another company's accounts are neither listed nor matched, and figures never cross companies.
- **AT-10 [BE]** `dataset=chat` with the filter is 422 `unknown_param`.
- **AT-11 [T]** Tie-out on seeded rows with the PDF's figures, one agent, January 2026: account 4 RM 96,416.80 and account 3
  RM 315,483.59, each across two agent codes; total RM 694,104.16; brand CABANA on account 3 RM 76,877.71. Account 1 and the untagged
  RM 393.00 follow the open question.
- **AT-12 [BE]** Held for the owner's mock OK: on the reports metadata for the six Sales & outstanding definitions, the new param and
  column are `hidden`. The Sales by debtor type and Top selling items reports are unchanged.
- **AT-13 [T]** The MCP tool lists the param, its text names the axis, and the presenter prints the plural, the filter line and the
  refused message verbatim.

## Later

Screen part (after the owner OKs the mock): the param and column stop being hidden; 375 and 1280 browser pass.

PR 2: the parser's reading of "account type 4", "account 4" and "A/C IV"; a bare brand word stays the brand; the period rule; user
guide. Its ACs land here before its code.
