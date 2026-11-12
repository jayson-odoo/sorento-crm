# PLAN: CHATBOT-CODE-MATCH (stock code matching, close-code offers)

Status: Build, slice 1 (card v3 approved by crew 12 Nov with 8 changes, folded in below). Track: size M, lead pattern, cloud lane. Phase 1 of the
chatbot plan v2 (D3, owner 12 Nov 16:08 "ok"): lookup only, no parser prompt change, no migration.

Card: `CARD-chatbot-code-match-12nov.md` (v3, generic rules R0-R7). UAC: `chatbot-code-match-acceptance-criteria.md`.

Goal: fewer stock "Couldn't find" replies with no wrong answers (9.9% of stock asks on the 2 Nov week -> 8% or less,
estimate); second line: dead-end replies (no code offered).

Owner approved chatbot plan v2 (12 Nov 17:28): paid LLM runs (LIVE x3 etc.) use the owner's personal API key that
the crew test copies use, never the production key; every paid run is asked of crew first with its cap. Daily loop:
each slice that lands gives the 10:00 test card (3-5 Console questions, before/after).

Owner rule (12 Nov): no rule so customised it cannot be replicated for another company in a different industry.

## Slices (one a day; each one PR commit series on this branch, each with red-first + kill proof)

Each slice gives the owner 3-5 changed questions he can try in the Chatbot Console on the test copy (dry run, no
WhatsApp send), before -> after. Codes are catalogue codes from the review.

### Slice 1: dealer close-code offers + trace (R1, R6, R7; AC-10..AC-17)
Change: `engine._exact_codes_only` keeps a miss's did-you-mean candidates for an availability-only contact; the answer
bridge's existing dealer pick (`dealer_stock.did_you_mean`) prints them. `code_candidates` trace entry on every miss.
Console questions (dealer contact):
1. "Swtwc8354-SH-UF x 3" - before: "Please refer to your salesman." after: "Couldn't find SWTWC8354-SH-UF. Did you mean SRTWC8354-SH-UF?"
2. "C21120UW-2-MY stock" - before: refer line; after: "Did you mean BRC21120UW-2-MY?"
3. reply "yes" to 1 - after: stock of SRTWC8354-SH-UF for 3 units.
4. "ZZZ999 stock" (no close code) - unchanged.
5. An exact code - unchanged.

### Slice 2: all-typed-parts ranking (R2)
Change: one ranking step over the candidate list `did_you_mean_by_token` reads; same for staff and dealers.
Console questions (staff and dealer):
1. "8354-SH-UF stock" - before: trigram order; after: SRTWC8354-SH-UF first (every typed part held).
2. "8152 stock" - before/after: which-one pick; after: all-parts codes first.
3. "BT015SSCR stock" (dash only) - answered directly before and after (guard).
4. "SRTWC8354-SH-UF x 2, Swtwc8152 x 1" - each code ranked the same way as alone.

### Slice 3: sets through the membership table (R3)
Change: a token close to a registered set offers the set then its members (`product_set_members`); an exact set on a
stock ask answers the set.
Also: the "X" insert in the family rule (`product_code_family.py:88`) is removed (plan v2 section 3b, D3); the
set rule replaces it; the frozen set (slice 5) must show no regression.
Console questions:
1. "CWC604RL x 2" - before: refer line / unrelated list; after: offer CWC604-P-RL (set) then its members.
2. "CWC604PRL stock" - after: the set answered (members' stock, complete sets).
3. "Srtwc7604 p trap price" (was found by the X insert) - same answer as before, now through the set/member rule.
4. A dealer asking a set whose members they may not see - not offered.

### Slice 4: size from stored values (R4)
Change: a number in the typed code is read against the category's size key (Q2, registry), stored values only; offers
show "Size: N mm" / "Size: not recorded". Data list (read-only SQL) of active products in sized categories with no
stored size (the review's 419 of 979 water closets).
Also: "None with size 300 mm." (`lanes/business/answer.py:2872`) takes its unit from the registry key.
Console questions:
1. "8152-300-SH stock" - before: "Couldn't find"; after: "Did you mean SRTWC8152-SH-300?" with "Size: 300 mm".
2. "SRTWC8152-SH-UF-250 stock" - after: close codes with stored sizes or "Size: not recorded"; never answered as 250.
3. "SRTWC8152-SH-UF-400" (no member holds 400) - after: "Couldn't find" plus close codes with stored sizes.
4. A category with two length keys holding the typed number - every matching key offered, none guessed.

### Slice 5: frozen set + before/after
Gate: the frozen set = the 23 sampled defect turns + the 34 recovered typos + every past owner-FAIL code-lookup /
stock "not found" turn + multi-turn follow-ups (refine, answer the bot's question, topic switch). Pass = 0 wrong codes
answered directly, and no regression on turns that pass on main. Order: US$0 replay of recorded turns first; then LIVE
x3 under a crew-approved cap (`crew-ask: live run: <turns> x <runs>, cap US$X`), x1 before any set, stop at a degrading
checkpoint; every paid run ledgered in a PR comment. After 3 failed rounds stop and re-scope with the owner.
Before/after "couldn't find" and dead-end rates; hand-test script.
Console questions: 3-5 turns picked from the frozen set, before -> after.

## crew-done criteria
Red-first + kill proof per slice; `crew-tests:` on the exact head; browser pass note; frozen set LIVE x3 pass;
"generic: N checked, 0 open" (no company-specific letter, marker, size or code shape in new code); "standing rules: N
checked, 0 open"; reused functions listed with file:line; guide line.

## Not in this lane
Parser prompt or publish (lane 4); engine stale-typo / focus-carry path; scoreboard queries (CHATBOT-SCOREBOARD #2369);
stage timing, `chatbot_lookup_edits.py`, `head/lookup_lists.py` (CHATBOT-SPEED #2368).
