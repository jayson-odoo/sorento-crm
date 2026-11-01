# SALES-ACCOUNT-TYPE: sales by the customer's account type

**Status:** Plan. Size M. Behaviour card v2 filed; one question open (how "account type 4" maps). No product code yet.

Lane brief: crew `SALES-ACCOUNT-TYPE`. Branch `crew/sales-account-type`. UAC: `sales-account-type-acceptance-criteria.md`.
Agent codes are masked (AGENT A, AGENT B) because this repo is public. The real codes are in the crew card.

## 1. Why

The bot's "sales for cabana in Jan" did not tally with AutoCount's "Sorento sales report by account". Both figures are right for
what they read:

| Reading | AGENT A, January 2026 |
| --- | --- |
| CABANA is the customer's account (the AutoCount report) | RM 96,416.80 |
| CABANA is the item's brand (the bot, `billing_document_lines.py:85-86`) | RM 153,888.62 |

The CRM cannot answer the first reading, and a bot asked for "account 4" reads it as a customer name.

## 2. Findings (measured)

- **AutoCount has the type, not the number.** `Debtor.DebtorType` holds `SORENTO`, `CERAMIC` and so on. No Debtor field holds
  the number; it exists only as the `[A/C I]` tag in `CompanyName` (shared service
  `service_backend/tests/fixtures/autocount_http/debtor_page.json`).
- **The shared service does not send the type.** `CanonicalCustomer.SINK_FIELDS` lists no `market_segment_code` (shared service
  `service_backend/modules/autocount/canonical/masters.py`), and no code in `modules/autocount/` names `DebtorType`
  (`git grep` on origin/main, ed0fc6e0).
- **The CRM is ready to receive it.** `market_segment_code` is in the customers contract (`app/api/v1/external/contract.py:88`),
  and `_customer_columns` stores it in `customers.autocount_debtor_type` (`app/services/master_ingest_service.py:493-498`).
  On the 1028 copy that column is filled on 0 ledgers, in every company and tag.
- **The kernel already has the figure.** `invoiced_sales.debtor_type()` (`app/services/sales/invoiced_sales.py:169-176`) and the
  Sales by debtor type report exist. The bot's report ask has no such param (`billing_document_lines.py:226-238`).
- **The agent suffix is not the account.** One agent's code `I` holds ledgers of every tag, so the filter must read the customer.
- **No 2026 sale lacks a customer**, so every line reaches a customer's type and tag.
- **Ledger tags on the copy.** Sorento: none 2,657, A/C I 521, A/C IV 517, A/C III 510, A/C II 83, A/C V 1. Mocha: none 1,735,
  A/C I 839, A/C IV 11, and no 2026 documents, so every tie-out is Sorento.
- **Tag quality.** The check found four ledgers of 6,874 with a tag the pattern `\[(A/C [IVX]+)\]\s*$` misses: `[A/C]`, `[A/C1]`,
  `(A/C 2)`, and one tag not at the end of the name.
- **Brands.** SORENTO, BRAVAT and CABANA are Sorento brands, so a bare word stays the brand. Production parser prompt on the copy:
  v70, md5 `0e52eb27f27a6bd51d754ae34c43f4f0`.

## 3. Tie-out: the `[A/C]` tag against the AutoCount PDF

The PDF is "Sorento sales report by account", 01/01/26 to 04/09/26. Its file is an Excel export, so a hand adjustment cannot be
ruled out. Compared per agent and month: 78 agent-months across 10 agents. Four other PDF rows were not mapped to agent codes.

| Number | PDF column | Cells that tie | PDF RM | Tag RM | Gap RM | Gap % |
| --- | --- | --- | --- | --- | --- | --- |
| A/C I | SORENTO | 58 of 78 | 20,130,863.38 | 20,115,768.01 | 15,095.37 | 0.07 |
| A/C II | BRAVAT | 78 of 78 | 53,261.33 | 53,261.33 | 0.00 | 0.00 |
| A/C III | CERAMIC | 75 of 78 | 20,051,403.22 | 20,056,934.98 | -5,531.76 | 0.03 |
| A/C IV | CABANA | 71 of 78 | 5,200,588.98 | 5,214,345.49 | -13,756.51 | 0.26 |

The gaps have two causes:

- **An untagged ledger the report counts in a column.** AGENT A, January: RM 393.00 is in SORENTO. It is the agent's only gap in
  nine months and four columns. The same shape lands elsewhere for another agent: RM 1,588.50 untagged is in PROJECT.
- **A ledger whose tag and report column disagree.** AGENT B: CABANA by tag is RM 14,047.08 above the PDF over March to August,
  and SORENTO is below it by nearly the same amounts. UNVERIFIED cause, most likely ledgers tagged `[A/C IV]` with type SORENTO;
  the partner lane's DebtorType x tag table will show it.

Four of the differing cells belong to one PDF row whose agent code was inferred from its January figures, and the PDF has a similar
row beside it, so those four may be the comparison's mapping rather than the tag.

AGENT A by month, CABANA account and `[A/C IV]` both: Jan 96,416.80, Feb 71,106.53, Mar 102,371.78, Apr 118,942.40, May 86,356.80,
Jun 114,335.11, Jul 91,924.56, Aug 76,240.53, 1-4 Sep 27,290.36; total 784,984.87.

AGENT A January: SORENTO 282,203.77 (A/C I 281,810.77 + untagged 393.00), CERAMIC 315,483.59, CABANA 96,416.80, total 694,104.16.
Brand CABANA across accounts: A/C III 76,877.71 + A/C IV 77,010.91 = 153,888.62, the bot's figure.

## 4. Behaviour card v2 (filed to crew; answers go here)

Mock v2: `documentation/mockups/SALES-ACCOUNT-TYPE/index.html`.

Owner, 1 Nov: "don't need customzie this logic, just allow the user to ask by brand, we are not hard setting caban is account 4",
then "for account type, when cabana, still go to cabana, i will ask the user to say it is account type 4".

Rules:

1. A bare brand word (cabana, sorento, bravat) stays the item brand, as today, with no question.
2. "account type 4", "account 4" and "A/C IV" mean the numbered account. No code or row states that 4 is CABANA.
3. One filter and one split in the shared report ask, on all six bases: invoiced, delivered, ordered, undelivered, pending
   delivery, unpaid. The bot, the AI panel (MCP) and Sales & outstanding all read it. Label "Account type" (the label "Debtor type"
   is already the CRM's own project / cash concept, `app/models/order.py:184-190`).
4. A month alone is that month of this year. A month or year split never prints "Top N".
5. An unknown number says so and lists the account types. Rows add up to all sales. "top accounts" stays customers.

Open question: option (a) the ledger tag, option (b) the debtor type with the number derived from the tags. See the card.

Withdrawn from v1: the brand-or-account question, and crew's answers to Q3 and Q4. Crew's Q1, the shared service partner lane,
stands.

## 5. Plan

- **Partner lane, shared service:** `DebtorType -> market_segment_code` on the customer task (mapping row, `SINK_FIELDS`,
  backfill like module Alembic 0029); each customer re-stages once. No CRM migration. It also reports DebtorType x tag.
- **PR 1, CRM, no prompt:** param and axis on the six datasets, route, MCP catalog, replies. The screen part follows the owner's OK
  on the mock.
- **PR 2, CRM, prompt gate:** parser's reading of the numbered account, the period fix, user guide. Prompt gate with v70 as the fixed
  baseline; only the owner moves the production label.

The "in Jan" cause is not reproduced yet. `TEMPLATE` already states the month rule (`head/parser_template.py:37`). First Build step
on PR 2: replay the message on pinned v70, fresh and with a held 2026 period, then fix where it falls.
