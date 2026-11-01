# SALES-ACCOUNT-TYPE acceptance criteria

Plan: `PLAN-sales-account-type-1nov.md`. Decided by the owner on card v2: account type 4 reads the debtor type, with the number derived
from the ledger tags.

## Journey

A sales manager holds AutoCount's "Sorento sales report by account" and asks for one agent's sales on one numbered account, "account
type 4". They get that account's sales, shown the way they asked. They can split the same sales by account type, or combine an account
with a brand. A bare brand word stays the item brand. If the types have not reached the CRM, they are told so instead of seeing RM 0.
The AI panel and the Sales & outstanding screen read the same figures.

Decisions the user makes: only what they ask. Nothing about the account is configured.

## PR 1: filter and split on the shared report ask

The route is `GET /api/v1/order-management/report-ask`. The param is `account_types`, the axis `group_by=account_type`, the label
"Account type". The bases are invoiced, delivered, ordered, outstanding, pending_delivery, unpaid. A ledger's type is
`customers.autocount_debtor_type`; its tag is `[A/C IV]` at the end of `customer_name`.

- **AT-1 [BE]** Given ledgers typed CABANA and CERAMIC and one with no type, when invoiced is asked with `account_types=4`, then the
  total is only the sales of customers whose type is the number's type, a credit note negative.
- **AT-2 [BE]** AT-1 holds on each of delivered, ordered, outstanding, pending_delivery and unpaid.
- **AT-3 [BE]** The filter reads the type, not the ledger's own tag. Given number 4's type is CABANA: a ledger typed CABANA with no tag
  counts under 4; a ledger tagged `[A/C IV]` but typed SORENTO does not.
- **AT-4 [BE]** The agent code's suffix never decides the account: a customer typed CABANA under an agent code ending `III` counts
  under 4.
- **AT-5 [BE]** `4`, `IV`, `iv`, `A/C IV`, `a/c iv`, `CABANA` and `cabana` give the same figures.
- **AT-6 [BE]** The number's type is derived per company: the type most ledgers with that tag carry. One stray ledger does not move it.
  A seeded made-up type (`ZZT TYPE`) on the `[A/C IV]` ledgers makes 4 mean `ZZT TYPE`, proving nothing is hard-coded. Ties go to the first
  type by name.
- **AT-7 [BE]** The filter echo reads the account as asked: `account_types=4` gives key `account_type`, label "Account type", values
  `["4"]`, and neither the echo nor any other field of the response states the type behind it.
- **AT-8 [BE]** On all six bases `group_by=account_type` returns one row per stored type plus the `(blank)` row for customers with no type,
  `group_label` "Account type", and the rows add up to the unfiltered total.
- **AT-9 [BE]** The filter ANDs with the others: brand CABANA on account 3 returns only those lines.
- **AT-10 [BE]** Nothing loaded. When no customer in the caller's companies has a type, a filter or a split returns `status: refused`,
  message "Account types are not loaded from AutoCount yet", no rows, even though sales exist. The printed reply is the message alone, no RM figure.
- **AT-11 [BE]** Unknown. `account_types=9` returns `status: refused`, message "No account type 9. Account types: 1, 3, 4, PROJECT.": the
  numbers in order, then any stored type no number leads to, by name. No rows; the printed reply is the message alone.
- **AT-12 [BE]** `account_types=` is 422 `empty_filter`; more than 50 values is 422 `too_many_values`.
- **AT-13 [BE]** A customer-scoped contact (dealer) naming the filter or the split is 403 `report_dimension_not_allowed`.
- **AT-14 [BE]** Another company's types and numbers are neither listed nor matched, and figures never cross companies.
- **AT-15 [BE]** `dataset=chat` with `account_types` is 422 `unknown_param`.
- **AT-16 [T]** Tie-out on seeded rows with the AutoCount report's figures, one agent, January 2026, types on every ledger: account 1 RM
  282,203.77 (281,810.77 on `[A/C I]` ledgers + 393.00 on an untagged ledger typed SORENTO), account 3 RM 315,483.59 (27,717.93 + 287,765.66 across
  two agent codes), account 4 RM 96,416.80 (6,561.00 + 89,855.80), total RM 694,104.16. Brand CABANA on account 3: RM 76,877.71.
- **AT-17 [BE]** Master ingest: a pushed `market_segment_code` sets `autocount_debtor_type` on the customer and on every other ledger of that
  company with the same debtor code, as the agent does, and not on another company's ledger with that code. A later push with a
  different type moves all of them. A push with no type leaves them unchanged.
- **AT-18 [BE]** Held for the owner's mock OK: on the reports metadata for the six Sales & outstanding definitions, the new param and column
  are `hidden`. The Sales by debtor type and Top selling items reports are unchanged.
- **AT-19 [T]** The MCP tool lists `account_types`, its text names `group_by` `account_type`, and the presenter prints "Account type: 4",
  the plural "account types" and the refused message verbatim.

## Later

Screen part (after the owner OKs the mock): the param and column stop being hidden; 375 and 1280 browser pass.

PR 2: the parser's reading of "account type 4", "account 4" and "A/C IV"; a bare brand word stays the brand; the period rule; user
guide. Its ACs land here before its code.
