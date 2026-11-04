# Parser prompt change, semantic carry (SALES-ACCOUNT-TYPE PR A)

Base: parser text md5 `99b5fc650abed7a2c063ab4701370771` (#2074's candidate, copy v71, which the owner hand-tested on
2 Nov). Result: md5 `e4aa6d43fedd996579b8c1caa2c54556` (round 2 "D3"; round 1 was `6769d31d`). Not published; only the
owner moves the production label. On another base, apply the one edit below by its anchor, then re-run the gold rows
(`scripts/chatbot_eval/gold/parser_report_semantic_carry.jsonl`) before use. Plan: `PLAN-report-semantic-carry-2nov.md`.
The first line of the section is the marker (`parser.REPORT_ASK_LINE`) that turns the `report_ask` schema object and the
`Held report:` line on; a text without it keeps today's schema and user block. Owner rule kept: no gold-message examples
and no word lists in the section (every example is an abstract slot rule).

## Edit 1, a section inserted before the banner line that precedes `TOP SELLING` (the line of `━` characters, then `TOP SELLING`)

```text
== REPORT_ASK: the whole sales or outstanding report after this message, one object ==
A NEW output key on every object, report_ask: an object on a sales or outstanding ask (order_status sales_report, sales_ranking, sales_analysis, top_selling or an outstanding kind) and on a reply that answers the assistant's question about one; null on every other message.
  {"kind": "sales|outstanding", "basis": same values as basis, "date_from": "YYYY-MM-DD|null", "date_to": "YYYY-MM-DD|null", "group_by": same values as group_by, "top_n": number or null, "measure": same values as measure, "channel": "dealer|project|null", "company": "string|null", "sales_agents": [], "account_types": [], "brands": [], "categories": [], "customers": [], "products": [], "brand_or_account_type": []}
It is the report the user wants AFTER this message, every slot, not only what this message says:
  - A "Held report:" line in the user block is the last report; "Held report (open question: X):" is the ask the assistant's open question X is completing. Copy that object first, every key, then change ONLY what this message changes. Every slot the message does not touch stays exactly as held: period, basis, breakdown, count, channel, company and every list (a held account_types, brands or categories list stays when the message only changes the agent, the period or the breakdown).
  - A slot the message names replaces that slot and only that slot: a sales agent it names replaces the held sales_agents, an account type the held account_types, a brand, category, customer or product its own list, a breakdown the group_by, a period the dates, a count the top_n, a channel the channel, a company the company. Two names joined together are both. A message that widens a slot to every value ("all" of it) empties that list.
  - An answer to the open question fills the asked slot and keeps the rest: a basis answers the basis question; a reply to the brand-or-account-type question that says account type moves every word of brand_or_account_type to account_types, one that says brand moves them to brands, and brand_or_account_type becomes []; a company name answers the company question.
  - A message that asks a report again in full, with its own report word, its own subject and its own period, is a new report: only the slots it names, plus the held basis; channel, breakdown, count, company and every list it does not name are null or [] (a channel it does not repeat is null).
  - A message about something else (stock, a product, a price, a document, a delivery) -> report_ask null. No Held report line -> build the object from this message alone.
  - The lists and company hold NAMES as the user or the Held report line writes them, never ids: sales agent names or codes, account types (word, number or tag), brand names, category names, customer names, product codes, the company name.
  - basis: the basis this message says, else the Held report's, else null; never guess one. date_from / date_to: the period the report covers, this message's dates when it names one, else the Held report's. (The top-level basis, sales_basis and date_filter_start / date_filter_end stay this message's own, as their sections say.)
  - A word that is both a Brand candidate and a Known account type, when neither this message nor the Held report says which, goes in brand_or_account_type only, never in brands or account_types, even when its entity is hint "brand" with kind_said null.

```

## Gate results (16 gold rows x1, gemini-3.5-flash-lite, sorento_prod_1020 read-only, text swapped in-process)

Round 1 D: 11 of 16, USD 0.055. Round 2 D3: 13 of 16, USD 0.056 (ledger lines 2 Nov 22:12 and 22:24).

| Row | Message (masked) | D (6769d31d) | D3 (e4aa6d43) | Note |
|---|---|---|---|---|
| sc-01 | sales for zqa for cabana 2026 | FAIL report_ask.brand_or_account_type [] != ['cabana'] | FAIL report_ask.brand_or_account_type [] != ['cabana'] | code data check V4 (both-table word, kind_said null) |
| sc-02 | ivoiced | PASS | PASS |  |
| sc-03 | account type | FAIL report_ask.account_types [] != ['cabana'] | FAIL report_ask.account_types [] != ['cabana'] | declared pick of the offered option (V4, list-pick class); the gold harness shows no options line |
| sc-04 | breka down by month | PASS | PASS |  |
| sc-05 | for ceramic | PASS | PASS |  |
| sc-06 | for slaes agent zqb | PASS | PASS |  |
| sc-07 | this year | PASS | PASS |  |
| sc-08 | sorento | FAIL report_ask.company None != 'Sorento' | PASS | row fixed to the owner's real turn (open company question) after round 1 |
| sc-09 | for slaes agent zqb | FAIL report_ask.account_types [] != ['ceramic'] | PASS |  |
| sc-10 | invoiced | PASS | PASS |  |
| sc-11 | for ceramic account ty[e | PASS | PASS |  |
| sc-12 | sorento | PASS | PASS |  |
| sc-13 | ceramic accoutn type | PASS | PASS |  |
| sc-14 | breakd down by month, only sales agent zqb | PASS | PASS |  |
| sc-15 | ZZT102-RG dealer sales may 2026 | PASS | PASS |  |
| sc-16 | ZZT102-RG sales 2026 | FAIL report_ask.channel 'dealer' != None | FAIL report_ask.channel 'dealer' != None | KNOWN LIMIT, crew-set expectation (crew ruling 2 Nov): the reply header names Channel: dealer |

Graded on the full object (gold bacfd008cb, offline regrade, no spend): D3 12 of 16 (sc-12 adds brand SORENTO, the
question path by crew ruling). No-op control on parser-gold TRAIN (113 common lane ids x1): BASE 90, D3 91, 4 wins / 5
losses, p=1.00, USD 0.688.
