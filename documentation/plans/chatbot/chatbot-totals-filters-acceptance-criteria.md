# UAC: chatbot totals vs top-N, one name one filter, clear one filter, combined turn

Status: Q1 (a) and Q3 (a) answered by crew 4 Nov (new path only, no old-path patch; held filters survive every
follow-up until the user changes them). Q2, Q4, Q5 are with the owner (ask a57420216): rows marked PENDING-Q2 /
PENDING-Q4 are not built until he answers. Plan: `PLAN-chatbot-totals-filters-4nov.md`.

Scope: the NEW report-ask path (`parser.REPORT_ASK_LINE` marker, `report_ask.from_object`). Production gets these once
the parser label moves to the lane's prompt text. Staff contact who sees two companies (Sorento, Mocha) unless a row says
otherwise. "Held" = the state the previous turn left. Every row is checked on the reply AND on the held state after.

## Ask frame (R1)

| # | Held before | Message | Expected |
|---|---|---|---|
| AF-1 | nothing | "Total sale delivered 1/10-9/10/26 Sorento brand" | One total (RM + pcs), Brand SORENTO, 1-9 Oct, delivered. No "How many?", no "By quantity or by amount?" |
| AF-2 | Company Sorento, delivered, Sep, split by channel (dealer / project) | "show dealer and project" | Breakdown by channel, every row, no count or measure question |
| AF-3 | a top 10 products ranking | "i want total sales, by qty" | One total; top N and axis dropped; filters, period, basis kept |
| AF-4 | a breakdown by channel | "top 5" | Ranking on channel, top 5; asks qty-or-amount only if no measure is held or said |
| AF-5 | nothing | "top 10 products September delivered" | Ranking; asks only "By quantity or by amount?" |
| AF-6 PENDING-Q4 | nothing | "Total sale for all sale agents on September 2026" (basis held) | Breakdown by sales agent, every agent + grand total, no "How many?" (Q4) |

## One name, one filter (R2)

| # | Held before | Message | Expected |
|---|---|---|---|
| ON-1 | Sep, delivered, split by channel | "sorento company only" | Company Sorento only; NO brand filter; split, period, basis kept |
| ON-2 | Sep, delivered | "Sorento brand only" | Brand SORENTO only; no company filter added |
| ON-3 PENDING-Q2 | nothing | "Sorento total sale September 2026" | Basis asked; then Company Sorento (Q2), no brand filter, NOT the two-company table |
| ON-4 | nothing | same as ON-1/ON-2 with Mocha | Same, for Mocha |
| ON-5 PENDING-Q2 | nothing | a contact who sees one company, "Sorento total sale September 2026" | Brand SORENTO (no company choice exists) |
| ON-6 | nothing | "Cabana sales Sep delivered" | Unchanged #2105 behaviour: "brand or account type?" |
| ON-7 | overlap detection | any name present in two filter lists | Found from data (the name resolves in both), never from a list of names in code |

## Clear one filter (R3)

| # | Held before | Message | Expected |
|---|---|---|---|
| CL-1 | Company Sorento, Brand SORENTO, split by channel, Sep, delivered | "all brands" | Brand gone; company, split, period, basis kept; report runs, nothing asked |
| CL-2 | same | "clear the brand filter" | Same as CL-1 |
| CL-3 | same | "brand is all brand" | Same as CL-1 |
| CL-4 | a customer filter + rest | "all customers" | Customer gone, rest kept |
| CL-5 | product / category / agent / account type / channel / company held | "all <kind>" / "clear the <kind> filter" | Only that filter goes (one matrix over every kind) |
| CL-6 | no brand held | "all brands" | No-op: same report, nothing asked, nothing else dropped |
| CL-7 | anything | "start over" | Everything cleared (existing reset) |

## Combined turn (R4)

| # | Held before | Message | Expected |
|---|---|---|---|
| CT-1 | Sep, delivered, total | "sorento company only, show dealer and project" | Company Sorento AND split by channel in the same reply |
| CT-2 | split by channel held, an open "How many?" | a message whose report ask is a breakdown on another axis (e.g. "break it down by brand") | Breakdown by that axis (the typed axis wins over the held one); the agent wording itself is AF-6 |
| CT-3 | total held | "October, by brand" | Period October AND breakdown by brand together |

## Basis (R5)

| # | Held before | Message | Expected |
|---|---|---|---|
| BA-1 | nothing | "Total sale deliver for 1/10-9/10/26 Sorento brand" | Delivered taken from the message; no basis question |
| BA-2 | delivered held | "i want total sales, by qty" | Delivered kept; no basis question |
| BA-3 | nothing | "Sorento total sale September 2026" | Basis asked (never defaulted), Invoiced listed first |

## Held filters on a complete new question (Q3)

| # | Held before | Message | Expected |
|---|---|---|---|
| HF-1 | Customer filter from a dealer thread | "Total sale deliver for 1/10-9/10/26 Sorento brand" | Customer kept; the header lists it |
| HF-2 | Company Sorento held | "Total sale for all sale agents on September 2026" | Company kept; no brand appears that the user never said |

## Robustness (#2105 follow-up)

| # | Case | Expected |
|---|---|---|
| RB-1 | `with_customer_groups`, `arg_names`, `_group_names` given a non-UUID id | Bad id skipped, no DataError, the rest of the report runs |

## Prompt gate

- One prompt text built on e4aa6d43, pinned by md5.
- Parser-gold TRAIN no-op control on gemini-3.5-flash-lite, both arms: not worse than BASE.
- Gold rows from AF / ON / CL / CT / BA, written as whole report-ask objects (equivalence, not reply shape): every row passes.
