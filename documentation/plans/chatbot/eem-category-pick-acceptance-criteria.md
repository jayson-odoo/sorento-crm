# UAC: EEM-CATEGORY-PICK (plan: PLAN-eem-category-pick-27oct.md)

## Journey
A staff member or dealer asks "top 100 hot selling sorento wc in 2026", "马桶", "matong ada stok?" or "water clost?".
The span pass already matches the words to the Water Closet rows. Now the parser hands the matched category to the
report, a bare "WC" with no brand means every WC category, a named brand narrows it, and the reply comes back in the
language the user wrote in.

## A. Parser picks the category (prompt, behind a marker)
- **AC-CP-1 [BE]** `CATEGORY_PICK_ASK` (a constant in the chatbot package) is the sentence a parser prompt carries
  when it asks for a category's canonical_code. Today's prompts (no sentence) behave exactly as now.
- **AC-CP-2 [T]** The copy-only parser version (v132 text + the two marker paragraphs) is built from the constants,
  published UNLABELLED on the copy, and its md5 is recorded; no label moves.

## B. Category block one line per class
- **AC-CP-3 [BE]** With `CATEGORY_PICK_ASK` in the turn's parser prompt, the Category candidates block renders one
  line per class: "- Water Closet: BRT-WC, CB-WC, IDC-WC, M-WC, SRT-WC, WC"; a class whose only matched row is the
  class row itself renders "- Water Closet"; a row with no class renders "- <label>" as today.
- **AC-CP-4 [BE]** A category row's class = its `class_label`; with none, the ONE class the class vocabulary
  (`product_class_signal.resolve_classes_for_term`) gives its code or name (generic WC -> Water Closet); none or
  several -> no class. No word list.
- **AC-CP-5 [BE]** Without the sentence the block renders exactly as today (byte-identical lines), on the n-gram path
  and the span path.

## C. Report: class word / generic code = the whole class
- **AC-CP-6 [BE]** `_top_selling_category_ids`: "Water Closet" -> every Water Closet category, the class-less ones the
  AC-CP-4 rule maps included (6 ids on the copy data). "wc" (hits only the class-less generic row) -> the same 6
  ids. "SRT-WC" (a classed code) -> 1 id. A word matching nothing -> unknown, as today.
- **AC-CP-7 [BE]** With a brand word the report's existing brand filter narrows the class (no brand row pick); with no
  brand all WC categories are counted ("wc" no brand = all WC across brands, owner rule).
- **AC-CP-8 [BE]** The ranking takes the parser's category canonical_code when set (`report_ask.take_words`, AC-HT8-12),
  so "马桶" / "water clost" / "matong" with canonical "Water Closet" resolve to the class.

## D'. Reply language from the parser
- **AC-CP-9 [BE]** `LANGUAGE_ASK` marks a parser prompt that returns top-level `message_language` ("en" | "ms" |
  "zh" | null). The field joins the parser JSON schema only for such a prompt (today's prompts: schema unchanged).
- **AC-CP-10 [BE]** On a parsed turn the reply language is the parsed `message_language`; when null or absent, the
  contact's saved language, then the conversation language. "water clost?" after "马桶" with message_language "en"
  replies in English; a bare code (null) keeps the saved / conversation language.
- **AC-CP-11 [BE]** Turns with no parser call keep today's language chain. No new script or keyword rule anywhere.

## E. Test hygiene
- **AC-CP-12 [T]** test_lookup_warm_retry.py default-jitter test no longer calls `monkeypatch.undo()`.

## Gate and hand test
- **AC-CP-13 [T]** 200-msg gold on the new version: overall right-row not below today's S3 74.2 beyond noise
  (paired CI), category kind up; category set (owner 3 + 10 real prod + the owner's romanised / Malay words): the
  Water Closet canonical on every WC row, the right reply language per row. Spend logged (owner waiver, cap 1.50).
- **AC-CP-14 [T]** Hand test on the copy: the owner's three messages, "sorento wc", "wc", "matong ada stok?",
  "mangkuk tandas sorento top 10".
