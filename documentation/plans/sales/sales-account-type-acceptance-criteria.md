# SALES-ACCOUNT-TYPE acceptance criteria

Plan: `PLAN-sales-account-type-1nov.md`. Decided by the owner on card v2: account type 4 reads the debtor type, with the number derived
from the ledger tags.

## Journey

A sales manager holds AutoCount's "Sorento sales report by account" and asks for one agent's sales on one numbered account, "account
type 4". They get that account's sales, shown the way they asked. They can split the same sales by account type, or combine an account
with a brand. If a word is both a brand and an account type, the bot asks which. If the types have not reached the CRM, they are told so instead of seeing RM 0.
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
- **AT-5 [BE]** `4`, `IV`, `iv`, `A/C IV`, `a/c iv`, `CABANA` and `cabana` give the same figures. An odd value (`²`, `①`) is an unknown value, never a 500, on the route and on the screen run; 5,000 digits is AT-12's 422 on the route and zero rows on the screen run.
- **AT-6 [BE]** The number's type is derived per company: the type most ledgers with that tag carry. One stray ledger does not move it.
  A seeded made-up type (`ZZT TYPE`) on the `[A/C IV]` ledgers makes 4 mean `ZZT TYPE`, proving nothing is hard-coded. Ties go to the first
  type by name. A type answers to one number only, the one most of its ledgers carry: one `[A/C V]` ledger typed SORENTO does not make 5 mean SORENTO, so 5 is unknown and not listed.
- **AT-7 [BE]** The filter echo reads the account as asked: `account_types=4` gives key `account_type`, label "Account type", values
  `["4"]`, and neither the echo nor any other field of the response states the type behind it.
- **AT-8 [BE]** On all six bases `group_by=account_type` returns one row per stored type plus the `(blank)` row for customers with no type (and, tested on invoiced and pending_delivery, lines with no customer),
  `group_label` "Account type", and the rows add up to the unfiltered total.
- **AT-9 [BE]** The filter ANDs with the others: brand CABANA on account 3 returns only those lines.
- **AT-10 [BE]** Nothing loaded. When no customer in the caller's companies has a type, a filter or a split returns `status: refused`,
  message "Account types are not loaded from AutoCount yet", no rows, even though sales exist. The printed reply is the message alone, no RM figure.
- **AT-11 [BE]** Unknown. `account_types=9` returns `status: refused`, message "No account type 9. Account types: 1, 3, 4, PROJECT.": the
  numbers in order, then any stored type no number leads to, by name. No rows; the printed reply is the message alone.
- **AT-12 [BE]** `account_types=` is 422 `empty_filter`; more than 50 values is 422 `too_many_values`; a value over 50 characters is 422 `value_too_long`.
- **AT-13 [BE]** A customer-scoped contact (dealer) naming the filter or the split is 403 `report_dimension_not_allowed`.
- **AT-14 [BE]** Another company's types and numbers are neither listed nor matched, and figures never cross companies: not on the screen run for a user granted one company, and not with `company=` naming one of a contact's two companies, where the number and the list are that company's own. A brand-scoped contact's figure stays inside its brands with the filter on.
- **AT-15 [BE]** `dataset=chat` with `account_types` is 422 `unknown_param`.
- **AT-16 [T]** Tie-out shape on seeded rows, invented figures, one agent, January 2026, types on every ledger: account 1 RM 200,100.00 (199,700.00 on `[A/C I]`
  ledgers + 400.00 on an untagged ledger typed SORENTO), account 3 RM 300,300.00 (30,000.00 + 270,300.00 across two agent codes), account 4 RM 100,400.00 (6,000.00 +
  94,400.00), total RM 600,800.00. Brand CABANA on account 3: RM 70,000.00.
- **AT-17** Dropped. A same-code fan-out for the type has no problem to solve: no company has two ledgers with one debtor code on the
  28 Oct copy (`account-type-check-4-output.txt`).
- **AT-18 [BE]** Screen, approved on mock v4 (owner, 1 Nov 15:34): on the reports metadata for the six Sales & outstanding definitions, the
  param and column `account_type` are visible, label "Account type". The param's options are the stored types of the caller's company, never a
  fixed list and never another company's. Running a definition with `account_type` = CABANA gives the same amount as the route's
  `account_types=CABANA`. The Sales by debtor type and Top selling items reports have no `account_type` and keep a visible `debtor_type`.
- **AT-19 [T]** The MCP tool lists `account_types`, its text names `group_by` `account_type`, and the presenter prints "Account type: 4",
  the plural "account types" and the refused message verbatim.

- **AT-31 [UX]** Browser, by sidebar clicks from `/`, at 1280 and 375, on the lane's test copy with test types: Sales & outstanding shows the Account type
  filter on all six tabs; choosing CABANA with the agent narrows the table; Configure summary can split by Account type; nothing is clipped.

## PR 2: the bot (ACs fixed here before its code; tests come from these)

All on sales and outstanding asks, through the parser, with no regex or word list on the user's words. Prompt gate with crew's production text, md5 `57d7d412`, as the fixed
baseline. "Stored types" are the types the customers of the asker's company carry; "brands" are the Known brands line.

- **AT-20 [T]** "AGENT sales for cabana in Jan", with CABANA both a brand and a stored type: the bot's whole reply is "Cabana: brand or account type?" (no numbered list, mock v4) and
  it runs nothing yet. It is the last question of the ask: a basis, company or agent pick still owed is asked first, and nothing the message settled is lost.
- **AT-21 [T]** Answering "account type" runs the held ask with the account filter, replacing any account filter held from before; answering "brand" runs it with the brand filter. The agent,
  period and axis are not asked again. A reply repeating the word and nothing else ("cabana account") is the answer. A reply carrying its own period, axis, count or another subject ("cabana brand in Feb", "cabana account by customer top 5", "cabana brand stock") is a new ask.
- **AT-22 [T]** The overlap comes from data: a seeded made-up word that is both a brand and a stored type asks; CABANA asks nothing when no
  customer carries it (it reads as the brand, as today).
- **AT-23 [T]** "cabana brand" and "cabana account" (and "CABANA debtor type") ask nothing and run that filter.
- **AT-24 [T]** A word that is only a stored type ("ceramic" with no such brand) runs the account filter with no question. A full customer name
  containing the word stays the customer.
- **AT-25 [T]** "account type 4", "account 4" and "A/C IV" run `account_types`; the reply reads "Account type: 4" as asked, and no reply prints a
  number's type.
- **AT-26 [T]** A word and a number: "cabana ... account 4", where CABANA is 4's type, asks nothing and runs the account filter alone, no brand
  filter. "cabana on account type 3", where it is not, asks nothing and runs brand CABANA on account 3.
- **AT-27 [T]** Unchanged readings: "cabana stock" stays the brand with no question; "project sales" stays the channel; a verdict reading "sample" as a category stays the category (the production parser gives it no entity today, so the gate grades it as any stored type);
  "top accounts" stays customers.
- **AT-28 [T]** "sales for cabana in Jan" means 1 Jan to 31 Jan of this year, one total, on a fresh conversation and after a held 2026 month list. A month or year split never prints
  "Top N": its first line reads "By month, invoiced" ("By year, delivered"), and the lines under it stay as they are. Every other axis keeps "Top N". A stray month axis on one month still prints the right figure, one row under "By month".
- **AT-29 [T]** The owner's examples on AT-16's invented figures: account RM 100,400.00, brand RM 150,000.00.
- **AT-30 [T]** The AI panel's agent can pass an account type word or number through `crm_report_ask` and reads the same reply.
- **AT-32 [T]** A customer-scoped contact (dealer): "cabana" stays the brand with no question, "account 4" is the dealer refusal, and the Known account types line is never in their parser input.
- **AT-33 [T]** A customer's own ledger stays: "ZZT TRADING a/c 3" (a customer entity with `account: 3`) keeps today's reading and sends no `account_types`.
- **AT-34 [T]** On a follow-up: a word that is both asks and the answer keeps what is on screen; an account word replaces the held account filter; a new axis keeps the held account filter; `group_by` account type on the bot lists one row per type.
- **AT-35 [T]** A contact in two companies who names only an account type, or a word that asks, is asked the company first, then the word. A contact naming the company is not asked it. The answer runs the held filter for that company. Word and number agree only when every company in play reads that number as that word's type; otherwise the brand stays beside the number.
- **AT-37 [T]** A contact the sales report refuses gets no Known account types line. The question prints the stored type's own name unless the typed word is that name, so a crafted `raw` never reaches a reply. A dealer's account word on a follow-up is the dealer refusal.
- **AT-36 [T]** Before the label moves: a parse whose entities have no `kind_said` key (a text that does not define it) asks nothing and reads as today, and the user block carries no Known account types line for that text. With a text that defines it, the line lists the stored types of the scoped company only, and is absent when no customer carries a type.
