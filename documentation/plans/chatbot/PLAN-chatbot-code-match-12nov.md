# PLAN: CHATBOT-CODE-MATCH (stock code matching, close-code offers)

Status: Build, slice 1 (unparked 12 Nov; card v3 filed). Track: size M, lead pattern, cloud lane. Phase 1 of the
chatbot plan v2 (D3, owner 12 Nov 16:08 "ok"): lookup only, no parser prompt change, no migration.

Card: `CARD-chatbot-code-match-12nov.md` (v3, generic rules R0-R7). UAC: `chatbot-code-match-acceptance-criteria.md`.

Goal: fewer stock "Couldn't find" replies with no wrong answers (9.9% of stock asks on the 2 Nov week -> 8% or less,
estimate); second line: dead-end replies (no code offered).

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
Console: "8354-SH-UF" ranks SRTWC8354-SH-UF first; a short "8152" keeps the which-one pick, all-parts first; a
two-code ask ranks each code the same way.

### Slice 3: sets through the membership table (R3)
Change: a token close to a registered set offers the set then its members (`product_set_members`); an exact set on a
stock ask answers the set.
Console: "CWC604RL x 2" offers CWC604-P-RL and its members; "CWC604PRL stock" answers the set.

### Slice 4: size from stored values (R4)
Change: a number in the typed code is read against the category's size key (Q2, registry), stored values only; offers
show "Size: N mm" / "Size: not recorded". Data list (read-only SQL) of active products in sized categories with no
stored size (the review's 419 of 979 water closets).
Console: "8152-300-SH"; "SRTWC8152-SH-UF-250"; a size no member holds.

### Slice 5: frozen set + before/after
Frozen set (owner-FAIL code lookups, the 23 defect turns, 34 recovered typos, multi-turn follow-ups): $0 replay first,
LIVE x3 after crew's cap ask; before/after "couldn't find" and dead-end rates; hand-test script.

## Not in this lane
Parser prompt or publish (lane 4); engine stale-typo / focus-carry path; scoreboard queries (CHATBOT-SCOREBOARD #2369);
stage timing, `chatbot_lookup_edits.py`, `head/lookup_lists.py` (CHATBOT-SPEED #2368); the existing "X" family insert
(Q4).
