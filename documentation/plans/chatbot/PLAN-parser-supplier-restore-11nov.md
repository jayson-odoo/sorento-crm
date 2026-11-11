# PLAN: restore the supplier lines in the production-candidate parser prompt (PARSER-SUPPLIER-RESTORE)

Status: built, gate passed, publish package ready for the owner (small fix track: prompt text + gold + harness + one guard
test, no migration, no auth change). 11 Nov 2026. Package: `PROMPT-parser-supplier-restore-b1c59343.md`.

## Problem (owner, prod Chatbot Console, 11 Nov ~16:50 MYT, parser v72 production)

"outstiang for taiyang" answered `Couldn't find "taiyang" (customer). Did you mean ZHI YANG?`. Suppliers 400-X001 / -X006 /
-X008 are XIAMEN TAIYANG TECHNOLOGY CO., LTD on the dev copy.

## Cause (verified on the dev copy sorento_prod_1104, read-only)

- The supplier path switches on only when the RAW parser text holds `parser.SUPPLIER_ID_ASK`
  (`app/services/chatbot/head/parser.py:1110`, read at `:1322`). Without it supplier candidate lines carry no id
  (`head/lookup_lists.py:480`) and the supplier match never binds.
- Prod v71 (md5 d106ff95, dev v71) carried two lines right after `== LOOKUP SPANS ==`: the supplier line
  (`alembic/versions/sask_0002_span_supplier.py` `PARSER_SUPPLIER_LINE`) and the after/before-year line
  (`AFTER_YEAR_SENTENCE`). Prod v72 (md5 d29c1983, dev v74) dropped both; it ends on a bare marker.
- 289da7e5 (REPORT-FILTER-ALL #2209, dev v79, `documentation/plans/chatbot/prompt-report-filter-all.txt`) is built on
  v72, so it lacks both lines too.
- Span prompt: dev production span v2 (md5 1685b3af) has no `- supplier:` type line; unlabelled v3 (e42387fd) has it.

## Architecture

- Layer: prompt text only (DB rows in `ai_prompt_versions`, label moved by the owner on the Prompts page). No code path
  changes. The candidate is built with the migration's own frozen functions (`with_supplier_line`, `with_after_year`,
  `with_supplier_type` in `sask_0002_span_supplier.py`) so the lines are byte-identical to v71 / v3.
- Candidate parser = 289da7e5 + the two v71 lines after the marker. Candidate span = v3 text (with_supplier_type(v2)).
- Guard (tiny, test only): a pytest that reads the repo's production-candidate prompt file and asserts it holds
  `parser.SUPPLIER_ID_ASK` and the span marker, so a future candidate built on a supplier-less base fails CI.

## Steps

1. Build candidate files, diff vs 289da7e5 and v71, record md5s.
2. Gold rows in `scripts/chatbot_eval/gold/parser_supplier_restore.jsonl` (fake personal names): supplier-only name ->
   supplier entity / PO side; real customer stays customer; both-sides name -> party_side unclear.
3. Gate on the dev copy sorento_prod_1104, parser-level, x1, gemini-3.5-flash-lite (ORG key in-process only, crew
   decision 11 Nov), ledger before + after: candidate vs 289da7e5. Regression: `parser_report_filter_all.jsonl`.
   Result: supplier gold A 5/12, B 10/12 (taiyang rows 0/5 vs 5/5); filter_all no regression. USD 0.2818.
4. Publish package for the owner: text files, md5s, Prompts page steps, after-checks.
5. Guard test red-first, then the candidate file that makes it green.

## Out of scope

- Moving any label on any DB. Prod access. Code changes to the supplier path.
