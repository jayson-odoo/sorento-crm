# CARD: CHATBOT-CLOSE-CODES behaviour card v1 (dealer gets up to 3 close codes)

Lane CHATBOT-CLOSE-CODES, plan `PLAN-chatbot-close-codes-13nov.md`. Chatbot plan v2 Phase 1 slice 2. Codes below are
catalogue codes (business data); no customer, person, phone or price appears.

## Starting point: what PR #2370 already ships (main 0f80d519)

On a dealer stock ask, a mistyped code (one wrong or extra letter, a digit code missing its prefix, a set typo) already
gets "Couldn't find X. Did you mean Y?" or a numbered list of up to 3 codes from the dealer's own company, with the
typed quantity carried. The ranking holds every typed part first, and the trace writes `code_candidates`.
Tests: `tests/chatbot/test_code_match_dealer_offers.py` (AC-10..AC-17), AC-19 (letters-only single code), AC-27b
(missing prefix), AC-9 (short token).

So this lane closes the paths that still end in "Please refer to your salesman." or a bare "Couldn't find: X." while a
close code exists. Discovery (static read on main, each one gets a red test before any fix):

| Gap | Today (dealer) | Where |
| --- | --- | --- |
| G1 letters-only miss in a multi-code ask | dropped without a word: no "Couldn't find", no offer, no trace | `app/services/chatbot/engine.py:1066-1067`, `:1087` (`_exact_codes_only`) |
| G2 miss beside a found code whose reply asks a question ("How many units?", a which-one list) | bare "Couldn't find: X." | `engine.py:10077` (offer skipped when the reply already asks) |
| G3 letters-only code that is a lone prefix of a code, or sits inside one | refer line, no offer | `engine.py:1066`, `lanes/business/miss_suggest.py:150-170`, `app/api/v1/system/references.py:1792`, `lanes/business/code_sizes.py:296` |
| G4 dealer incoming/ETA ask with a typo | "Did you mean Y?" then "Please refer to your salesman." and nothing stored, so "yes" answers nothing | `answer_bridge.py:1410-1418`, `dealer_stock.py:28-75`; dealer pick only for stock asks `answer_bridge.py:2205` |
| G5 (inferred, needs data) digit typo the embedding tier takes as a match | "Couldn't find. Please refer to your salesman." | `entity_resolver.py:5945-5965`, `:6015-6018`, `miss_suggest.py:166-171` |
| G6 ranking sees only the resolver's first 5 trigram rows | an all-parts code ranked 6th or lower is never offered | `entity_resolver.py:3258`, `:6080`; ranking `answer.py:4999-5021` |
| G7 trace | no all-parts flag; a miss with no candidate reads `answered` | `app/services/chatbot/trace.py:479-547` |

## Rules (plain words)

C1. Every code a dealer types that is not found gets the same treatment, alone or among other codes: "Couldn't find X."
then up to 3 close codes from the dealer's own company as "Did you mean ...?", quantity carried. Letters-only codes
included (owner Q1 (b), 13 Nov). Nothing is dropped silently. (G1, G3)

C2. Direct answer ONLY when the typed code equals one catalogue code with case, dashes and spaces ignored, or is a
registered set. Everything else is offered and asked. (Owner 12 Nov 15:10, minus "default size": see Q1.)

C3. A miss beside a found code whose reply already asks a question still gets its offer (see Q3 for the shape).

C4. On an incoming/ETA ask a dealer's offer is a real pick ("yes" / a number answers it), and the refer line is
added only when there is no close code. (G4)

C5. Ranking: the top 3 are chosen from the resolver's full close-code list (up to 15 rows), codes holding every typed
part first, then similarity. One shared ranking for staff and dealers, single and multi-code. (G6)

C6. A short token with more than 3 all-parts matches keeps today's which-one list (AC-9, PICKER-NO-CAP), unchanged.

C7. Trace: each missed code writes `code_candidates` with the offered codes in order, tier, similarity, all-parts flag,
and `offered` or `no_candidate`. (G7)

No keyword, phrase or code-shape rule on what the customer wrote; all matching reads catalogue codes, set membership
and the dealer's company scope. Prompt pinned (no change). Span step and stale-typo / focus-carry path untouched.

## Example shapes (codes from the 12 Nov review; crew's masked rows replace these if they differ)

| # | Contact | Typed | Today | After |
| --- | --- | --- | --- | --- |
| 1 | dealer | `SRTWC8354-SH-UF x 2, SRTWCSHUF x 1` (2nd code letters-only) | stock of the first; the second vanishes | stock of the first; "Couldn't find SRTWCSHUF. Did you mean SRTWC8354-SH-UF?" (or a list of up to 3) |
| 2 | dealer | `SRTWC8354-SH-UF stock, SWTWC8152 stock` (first needs "how many") | "How many units of SRTWC8354-SH-UF?" + "Couldn't find: SWTWC8152." | per Q3 |
| 3 | dealer | `SWTWC8354-SH-UF bila sampai?` (ETA, one wrong letter) | "Did you mean SRTWC8354-SH-UF?" + "Please refer to your salesman."; "yes" answers nothing | "Couldn't find SWTWC8354-SH-UF. Did you mean SRTWC8354-SH-UF?"; "yes" gives its incoming |
| 4 | dealer | `BRC21120UW stock` (letters+digits, missing nothing) | answered (exact) | unchanged |
| 5 | dealer | `ZZZ999 stock` (no close code) | refer line | unchanged |

## Edge cases

- A close code in another company is never offered to a dealer, on every tier (today only the trigram tier and the
  replacement case are tested for this; this lane adds a test per tier).
- Inactive, discontinued or placeholder codes are never offered (owner Q3/Q4 of #2370).
- "no" to an offer: the refer line naming the code (today's AC-15d shape).
- An exact code's reply is byte-identical to main.
- A greeting, a typo and a Malay phrasing are each tested (standing rule, AI/chatbot line 1).

## Questions (owner answers once)

Q1. The 12 Nov 15:10 direct-answer rule lists "the default size", but the newer 12 Nov ~16:05 ruling says no default
size, and the code stores none. (a) drop it: direct answer only for dashes/spaces or a registered set; (b) keep a
default size per category in settings. Recommendation: (a), newest ruling wins and nothing stores a default.

Q2. A typed code that is a lone PREFIX of exactly one catalogue code (`SRTWC287-S` -> only SRTWC287-S-150) is answered
directly today (test S08, `code_sizes.py:331-333`). (a) offer it ("Did you mean SRTWC287-S-150?"), per the direct-answer
rule; (b) keep answering it directly. Recommendation: (a), the rule says only dashes/spaces or a set are answered, and
0 wrong codes answered directly is the finish line; it costs one "yes" when the guess was right.

Q3. A miss beside a code whose reply already asks (example 2). (a) one reply, one numbered list: the open question's
options first, then "Couldn't find X. Did you mean:" numbered on (the multi-miss shape AC-15d already uses);
(b) keep one question per reply and show only "Couldn't find X." for the miss (today). Recommendation: (a), the dead-end
count is the finish line and the numbered-on shape is already owner-tested.

Q4. Incoming/ETA asks (G4): (a) dealers get the same pick as on stock asks, no refer line when a close code is offered;
(b) leave ETA asks as today (stock only). Recommendation: (a), same function for every dealer lookup.

Q5. Ranking pool (G6): (a) rank all the resolver's close-code rows (up to 15) and offer the top 3; (b) keep the first 5.
Recommendation: (a), an all-parts code beyond row 5 is the review's "right code never offered" shape; cost is one
in-memory sort.

## Data request (crew masks)

`chatbot_turn_traces` (or the turn-trace table) for the last 14 days, availability-only (dealer) contacts, stock or
incoming asks whose reply contains "refer to your salesman" or "Couldn't find": the typed token, the resolve tier per
token (to size G5: tier `embedding`), the `code_candidates` entry, and the reply. Plus counts per gap shape G1-G5.
Why: to replace the example shapes with real ones and to confirm G5 exists before building for it.
