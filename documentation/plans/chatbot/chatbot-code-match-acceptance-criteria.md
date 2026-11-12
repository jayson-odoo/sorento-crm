# UAC: CHATBOT-CODE-MATCH

Card: `CARD-chatbot-code-match-12nov.md`. Plan: `PLAN-chatbot-code-match-12nov.md`.
Status: draft, written on the card's recommended answers; revised when the owner answers Q1-Q5.

All tests on Postgres (`tests/_pg_fixture.py`), seeding their own products, sets, specs and companies (fake codes of
the same SHAPE as the card; CI has no data). The parser is not called: each test hands the resolver / answer layer the
token the parser would have extracted.

## Resolver layer (`entity_resolver`, `product_code_family`)

- AC-1 Part form. Seed set `TWC604-P-RL` (members `TWCX604-P-RL`, `TWCY604-RL`) and product `TWCX604-S-RL`. Token
  `TWC604RL` with no exact hit returns candidates including `TWCX604-P-RL` and `TWCX604-S-RL` (tier `part_form`) and the
  set `TWC604-P-RL`; none is marked direct.
- AC-2 Dashes / spaces / case only. Token `twc 8354 sh uf` against `TWC8354-SH-UF` resolves exactly (direct answer).
- AC-3 Registered set direct. Token `TWC604PRL` (dash-only difference from set `TWC604-P-RL`) resolves to the set,
  direct, with members and the complete-sets figure on the entity (`_product_set_entities`).
- AC-4 Size in code, default. Family `TWC8152-SH-UF` (no size marker, trap_length 250 or empty) plus sized siblings
  `TWC8152-SH-UF-300` (trap_length 300). Token `TWC8152-SH-UF-250` resolves direct to `TWC8152-SH-UF`.
- AC-5 Size in code, non-default. Token `8152-300-SH` with `TWC8152-SH-300` (trap_length 300) in the family returns ONE
  candidate `TWC8152-SH-300`, offered, not direct (Q1 a).
- AC-6 Mocha sizes. Codes `MOC100-S6/-S8/-S10/-S12` with trap_length 150/200/250/300: token `MOC100 300` offers
  `MOC100-S12`; token `MOC100` (unmarked) answers `MOC100-S10` directly only under Q2's rule.
- AC-7 Size not held. Token `TWC8152-SH-400`: no member with 400; reply starts `Couldn't find TWC8152-SH-400` and
  offers up to 3 family members; it is never the bare "None with size 400 mm." line.
- AC-8 All-parts ranking. Token `TWC8354SHUF` typo `SWTWC8354-SH-UF`: candidates holding every typed part (8354, SH,
  UF) rank above higher-trigram candidates that miss a part.
- AC-9 Short token. Token `8152` with 6 matching codes keeps the which-one picker (all 6 listed), all-parts first.

## Answer layer (staff and dealer)

- AC-10 Dealer offer. Availability-only contact, token `SWTWC8354-SH-UF x 3`, `TWC8354-SH-UF` exists in the dealer's
  company: reply `Couldn't find SWTWC8354-SH-UF. Did you mean TWC8354-SH-UF?`; the pending pick carries quantity 3;
  no "Please refer to your salesman." line; no escalation offer.
- AC-11 Dealer, up to 3. Four close codes: the reply lists exactly 3, numbered, `Couldn't find X. Did you mean:`.
- AC-12 Dealer, other company. The only close code belongs to another company: reply is today's refer reply
  (`Couldn't find X.` then the refer line); the other company's code is not in the text or the pending options.
- AC-13 Dealer, no close code: unchanged from main (byte-identical reply).
- AC-14 Staff offer uses the same function (Q5 a): the same token on a staff contact lists the same candidates in the
  same order (staff wording as today's did-you-mean).
- AC-15 Multi-code ask. `TWC8354-SH-UF x 2` (exact) plus `SWTWC8152 x 1` (miss): the exact code is answered, the miss
  gets its own did-you-mean from the same function as AC-10 / AC-14.
- AC-16 Exact code unchanged: an exact code's reply is byte-identical to main (staff and dealer).

## Trace

- AC-17 Every miss writes a `code_candidates` trace entry: typed token, candidate codes in offered order, tier and
  similarity per candidate, and `answered` or `offered`.

## Data list (no data edit)

- AC-18 `scripts/chatbot_wc_without_size.sql` (read-only SELECT) lists active water closets with no `trap_length`
  (code, name, category); crew runs it on the dev copy and attaches the count (review: 419 of 979).

## Not changed

Parser prompt; engine stale-typo / focus-carry path; scoreboard queries; `chatbot_lookup_edits.py`,
`head/lookup_lists.py`.
