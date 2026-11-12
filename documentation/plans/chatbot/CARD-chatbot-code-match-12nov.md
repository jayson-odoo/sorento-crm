# CARD: CHATBOT-CODE-MATCH behaviour card v3 (generic rules, Phase 1 of the chatbot plan)

Lane CHATBOT-CODE-MATCH, plan `PLAN-chatbot-code-match-12nov.md` (holds the 5-slice plan). Chatbot plan v2, D3 (owner
12 Nov 16:08 "ok"): code matching is Phase 1, lookup only, no prompt change. Codes below are catalogue codes (business
data); no customer, person, phone or price appears.

Binding owner rule (12 Nov, verbatim): "when we fix things along the way we shouldn't make the rule too customized and
cannot be repclicated for another company in differtn industry". So every rule below reads only generic data: codes,
the set membership table, the spec registry and stored spec values. No company's code letters, size markers or default
sizes appear in code. v3 replaces v2: the X = pan / Y = cistern letters, the trap_length / S6-S12 / -250 markers and
the letters-then-digits code shape are gone.

## What exists today (file:line on main 7ede7cfa) and what each slice does with it

| Piece | Where | Use |
| --- | --- | --- |
| Code probe: prefix, else substring, on the code with spaces folded | `app/services/entity_resolver.py:2087` `_code_prefix_then_substring`, `:2110`, `:2136` | reuse; ranking extended (slice 2) |
| Trigram did-you-mean (0.25 floor, 15 rows, prefix-extensions first) | `entity_resolver.py:3225`, `:3317` `_trgm_lookup`, `:3289` `_trgm_product_sets` | reuse as is |
| Per-token did-you-mean, first 3 | `lanes/business/answer.py:4973` `did_you_mean_by_token` | reuse as is: ONE function for staff, dealer, single and multi-code |
| Dealer did-you-mean pick (carries quantity, no escalation) | `chatbot/dealer_stock.py:77` `did_you_mean`; `answer_bridge.py:2190`, `:2287` | reuse; feed it the candidates it never gets (slice 1) |
| Dealer exact-codes-only filter | `chatbot/engine.py:975` `_exact_codes_only`, called `:7745` | extend: a miss keeps its candidates (slice 1) |
| Set entity with members, stock, complete-sets figure | `entity_resolver.py:931` `_product_set_entities`; members in `product_set_members` (`app/models/product_set.py:88`) | reuse (slice 3) |
| Size keys by data: every numeric key in the registry's length unit, `matches_bare_size`, a key a class scopes (`applies_when.class`) | `chatbot/head/bare_size.py:1-11`, `:125-134`; `app/models/product_spec.py:32-80` | reuse as the category's size setting (slice 4, Q2) |
| Units and unit aliases | `product_spec_registry.unit`, `unit_aliases` (`product_spec.py:52`, `:80`) | reuse (slice 4) |
| Family by code word | `app/services/product_code_family.py:47` `_CODE_WORD` (letters then digits), `:71` `_family_rows` (inserts an "X") | NOT extended: Sorento-shaped; new matching goes through the generic probe (slice 5 retires the X insert only if the owner asks, Q4) |
| Turn trace | `turn_trace.add(...)` (e.g. `engine.py:7759`) | one `code_candidates` entry (slice 1) |

## Rules

R0. Answer a code directly ONLY when the typed code equals one catalogue code with case, dashes and spaces ignored, or
is a registered product set (same fold). Every other near match is OFFERED (up to 3, numbered) and the bot asks.
Nothing is answered on a guess, and no size is ever assumed.

R1. Dealers get offers. When a dealer's (availability-only contact) exact code fails, they get up to 3 close codes from
their own company as a numbered pick carrying the typed quantity, instead of "Please refer to your salesman." No close
code: today's reply, unchanged.

R2. Ranking. A candidate holding every typed part (the typed code split at its letter/digit boundaries and separators,
each part found in the candidate's code in order) ranks before one that misses a part; then today's order. A token
with more than 3 such candidates keeps today's which-one picker, all-parts first.

R3. Sets through the membership table. A typed code close to a registered set code (R2 match, not an R0 equal) offers
the set and its member products (from `product_set_members`), up to 3. A set typed exactly (R0) on a stock ask answers
the set: members' stock and the complete-sets figure (the existing set reply). No code letter is read as a part role.

R4. Size only from stored values. A number in the typed code counts as a size ONLY when it equals a value stored on a
candidate under the category's size key (Q2), in that key's registry unit. Such a candidate ranks first and is OFFERED
with its stored size ("Size: 300 mm"); a candidate with no stored value shows "Size: not recorded". A typed size no
candidate holds: "Couldn't find X" and the close codes with their stored sizes. Never "None with size 300 mm." alone.

R5. Any code shape. A typed token that is a prefix or substring of a catalogue code is a code, whatever its shape
(letters only, digits first, dashes); the letters-then-digits assumption is not used by any new rule.

R6. Trace. Every miss writes `code_candidates`: typed token, candidate codes in offered order, tier, similarity, all-parts
flag, stored size when read, and `answered` or `offered`.

R7. Multi-code: each code runs the same function as a single-code ask, once per code.

## Examples (shapes from the 12 Nov review)

| Typed (stock ask) | Catalogue holds | Reply |
| --- | --- | --- |
| `Swtwc8354-SH-UF x 3` (dealer) | SRTWC8354-SH-UF in the dealer's company (trigram 0.67) | Today "Please refer to your salesman."; new: "Couldn't find SWTWC8354-SH-UF. Did you mean SRTWC8354-SH-UF?", quantity 3 carried |
| `C21120UW-2-MY` | BRC21120UW-2-MY (substring, all parts held) | "Did you mean BRC21120UW-2-MY?" (offer, not answer) |
| `CWC604RL x 2` | registered set CWC604-P-RL; its members | Offer 1. CWC604-P-RL (set) then its members from the membership table, up to 3; quantity carried |
| `8152-300-SH` | SRTWC8152-SH-300 with 300 stored under the size key | "Did you mean SRTWC8152-SH-300?" with "Size: 300 mm" |
| `SRTWC8152-SH-UF-250` | SRTWC8152-SH-UF (nothing stored), siblings with stored sizes | "Couldn't find SRTWC8152-SH-UF-250." then the close codes, each with its stored size or "Size: not recorded"; never answered as 250 |
| `srtwc 8354 sh uf` | SRTWC8354-SH-UF | Equal with spaces folded: answered directly |

Edge cases: a close code in another company is never offered to a dealer; a set whose members the dealer may not see is
not offered (`visible_set_clauses`); an inactive or placeholder code is never offered (`_chat_visible_product_ids`);
"no" to an offer = "Couldn't find X." (staff) or the refer line (dealer); an exact code's reply is byte-identical to
main.

## Questions (each with a recommendation)

Q1. `8152-300-SH` (every part matched, one candidate, stored size equals the typed number). (a) one-option "Did you
mean" offer; (b) answer directly. Recommendation: (a): only an R0 equal or a set is answered directly.

Q2. The category's size setting. (a) reuse the spec registry: the size key of a category is the registry key scoped to
its class (`applies_when.class`), else the keys flagged `matches_bare_size`, the rule `bare_size.py` already uses; set
on the existing Spec Registry screen, no migration; (b) a new `size_spec_key` column on product categories (migration,
new setting). Recommendation: (a): the setting exists and is already per-category and per-industry.

Q3. Dealer close code only in another company sharing the trading name. (a) offer it; (b) own company only.
Recommendation: (b): product scope is the catalogue company; same-name accounts are a customer-ledger rule.

Q4. The existing family rule inserts an "X" after the letters (`product_code_family.py:88`, SRTWC7604 -> SRTWCX7604), a
Sorento-shaped rule from 27 Sep. (a) leave it (not this lane's, and removing it changes answers that pass today);
(b) replace it by R3 in slice 5. Recommendation: (a) now, listed as a follow-up for the plan's generic clean-up.

Q5. Same offers and ranking for staff as for dealers. (a) yes, one shared function; (b) dealers only.
Recommendation: (a): the review's 20 "right code never offered" turns are both audiences.

## Changed in v3

- Owner 12 Nov ~16:05: no default size ("we shouldn't default 250mm").
- Owner 12 Nov 16:08 / plan v2: no customer-specific rule; sizes, units and set parts come from settings and tables.
