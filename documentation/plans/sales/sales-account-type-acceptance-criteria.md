# SALES-ACCOUNT-TYPE acceptance criteria

Plan: `PLAN-sales-account-type-1nov.md`. Behaviour card v2: owner's feedback on mock v1 withdrew the brand-or-account question and the derived alias.

## Journey

A sales manager holds AutoCount's "Sorento sales report by account" and asks for one agent's sales on one customer account.
They name the account type, CABANA, and get the figure on the PDF. They can split the same sales by account type, or combine
an account with a brand. A bare brand word stays the item brand. If the account types have not reached the CRM yet, they are told so instead of seeing RM 0.
The AI panel and the Sales & outstanding screen read the same figures.

Decisions the user makes: only what they ask. The types offered are whatever the customers carry.

## PR 1: filter and split on the shared report ask

The route is `GET /api/v1/order-management/report-ask`. The param is `debtor_types`, the axis `group_by=debtor_type`, the label
"Account type". The bases are invoiced, delivered, ordered, outstanding, pending_delivery, unpaid.

- **AT-1 [BE]** Given customers typed CABANA and CERAMIC and one with no type, when invoiced is asked with
  `debtor_types=CABANA`, then the total is only the CABANA customer's sales, a credit note negative.
- **AT-2 [BE]** The filter reads the customer's stored type only. A customer typed CABANA whose name ends `[A/C III]` and whose
  agent code ends `III` counts under CABANA, not CERAMIC.
- **AT-3 [BE]** AT-1 holds on each of delivered, ordered, outstanding, pending_delivery and unpaid.
- **AT-4 [BE]** On all six bases `group_by=debtor_type` returns one row per type plus the `(blank)` row for customers with no
  type, `group_label` "Account type", and the rows add up to the unfiltered total.
- **AT-5 [BE]** The filter ANDs with the others: brand CABANA on account CERAMIC returns only those lines.
- **AT-6 [BE]** `debtor_types` matches a stored type in any case: `CABANA` and `cabana` give the same figures, and the filter
  echo reads `CABANA`, key `debtor_type`, label "Account type".
- **AT-7 [BE]** The route holds no link between a type and an account number. `debtor_types=A/C IV` and `debtor_types=4` are
  unknown values (AT-9) even when customers typed CABANA have names ending `[A/C IV]`.
- **AT-8 [BE]** Rule 6, nothing loaded. When no customer in the caller's companies has a type, a filter or a split returns
  `status: refused`, message "Account types are not loaded from AutoCount yet", no rows and no total, even though sales exist.
- **AT-9 [BE]** Rule 6, unknown. `debtor_types=ACCOUNT 9` returns `status: refused`, message
  "No account type ACCOUNT 9. Account types: BRAVAT, CABANA, ...", in name order.
- **AT-10 [BE]** `debtor_types=` is 422 `empty_filter`; more than 50 values is 422 `too_many_values`.
- **AT-11 [BE]** A customer-scoped contact (dealer) naming the filter or the split is 403 `report_dimension_not_allowed`.
- **AT-12 [BE]** Another company's types are neither listed nor matched. A type stored only outside the caller's companies is
  unknown (AT-9), and figures never cross companies.
- **AT-13 [BE]** `dataset=chat` with `debtor_types` is 422 `unknown_param`.
- **AT-14 [T]** Tie-out on seeded rows with the PDF's figures, one agent January 2026: SORENTO 282,203.77 (281,810.77 tagged
  A/C I + 393.00 untagged, both typed SORENTO), CERAMIC 315,483.59 (27,717.93 + 287,765.66 across two agent codes), CABANA
  96,416.80 (6,561.00 + 89,855.80), total 694,104.16. Filter alone: 96,416.80. Brand on account: 76,877.71.
- **AT-15 [BE]** Held for the owner's mock OK: on the reports metadata for the six Sales & outstanding definitions, the new
  param and column are `hidden`. The Sales by debtor type and Top selling items reports keep "Debtor type" unchanged.
- **AT-16 [T]** The MCP tool lists `debtor_types`, its text names `group_by` `debtor_type`, and the presenter prints the plural
  "account types", the filter line and the refused message verbatim.

## Later

Screen part (after the owner OKs the mock): the param and column stop being hidden; 375 and 1280 browser pass.

PR 2 (after the owner answers the open "account 4" question): parser's by-account reading, a bare brand word stays the brand,
period rule, user guide. Its ACs land here before its code.
