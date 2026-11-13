# UAC: CHATBOT-SET-CODES (final; crew answers to card v1, 13 Nov)

Card: `CARD-chatbot-set-codes-13nov.md`. Plan: `PLAN-chatbot-set-codes-13nov.md`.
Crew answers: Q1 (a) no role column; Q2 no X insert and no code-shape suffix rule, unlinked X products are a data-fill
gap (listed, not edited); Q3 (a); Q4 (a) trace is internal only; Q5 case + dashes + spaces only.

Scope = what main (0f80d519, after #2370) still gets wrong on the dev data's real shape (crew data 13 Nov: 15 sets
`CWC604-*` / `CWC605-*`, each a pan member + a cistern member, cisterns shared across sets, no product carries a set
code, CWC609-RL discontinued). Sandbox replay of that shape on main:

| Typed | Main today | Defect |
| --- | --- | --- |
| `cwc604-rl x 2` | offers CWC604-P-RL, then its 2 members | 4 sets hold every typed part; the S-trap set is never offered |
| `cwc604 p rl stock` | staff: two pan PRODUCTS (P-RL and P-RL-NEW pans); dealer: refer line | a space-typed registered set is not answered as the set |
| `CWC605RL x 1` | staff: CWC605-RL plus -SOFT, -NEW, -WEPLS sets; dealer: "How many units for each?" over members | an exact set answers its prefix siblings too |

Harness: `engine.run_turn` over seeded Postgres rows (Console in `tests/chatbot/test_code_match_dealer_offers.py`,
`_make_set` in `tests/chatbot/test_code_match_sets.py`). Seeded codes are synthetic but keep the real SHAPE (e.g.
`QWC604-P-RL` with members `QWCX604-P-RL`, `QWCY604`); no letter of any code is read as a role by the code under test.

## Sets

- AC-1 (several close sets). Sets QWC604-P-RL, QWC604-S-RL, QWC604-P-RL-NEW, QWC604-S-RL-NEW (each: its own pan
  member + the shared cistern QWCY604), product QWC609-RL discontinued. `qwc604-rl x 2` (dealer and staff): the offer is
  3 SETS and nothing else (no member code, never QWC609-RL), QWC604-P-RL and QWC604-S-RL are both among them, every
  offered set holds every typed part; nothing answered; quantity 2 carried. Picking an offered set answers it exactly
  as typing that set's code at x2.
  Rule: when more than one close set holds every typed part, those sets are offered (up to 3, the resolver's order);
  their members are not. When exactly one does, today's "set, then its members" stays (AC-1b).
- AC-1b (one close set, regression lock). Sets QWC605-S-200-RL (+ members); `qwc605-s-rl x 1` offers QWC605-S-200-RL
  first, then its members (unchanged from main).
- AC-2 (space-typed exact set). `qwc604 p rl stock` and `QWC604 P RL x 2` answer the set QWC604-P-RL (its members'
  stock: QWCX604-P-RL and QWCY604), dealer and staff; never QWCX604-P-RL-NEW; no did-you-mean; dealer never gets the
  refer line for it. Same when it is one code of a multi-code ask beside a found product code.
- AC-3 (exact set answers only itself). Sets QWC605-RL, QWC605-RL-SOFT, QWC605-RL-NEW, QWC605-RL-WEPLS.
  `QWC605RL x 1` and `qwc605-rl stock`: staff reply holds exactly one set block (QWC605-RL) and none of the 3 siblings'
  codes; dealer reply is the QWC605-RL answer at x1 (no "How many units for each?", none of the siblings' codes).
- AC-2b..AC-2i (review rounds and owner ruling 13 Nov ~17:40, "CWC605-RL soft" IS CWC605-RL-SOFT): a set code typed
  with spaces whose last part is a word is the set (2b); a code plus the words after it ON ITS OWN LINE that fold
  (case, dashes, spaces) to a real code is that code, direct answer (2c set, 2d product); a word completing no code
  changes nothing (2e); a set whose words complete nothing stays the set (2f); another line never narrows or completes
  a code (2g, 2h); a family word plus a class word is not answered as its sets with the word ignored (2i). Tests:
  `tests/chatbot/test_set_codes.py`. Dealer set + typed quantity ("How many units for each?") is slice 2 (strict xfail).
- AC-4 (fold, Q5). `qwc604/p/rl stock` is never answered directly as QWC604-P-RL.

## Family from catalogue links only (Q2)

- AC-5. The X insert is gone: `product_code_family._family_rows` builds no pattern from the code's letters plus a fixed
  extra letter (source scan, a kill guard).
- AC-6. The 20 tests that relied on it (`test_attribute_asks_round7.py` 8, `test_narrow_code_own_line.py` 8,
  `test_code_match_family.py` AC-24a/24d control pairs 4) keep every assertion; only their seed gains the catalogue link
  (a registered set of the family holding the X-coded variant, or a hand-set Family code) and they pass.
- AC-7. A family whose X-coded variant has neither link: that variant is never in the reply to "code + words".

## Trace (Q4, internal)

- AC-8. A turn that answers a set writes one `code_candidates` entry: `typed`, the set code, its member codes in
  membership order, `outcome: answered`. Codes only, no row ids.
- AC-9. A turn that offers sets writes the offered codes in offered order with `outcome: offered` (the existing miss
  event; existing assertions stay green).

## Unchanged

- AC-10. Every test in `tests/chatbot/test_code_match_*.py` stays green (AC-6 re-seeds aside); an exact product code's
  reply is unchanged.
