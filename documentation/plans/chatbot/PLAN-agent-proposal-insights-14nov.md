# PLAN: Agent panel proposal comparison with insights + correct Prepared By (AGENT-PROPOSAL-INSIGHTS)

Status: behaviour card filed, waiting on owner answers (size M, LEAD pattern). No product code yet.

Base: origin/main ad06893097. Paths under `sorento_crm_backend/app/services/` unless noted.

## Journey (owner, 14 Nov, CRM AI assistant panel, Agent mode, on a project)

1. "please compare the 3 proposals for the project" got one compact table
   `qty x price (74.52% below list) = total` per code, a literal `<br>` in cells, a duplicated line,
   "100% below list" on RM 0 lines and one summary sentence. Owner: "I don't need to know the how many
   percent below list ... I was expecting like more insights".
2. "who quoted these proposals" got "All three ... created by <project owner>". Wrong: one proposal's
   Prepared By is a different user. Owner rule 11 Nov: Prepared By = document creator, never the project owner.

## Why it happens (code, cited)

| Symptom | Cause |
| --- | --- |
| "% below list" text everywhere | `chatbot/agent/quotation_lines.py:24-38` `vs_list()` builds it per line; `chatbot/agent/tools.py:393-396` tells the model to print `qty x unit price (vs_list as given) = line total` |
| Only a table + one sentence | Same description: "one compact markdown table ... then one sentence on the differences" (`tools.py:393-396`); prompt says "Answer concisely" and "never do arithmetic on results" (`ai_prompt_registry.py:1033-1100`) so no gaps or deltas are allowed |
| Literal `<br>` | "a row per item code, a column per document" forces two lines of one code into one cell; panel renders ReactMarkdown + remarkGfm, no raw HTML (`sorento_crm_frontend/app/components/common/AIAssistantBubble.tsx:823-825`) |
| "100% below list" on RM 0 lines | `vs_list` has no special case for unit price 0 with a list price |
| Duplicate line | the document really has two lines with the same code; the "row per code" rule merges them into one cell |
| Wrong "who quoted" | no agent tool returns the creator: `quotation_lines.py:115-135` (ref, document_no, revision, total, scopes) and `project_quotation_service.py:1756-1776` (list) carry no `created_by`; the model inferred it from the project owner |
| Shallow reasoning | model default gemini-3.5-flash at effort `low` (`chatbot/agent/loop.py:61-65`); after the lines tool the loop narrows tools to lines + answer + plan (`loop.py:118-123`) |

## Behaviour card (filed as crew-ask)

### A. "Compare the proposals" answer

Findings first, in plain WhatsApp-style bullets (the panel and WhatsApp share the prompt's FORMAT rule), then the table.

1. **Headline**: each proposal's total; which is lowest and which is highest, and the gap between them in RM
   (the gap is computed by the tool, never by the model).
2. **Scope differences**: scopes present in some proposals only; per scope, the total in each proposal.
3. **Codes only in some proposals**: "In A and C, not in B: SRTWHBWP".
4. **Biggest price differences**: for codes in 2+ proposals, the codes where unit price or qty differ most,
   naming the cheapest proposal for that code, with the RM difference (tool-computed).
5. **Watch items**: lines at RM 0 (named "no charge", never "100% below list"), the same code repeated
   inside one proposal, rate-only lines (priced per unit, not in the total), lines cut by the size cap.
6. **Then a clean table**: one row per line occurrence (a repeated code is two rows, so no `<br>`), columns
   Code, then per proposal Qty and Unit price (RM), and Line total; a totals row. No percent text, no
   list-price comparison unless the user asks about list price.
7. The model may add a short judgement ("B is cheapest but leaves out the pump scope") built only from the
   tool's facts. No invented reasons (why a price is lower) and no recommendation to the customer.

### B. "Who quoted these proposals"

- Per proposal: `Prepared By: <name>` = the user who created the document (`prepared_by_of`,
  `project_quotation_template_service.py:258-261`, the same function the PDF uses at
  `project_quotation_document_service.py:1482-1486,1627`). Never the project owner or sales agent.
- Proposals by different people are listed separately; same person = said once.
- No creator recorded (legacy rows, `created_by` null): "I cannot see who prepared <doc no>."

### C. Example shapes (masked; real rows requested from crew, see data request)

Shapes from the masked dev extract (crew, 14 Nov). Codes and qty kept; people are "Salesperson A/B/C";
prices are left out here on purpose (tests seed their own fake prices). Tables live in schema `projects`
(`quotation_documents`, `quotations`, `quotation_versions`, `quotation_lines`, `quotation_issues`).

1. **The owner's case shape (project with 4 documents)**:
   - Doc 1 (Salesperson A): scope UNIT, 2 lines: SRTWC8518-SH qty 1, CB310-CR-PJ qty 1 (no list price).
   - Doc 2 (Salesperson A): 3 scopes (UNIT 15 lines, LEVEL 9 1 line, Guard House 1 line). In UNIT: SRTWHBWP
     twice with the same qty 6 (the "duplicated line"), SRTWT907SS twice with qty 6 and qty 5 at different
     prices, 7 lines at unit price 0 with a list price > 0 (the "100% below list" lines), 3 lines with no list
     price, one line at qty 0, SRT73-CR in SET while the rest are UNIT.
   - Doc 3 (Salesperson B): scope UNIT, 1 line: SRTWC8518-SH qty 1 at a lower unit price than docs 1 and 2.
   - Doc 4 (Salesperson A): no scopes, no lines (must be named as empty, not dropped silently).
   Findings expected: totals per doc and gap; LEVEL 9 and Guard House only in doc 2; SRTWC8518-SH in all
   three with doc 3 cheapest per unit and doc 2 at qty 6; CB310-CR-PJ vs CB310-CR-L are different codes;
   no-charge lines and the repeated SRTWHBWP flagged; Prepared By: docs 1, 2, 4 Salesperson A, doc 3
   Salesperson B (the owner's "who quoted" case).
2. **Issued revisions + same code in several docs at list vs discounted**: doc 1 (Salesperson A, issued R1
   and R2, 1 line SRTWC286-SH discounted), doc 2 (Salesperson B, SRTWC286-SH and SRTWC8518-SH at list),
   doc 3 (Salesperson B, version 2, issued revision A, 3 lines SRTBT1872-17 qty 4, SRTWB242 qty 10,
   SRTBT1842-15 qty 10). Findings: SRTWC286-SH much cheaper in doc 1; docs 2 and 3 share no code.
3. **Same code twice in one doc, test-like docs**: doc 1 (Salesperson A, version 3, issued A and B, 3 lines,
   2 at RM 0 with no list price), doc 2 (Salesperson C, ZZT-NC-TUB-A twice, qty 5 and 10, same price),
   doc 3 (Salesperson C, issued A, ZZT-NC-TUB-A qty 10 + ZZT-NC-TAP-B qty 10). Findings: doc 2 and doc 3
   share ZZT-NC-TUB-A at the same price; doc 2 holds it twice (total qty 15 vs 10); TAP-B only in doc 3.

Edge cases the extract adds: an empty document; a code repeated in one doc at different qty AND price
(per-code spread must compare per line, not assume one price per code); a line at qty 0; a no-list-price
line with a unit price (no list comparison possible: shows "-" if ever shown).

### D. Facts the tool will compute (code, deterministic; the model analyses, it does not add up)

Per call, beside the documents and lines (no `vs_list`):

- per document: `prepared_by` (name or null), total, line count, rm0_lines, repeated_codes, rate_only count.
- `comparison` (only when 2+ documents): totals ranked with `gap_to_lowest` per document; per code present in
  2+ documents: qty and unit price per document, `cheapest` ref, `unit_price_spread`, `line_total_spread`;
  `only_in` codes with the refs that have them; scopes only in some documents; per scope total per document.
- Tool description stops prescribing a format: it says what the fields mean and that differences are computed.
- Same `prepared_by` on the quotations list (`serialize_quotations` gains the document's creator name per row,
  one batched user lookup) so "who quoted" works from either tool.

### E. Edge cases

- One proposal only: no comparison block; the answer lists its findings (RM 0, repeats) without inventing a contrast.
- Size cap cuts lines (`_fit`, `quotation_lines.py:153+`): comparison is computed BEFORE the cut and says
  lines were left out, so findings still cover the whole document.
- Different UOMs for one code across proposals: no price spread, flagged as "different unit".
- A user who cannot see a project: the route's 404 stays (`projects.get_project_or_404`).

## Questions for the owner (max 5)

1. **Model / effort for the agent**: (a) raise default effort `low` -> `medium` in code (`loop.py:65`), (b) leave
   code and the owner switches the production label to a stronger model, (c) both.
   Recommendation: (a) plus a label check, because the shallow answer is mainly the tool + prompt
   instructions; medium effort gives the model room to rank findings, at modest cost.
2. **Cost / margin in the comparison**: (a) no cost or margin at all, (b) margin per proposal for users with
   `products.cost.view` (same gate as `tools.py:120-121`).
   Recommendation: (a) for this lane, because quotation lines store no cost (`models/projects.py` has no cost
   column on lines) so margin needs a product-cost join and its own ruling; ship insights first.
3. **List price**: (a) drop list price from the comparison entirely unless the user asks, (b) keep a
   "below list" column. Recommendation: (a), per your 14 Nov remark.
4. **Table**: (a) findings then the full table every time, (b) findings only, table when asked.
   Recommendation: (a) for 2-3 proposals under ~30 lines, findings only with "Reply "table" for the full
   table." when bigger, because a 60-row table buries the findings.
5. **DECIDED (crew, 14 Nov 11:45): (a)**, `bump_prompt_to_fallback` migration, owner publishes.
   **Prompt shipping path**: the agent prompt edit ships as a new prompt version via a
   `bump_prompt_to_fallback` migration (`ai_prompt_seed.py:102`) that you publish, or (b) as a draft version
   you review in Prompts and publish by hand. Recommendation: (a), the existing path for agent prompt edits.

## Reuse (owner 12 Nov)

| Need | Existing function | Use |
| --- | --- | --- |
| Creator name | `prepared_by_of` / `prepared_by_user` (`project_quotation_template_service.py:246-261`) | reuse; add a batched variant only if N+1 matters (3-10 docs: reuse as is) |
| Lines per version | `_fill` (`quotation_lines.py:61-77`) | reuse |
| Line text | `svc.line_text` | reuse |
| Prompt bump | `bump_prompt_to_fallback` (`ai_prompt_seed.py:102`) | reuse |
| List rows | `serialize_quotations` (`project_quotation_service.py:1756`) | extend with `prepared_by` |

## Standing rules that apply

AI/chatbot block (all 10), "Prepared By is the creator", "a value that cannot be worked out shows -",
"no internal ids", "one fact per line", "states only what the data holds", "reuse functions".

## Test list (tester, red first; after owner answers)

- tool output has `prepared_by` per document = creator name, not the project owner (two users seeded).
- tool output has no `vs_list` and no "% below/above list" text anywhere.
- comparison: cheapest per shared code, spreads, `only_in`, repeated codes, RM 0 lines, gap_to_lowest.
- comparison computed before `_fit` cuts lines.
- tool description has no "compact markdown table" / "vs_list" / "one sentence" instruction.
- agent prompt fallback allows analysis and has the Prepared By rule; migration bumps the prompt.
- quotations list rows carry `prepared_by`.
- LIVE frozen set x3 (both owner turns + earlier agent owner-FAIL turns).
