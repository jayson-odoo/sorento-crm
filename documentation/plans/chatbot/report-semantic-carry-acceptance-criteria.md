# UAC: the parser writes the whole report ask each turn (semantic carry, 2 Nov 2026)

Plan: `PLAN-report-semantic-carry-2nov.md`. Agent codes are masked (AGENT A, AGENT B: public repo). "Ran" means the
`crm_report_ask` args the turn sent; a question means no report ran and the reply is that question. Every check is on
the args that ran, not on reply wording, except where a reply line is named.

## A. Parser contract

- SC-1 A prompt text carrying the report-ask marker line turns `ParserConfig.report_ask` on and the parse schema gains
  `report_ask`: an object or null, every key required and nullable (strict mode), last in `properties` and `required`.
- SC-2 A text without the marker gets today's schema, byte for byte, and today's user block, byte for byte.
- SC-3 With the flag on and a held report, the user block carries ONE `Held report:` line in words: kind, basis,
  period (from and to), breakdown, count, measure, channel, company NAME, sales agent NAME(S), account type(s), brand
  NAME(S), category NAME(S), customer NAME(S), product code(s). No UUID appears in it. The line is `Held report: `
  followed by compact JSON with exactly the `report_ask` keys.
- SC-4 While a field question is open (basis, period, count, company, brand or account type, agent pick), the line
  shows the ask so far and names the open question: `Held report (open question: <basis|period|count|company|brand or account type|sales agent>): ` + the JSON.
- SC-5 (revised in review round 2) A held agent, brand or category is shown by a word that resolves back to exactly
  the held rows (agent code; brand or category name, else its code) and is resolved again inside the ask's company,
  through the permission-gated resolvers, so it sends the same ids. A held customer sends its held id when that id is
  in the ask's company (or no company is named), else the one customer of that exact name in the named company
  (behind the customers permission; a dealer's linked customers only); none or several give the same reply as that
  name typed in the named company.

## B. The owner's 14 turns (one conversation, staff contact with two companies, flag on)

The fake parser returns the object the owner expects at each turn; the assertions are the args that ran.

| # | Message (masked) | Expected |
|---|---|---|
| 1 | sales for agent a for cabana 2026 | basis question |
| 2 | ivoiced | "brand or account type?" for cabana |
| 3 | account type | ran: invoiced, AGENT A, account type CABANA, 2026, no breakdown |
| 4 | breka down by month | ran: same + by month |
| 5 | for ceramic | ran: account type CERAMIC, AGENT A, by month, 2026, invoiced |
| 6 | for slaes agent b | ran: AGENT B (alone), CERAMIC, by month, 2026, invoiced; no question |
| 7 | this year | ran: same as 6 (2026); no company question |
| 8 | sorento | ran: company Sorento + every slot of 7 |
| 9 | for slaes agent b | ran: same as 8; no basis question |
| 10 | invoiced | ran: same as 8; CERAMIC kept |
| 11 | for ceramic account ty[e | ran: account type CERAMIC, Sorento kept; no company question |
| 12 | sorento | ran: same as 11 when read as the company; read as a brand (nothing open, SORENTO is a brand and an account type) it asks "Sorento: brand or account type?" (crew ruling 2 Nov) |
| 13 | ceramic accoutn type | ran: CERAMIC, AGENT B, by month, Sorento, 2026, invoiced |
| 14 | breakd down by month, only sales agent b | ran: by month, AGENT B, 2026, invoiced, Sorento, CERAMIC |

- SC-6 Each row above holds with the fake parser returning the expected object.
- SC-7 The live candidate prompt (parser gold, x1) returns the expected slot set on each of the 14 rows, scored slot
  by slot; a row it misses is reported, not hidden.

## C. Restated ask (crew-set, owner can change)

- SC-8 "srt102-rg dealer sales may 2026" (basis answered "invoiced" when asked) runs product srt102-rg, channel
  dealer, May 2026; then "srt102-rg sales 2026" runs product srt102-rg, 2026, invoiced, every channel, and the reply
  header names the channel (all). Crew-set; the live prompt keeps dealer (2 of 2 runs): known limit for PR A, crew
  ruling 2 Nov (the header shows "Channel: dealer"). The engine test SC-8 still holds with the expected object.

## D. Value checks (code, no language rules)

- SC-9 Basis: an object basis that this message does not say and the held report / open ask does not have -> the
  basis question, never a default. A basis the held report already has carries without a question.
- SC-10 (REVISED 3 Nov, owner ruling O-R2; the company question is gone) Company: an object company the contact does
  not hold -> the forbidden-company line; a company the ask names narrows the run to it (sales and outstanding); no
  company named -> no question, the run covers every company the contact holds (see SC-18).
- SC-11 Dealer: a dealer contact's object asking outside its own customer -> the existing refusal.
- SC-12 A word in both the brand and the account type tables left in `brand_or_account_type` -> "brand or account
  type?"; a word in one table only goes to that one with no question.
- SC-12b (refined 2 Nov from the prototype) A both-table word the object put in brands or account_types asks when
  this message's entity for it has kind_said null (V4a); kind_said "brand" / "account type" settles it with no
  question (V4b); a settled word carried with no entity this turn never asks (V4c); while the question is open, the
  declared pick of an offered option answers it and keeps every other held slot (V4d).
- SC-13 An agent name matching several agents -> the agent pick; no period -> the period question; a ranking with no
  count -> the count question.
- SC-14 A drill, a list pick and "more" over rows on screen behave as today.

## E. Unchanged

- SC-15 Flag off (every production text today): the #2070, #2074 and sales channel suites pass, except the tests that
  pinned the company question (rewritten to O-R2, round 7) and the R3 carry (SC-21).
- SC-16 The reply template is unchanged (header names basis, period, filters, channel, then the table), except the
  per-company lines of SC-18.

## G. Round 7 (3 Nov): owner production feedback + crew round-6 decisions (both paths unless named)

- SC-18 (owner O-R2) "Sorento or Mocha?" is never asked. A staff contact with two companies asking "sales 2026"
  (basis answered) gets a run with no company arg. When two or more companies have figures for the filters, the reply
  shows one line per company ("<Company> RM x, n pcs", in the contact's company order) right before the Total line;
  a company with no figure is left out, so a subject that exists in one company prints no split. A named company
  prints no split. The route's response carries the per-company totals as `companies`.
- SC-19 (crew C6-1, flag on) A both-table word that is also one of the contact's companies is asked "<WORD>: brand,
  account type or company?"; picking company runs that company with no brand / account type of that word. An object
  whose company is that word asks nothing and runs the company.
- SC-20 (crew C6-2, flag on) A held filter the model drops on a follow-up whose own entities name nothing of that kind
  still runs (agent change keeps the account type; "invoiced" keeps the account type, company and month); a new value
  of a kind replaces that kind only; another report kind or a topic reset carries nothing. A breakdown by a slot the
  ask filters to one value runs as the plain report (no "Top 1" list).
- SC-21 (owner O-R3) A held customer survives every follow-up that names no customer: the basis answer, the company
  answer, "breakdown product", "top 5, by invoiced qty". The reply header names the customer each time.
- SC-22 (owner O-R4) "<customer> only" / "customer <customer> only" after a report runs that report narrowed to the
  customer, with no question and no menu.

## F. PR B (after the label moves)

- SC-17 The carry functions listed in the plan's Deletion section are gone; SC-6, SC-8 to SC-14 still pass.
