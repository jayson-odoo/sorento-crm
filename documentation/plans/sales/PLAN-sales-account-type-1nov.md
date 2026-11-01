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

## 4. Plan

To be completed from the behaviour card. Open parts: the partner shared service change, the report ask param and axis, the
parser's account word and brand-or-account question, the "in Jan" period bug.
