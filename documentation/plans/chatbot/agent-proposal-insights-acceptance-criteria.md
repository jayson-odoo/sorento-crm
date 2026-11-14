# UAC: AGENT-PROPOSAL-INSIGHTS

Owner answers 14 Nov ~11:58: Q1 effort low -> medium; Q2 none (no cost/margin this lane); Q3 the below-list
text is not shown by default but stays in the tool data so the agent answers when asked (no hard
restriction); Q4 findings + full table up to ~30 lines, bigger = findings + 'Reply "table"' offer;
Q5 prompt via `bump_prompt_to_fallback` migration, owner publishes (deploys).

Tool = `crm_project_quotation_lines` (`app/services/chatbot/agent/quotation_lines.py`, schema in
`app/services/chatbot/agent/tools.py` QUOTATION_LINES_SCHEMA). "doc" = one entry of `data["documents"]`.

## A. Prepared By (who quoted)

- A1 Every doc carries `prepared_by`: the display name of the user who created the quotation document
  (`quotation_documents.created_by`), via the existing `prepared_by_of`
  (`app/services/project_quotation_template_service.py:258`). An issued-revision doc carries its document's
  creator too.
- A2 A project owned by user X with a document created by user Y: that doc's `prepared_by` is Y's name, never X's.
- A3 A document with no `created_by` (or an unknown user id): `prepared_by` is null (the key is present).
- A4 The quotations list (`serialize_quotations`, `app/services/project_quotation_service.py:1756`; feeds
  `crm_project_quotations_list` and GET /projects/{id}/quotations) carries `prepared_by` per row = the row's
  document creator name (null without a document or creator). User names are read in one query per call, not
  one per row.

## B. Per-document facts (computed in code)

Per doc, beside `lines`:
- B1 `line_count`: the doc's lines across its scopes (before any size cut).
- B2 `no_charge_lines`: codes of lines with unit price 0 and qty > 0 that are not rate_only, in line order
  unique codes, first-seen order.
- B3 `repeated_codes`: list of `{code, times}` for codes on more than one line within the same doc (across
  its scopes), times >= 2, first-seen order.
- B4 `rate_only_lines`: count of rate_only lines.
- B5 A doc with no scopes is still returned with `scopes: []`, `line_count: 0`, `empty: true`; other docs
  carry `empty: false`.

## C. Comparison (only when 2 or more docs are returned; absent otherwise)

`data["comparison"]`:
- C1 `totals`: one entry per doc `{ref, total, gap_to_lowest}` ordered by total ascending (ties keep doc
  order); `gap_to_lowest` = total minus the lowest total, rounded to 2 dp (0 for the lowest).
  `lowest` and `highest` = the refs of the first and last entries.
- C2 `only_in`: for every code present in at least one doc but not in all docs: `{code, refs}` (refs in doc
  order), codes in first-seen order.
- C3 `shared`: for every code present in 2+ docs: `{code, docs: [{ref, qty, unit_prices, line_total}],
  cheapest, unit_price_gap, line_total_gap, same_uom}` where per doc qty and line_total are summed over that
  doc's lines of the code, `unit_prices` is the sorted distinct unit prices of those lines; `cheapest` = the
  ref with the lowest min unit price (null when all equal or when `same_uom` is false);
  `unit_price_gap` = max of the per-doc min unit prices minus the min of them (null when `same_uom` false);
  `line_total_gap` = max minus min of the per-doc line totals. Ordered by `line_total_gap` descending.
- C4 `scopes_only_in`: scope labels not in every doc: `{scope, refs}`.
- C5 `scope_totals`: for scope labels in 2+ docs: `{scope, totals: [{ref, total}]}`.
- C6 Each of `only_in`, `shared`, `scopes_only_in`, `scope_totals` holds at most 20 entries; past that the
  block carries `<name>_not_shown: N`.
- C7 The comparison is built from every line BEFORE the size cap (`_fit`) cuts lines, so a cut never
  changes it.
- C8 Rate-only lines count like any other line in C2 to C5 (their stored line_total is used); they are
  flagged per doc via B4.
- C9 `total_lines`: sum of every doc's `line_count` (top level of `data`, also when only one doc).

## D. Below-list text

- D1 Each line keeps `list_price`, `unit_price` and `vs_list` (owner Q3: available when asked).
- D2 `vs_list` for a line with unit price 0 and a list price is "no charge", never "100% below list".
- D3 The tool description no longer tells the model to show vs_list, a table, or "one sentence"; it says
  vs_list is for when the user asks about list price. It no longer contains "compact markdown table",
  "(vs_list as given)" or "one sentence".
- D4 The description states that the comparison block is computed by the tool (cheapest, gaps, codes only in
  some documents) and that `prepared_by` is the document's creator.

## E. Agent prompt (`_chatbot_agent_fallback`, `app/services/ai_prompt_registry.py:1033`)

- E1 Has a COMPARING section: findings first (totals and the gap, lowest and highest, scopes or codes in only
  some documents, the biggest price differences naming the cheapest, no charge lines, repeated codes,
  rate only lines, empty documents), using only the tool's computed differences; then the full table when
  `total_lines` is 30 or fewer, otherwise end with `Reply "table" for the full table.`; the table has one row
  per line (a repeated code is two rows), qty and unit price in their own columns, never HTML such as <br>;
  no percent against list price unless the user asks about list price.
- E2 Has the rule: who prepared or quoted a document is its prepared_by; never take it from the project
  owner, sales agent or anyone else; if prepared_by is missing, say you cannot see who prepared it.
- E3 Allows analysis: no longer says only "Answer concisely" for comparisons (concise stays for simple
  lookups). Keeps "never do arithmetic on results" and "every number must come from a tool result".
- E4 No dashes in the copy (existing rule for this prompt).
- E5 A new migration calls `bump_prompt_to_fallback(bind, "chatbot_agent")`; downgrade is a no-op. Single
  alembic head; revision id <= 32 chars.

## F. Effort

- F1 `DEFAULT_EFFORT` in `app/services/chatbot/agent/loop.py` is "medium" (used when the label sets none).

## G. Unchanged

- G1 Existing refs / not_found / issued revision / 404 / permission behaviour unchanged (existing tests stay green).
- G2 `narrow_after_query` behaviour unchanged.

## H. Live (frozen set, x3, real model, sandbox data shaped like the masked extract)

- H1 "please compare the 3 proposals for the project": findings first, no "% below list", no "<br>", the
  repeated code as separate rows or named as repeated, no charge lines named as such, no invented figures.
- H2 "who quoted these proposals": each proposal's Prepared By from the document; the different creator named.

## Review round 1 amendments (lead, 14 Nov, reviewer findings 1, 2, 4, 5, 6)

- R1 (C1, C2, C4, C5 amended) The comparison covers only NON-EMPTY docs (B5 `empty: false`). Empty docs are
  listed in `comparison.empty_documents` (refs, doc order) and have no entry in `totals`; they never make a
  code or scope "only in some". The comparison block is present when 2 or more non-empty docs are returned;
  with fewer, it is absent (an empty doc beside one non-empty doc gives no comparison).
- R2 (C1) On tied totals, `lowest` is the first doc with the lowest total and `highest` the first doc with the
  highest total, in doc order.
- R3 (C6, size cap) `_fit` keeps the whole payload under the cap: after every line is cut and it is still over,
  it trims the comparison lists (largest first, keeping the first entries, raising `<name>_not_shown`)
  before it drops whole documents; when it drops documents it also drops the comparison block entirely (a
  comparison never names a document that is not in `documents`). Final JSON length <= cap for any input that
  the old code kept under the cap.
- R4 (E1) The prompt's full table rule: a markdown table (the panel renders it), only when total_lines is 30
  or fewer AND no scope has lines_not_shown; otherwise end with Reply "table" for the full table.
- R5 (A1, reuse) One creator-name rule: `prepared_by_of` calls `prepared_by_names`; the lines tool reads all
  creator names in one users query per call.

## Round 2 (lead, 14 Nov, crew live pass: a compare answer took ~7.8k output tokens / ~30 s, a second one timed out at 45 s)

- R6 No instruction tells the model to list every number in figures. The agent prompt fallback (FINISHING), the
  answer nudge and the final-call instruction in `loop.py`, and ANSWER_SCHEMA's description say: figures holds only
  the key numbers (totals, gaps) with their call_id, never every table cell. The verifier already checks the
  text's numbers against the tool results itself. The prompt keeps "Every number in your answer must come from a
  tool result".
- R7 A turn whose answer text holds a markdown table with numbers from the tool result (qty, unit prices, line
  totals) while `figures` lists only the document totals is shown as written: no "(not verified)", status
  answered.
- R8 The prompt says no tool returns a quotation's cost or margin, so when asked the agent replies in one plain
  line that cost and margin are not available, without calling other tools for them.
