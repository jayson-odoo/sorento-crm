# CARD: CHATBOT-SET-CODES behaviour card v1 (plan v2 Phase 1 slice 3)

Lane CHATBOT-SET-CODES, PR #2395. Builds on PR #2370 (CHATBOT-CODE-MATCH, merged 13 Nov, not yet deployed). Codes
are catalogue codes (business data); no customer, person, phone or price appears. Tool/resolver layer only: no prompt
change, no migration.

## What main already does after #2370 (file:line on 0f80d519) and what this lane does with it

| Piece | Where | This lane |
| --- | --- | --- |
| Exact set: typed code equal to a set code with case, dashes, spaces ignored, answered with members, stock, complete sets | `app/services/entity_resolver.py:886` `_probe_product_set`, `:931` `_product_set_entities`, fold `:741` `_strip_all_ws` | reuse as is (inactive or hidden sets already refused in chat: `lanes/business/gate.py:447` via `visible_set_ids`) |
| Close set (prefix, substring, trigram): offered first, then its members in membership order, up to 3 | `entity_resolver.py:2136` `_prefix_probe_product_set`, `:3297` `_trgm_product_sets`; `lanes/business/answer.py:5023` `_set_then_its_members` | reuse as is |
| All-typed-parts ranking (CWC604-P-RL holds cwc/604/rl, CWC609-RL does not) | `answer.py:5134` `holds_every_typed_part` | reuse as is |
| Family read for "code + words" asks ("Srtwc7604 p trap price") | `app/services/product_code_family.py:71` `_family_rows`; X insert at `:88` | X insert REMOVED; family = `family_code` (derived or hand-set) + members of a registered set of that family (already read at `:91-96`) |
| Trace on a miss | `app/services/chatbot/trace.py:479` `code_candidates_events`, written at `engine.py:9574` | extended: a set answered or offered also writes its candidate list |

## Rules

S1. A registered set typed with case, dashes or spaces different (CWC604PRL, cwc604-p-rl, "cwc 604 p rl") is answered
as the set: its members from the membership table in the table's order, each member's stock, and the complete-sets
figure. Same for staff and dealers, one code or several in a message (each code through the same function).

S2. A typed code that is close to a set but not equal (a part missing or extra, CWC604-RL vs CWC604-P-RL) is OFFERED:
the set first, then its members, up to 3, numbered; nothing is answered. Picking the set answers it as S1.

S3. A part's role is never read from a letter in the code. The family of a code (the products a "code + words" ask
narrows among) is what the catalogue links: the product's Family code (derived or set by hand) and the members of a
registered set of that family. The rule that inserts an "X" after the code's letters is removed. A variant the
catalogue does not link is no longer in the family; it is still found by the generic close-code offer (offered, not
answered).

S4. Trace: every turn that answers or offers a set writes one `code_candidates` entry: the typed code, the set, its
member codes in membership order, the other candidates in offered order, and `answered` or `offered`.

## Examples (shapes from the 12 Nov review; data request on #2395 confirms them on dev data)

| # | Contact | Typed | Catalogue | Prod today (before #2370) | Expected after this lane |
| --- | --- | --- | --- | --- | --- |
| 1 | dealer | `cwc604-rl x 2` | registered set CWC604-P-RL; product CWC609-RL | "Did you mean CWC609-RL?" | "Couldn't find CWC604-RL. Did you mean:" 1. CWC604-P-RL (the set), 2-3. its members; quantity 2 kept |
| 2 | staff | `CWC604PRL stock` | same set | set answered | set answered (members' stock, complete sets), unchanged |
| 3 | staff | `Srtwc7604 p trap price` | SRTWC7604-SC, SRTWCX7604-P, a registered set holding both | narrowed to SRTWCX7604-P by the X rule | narrowed to SRTWCX7604-P through the set link (same answer) |
| 4 | staff | `Srtwc7604 p trap price` | same, but NO set and no Family code links SRTWCX7604-P | narrowed to SRTWCX7604-P by the X rule | the family is SRTWC7604-* only; SRTWCX7604-P is offered by the close-code offer, never answered |
| 5 | dealer | `cwc604prl` | set with one member the dealer may not see | n/a | not answered and not offered (existing `visible_set_clauses`, `entity_resolver.py:3276`) |

Edge cases: an inactive set, or one with no members, is neither answered nor offered (existing `visible_set_clauses`); a discontinued member is listed in the set
answer but never offered on its own (owner Q4, 13 Nov); multi-code: each code answered/offered as if asked alone.

## Questions (each with a recommendation)

Q1. Part role. The brief says "a part's role is a field on the membership row"; `product_set_members` has no role
column, deliberately (`app/models/product_set.py:14`: the description already says "CISTERN ONLY"). (a) no new column:
members show their own description, the role is never read from a code letter; (b) add a role column (migration,
lane becomes size L). Recommendation: (a), nothing reads a role today and a column would restate the description.

Q2. The X insert goes now. Crew data (12 Nov): 54 active X-coded products in 29 families have neither a set nor a
Family code link, so example 4 changes for them (narrowed answer becomes an offer). (a) remove now; the 54 are listed
for data fill (set Family code or register a set), and the #833 owner tests are re-seeded with a set link so their
answers stay; (b) keep the X insert as a fallback until those 54 are linked. Recommendation: (a), the brief's rule
("family = products the catalogue links") and an offer is never a wrong answer.

Q3. "Make card v3 R1 generic". Card v3's R1 is dealer close-code offers, owned by lane CHATBOT-CLOSE-CODES. (a) read
it as "the family/set rule is generic" (S3 here); (b) it means dealer offers, out of this lane. Recommendation: (a).

Q4. Trace scope. `code_candidates` is written today only for a missed code (`engine.py:9574`). (a) also write it
when a set is ANSWERED (typed code, set, member codes) so a replay can tell a set answer from a product answer; (b)
misses and offers only. Recommendation: (a), the scoreboard can then count set answers without reading reply text.

Q5. Fold for "equal". (a) case, dashes and spaces only (owner 12 Nov 15:10, `_strip_all_ws`); (b) also `/ . _`.
Recommendation: (a), the owner's rule names dashes and spaces.
