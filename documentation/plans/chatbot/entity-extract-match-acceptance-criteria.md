# UAC: ENTITY-EXTRACT-MATCH (extract then match)

Plan: `documentation/plans/chatbot/PLAN-entity-extract-match-26oct.md`. Owner rulings 26 Oct ~16:15: Q1 (a) two-pass +
union in slices S1-S4; Q2 +~1.0 s per turn OK; Q3 (a) no new alias table; Q4 (a) in-process vector cache.

## Journey

1. A dealer or staff member writes to the WhatsApp assistant naming things in their own words: "hanlim wc cert",
   "srt basin hitam ada?", "马桶 picture", "jhonson suise catelog".
2. The system already knows every list the person may see (brands, categories, spec values and names, file types,
   promotion kinds, warehouses, salespeople, customers) and the alias texts admins keep on those rows.
3. A small span pass (S2) copies out each mention and a rough type, without seeing any list values.
4. The resolver (S1) matches each mention to the row(s) it names across ALL lists: exact, alias text, typo, partial
   name, meaning. Type only breaks ties. Two close rows -> ambiguous (the assistant will ask). Nothing close -> none.
5. The parser sees only the matched rows (S2); mentions it leaves out are added back (S3, if it wins the measure).
6. The person gets the right answer without being asked for what they already wrote, and is asked only when two rows
   are genuinely close.

S1 is step 4 alone: a library plus an offline eval. No turn changes behaviour in S1.

## S1: list resolver (no behaviour change)

Fixtures in tests are invented (public repo): never a real customer, salesperson or person name.

- **AC-S1-1 [BE]** Given rows across lists, when a span equals a row text after case/space folding ("Mocha" vs brand
  "MOCHA"), then status `resolved`, that row first, signal `exact`.
- **AC-S1-2 [BE]** Given a row whose extra texts hold an alias ("SRT" on brand SORENTO; "马桶" on category Water
  Closet), when the span is the alias ("srt", "马桶"), then it resolves to that row; the resolver holds no alias words
  of its own (no hard-coded word lists in the module).
- **AC-S1-3 [BE]** Given a misspelled span ("jhonson suise" vs "JOHNSON SUISSE"), then it resolves by spelling.
- **AC-S1-4 [BE]** Given customer rows with long names ("KIMLAN TRADING SDN BHD", "BUMI CERAMIC SDN BHD"), when the
  span is a partial name ("Kimlan") or a partial name with a one-letter typo in a token ("Bumi ceramics"), then it
  resolves to the right row; when the span shares only common tokens with a row ("trading sdn bhd" vs many "... SDN
  BHD" rows), then it does NOT resolve to one of them. Token weights come from the list's own texts (IDF), not a word
  list.
- **AC-S1-5 [BE]** Type is a tie-break, never a filter: a span typed `file_type` that only matches a promotion_kind
  row resolves to that promotion_kind row; when the typed list and another list match the span equally well, the
  typed list's row wins; an untyped span (type None) resolves over all lists.
- **AC-S1-6 [BE]** Given two different rows whose scores are within the ambiguity margin of each other (or rows that
  share the matching text, e.g. salesperson codes "LEE - I" and "LEE - II" both carrying "LEE"), then status
  `ambiguous` with every close row as a candidate, best first.
- **AC-S1-7 [BE]** Given a span that names nothing ("stock", "please"), then status `unresolved` with no candidate;
  each list applies its own floors (spelling, partial, meaning) from one constant table in the module.
- **AC-S1-8 [BE]** A span typed `product_code` is returned with status `skipped` and no candidates (products resolve
  elsewhere).
- **AC-S1-9 [BE]** Given an embedder (callable returning vectors), a span with no spelling overlap but a close vector
  ("booster pump" -> "Water pump") resolves with signal `meaning`; given no embedder or an embedder that raises, the
  resolver still resolves spelled spans and never raises.
- **AC-S1-10 [BE]** `resolve()` returns exactly one result per input span, in input order; an empty span list returns
  an empty list; a span whose text is blank is `unresolved`.
- **AC-S1-11 [BE]** Spec-name rows: given product spec registry entries, the resolver's spec_key row builder yields one
  row per active key with the label, the key spelled with spaces, synonyms and user synonyms, minus suppressed
  synonyms; "colour" resolves to the finish/colour key when that synonym is present.
- **AC-S1-12 [T]** Offline eval CLI `scripts/chatbot_eval/span_resolve.py` on the committed synthetic fixture (lists +
  gold + spans, under tests fixtures) prints the oracle and right-row numbers and they equal the expected values in
  the test; it makes no network call and needs no DB.
- **AC-S1-13 [T]** Gate (evidence in the PR, data stays outside git): the CLI on the phase-1 gold
  (crew/state/eval/eem) reproduces oracle >= 268/271 and B1-span right row on the test half >= 77%.
- **AC-S1-14 [T]** No behaviour change: no module on the turn path imports `list_resolver` in S1; the existing head
  lookup tests pass unchanged.
