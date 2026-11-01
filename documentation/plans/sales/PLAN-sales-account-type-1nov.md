# SALES-ACCOUNT-TYPE: sales by the customer's account type

**Status:** PR 1 (#2067) ready, Waiting:ci; on-screen figures and the hand test wait for INVOICED-CHANNEL-PERF. PR 2 in Build on `crew/sales-account-type-pr2`, stacked on #2067: replay done, tests next. Size M. Card decided by the owner: debtor type, number derived; a word that is both a brand and a type asks which. Owner approved mock v4 (15:34), so the screen is in PR 1.

Lane brief: crew `SALES-ACCOUNT-TYPE`. Branch `crew/sales-account-type`. UAC: `sales-account-type-acceptance-criteria.md`.
Agent codes are masked (AGENT A, AGENT B) because this repo is public. The real codes are in the crew card.

## 1. Why

The bot's "sales for cabana in Jan" did not tally with AutoCount's "Sorento sales report by account". Both figures were right for what
they read: one read the customer's account, the other the item's brand (`billing_document_lines.py:85-86`). On the real data the two differ
by about half. The CRM could not answer the first reading, and a bot asked for "account 4" read it as a customer name.

Figures in this repo (plan, mock, tests) are invented, of the same shape. The real tie-out is kept out of this public repo.

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
- **No same-code ledgers.** No company has two ledgers with one debtor code on the copy, so a pushed type reaches its one ledger;
  the agent's same-code fan-out (`master_ingest_service.py:1252`) has no twin here. The check compared codes exactly, not by case.
- **Brands.** SORENTO, BRAVAT and CABANA are Sorento brands. Production parser prompt on the 28 Oct copy:
  v70, md5 `0e52eb27f27a6bd51d754ae34c43f4f0`; crew records a later production text, section 5.

## 3. Tie-out: the `[A/C]` tag against the AutoCount PDF

The PDF is "Sorento sales report by account", 1 Jan to 4 Sep 2026. Its file is an Excel export, so a hand adjustment cannot be ruled out.
Compared per agent and month: 78 agent-months across 10 agents. Four other PDF rows were not mapped to agent codes.

| Number | PDF column | Cells that tie | Gap % |
| --- | --- | --- | --- |
| A/C I | SORENTO | 58 of 78 | 0.07 |
| A/C II | BRAVAT | 78 of 78 | 0.00 |
| A/C III | CERAMIC | 75 of 78 | 0.03 |
| A/C IV | CABANA | 71 of 78 | 0.26 |

The gaps have two causes:

- **An untagged ledger the report counts in a column.** The same shape lands in SORENTO for one agent and PROJECT for another, so a name with no
  tag cannot say which column it belongs to.
- **A ledger whose tag and report column disagree.** One agent's CABANA by tag is above the PDF over six months, and SORENTO below it by nearly
  the same amounts. UNVERIFIED cause, most likely ledgers tagged `[A/C IV]` with type SORENTO; the partner lane's DebtorType x tag table will show it.

Four of the differing cells belong to one PDF row whose agent code was inferred from its January figures, and the PDF has a similar row beside it, so
those four may be the comparison's mapping rather than the tag.

Shape of the agreed examples, in invented figures. AGENT A, January: account 1 RM 200,100.00 (199,700.00 tagged + 400.00 untagged), account 3 RM
300,300.00, account 4 RM 100,400.00, total RM 600,800.00. Brand CABANA across accounts RM 150,000.00: RM 70,000.00 on account 3 and RM 80,000.00 on
account 4.

## 4. Behaviour card (decided)

Mock v4: `documentation/mockups/SALES-ACCOUNT-TYPE/index.html`.

Owner, 1 Nov: "don't need customzie this logic, just allow the user to ask by brand, we are not hard setting caban is account 4",
"for account type, when cabana, still go to cabana, i will ask the user to say it is account type 4", and on card v2: "i dont need
the definition of Account 4 = cabana, I just need to be able to search by account 4 just like b". On test data: "yeah can fill test
account types on test copy". Then at 15:30, replacing the earlier "cabana stays the brand": "when they ask for sales for Sorrento, we can
clarify, is it brand or is it the [debtor] type? Same goes for Cabana, all those. If [AutoCount] have that, then we need to be able to
understand and clarify."

Rules:

1. On a sales or outstanding ask, a word that is both a brand and a stored account type asks "brand or account type?", and the answer
   resumes the same ask. The overlap comes from the data, the stored types against the brand list, never a word list; on Sorento today
   it is SORENTO, BRAVAT and CABANA. "cabana brand" and "cabana account" say which, so no question. A word that is only a stored type
   (CERAMIC on Sorento) reads as the account type. Asks that are not sales ("cabana stock") stay the brand.
2. "account type 4", "account 4" and "A/C IV" find the customers of that account by their AutoCount debtor type. For each company,
   the number's type is the one most ledgers tagged `[A/C IV]` carry, read from the data. A type answers to one number only, the one most of its ledgers carry, so a lone `[A/C V]` ledger does not make 5 mean that whole type. Where that hides a number (one type on every tag, or a tag whose majority type has a bigger tag), the reply refuses and lists what exists; it never answers with the wrong sales. No code or row states that 4 is CABANA,
   and no table holds it.
3. The reply shows the account the way it was asked ("Account type: 4"), never a definition such as "Account type 4: CABANA".
4. One filter and one split in the shared report ask, on all six bases: invoiced, delivered, ordered, undelivered, pending
   delivery, unpaid. The bot, the AI panel (MCP) and Sales & outstanding all read it. Label "Account type" (the label "Debtor type"
   is already the CRM's own project / cash concept, `app/models/order.py:184-190`).
5. A month alone is that month of this year. A month or year split never prints "Top N".
6. A word and a number in one message need no question: if the word is the number's type they name one account, so the account filter
   alone (the owner's "AGENT A, cabana, invoiced, by month, for account 4" ties to the report); if it differs, the word can
   only be the brand ("cabana on account type 3"). "project" stays the channel and "sample" the category, as today, unless the
   message says account type.
7. Nothing loaded: "Account types are not loaded from AutoCount yet", never RM 0. An unknown number says so and lists the numbers and
   any type with no number. Rows add up to all sales. "top accounts" stays customers.

Known limits on "tally 100%": the CRM's agent total itself differs from the PDF on two agent-months, whatever the account reads (cause UNVERIFIED; the
PDF was made on 4 Sep and the copy is from 28 Oct). The match on every other cell is expected, not measured, until real types arrive.

Test data: an UPDATE from the tag on this lane's own test copy only, never a shared copy.

## 5. Plan

- **Partner lane, shared service (crew's SS-DEBTOR-TYPE):** `DebtorType -> market_segment_code` on the customer task (mapping row,
  `SINK_FIELDS`, backfill like module Alembic 0029); each customer re-stages once. No CRM migration. It also reports DebtorType x tag.
- **PR 1, CRM, no prompt:** param `account_types` and axis `account_type` on the six datasets, route, MCP catalog, replies, and the screen's
  filter and column (drawn by the report kernel, no frontend code expected).
- **Rollout:** merge PR 1 after the partner lane is live, or the Account type dropdown is empty and the split is one blank row, with no message on the screen.
- **PR 2, CRM, prompt gate:** section 6. Baseline: the text crew records as the production label, md5 `57d7d412` (crew's ledger, 31 Oct; the 28 Oct copy's v70
  `0e52eb27` predates it; today's label is the owner's to confirm). Only the owner moves the production label.

## 6. PR 2: the bot

**"In Jan" replay (1 Nov, 2 rows x1, baseline text, gemini-3.5-flash-lite, USD 0.0067).** "AGENT A sales for cabana in Jan" parses to 1 Jan to 31 Jan 2026 with no `group_by`, fresh and after a
held 2026 month list. So the parser is not the cause on this text. No code widens a named month: `period_from` keeps the parser's two dates (`report_ask.py:175`, `:1916`). "Top 10 months" is the printed row
count (`presenters.py`: `{lead} {len(rows)} {plural}`) over a month list, ten months with sales, the shape of the owner's other message, "2026 ... breakdown by month". Reading: the reply belongs to that ask, whose period
was right and whose head is the defect. UNVERIFIED: the owner's own turn is in production and nobody on this lane can read it. One row x1 on another arm could still flip. So PR 2 fixes the head, pins the month in a lane test and in gold rows, and adds no month rule to the prompt.

### ARCHITECTURE

1. **Layer.** Parser input and prompt (a data line, one hint, one entity field) plus the report ask's own field. No route change: PR 1's param does the work.
2. **Shared mechanism.** The report ask's parser-only question, the one the company pick uses (`COMPANY`, `report_ask.py:390`; `offered` for the bare question). Every sales and outstanding ask already passes through it.
3. **Parser reads, data decides.** The parser says only what the message says: `hint: account_type` for a numbered account or a typed-only word, and `kind_said: true` when the message itself says brand or account ("cabana brand", "cabana account"). Whether a word overlaps comes from the data: stored types against active brands, in the contact's scoped session. A parser that forgets `kind_said` costs one extra question, never a silent wrong figure.
4. **Merge changes nothing until the label moves.** `kind_said` follows the `by_words` rule (`typed_group_by`, `report_ask.py:727`): a parse without the key comes from a text that does not define it, so no question. The Known account types line and the schema key follow the prompt text (`head/parser.py:1071-1075`). `account_type` is written in the prompt beside `sales_agent` (`parser_template.py:138`), not in `chatbot_entity_kinds`, whose rows render into every text.
5. **Also fixed, UNVERIFIED until measured.** Any axis on the same path takes `account_type` once listed (`GROUP_BY`, `AXIS_NOUNS`, `_AXIS_FILTERS`, held filters); a trend head stops saying "Top N" on month and year alike.
6. **Removes.** The "Which customer is Account 4 for?" dead end on a report ask when no customer is named. A customer's own ledger ("ZZT TRADING a/c 3") stays as it is.
7. **Not built.** No word list, no regex on the message, no table of numbers, no second question type.

### Calls made here, filed with crew

- Account type is NOT a named subject for the company question (`report_ask.py:1897`): a number means a different type per company, so a two-company contact asking "account 4" and nothing else is asked the company. A brand keeps today's reading. Cost: one question, on a rare shape.
- A customer-scoped contact (dealer) never gets the question or the line: the route refuses them the filter (AT-13), so "cabana" stays the brand and "account 4" is the dealer refusal.
- The word question comes before every other owed field and prints bare, as mock v4 draws it. A basis still owed is asked next.
- A word on a follow-up asks too, because rule 1 has no follow-up exception.
- Side finding, not this lane: on baseline one row read AGENT A as a customer and the other as a sales agent.
