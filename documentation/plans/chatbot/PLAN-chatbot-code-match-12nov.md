# PLAN: CHATBOT-CODE-MATCH (stock code matching, close-code offers)

Status: Build complete for slices 1-5 code (each reviewed READY); waiting on crew for the letters-only ruling, data counts, live-run cap and the slice 1 traces. Card v3 approved by crew 12 Nov with 8 changes, folded in below. Track: size M, lead pattern, cloud lane. Phase 1 of the
chatbot plan v2 (D3, owner 12 Nov 16:08 "ok"): lookup only, no parser prompt change, no migration.

Card: `CARD-chatbot-code-match-12nov.md` (v3, generic rules R0-R7). UAC: `chatbot-code-match-acceptance-criteria.md`.

Goal: fewer stock "Couldn't find" replies with no wrong answers (9.9% of stock asks on the 2 Nov week -> 8% or less,
estimate); second line: dead-end replies (no code offered).

Owner approved chatbot plan v2 (12 Nov 17:28): paid LLM runs (LIVE x3 etc.) use the owner's personal API key that
the crew test copies use, never the production key; every paid run is asked of crew first with its cap. Daily loop:
each slice that lands gives the 10:00 test card (3-5 Console questions, before/after).

Crew triage (12 Nov, evening): Phase 1 cap is US$0 (plan v2 section 7; US$1 only if the replay cannot re-run the
lookup, and it can: the resolver runs in process). The frozen set is replayed at US$0 on crew's dev copy first. Any live
x1 / x3 run and the letters-only digit rule (AC-19, recommendation b) are owner decisions. The slice 1 console pass is
run by crew (cap US$0.50 inside the US$1 code-match fallback). The X insert stays as fallback until a data-driven
replacement passes the owner #833 tests.

Owner answers (13 Nov ~00:13): Q1 = (b) letters-only word that looks like a mistyped code is OFFERED, never
answered; the digit rule stays for ordinary words. Q2 = (b) ONE live pass, hard cap US$1, frozen set + owner-FAIL set,
run by crew locally after the Q1 head; x3 only with a new owner OK. Q3 (inactive codes offered) still open: AC-20 kept.

Replay on 3dc5b84de3 (13 Nov): B-118 (M2155-NL-BLUE), B-52 (SRTKS8047), B-61 (SRTBF31514) lose their right close code
from the did-you-mean. Crew data: all three are active but DISCONTINUED, so owner Q3 removes them as ruled; crew does
not count them as code bugs. B-52 now offers the non-discontinued SRTKS8047-NEW; B-61's -NEW is discontinued too, so it
offers nothing. Pending owner follow-up: a MISTYPED discontinued code, strict Q3 (as now) vs offering its active
alternative. Red tests AC-20j (replacement) are written and HELD red until that answer; the live pass is held too.

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
The "X" insert moved to slice 5 (crew ruling 12 Nov, see there).
Console questions:
1. "CWC604RL x 2" - before: refer line / unrelated list; after: offer CWC604-P-RL (set) then its members.
2. "CWC604PRL stock" - after: the set answered (members' stock, complete sets).
3. Reply "1" to question 1 - the set answered at x2, as an exact set ask.
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

### Slice 5: X insert replaced from catalogue data, frozen set, before/after
X insert (crew ruling 12 Nov): do NOT remove it while it breaks owner-tested behaviour (27 Sep #833 and the 16 tests in
`test_attribute_asks_round7.py` and `test_narrow_code_own_line.py` stay green, always). REPLACE it: derive the same
family link from catalogue data (set membership, a variant group or a family field) so those 16 tests pass with the
letter rule gone. If the catalogue lacks that link for these codes, keep the X insert, list it in the generic audit
as "kept until the catalogue carries the link", and name the data that would remove it.
Discovery (12 Nov): the catalogue already has two family fields. `products.family_code` is derived as the text
before the first dash, so SRTWC7604-SC gives SRTWC7604 but SRTWCX7604-P gives SRTWCX7604 (`app/services/product_family.py:21`).
It can also be set by hand: `family_code_manual`, `product_service.set_family_code` at :1074. `products.variant_of_id`
is the longest boundary-prefix parent. Neither field links an X sibling to its base on its own. The data that would
remove the X insert: a hand-set `family_code` equal to the base family on each X-coded product, or a registered set
holding both. Slice 5 plan: read the family by `family_code` (derived or hand-set) plus set membership; keep the X
insert only for families where neither link exists, and report that count.
Crew data (12 Nov prod clone, read-only): 111 active X-sibling products in 29 families. 57 are linked to their base
by a registered set holding both, so the data read covers them. 0 have a hand-set family_code (0 of 15,167 active
products). 54 have neither link: for these the X insert is still the only link. Generic audit: the X insert is KEPT
until the catalogue carries the link for those 54. The data that removes it: set Family code on each, or register a set
holding both codes. The list: `sorento_crm_backend/scripts/chatbot_x_siblings_without_link.sql` (read-only).

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
