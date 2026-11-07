# UAC: report follow-ups widen what the parser widened; a settled name is not asked again (7 Nov 2026)

Plan: PLAN-chatbot-report-widen-reask-7nov.md. Engine tests feed the parser output (as the repro gave it, or the shape
named) through the report-ask lane; each row asserts the route args that ran, or the question asked. Held report
"T1" = sales, frame total, basis invoiced (or delivered on the test DB), Sep 2026, measure qty, Company Sorento,
Brand SORENTO, Category Kitchen Sink.

| # | Given | When (parse) | Expected |
|---|---|---|---|
| WR-1 | T1 held, then a channel breakdown held on it (T5 state) | "all brand all category": object brands [] and categories [], group_by channel, broaden_axis "all", broaden_to "all", entity_op "clear" (repro step 8 shape) | Channel breakdown for Company Sorento, no brand filter, no category filter, nothing asked |
| WR-2 | same | "for all brands and categories": object brands [] and categories [], broaden_axis "brand", broaden_to "all" (repro step 9) | Same as WR-1: the category is widened too, not carried back |
| WR-3 | same | "all" with object brands [] and categories [] and broaden_to "all" (any axis) | Same as WR-1 |
| WR-4 | T1 held | "clear all": object every list [] and company null, entity_op "clear", broaden_axis "all", broaden_to "all" (repro step 5; with and without topic_reset true) | No held brand, category or company comes back: either a report with none of them, or the report's own question (basis / period); never the T1 total again |
| WR-5 | T1 held, SORENTO also a stored account type, contact holds Sorento and Mocha | "sorento total slaes by delaer and proejct": object group_by channel, frame breakdown, brands [SORENTO], company Sorento, entity raw sorento hint brand, said_as null (or absent) | No "brand, account type or company?" question: channel breakdown runs with Company Sorento and Brand SORENTO (the held kinds) |
| WR-6 | T1 held | a follow-up that widens nothing and leaves brands / categories out of the object ("by month", no broaden fields) | Unchanged C6-2: the held brand and category are carried (lock) |
| WR-7 | nothing held | bare "Sorento ..." with said_as null | Unchanged: the one company / brand / both question (HT1-5, lock) |
| WR-8 | T1 held | the message types a kind for the word ("sorento account type", said_as / kind_said says it) | Unchanged: the typed kind decides (lock) |

### Review round 1 (7 Nov, NOT READY on 7b0b2df3c6): lead rulings

| # | Given | When (parse) | Expected |
|---|---|---|---|
| WR-1/2 (corrected) | as WR-1 / WR-2 | the REAL repro objects, including company "Sorento" and company_or_brand ["SORENTO"] | Same as WR-1: channel breakdown for Company Sorento, no brand, no category, no question. On a widen, a company_or_brand word equal to the object's own company is that company (parser fields only) |
| WR-9 | T1 held | "only company sorento" in the C6-1 shape (company Sorento, brands [SORENTO], entity canonical_code null, kind_said null, said_as null) | Company + the held category, no brand (the C6-1 company reading runs before the settled-name rule) |
| WR-10 | T1 held (brand and category held) | "for all customers" (broaden_axis customer, broaden_to all) or a date widen (broaden_axis date), the object leaving brands / categories out | The held brand and category are KEPT: an emptied list counts as widened only when the widen axis is "all", none, or a product-filter kind (brand, category, account type) |
| WR-11 | Brand SORENTO held, no company held | "sorento company only" with said_as null (the HT1-5 shape) | The one company / brand / both question (unchanged HT1-5). "Settled" = the held report has the name as its company AND among its brands (the prod T4 shape) |
| WR-12 | T1 held | entity_op "clear" with every broaden field null ("remove the filters") and the lists emptied | Lists widened (entity_op clear alone is a widen) |
| WR-13 | T1 held, SORENTO an account type | the kind is typed ("sorento account type", kind_said said) | The typed kind decides; the settled-name rule does not fire (WR-8 on a held report) |
| WR-14 | a held report of another kind (outstanding) or topic_reset true | "sorento total ..." with the word unsaid | The settled-name rule does not fire (the held report is not carried) |
