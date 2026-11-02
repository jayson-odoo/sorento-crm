# Parser prompt change, semantic carry (SALES-ACCOUNT-TYPE PR A)

Base: parser text md5 `99b5fc650abed7a2c063ab4701370771` (#2074's candidate, copy v71, which the owner hand-tested on
2 Nov). Result: md5 `6769d31dfa9072e259264b1da199564a`. Not published; only the owner moves the production label. On
another base, apply the one edit below by its anchor, then re-run the gold rows
(`scripts/chatbot_eval/gold/parser_report_semantic_carry.jsonl`) before use. Plan:
`PLAN-report-semantic-carry-2nov.md`. The first line of the section is the marker (`parser.REPORT_ASK_LINE`) that turns
the `report_ask` schema object and the `Held report:` line on; a text without it keeps today's schema and user block.

## Edit 1, a section inserted before the banner line that precedes `TOP SELLING` (the line of `━` characters, then `TOP SELLING`)

```text
== REPORT_ASK: the whole sales or outstanding report after this message, one object ==
A NEW output key on every object, report_ask: an object on a sales or outstanding ask (order_status sales_report, sales_ranking, sales_analysis, top_selling or an outstanding kind) and on a reply that answers the assistant's question about one; null on every other message.
  {"kind": "sales|outstanding", "basis": same values as basis, "date_from": "YYYY-MM-DD|null", "date_to": "YYYY-MM-DD|null", "group_by": same values as group_by, "top_n": number or null, "measure": same values as measure, "channel": "dealer|project|null", "company": "string|null", "sales_agents": [], "account_types": [], "brands": [], "categories": [], "customers": [], "products": [], "brand_or_account_type": []}
It is the report the user wants AFTER this message, every slot, not only what this message says:
  - A "Held report:" line in the user block is the last report; "Held report (open question: X):" is the ask the assistant's open question X is completing. Copy that object and change ONLY what this message changes. Every slot the message does not touch stays as held: period, basis, breakdown, count, channel, company and every list.
  - A slot the message names replaces that slot: "for sales agent X" after another agent -> sales_agents ["X"] alone; "for ceramic" after account type CABANA -> account_types ["CERAMIC"]; "break down by month" -> group_by "month"; "this year" -> this year's dates; "X and Y" -> both. "all agents" / "all customers" -> that list empty.
  - An answer to the open question fills the asked slot and keeps the rest: "invoiced" to the basis question -> basis "invoiced"; "account type" to "brand or account type?" -> the word moves from brand_or_account_type to account_types; a company name to the company question -> company.
  - A message that asks the report again in full, with its own report word, subject and period ("<code> sales 2026" after "<code> dealer sales may 2026"), is a new report: only the slots it names, plus the held basis.
  - A message about something else (stock, a product, a price, a document, a delivery) -> report_ask null. No Held report line -> build the object from this message alone.
  - The lists and company hold NAMES as the user or the Held report line writes them, never ids: sales agent names or codes, account types (word, number or tag), brand names, category names, customer names, product codes, the company name.
  - basis: the basis this message says, else the Held report's, else null; never guess one. date_from / date_to: the period the report covers, this message's dates when it names one, else the Held report's. (The top-level basis, sales_basis and date_filter_start / date_filter_end stay this message's own, as their sections say.)
  - A word that is both a Brand candidate and a Known account type, when neither this message nor the Held report says which, goes in brand_or_account_type only.

```

## Gate results

Pending: the 16 gold rows x1 on arm D (this text), then a no-op control on parser-gold TRAIN rows if crew approves the spend.
