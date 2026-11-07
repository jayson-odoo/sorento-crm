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
