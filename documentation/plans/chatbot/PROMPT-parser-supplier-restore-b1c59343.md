# Prompt publish package: restore the supplier lines (PARSER-SUPPLIER-RESTORE, 11 Nov 2026)

Only the owner publishes. Crew did not touch prod. Pin by md5, never by version number: version numbers differ per
database.

## Why

On prod (11 Nov ~16:50 MYT, parser v72 production), "outstiang for taiyang" answered `Couldn't find "taiyang"
(customer). Did you mean ZHI YANG?`. The cause is in the prompt text, not the code:

- The supplier path turns on only when the parser text holds the exact sentence `parser.SUPPLIER_ID_ASK`
  (`sorento_crm_backend/app/services/chatbot/head/parser.py:1110`, read at `:1322`). Without it, supplier candidate
  lines carry no id (`head/lookup_lists.py:480`), nothing binds a supplier, and the customer-or-supplier checks are
  skipped (`engine.py:2149`, `:2393-2396`).
- Prod v71 (md5 `d106ff95`) carried that sentence and an after/before-year line, right after `== LOOKUP SPANS ==`.
  Prod v72 (md5 `d29c1983`) dropped both lines. 289da7e5 (REPORT-FILTER-ALL) was built on v72, so it lacks them too.

## Files (exact text, committed in this folder)

| What | File | md5 |
|---|---|---|
| Parser candidate (publish this) | `prompt-parser-supplier-restore.txt` | `b1c5934301f23a5c43ca90670aacb81b` |
| Parser base (REPORT-FILTER-ALL round 5) | `prompt-report-filter-all.txt` | `289da7e56130a489ecb624031996acc2` |
| Span candidate (publish this if prod's span text lacks the supplier line) | `prompt-span-supplier-restore.txt` | `e42387fd1804df730dfb5bfe7a66efd4` |
| Span base (production span v2 on the dev copy) | `prompt-span-prod-v2.txt` | `1685b3af11542871e9ee48d469eb0149` |

Both candidates are built by the migration's own functions (`alembic/versions/sask_0002_span_supplier.py`:
`with_supplier_line` + `with_after_year` for the parser, `with_supplier_type` for the span prompt).
`tests/chatbot/test_parser_supplier_restore.py` pins all four md5s and the build.

#2209 (REPORT-FILTER-ALL code) is on prod already (merge 3200ee1a is an ancestor of prod f6413b84), so the parser
candidate can go out now. It carries all of 289da7e5's edits: publish it **instead of** 289da7e5.

### Diff: parser candidate vs 289da7e5 (two lines added at the very end, nothing else)

```
@@ -1036,3 +1036,5 @@
 {{find_filters}}
 <<<END CHATBOT POLICY BLOCKS>>>
 == LOOKUP SPANS ==
+For a supplier entity, canonical_code is the id of the Supplier candidates line the message means. A supplier is a company we buy goods from; what is outstanding with a supplier is our open purchase orders to it (domain purchase_order). A phrase whose only candidates are Supplier candidates lines is a supplier entity with that line's id, never a customer, whatever else the message says.
+"After <year>" starts on 1 January of the next year ("after 2025" -> 2026-01-01) and "before <year>" ends on 31 December of the year before; "since <year>" and "from <year>" start on 1 January of that year. Each leaves the other end null.
```

### Against v71 (d106ff95)

From `== LOOKUP SPANS ==` to the end, the candidate equals v71 character for character, except that v71 ends with one
extra blank line. Everything above the marker is 289da7e5 (the v72 lineage plus REPORT-FILTER-ALL), not v71.

### Diff: span candidate vs production span v2

```
@@ -3,6 +3,7 @@
 - customer: a customer company, shop or account (e.g. "Kim Hardware", "ABC Trading Sdn Bhd")
+- supplier: a company we buy goods from, a supplier, vendor or factory (e.g. "Xiamen ABC Technology")
 - salesperson: a sales staff person, by name or staff code
```

The last line also gains the migration's name sentence: `When the span is a company name written in another script,
"meaning" is that name as the company writes it in Latin letters. A span written in any script other than Latin
letters always carries a "meaning"; it is never null.`

## Gate (crew, 11 Nov, gemini-3.5-flash-lite x1, dev copy sorento_prod_1104, staff contact with the supplier reveal)

Harness: `scripts/chatbot_eval/parser_gold.py live` (rolled back, no writes), arm text pinned by md5. Spend USD 0.2818
of crew's 0.40, ledgered.

| Set | A = 289da7e5 + span v2 | B = b1c59343 + span v3 |
|---|---|---|
| `parser_supplier_restore.jsonl` (12 rows) | 5/12 | **10/12** |
| supplier rows sr-01..05 ("outstiang for taiyang" and 4 more) | 0/5 bound a supplier: 2 read customer, 1 read brand, 2 wrote the supplier's name, which binds nothing | **5/5** bound the TAIYANG supplier by its row id, domain purchase_order |
| customer-only rows sr-06..08 (incl. "after 2025" -> 2026-01-01) | 3/3 | 3/3 |
| both-sides names sr-09..12 | 2/4 | 2/4 (the same two) |
| `parser_report_filter_all.jsonl` (40 rows, regression) | the 17 rows B failed: 17/17 fail on A too | 23/40 |

- No regression: every filter_all row B fails also fails on A, with the same kind of reason (ALL written where the gold
  wants an empty slot, or channel ALL where the gold wants null). These are 289da7e5's own open items, not this change.
- sr-09 / sr-10 ("outstanding for shing soon heng", "outstanding for fullshun", both names are customer and supplier)
  read `party_side` customer on BOTH arms; the gold wants unclear. That is the PARTY_SIDE section's behaviour,
  unchanged here.

## Owner steps (Prompts page)

Path: sidebar **System > AI Assistant > Prompts** (`/system-management/ai-assistant/prompts`). The page shows no md5;
the **Diff** button in the editor is the check.

### 1. Parser

1. Open `chatbot_semantic_parser`. Click **Edit**. The editor opens on the production text (v72 on prod).
2. Clear the editor. Paste the whole of `prompt-parser-supplier-restore.txt`.
3. Click **Diff** and compare against the production version. Expected: the REPORT-FILTER-ALL edits in the
   REPORT_ASK section (listed in `PROMPT-report-filter-all-289da7e5.md`) and the two lines above at the very end,
   after `== LOOKUP SPANS ==`. Nothing else.
4. Commit message: `PARSER-SUPPLIER-RESTORE: 289da7e5 + v71 supplier lines, md5 b1c59343`. Click **Save as new
   version**. Note its number N.
5. **Versions** tab, row vN, "..." menu, **Publish vN**, then **Publish to production**. The provider and model on the
   production label stay as they are.

### 2. Span prompt

1. Open `chatbot_span_extractor`, **Versions** tab, open the production version.
2. Look for the line `- supplier: a company we buy goods from, a supplier, vendor or factory`. If it is there, stop.
3. If not, look for an unlabelled version whose commit message is `SUPPLIER-ASK: the span extractor prompt with
   meanings and the supplier type. Unlabelled.` (migration `sask_0002` published it on prod). Use **Diff** against
   production: expected exactly the span diff above. If it matches, **Publish** it.
4. If there is no such version, **Edit**, paste `prompt-span-supplier-restore.txt`, check with **Diff** (span diff
   above), commit message `PARSER-SUPPLIER-RESTORE: span supplier type, md5 e42387fd`, **Save as new version**,
   **Publish**.

Not measured: moving only the parser label without the span label. The gate's B arm ran both together, as SUPPLIER-ASK
designed it. Move both.

### 3. Check after (prod Chatbot Console, the same staff contact)

1. `outstiang for taiyang`: the reply is about open purchase orders to XIAMEN TAIYANG TECHNOLOGY, or it asks which of the
   TAIYANG supplier accounts. It must NOT say `Couldn't find "taiyang" (customer)`.
2. `outstanding PO for taiyang after 2025`: the period starts 1 January 2026.
3. `outstanding for <any customer that is not a supplier>`: still that customer's sales orders.
4. `sales for fullshun this year`: customer side, no "customer or supplier?" question.

### Roll back

Publish the previous production versions again: parser v72 (md5 d29c1983), and span v2 if you moved it.
