# PLAN: EEM-CATEGORY-PICK - the matched category reaches the report; the reply language follows the parser

Status: 27 Oct 16:2x, building (lane ENTITY-EXTRACT-MATCH, size M, no migration). Stacked on #1898
(branch crew/eem-category-pick on crew/eem-semantic-bridge); draft PR, base #1898's branch, retarget to main after
#1898 merges. Red-first per slice; gate spend approved by the owner 16:1x (one 200-msg arm + the real category
messages, cap USD 1.50, Gemini org key).

UAC: `eem-category-pick-acceptance-criteria.md` (AC-CP-1..14).

## Why (owner hand test of #1898, 27 Oct 12:0x; diagnosis crew-notes 6433563087 / 6433563388 / 6433563745)

- Parser v132's entity schema says a category's `canonical_code` is "else null" (template line 207): 0 of 84 / 42 /
  44 category entities carry one on the 200-msg gate. The span pass matched 马桶 -> Water Closet, but the row never
  reached the report, which re-matched the raw word (`lanes/business/report_ask.py:476-477` ->
  `lanes/business/__init__.py:507-512`) and failed: "马桶" and "water clost" unknown; "wc" hit the 1-product generic
  WC row instead of the Water Closet class (SORENTO SRT-WC: 11,768 lines in 2026).
- "water clost?" after "马桶" replied in Chinese: `language.detect` found no English marker word and `choose` carried
  zh (`language.py:25-50`).

## Owner rules (14:2x, 16:1x)

1. No brand specified: "WC" means all WC categories across brands. A named brand narrows it.
2. The generic "WC" category stays (no data change); it is one of the WC categories.
3. Understanding stays semantic in any language or romanisation (matong, ma tong, mangkuk tandas, jamban, tandas
   duduk, 坐厕, toilet bowl -> Water Closet through the span pass meaning). No word lists, no script rules.
4. The reply language is the parser's own reading of the message, then the contact's saved language, then the
   conversation language. "water clost?" after "马桶" is English because the parser reads it as English.
5. Standing: parser extracts, code picks; fix at the parser input, never a post-parser override; clarify, never
   assume; >= 8 real messages per behaviour.

## Card decisions (crew 16:0x, confirmed with data)

- Generic WC row: INSIDE the Water Closet line. Data: `product_categories` 5ef3d0ff code "WC", name "WC", no class
  label; `product_class_signal.resolve_classes_for_term(db, "WC")` answers exactly one class, "Water Closet". A
  class-less category joins the one class the class vocabulary gives its code or name; none or several -> its own line.
- Brand narrowing: the report's existing brand filter (`brand_ids` from the brand word), not a brand row pick. The
  parser names the class; the brand stays its own entity.

## Design

### A. Parser prompt (text, copy only, unlabelled)
A new parser version on the copy = the copy's live v132 text + two paragraphs, each holding a marker sentence the code
keys on (the S3 `MEANING_ASK` pattern, so prod v67 / v68 behave exactly as today until a version with the sentence is
labelled):
- `CATEGORY_PICK_ASK`: a category entity's canonical_code is the label before the colon of the Category candidates
  line the message means (any language, romanisation or typo), else null. The schema line ("else null") gains the
  category case.
- `LANGUAGE_ASK`: top-level `message_language`: the language the user wrote this message in ("en", "ms", "zh"), by
  meaning (romanised Chinese like "matong" is the user's language choice to read, not a script), null when the
  message carries no language of its own (a bare code, a number, "ok").
Built by a kit script from the copy's v132 + the code constants; crew applies the publish (SQL) on the copy only.

### B. Category block grouped by class (head/lookup_lists.py)
Only when the turn's parser prompt holds `CATEGORY_PICK_ASK`: the Category candidates block renders one line per
class, "- Water Closet: BRT-WC, CB-WC, IDC-WC, M-WC, SRT-WC, WC" (rows in today's order), "- Water Closet" when only
the class row matched, class-less rows mapped by the rule above, other rows "- <label>" as today. `LookupRow` gains
the row's class (set at load: `class_label`, else the one vocabulary class, else none). Both paths (n-gram lookup and
span pass) render through `render`.

### C. Report: a class word or a generic code means the whole class (lanes/business)
`_top_selling_category_ids`: a word that hits only class-less rows by code or name ("wc" -> generic WC) also takes
the class the vocabulary gives that word, union of both ("wc" -> 6 ids); a class label ("Water Closet") -> its
classed rows plus the class-less rows mapped to it (6 ids). A classed code ("SRT-WC") stays exact (1 id). The brand
filter narrows as today. One shared helper with B for "the class of a category" (core service, so lanes and head use
the same rule).

### D'. Reply language from the parser (engine + language.py)
Parser output `message_language` joins the JSON schema only when the prompt holds `LANGUAGE_ASK`. `_turn_language`
takes the turn's parsed `message_language` first; when it is null or absent: the contact's saved language, then the
conversation language (`choose` order changes from detected / conversation / saved to parsed / saved / conversation on
a parsed turn). Turns with no parser call (escalate word, media notice, reset before parse) keep today's chain.

### E. Carry-over test hygiene
`tests/chatbot/test_lookup_warm_retry.py` default-jitter test: `monkeypatch.undo()` -> `monkeypatch.setattr(ll,
"_jitter", random.random)` (the undo dropped the autouse no-live-call fixtures).

## Gate
- 200-msg parser gold (eem kit, S3 runner) on the new version vs today's S3 arm (74.2 right-row; category 59.6).
- Category set: the owner's 3 hand-test messages, 10 real prod messages (7 Chinese 马桶, 1 Malay sinki dapur, 2
  "water closer" typos; read-only chat connector), plus the owner's romanised / Malay words as messages (matong, ma
  tong, mangkuk tandas, jamban, tandas duduk, 坐厕, toilet bowl): category canonical + reply language per row.
- Spend: Gemini org key, owner waiver cap 1.50, ledger before / after.

## Hand test
The three owner messages, "sorento wc" and "wc" (brand / no brand), plus 2 romanised rows ("matong ada stok?",
"mangkuk tandas sorento top 10").
