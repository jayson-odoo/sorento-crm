# CARD: CHATBOT-CODE-MATCH behaviour card (one crew ask before code)

Lane CHATBOT-CODE-MATCH, plan `PLAN-chatbot-code-match-12nov.md`. Codes below are catalogue codes (business data);
no customer, person, phone or price appears.

## What exists today (discovery, file:line on main 7ede7cfa)

| Piece | Where | Reuse |
| --- | --- | --- |
| Code probe: prefix, else substring, on the code with spaces folded | `app/services/entity_resolver.py:2087` `_code_prefix_then_substring`, `:2110` `_prefix_probe_product`, `:2136` `_prefix_probe_product_set` | extend (X / Y part form, all-parts ranking) |
| Family rule incl. the X sibling (SRTWC7604 and SRTWCX7604) | `app/services/product_code_family.py:71` `_family_rows` (body regex `:88`) | extend (Y sibling, size word) |
| Spec narrowing of a family + "None with size 300 mm." | `product_code_family.py:161` `narrow_code_tokens_by_specs`; `lanes/business/answer.py:2872` `no_variant_clause` | extend (size read from the code itself or the size field, never assumed) |
| Trigram did-you-mean (0.25 floor, 15 rows, variants first) | `entity_resolver.py:3225`, `:3317` `_trgm_lookup`, `:3289` `_trgm_product_sets` | reuse as is |
| Per-token did-you-mean candidates, capped at 3 | `lanes/business/answer.py:4973` `did_you_mean_by_token` (`_cap3`, `miss_token_candidates`) | reuse as is (one function for single and multi-code) |
| Dealer did-you-mean pick (carries the typed quantity, no escalation) | `chatbot/dealer_stock.py:77` `did_you_mean`; `answer_bridge.py:2190`, `:2287` `_dealer_did_you_mean` | reuse; feed it the candidates it never gets |
| Dealer exact-codes-only filter | `chatbot/engine.py:975` `_exact_codes_only`, called `:7745` | extend: keep the miss's candidates instead of dropping to "refer to your salesman" |
| Set entity with members, stock, complete-sets figure | `entity_resolver.py:931` `_product_set_entities` | reuse as is |
| Turn trace | `turn_trace.add(...)` (e.g. `engine.py:7759`) | add one `code_candidates` entry |

## Rules

R0. The bot answers a code directly ONLY when the typed code differs from one catalogue code by case, dashes or
spaces, or is a registered product set. Every other near match is OFFERED (up to 3, numbered) and the bot asks. Nothing
is answered on a guess. (Owner 12 Nov 15:10 agreed the "couldn't find" improvement, especially for dealers; the wording
of this rule is the lane's. Owner 12 Nov ~16:05: no default size, "we shouldn't default 250mm".)

R1. Pan / cistern form of a set code. A typed code with no exact hit is also tried with the part role letter after its
letters (X = pan, Y = cistern: CWC604RL -> CWCX604..., CWCY604...), the way `_family_rows` already tries X. The parts
found are OFFERED (they are not the typed code), unless the typed code is a registered set (R2).

R2. A registered set code on a stock ask answers the set: its members' stock and the complete-sets figure, the existing
set stock reply (`_product_set_entities`). Direct answer, no question.

R3. A size is read ONLY from the product's size field (`trap_length`) or from the typed code (300, S10, -250; Mocha
S6/S8/S10/S12 are read as written, and matched to the size field). There is no default size: a code with no size marker
has no size unless its size field holds one. A typed size that has no exact code is never answered directly: the family's
close codes are OFFERED (up to 3) with their real sizes from the size field ("size not recorded" when it is empty), and
the bot asks. Never the bare "None with size 300 mm." line alone.

R4. Dealers. When the exact code fails, the dealer gets up to 3 close codes from their OWN company (the existing company
scope on every probe) as a numbered pick that carries the typed quantity (`dealer_stock.did_you_mean`), instead of
"Please refer to your salesman." With no close code at all: "Couldn't find X." then the refer line (today's reply).

R5. Ranking. Candidates holding every typed part (letters block, digits block, each suffix) come first, then trigram
order. A short token with more than 3 matches (e.g. "8152") keeps today's which-one picker, all-parts matches first.

R6. Trace. Every miss writes `code_candidates`: typed token, each candidate code, its tier (exact / prefix / substring /
part_form / set / size / trgm), similarity, and whether it was answered or offered. Logs keep it.

R7. Multi-code ask: each code runs the same function as a single-code ask (`did_you_mean_by_token`), once per code.

## Examples (shapes from the 12 Nov review)

| Typed (stock ask) | Catalogue holds | Reply |
| --- | --- | --- |
| `CWC604RL x 2` | sets CWC604-P-RL (registered), parts CWCX604-P-RL, CWCX604-S-RL | Dashes only vs set CWC604-P-RL? No (P missing), so OFFER: 1. CWC604-P-RL (set) 2. CWCX604-P-RL 3. CWCX604-S-RL, quantity 2 carried |
| `8152-300-SH` | SRTWC8152-SH-300 (trap_length 300) | All parts held, size 300 is not the default: "Couldn't find 8152-300-SH. Did you mean SRTWC8152-SH-300?" (yes answers it) |
| `SRTWC8152-SH-UF-250` | SRTWC8152-SH-UF (no size marker), sized siblings | No exact code: OFFER the close codes with their real sizes (e.g. 1. SRTWC8152-SH-UF, size not recorded 2. SRTWC8152-SH-UF-300, 300 mm) and ask; never answered as 250 |
| `Swtwc8354-SH-UF` (dealer) | SRTWC8354-SH-UF in the dealer's company (trigram 0.67) | Today "Please refer to your salesman."; new: "Couldn't find SWTWC8354-SH-UF. Did you mean SRTWC8354-SH-UF?" |
| `C21120UW-2-MY` | BRC21120UW-2-MY (substring) | Not a dashes-only difference: one-option offer "Did you mean BRC21120UW-2-MY?" |
| `srtwc 8354 sh uf` | SRTWC8354-SH-UF | Spaces only: answered directly |

Edge cases: a close code in ANOTHER company is never offered to a dealer; a set whose members the dealer may not see is
not offered (`visible_set_clauses`); typed quantity rides on every offer; "no" to an offer = "Couldn't find X." (staff)
or the refer line (dealer); an inactive or placeholder code is never offered (existing `_chat_visible_product_ids`);
the 419 water closets with no `trap_length` are never given a size: they show "size not recorded" in an offer (R3).

## Questions (each with a recommendation)

Q1. `8152-300-SH` (all parts held, one candidate, non-default size). (a) one-option "Did you mean X?" offer; (b) answer
directly because every part matched. Recommendation: (a), only a dashes/spaces difference or a registered set is answered
directly.

Q2. Withdrawn (owner ~16:05: no default size; R3 rewritten).

Q3. Dealer offer when the close code is only in another company of the same trading name (same-name accounts).
(a) offer it: same-name accounts count as one customer (9 Nov); (b) own company row only. Recommendation: (b) for product
codes, because the scope is company (catalogue owner), not the customer ledger; same-name accounts are a customer rule.

Q4. A registered set typed with a dash/space difference (CWC604PRL). (a) answer the set directly (R0 dashes rule + R2);
(b) offer. Recommendation: (a), both direct-answer conditions hold.

Q5. The R0 offer for STAFF (not only dealers): today staff already get a did-you-mean list. (a) same R5 ranking and
X / Y / size candidates for staff too, one shared function; (b) dealers only. Recommendation: (a): one function, and the
review's 20 "right code never offered" turns are staff and dealer both.
