# UAC: CHATBOT-SET-CODES (draft; final once the owner answers card Q1-Q5)

Card: `CARD-chatbot-set-codes-13nov.md`. Plan: `PLAN-chatbot-set-codes-13nov.md`. Written assuming each question's
recommendation; any other answer rewrites the affected AC before tests are written.

Harness: `engine.run_turn` over seeded Postgres rows (`tests/chatbot/test_code_match_dealer_offers.py` Console), sets
in `product_sets` / `product_set_members`. Seeded codes are synthetic (ZZT / TWC shapes), never real data. No code's
letters are read as a role in any assertion's setup: member codes do not share the set code as a prefix.

## Sets (S1, S2)

- AC-1 (S2, the plan's case). Set `TWC604-P-RL` with two members; a product `TWC609-RL` also exists. A dealer types
  `twc604-rl x 2`: the offer lists the set first, then its members, and `TWC609-RL` is not before them; nothing is
  answered; the quantity 2 is carried. Same list for staff.
- AC-2 (S1). `TWC604PRL stock`, `twc604-p-rl stock` and `twc 604 p rl stock` each answer the set (members' stock and
  the complete-sets figure), staff and dealer, with no did-you-mean.
- AC-3 (S1, multi-code). `<found code> x 1, twc604prl x 2` answers both; the set's part of the reply equals the reply to
  `twc604prl x 2` asked alone.
- AC-4 (Q5). `twc604/p/rl` is not an exact set answer (offered or not found, never answered directly).

## Family from catalogue links (S3, Q2)

- AC-5. With the X insert gone, a family whose X-coded variant is a member of a registered set of that family still
  narrows "code + words" to that variant (the #833 owner shapes: `Srtwc7604 p trap price`), staff and dealer.
- AC-6. A family whose X-coded variant has a hand-set Family code equal to the base family still narrows to it.
- AC-7. A family whose X-coded variant has neither link: the variant is never in the reply (not answered, not listed);
  the reply is the base family's, as for any family with no link.
- AC-8 (kill guard). No string in `product_code_family.py` builds a pattern from the code's letters plus a fixed
  letter (source scan).

## Trace (S4, Q4)

- AC-9. A turn that answers a set writes one `code_candidates` entry: `typed`, the set code, member codes in membership
  order, `outcome: answered`. Codes only, no row ids.
- AC-10. A turn that offers a set writes the set and its members in offered order with `outcome: offered` (extends the
  existing miss event; the existing miss assertions stay green).

## Unchanged

- AC-11. An exact product code's reply is byte-identical to main. Every test in `test_code_match_*.py`,
  `test_attribute_asks_round7.py` and `test_narrow_code_own_line.py` stays green (re-seeded with a catalogue link where
  it relied on the X insert, Q2 a).
