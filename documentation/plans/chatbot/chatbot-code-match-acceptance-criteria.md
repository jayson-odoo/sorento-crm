# UAC: CHATBOT-CODE-MATCH

Card: `CARD-chatbot-code-match-12nov.md` (v3). Plan: `PLAN-chatbot-code-match-12nov.md` (5 slices).
Status: v3 approved by crew 12 Nov (Q1-Q5 settled by the owner's rules as recommended, Q4 now (b)); 8 crew changes folded in.

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
- AC-20 An inactive or chat-hidden placeholder close code is never offered (dealer and staff).
- AC-20f (owner 13 Nov, Q3: "discontineud still show for what"): a discontinued code (is_discontinued, even when
  active) is never offered in a did-you-mean / close-code list, like an inactive one (AC-20). Owner-FAIL #9 (CLB109A)
  therefore offers only CL8109A (C9109A inactive; CB3109A and CB4109A discontinued); this replaces the 22-23 Oct three.
- AC-20j (HELD pending owner follow-up, 13 Nov): a mistyped discontinued close code is replaced in the offer by its
  active, not-discontinued alternative (`product_alternatives`). Red tests exist; built only if the owner picks it over
  strict Q3. AC-20k/l (guards, green): no usable alternative means dropped; no duplicate; company scope kept.
- AC-20g guard: a discontinued code typed EXACTLY keeps today's reply (PRODUCT DISCONTINUED + the Alternative line,
  owner-FAIL #6 / #7).
- AC-21 Dealer says "no" to an offer: today's reply stays (the refer line alone, owner hand test ht26); nothing answered,
  the code is not offered again.
- AC-22 Dealer says "yes" / "1": the offered code is answered with the carried quantity.
- AC-17 Every miss writes a `code_candidates` trace entry: typed token, candidate codes in offered order, tier,
  similarity, and `answered` or `offered`.

## Slice 2: all-typed-parts ranking (R2, R5)

- AC-8 Typed `TWC8354-UF`: candidates holding every typed part (TWC, 8354, UF), in order, rank above a higher-trigram
  candidate that misses one (`TWC8354-UP`). A typo inside a part (e.g. the first letters block) leaves today's order.
- AC-8c Parts are split from the code AS TYPED: typed `TWC8354-SH-UF` treats SH and UF as two parts, so
  `TWC8354-SH-N-UF` holds every part.
- AC-9 Short token `8152` with 6 matching codes keeps the which-one picker (all 6), all-parts first.
- AC-2b A code that differs only by a dash (shape of BT015SS-CR typed BT015SSCR or BT015SS CR) is answered directly,
  staff and dealer (guard; red-first shows whether main already passes).
- AC-2 Token `twc 8354 sh uf` against `TWC8354-SH-UF` is answered directly (R0 equal).
- AC-19 letters-only (owner 13 Nov, Q1 = b): a letters-only word the parser hands as a product code, with a close
  catalogue code, gets a "Did you mean <code>?" OFFER, never a direct answer. The 28 Sep digit rule stays for ordinary
  words (basin, gunmetal, a word the parser types as a category or spec): no offer, reply unchanged.
- AC-19 Code shapes: a digits-first token (`8152-SH`) and a letters-only token (`ABCD`) both reach their catalogue
  codes through the same ranking.

## Slice 3: sets through the membership table (R3)

- AC-1 Token `TWC604RL` (not equal to set `TWC604-P-RL`) offers the set, then its members from `product_set_members`,
  up to 3; none answered directly. No code letter is read as a role.
- AC-3 Token `TWC604PRL` (equal with dashes folded) answers the set: members and the complete-sets figure.
- AC-23 A set whose members the dealer may not see (`visible_set_clauses`) is neither answered nor offered.
- AC-1b Picking the offered set ("1") answers the set at the carried quantity, as an exact set ask; picking a member
  answers that member.

## Slice 4: size from stored values (R4)

Seed a registry size key scoped to the test category (Q2 a) in mm.
- AC-4 Token `TWC8152-SH-UF-250`, family `TWC8152-SH-UF` (nothing stored) and `TWC8152-SH-UF-300` (300 stored): not
  answered; reply starts `Couldn't find TWC8152-SH-UF-250` and offers each with `Size: not recorded` / `Size: 300 mm`.
  Kill check: nothing maps a code with no stored value to any size.
- AC-5 Token `8152-300-SH`, `TWC8152-SH-300` with 300 stored: one candidate, offered (Q1 a), `Size: 300 mm`.
- AC-6 A number in the code that equals no stored value is not a size (the token is matched as a code only).
- AC-7 Typed size no candidate holds: `Couldn't find X` plus close codes with their stored sizes; never the bare
  "None with size 400 mm." line.
- AC-25 A category with several numeric length keys (registry keys in the same unit) where the typed number equals a
  stored value under more than one: every matching candidate is offered with the key it matched; no key is guessed.
- AC-26 "None with size N <unit>." takes the unit from the registry key (`lanes/business/answer.py:2872`), e.g. a key in
  cm prints cm.
- Scope (lead, review round 4): the size rules above apply when the message names exactly ONE product code. A
  message naming several product codes plus a size keeps main's behaviour (each existing code answered; the size is not
  paired to a code). Known limitation, follow-up: pair a size to its own code in a multi-code ask.
- Accepted limitations (reviewer, slice 4 final; both behave as on main, follow-ups): (1) a code plus a customer name
  plus a size still gives "None with size N." and an answer, because the resolver lists the code's prefix family and the
  code is not marked resolved; (2) the one-code count reads only entities hinted "product" (elsewhere a missing hint
  also counts as a product); a second code with no hint counts as one code.
- AC-18 `scripts/chatbot_products_without_size.sql` (read-only SELECT): active products in categories with a size key
  and no stored value (code, category); crew runs it on the dev copy.

## Slice 5: X insert replaced from catalogue data

- AC-24 (crew ruling 12 Nov) The family link the "X" insert gives (`product_code_family.py:88`) comes from catalogue
  data (set membership, variant group or family field) and the letter rule is gone, with the 16 owner tests in
  `test_attribute_asks_round7.py` and `test_narrow_code_own_line.py` green unchanged. If the data lacks the link, the
  insert stays and the generic audit names it "kept until the catalogue carries the link" with the data needed.

## Not changed

Parser prompt; engine stale-typo / focus-carry path; scoreboard queries; `chatbot_lookup_edits.py`,
`head/lookup_lists.py`; nothing else.
