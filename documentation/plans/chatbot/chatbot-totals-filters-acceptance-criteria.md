# UAC: chatbot totals vs top-N, one name one filter, clear one filter, combined turn

Status: answered 4 Nov. Q1 (a) new path only, no old-path patch. Q3 (a) held filters survive every follow-up until the
user changes them. Q2 (c) a bare name that is both a company and a brand asks ONCE which, and asking for both works.
Q5 the owner raised the report limit in Settings (no code). Q4 ruled: the basis question first is fine, then the
per-agent list (AF-6). Gate 1 (4 Nov): the model leaves kind_said null, so a bare overlap name goes in a
`company_or_brand` slot (mirrors #2105's brand_or_account_type); kind_said only refines. Plan: `PLAN-chatbot-totals-filters-4nov.md`.

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
| AF-7 | a channel breakdown held | "top 5" (object frame breakdown, top_n 5) | Top 5 by channel: the object's own count makes it a ranking cut to that count |
| AF-6 | nothing | "Total sale for all sale agents on September 2026" (basis held) | Breakdown by sales agent, every agent + grand total, no "How many?" (Q4) |

## One name, one filter (R2)

| # | Held before | Message | Expected |
|---|---|---|---|
| ON-1 | Sep, delivered, split by channel | "sorento company only" | Company Sorento only; NO brand filter; split, period, basis kept |
| ON-2 | Sep, delivered | "Sorento brand only" | Brand SORENTO only; no company filter added |
| ON-3 | nothing | "Sorento total sale September 2026" (basis given or held) | ONE question: Sorento, company or brand (options company / brand / both); no report runs yet; NOT the two-company table |
| ON-4 | nothing | same as ON-1/ON-2 with Mocha | Same, for Mocha |
| ON-5 | nothing | a contact who sees one company, "Sorento total sale September 2026" | Brand SORENTO (no company choice exists) |
| ON-8 | nothing | "sorento company and brand, Sep delivered" | Company Sorento AND Brand SORENTO together, no question |
| ON-9 | ON-3's open question | "company" | Company only, no brand; basis + period kept; not asked again |
| ON-10 | ON-3's open question | "brand" | Brand only, no company; rest kept |
| ON-11 | ON-3's open question | "both" | Company AND brand; rest kept |
| ON-12 | company Sorento already held (settled earlier) | a follow-up that does not mention Sorento | No question; held company kept (Q3) |
| ON-13 | nothing | a bare overlap name the parser puts in the object's `company_or_brand` slot | ONE company-or-brand question (company / brand / both); no report yet |
| ON-14 | ON-13's open question | the Held report line the parser sees | Labelled "company or brand", never "brand or account type" |
| ON-15 | a contact who sees one company | `company_or_brand` ["Sorento"] | Brand filter, no question |
| ON-16 | nothing | the object puts the same name in company AND brands with no kind word for both | One company-or-brand question, never both filters silently (wrong totals are worse than one question) |
| ON-6 | nothing | "Cabana sales Sep delivered" | Unchanged #2105 behaviour: "brand or account type?" |
| ON-7 | overlap detection | any name present in two filter lists | Found from data (the name resolves in both), never from a list of names in code |

| ON-17 | nothing | object company "Sorento" AND brands ["SORENTO"], kind_said null, the brand entity has NO canonical code (the parser did not match it as a listed brand) | The company, no question: #2105's C6-1 rule (a word that is the object's own company and no listed brand), kept by lead ruling 4 Nov |

## Known companies line (gate 2: the parser cannot know which brand names are companies)

| # | Case | Expected |
|---|---|---|
| KC-1 | prompt text names "Known companies", contact holds 2+ companies | parser user block carries `Known companies: <names sorted>` |
| KC-2 | prompt text without the phrase | user block byte for byte unchanged |
| KC-3 | contact holds one company | no line |
| KC-4 | parser config | flag `known_companies` set only when the text names the phrase |

## Outstanding kind question wording (owner ruling 4 Nov)

| # | Held before | Message | Expected |
|---|---|---|---|
| OW-1 | nothing, contact sees both kinds | "waht's my oustsgnidn" | "Sales order or delivery order?", options Sales order / Delivery order; nothing runs |
| OW-2 | OW-1's question | pick 1 / pick 2 | SO backlog (outstanding) / DO pending (pending_delivery) |
| OW-3 | OW-1's question | "sales order" / "delivery order" as a parse | same as OW-2 |
| OW-4 | contact sees one kind | same message | that kind, no question |

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
