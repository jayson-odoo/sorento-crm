# Parser prompt: the ONE combined candidate for the next production label (CHATBOT-TOTALS-FILTERS + #2120)

Result md5 `dc77a7ac8cb96f046b43f91878615ccb` (111,597 chars). Not published. Only the owner moves the production label.
Production today is v70, md5 57d7d412.

The text is built from three parts:
- Base: #2105's candidate, md5 `e4aa6d43fedd996579b8c1caa2c54556`.
- #2120's PARTY_SIDE section: md5 `9fcfa92c8b6045279b8889734c0fe4d8`, 1,315 bytes, from `PROMPT-party-side-3nov.md` Edit 1. It is inserted immediately before the `━` banner line that precedes `TOP SELLING` (after REPORT_ASK).
- This lane's edits, listed below.

Code that keys on these words:
- `parser.report_ask_defined_in`: `frame` and `company_or_brand` are in the schema only when the text defines them.
- `parser.KNOWN_COMPANIES_WORD`: the user block carries a data-built `Known companies:` line only when the text names it.

So #2105's text alone (e4aa6d43) sees none of this lane's changes.

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
