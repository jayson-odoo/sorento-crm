# UAC: CHATBOT-CODE-MATCH

Card: `CARD-chatbot-code-match-12nov.md` (v3). Plan: `PLAN-chatbot-code-match-12nov.md` (5 slices).
Status: v3 (generic rules; no assumed size). Written on the card's recommended answers.

All tests on Postgres (`tests/_pg_fixture.py`), seeding their own products, sets, registry keys, specs and companies
(fake codes of the same SHAPE as the card; CI has no data). The parser is not called: each test hands the resolver /
answer layer the token the parser would have extracted. No test seeds or asserts a Sorento-only code letter, size
marker or default size.

## Slice 1: dealer offers + trace (R1, R6, R7)

- AC-10 Dealer offer. Availability-only contact, token `SWTWC8354-SH-UF x 3`, `TWC8354-SH-UF` exists in the dealer's
  company: reply `Couldn't find SWTWC8354-SH-UF. Did you mean TWC8354-SH-UF?`; the pending pick carries quantity 3;
  no "Please refer to your salesman." line; no escalation offer.
- AC-11 Dealer, up to 3. Four close codes: the reply lists exactly 3, numbered, under `Couldn't find X. Did you mean:`.
- AC-12 Dealer, other company. The only close code belongs to another company: today's refer reply; the other
  company's code is in neither the text nor the pending options.
- AC-13 Dealer, no close code: byte-identical to main.
- AC-14 Staff uses the same function (Q5 a): the same miss on a staff contact yields the same candidates in the same
  order (staff wording unchanged).
- AC-15 Multi-code. `TWC8354-SH-UF x 2` (exact) plus `SWTWC8152 x 1` (miss) for a dealer: the exact code is answered,
  the miss gets its own did-you-mean from the same function as AC-10.
- AC-16 Exact code unchanged: reply byte-identical to main (staff and dealer).
- AC-17 Every miss writes a `code_candidates` trace entry: typed token, candidate codes in offered order, tier,
  similarity, and `answered` or `offered`.

## Slice 2: all-typed-parts ranking (R2, R5)

- AC-8 Token `SWTWC8354SHUF`: a candidate holding every typed part in order ranks above a higher-trigram candidate that
  misses one.
- AC-9 Short token `8152` with 6 matching codes keeps the which-one picker (all 6), all-parts first.
- AC-2 Token `twc 8354 sh uf` against `TWC8354-SH-UF` is answered directly (R0 equal).
- AC-19 Code shapes: a digits-first token (`8152-SH`) and a letters-only token (`ABCD`) both reach their catalogue
  codes through the same ranking.

## Slice 3: sets through the membership table (R3)

- AC-1 Token `TWC604RL` (not equal to set `TWC604-P-RL`) offers the set, then its members from `product_set_members`,
  up to 3; none answered directly. No code letter is read as a role.
- AC-3 Token `TWC604PRL` (equal with dashes folded) answers the set: members and the complete-sets figure.

## Slice 4: size from stored values (R4)

Seed a registry size key scoped to the test category (Q2 a) in mm.
- AC-4 Token `TWC8152-SH-UF-250`, family `TWC8152-SH-UF` (nothing stored) and `TWC8152-SH-UF-300` (300 stored): not
  answered; reply starts `Couldn't find TWC8152-SH-UF-250` and offers each with `Size: not recorded` / `Size: 300 mm`.
  Kill check: nothing maps a code with no stored value to any size.
- AC-5 Token `8152-300-SH`, `TWC8152-SH-300` with 300 stored: one candidate, offered (Q1 a), `Size: 300 mm`.
- AC-6 A number in the code that equals no stored value is not a size (the token is matched as a code only).
- AC-7 Typed size no candidate holds: `Couldn't find X` plus close codes with their stored sizes; never the bare
  "None with size 400 mm." line.
- AC-18 `scripts/chatbot_products_without_size.sql` (read-only SELECT): active products in categories with a size key
  and no stored value (code, category); crew runs it on the dev copy.

## Not changed

Parser prompt; engine stale-typo / focus-carry path; scoreboard queries; `chatbot_lookup_edits.py`,
`head/lookup_lists.py`; the existing family "X" insert (Q4).
