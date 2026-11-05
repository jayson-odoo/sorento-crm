# Parser prompt: the ONE combined candidate for the next production label (CHATBOT-TOTALS-FILTERS + #2120)

Result md5 `d29c19830b22aa47403a88ddcb8e817d` (112,531 chars), 5 Nov, after crew's re-pass on v200 (md5
`9ad88b43128b9135244f15395f8d0fc4`) found a bare "Sorento" given said_as "company" with no kind word (2 runs of 3).
Saved unlabelled as v202 (id 05f55303) on sorento_prod_1020. Not published; only the owner moves the production label.
Production today is v70, md5 57d7d412. Earlier candidates: v199 dc77a7ac (4 Nov, edits 1-8), v200 9ad88b43 (edits 9-11).

The text is built from three parts:
- Base: #2105's candidate, md5 `e4aa6d43fedd996579b8c1caa2c54556`.
- #2120's PARTY_SIDE section: md5 `9fcfa92c8b6045279b8889734c0fe4d8`, 1,315 bytes, from `PROMPT-party-side-3nov.md` Edit 1. It is inserted immediately before the `━` banner line that precedes `TOP SELLING` (after REPORT_ASK).
- This lane's edits, listed below.

Code that keys on these words:
- `parser.report_ask_defined_in`: `frame` and `company_or_brand` are in the schema only when the text defines them.
- `parser.KNOWN_COMPANIES_WORD`: the user block carries a data-built `Known companies:` line only when the text names it.
- `parser.COMPANY_CANDIDATES_WORD` (9ad88b43): a data-built `Company candidates` block (the contact's companies the message
  spells, 2+ companies) only when the text names it.
- `parser.SAID_AS_WORD` (9ad88b43): the entity key `said_as` (company | brand | both | null) only when the text defines it.
- `parser.SAID_AS_TEXT_WORD` (d29c1983): the entity key `said_as_text` (the message's own kind word, or null), ordered before
  said_as through Gemini `propertyOrdering`; with it defined, a said_as counts only when said_as_text is filled.

So #2105's text alone (e4aa6d43) sees none of this lane's changes, and dc77a7ac sees none of the 5 Nov ones.

Owner rule kept: no gold-message examples and no word lists. Every edit is a slot rule.

## Edits (all in `== REPORT_ASK ==` unless noted; apply by anchor)

1. Object shape: `"frame": "total|breakdown|ranking"` after `"kind"`; `"company_or_brand": []` after `"brand_or_account_type": []`.
2. Copy-first bullet, appended: "Asking for a total, a list or a ranking is such a change: it sets frame (a total also clears group_by and top_n)."
3. The full-new-ask bullet is replaced, per the owner's 3 Nov ruling. A full new ask "still keeps every held filter it does not change: basis, channel, company and every list stay as held until a message changes or widens them. Naming a filter of another kind adds it beside the held ones and never clears them. Its frame, group_by and top_n are this message's own."
4. A new `frame` bullet:
   - total: one figure;
   - breakdown: every row of group_by;
   - ranking: rows in order, cut to a count or a direction;
   - a filter / period / basis change keeps the held frame;
   - a total ask sets frame total;
   - values of one slot side by side make a breakdown on that slot.
5. A new one-name bullet, keyed to the `Known companies:` line. A name on that line that is also a Brand candidate is placed by the message's kind word:
   - company -> company only;
   - brand -> brands only;
   - both words -> both;
   - neither word -> `company_or_brand` only (the assistant asks).

   A reply to the company-or-brand question moves the name to the slot(s) it names.
6. Basis parenthesis, appended: "When this message says a basis, the top-level sales_basis is that same basis."
7. BRAND CANDIDATES section, appended: a token also on the `Known companies:` line that the message calls the company is the company, not a brand entity.
8. ORDER_STATUS section, appended to the CRM-asks-which-document sentence: a reply naming a document answers it, even with no outstanding word (sales order -> so_outstanding, delivery order -> do_outstanding, both -> outstanding_both). The CRM's question itself now reads "Sales order or delivery order?" (code, owner ruling 4 Nov).

9. (5 Nov, entity line) `"said_as"`: what THIS message calls a name that is both a brand and a company: company, brand,
   both (both words), else null.
10. (5 Nov, BRAND CANDIDATES) Edit 7's sentence is replaced: the user block may also carry a `Company candidates` block; a
    name in both blocks is still ONE brand entity (canonical_code as the Brand candidates block lists it), its said_as is
    what this message calls it, and report_ask puts the name where said_as says.
11. (5 Nov, one-name bullet of edit 5) "A name on that line, or in the Company candidates block, ... goes where this
    message's own kind word (its entity's said_as) puts it".

12. (5 Nov, entity line, d29c1983) `"said_as_text"` before `"said_as"`: the word(s) of THIS message that call the name a
    company or a brand, as typed, else null; said_as follows that word and is null whenever said_as_text is null.
13. (5 Nov, BRAND CANDIDATES, d29c1983) the example list names said_as_text with said_as, and adds: a message that types
    neither word for the name ("Sorento total sale September 2026") -> said_as_text null and said_as null, even when the
    name is a known company.

## Gates (gemini-3.5-flash-lite, x1, sorento_prod_1020 read-only, text swapped in-process; ledger lines 4 Nov)

Gold rows: `sorento_crm_backend/scripts/chatbot_eval/gold/parser_report_totals_filters.jsonl`, graded on the full object.

| Gate | Text md5 | Code | Gold | USD |
|---|---|---|---|---|
| 1 | 8098801c (lane edits v1 + PARTY_SIDE) | 22d5484321 + #2120 | 13 of 23 | 0.080 |
| 2 | ac43863a (company_or_brand, outstanding answer) | b3d1a33bff + #2120 | 17 of 26 | 0.089 |
| 3 | dc77a7ac (Known companies) | 99baab137f + #2120 | 19 of 26 | 0.091 |

Gate 3's 7 misses, read against the engine:
- tf-24/25/26: the parser gives `outstanding` / `so_outstanding` / `do_outstanding`, which the engine maps to the right kind. They miss only on the object's basis slot, which the engine does not need.
- tf-06 "top 5" over a held breakdown: frame breakdown with top_n 5. The engine fix is in this PR (AF-7).
- tf-09/10 "sorento company only": both slots filled, kind_said null. The engine asks "company or brand?" once and never gives wrong totals.
- tf-13 bare "Sorento": brands only, so it is answered as the brand with no question. The question path is built, but this model does not use `company_or_brand` for a bare name yet.

TRAIN no-op control (parser-gold TRAIN slices 1+2, same code, BASE e4aa6d43 vs this text): 93 vs 90 whole-parse passes on
the 112 common rows, 5 wins / 2 losses (G042, G047: intent), p=0.45: not worse. USD 0.73 for both arms.

Saved unlabelled on sorento_prod_1020 as v199, id 6ef0ec26-d7ba-4dc3-b46e-9d631e5c054e (4 Nov).

## Gates on 9ad88b43 (5 Nov, inside crew's USD 0.60 OK; ledger lines 5 Nov 00:41 and 00:47)

| Gate | Text md5 | Code | Gold | USD |
|---|---|---|---|---|
| 4 | 9ad88b43 (Company candidates + said_as) | 5156c84ae1 + #2120 (gate head 9bb6bed561) | 23 of 30 | 0.105 |

- The owner's T4 row (tf-27, "sorento company only" over the every-agent list) passes: company Sorento, brands [], said_as company.
- tf-28 (T5 "company sorento" over Brand SORENTO), tf-29 ("Sorento brand only") and tf-13 (bare name) fill company AND
  brands; said_as is company / brand / null, so the engine routes by said_as (tests on these exact parses:
  test_report_totals_filters_ht1.py). tf-06 / tf-24..26 as gate 3.

TRAIN no-op control, CAND arm only (BASE e4aa6d43 from 4 Nov reused: `git diff fd90e61b41 9bb6bed561` on the parser input
code is 5156c84ae1 only, all gated off for a text without the new words): 82 vs BASE 84 on the 105 common rows, 5 wins /
7 losses, p=0.77, not worse; vs dc77a7ac 82 vs 87, 2 / 7, p=0.18. Every loss is a non-report row (stock vs product intent,
picked option, find kind, period: G004, G014, G035, G042, G056, G085, G126), none touches a brand, company or said_as.
USD 0.366. Score: crew/state/eval/chatbot-totals-filters/runs/control_score_CAND5.md.

## Gates on d29c1983 (5 Nov, inside crew's USD 0.40 OK; ledger lines 5 Nov)

| Gate | Text md5 | Code | Gold | USD |
|---|---|---|---|---|
| 5 | d29c1983 (said_as_text) | b29b302cca + #2120 (gate head bb03ce6972) | 24 of 34 | 0.121 |

- Bare-name rows tf-31/32/33 pass (said_as_text and said_as null); tf-34 ("company" reply) passes. Every typed-word row has
  said_as_text right (tf-09/10/27/28 "company", tf-29 "brand", tf-30 "company and brand").
- tf-01 (top-level sales_basis) and tf-22 (a held customer) flipped from gate 4; neither touches the edited lines.

TRAIN no-op control, slice 1 only (crew ruling 5 Nov): 42 vs BASE e4aa6d43 44 on 52 common rows, 3 wins / 5 losses,
p=0.73; vs v200 41 vs 39. No loss carries a report_ask. Known pre-existing loss: G056, an outstanding-kind row
(report_ask null) losing picked_option; it also lost vs BASE on v200 and dc77a7ac. USD 0.182. Score:
crew/state/eval/chatbot-totals-filters/runs/control_score_CAND6.md.
