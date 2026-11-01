# SALES-ACCOUNT-TYPE: sales by the customer's account type

**Status:** Plan. Size M. Behaviour card not yet filed; no product code before crew relays the answers.

Lane brief: crew `SALES-ACCOUNT-TYPE`. Branch `crew/sales-account-type`. UAC:
`sales-account-type-acceptance-criteria.md` (written once the card is answered).

## 1. Why

The bot's "YMH sales for cabana in Jan" did not tally with AutoCount's "Sorento sales report by account".
Crew proved on the 28 Oct prod copy that both figures are right for what they read:

| Reading | YMH, January 2026 |
| --- | --- |
| CABANA is the customer's account (the AutoCount report) | RM 96,416.80 |
| CABANA is the item's brand (the bot, `billing_document_lines.py:85-86`) | RM 153,888.62 |

The CRM cannot answer the first reading, and a bot asked for "account 4" reads it as a customer name.

## 2. Findings (measured)

- **AutoCount has the field.** `Debtor.DebtorType` holds `SORENTO`, `CERAMIC` and so on, on the same row as the ledger's
  `[A/C I]` name tag (shared service `service_backend/tests/fixtures/autocount_http/debtor_page.json:9-11,33-35`). So name
  parsing is not needed.
- **The shared service does not send it.** `CanonicalCustomer.SINK_FIELDS` lists no `market_segment_code`
  (shared service `service_backend/modules/autocount/canonical/masters.py`, class `CanonicalCustomer`), and no code in
  `service_backend/modules/autocount/` names `DebtorType` or `market_segment_code` (`git grep` on origin/main, ed0fc6e0).
- **The CRM is ready to receive it.** `market_segment_code` is in the customers contract (`app/api/v1/external/contract.py:88`),
  and `_customer_columns` stores it upper and trimmed in `customers.autocount_debtor_type`
  (`app/services/master_ingest_service.py:493-498`). So all 6,874 customers on the 1028 copy being empty is the missing
  sender, not a CRM bug.
- **The kernel already has the figure.** `invoiced_sales.debtor_type()` (`app/services/sales/invoiced_sales.py:169-176`), the
  `debtor_type` column (`reports/datasets/billing_document_lines.py:132`), and the Sales by debtor type report
  (`reports/definitions/sales_by_debtor_type.py`) all exist and read that empty column. The bot's report ask has no such
  param (`billing_document_lines.py:226-238`).
- **The name tag cannot rebuild the report, so the real field is required.** The AutoCount report's columns are SORENTO,
  BRAVAT, CERAMIC, CABANA, PROJECT, SAMPLE. An untagged ledger lands in different columns: WT I's January RM 1,588.50 is
  PROJECT, YMH I's January RM 393.00 is SORENTO (PDF rows against `account-type-check-output.txt:133,140`).
- **The agent suffix is not the account.** YMH I holds ledgers of every tag; YMH CERAMIC January is YMH I A/C III 27,717.93 +
  YMH III 287,765.66 (`account-type-check-output.txt:33,142,144`). The filter must read the customer, not the agent code.
- **No sale lacks a customer.** The 2026 "no customer link" check returned no rows (section 6 absent from the output), so
  once the type is filled no 2026 line falls outside every account on the customer link.
- **Tags on the 1028 copy.** Sorento: none 2,657, A/C I 521, A/C IV 517, A/C III 510, A/C II 83, A/C V 1. Mocha: none 1,735,
  A/C I 839, A/C IV 11. `autocount_debtor_type` is filled on 0 of them.

## 3. Tie-out figures (AutoCount PDF "Sorento sales report by account", 01/01/26 to 04/09/26)

YMH by month, CABANA account: Jan 96,416.80, Feb 71,106.53, Mar 102,371.78, Apr 118,942.40, May 86,356.80, Jun 114,335.11,
Jul 91,924.56, Aug 76,240.53, 1-4 Sep 27,290.36; total 784,984.87 (the months add to it). The 1028 copy ties January to
August to the cent against `[A/C IV]`; September differs only because the PDF stops on 4 Sep.

YMH January by account: SORENTO 282,203.77 (A/C I 281,810.77 + untagged 393.00), CERAMIC 315,483.59, CABANA 96,416.80,
total 694,104.16.

YMH January, CABANA account crossed with item brand: CABANA 77,010.91, NO LOGO 19,405.89. CABANA brand across accounts:
A/C III 76,877.71 + A/C IV 77,010.91 = 153,888.62, the bot's figure.

Word collisions on the copy (`account-type-check-2-output.txt`): SORENTO, BRAVAT and CABANA are Sorento brands; CERAMIC is
no Sorento brand or category; PROJECT and SAMPLE are Sorento categories. Mocha has no 2026 documents on the copy, so every
tie-out is Sorento. Production parser prompt on the copy: v70, md5 `0e52eb27f27a6bd51d754ae34c43f4f0`.

YMH January, SORENTO: account 282,203.77, brand 520,609.65.

## 4. Behaviour card v2 (filed to crew; answers go here)

Mock v2: `documentation/mockups/SALES-ACCOUNT-TYPE/index.html`.

Owner on mock v1, 1 Nov: "don't need customzie this logic, just allow the user to ask by brand, we are not hard setting caban
is account 4". So the brand-or-account question, the derived `CABANA (A/C IV)` alias and crew's Q2 (a), Q3 (a) and Q4 are
withdrawn. Crew's Q1 (a), the shared service partner lane, stands.

Rules:

1. Account type is the customer's AutoCount `DebtorType`, stored in `customers.autocount_debtor_type`, its current value.
   Never the agent code's suffix, never the name tag.
2. One filter and one split in the shared report ask, on all six bases: invoiced, delivered, ordered, undelivered, pending
   delivery, unpaid. The bot, the AI panel (MCP) and Sales & outstanding all read it. Label "Account type" (the label
   "Debtor type" is already the CRM's own project / cash concept, `app/models/order.py:184-190`); the report "Sales by debtor
   type" keeps AutoCount's name.
3. A bare brand word (cabana, sorento, bravat) stays the item brand, as today, with no question. Account type applies only when
   the user asks by account: "cabana account", "CABANA debtor type", "by account type".
4. The CRM holds no link between a type and an account number. No alias, no table, no name parsing, no hard-coded rows.
5. A month alone is that month of this year. A month or year split never prints "Top N".
6. Nothing loaded: "Account types are not loaded from AutoCount yet", never RM 0. Unknown value: says so and lists the
   types. A customer with no type is the blank row, so rows add up to all sales. "top accounts" stays customers.

## 5. Plan

- **Partner lane, shared service:** `DebtorType -> market_segment_code` on the customer task (mapping row, `SINK_FIELDS`,
  backfill like module Alembic 0029); each customer re-stages once. No CRM migration. Can ship before or after the CRM PRs.
- **PR 1, CRM, no prompt:** param and axis on the six datasets, route (stored type values only), MCP catalog, rule 6's replies.
  Screen part follows the owner's OK on the mock.
- **PR 2, CRM, prompt gate:** parser's by-account reading, the open "account 4" answer, the period fix, user guide. Prompt gate
  with v70 as the fixed baseline; only the owner moves the production label.

The "in Jan" cause is not reproduced yet. `TEMPLATE` already states the month rule (`head/parser_template.py:37`). First Build
step on PR 2: replay the message on pinned v70, fresh and with a held 2026 period, then fix where it falls.
