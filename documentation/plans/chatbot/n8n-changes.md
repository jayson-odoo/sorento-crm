# n8n changes, per slice - Chatbot Turn Engine

Plan: `documentation/plans/chatbot/PLAN-chatbot-turn-engine.md`
UAC: `documentation/plans/chatbot/chatbot-turn-engine-acceptance-criteria.md`

**This file is the n8n half of the cut, written by whoever ships the CRM half, executed by
the owner.** Every slice moves logic out of n8n; the CRM change lands first and is inert,
then the n8n edit below switches the traffic over. Nothing here is automated: the prod n8n
instance is edited by hand, so each section is written at NODE level - which node, what it
becomes, and what proves it worked - rather than as prose.

Two rules that apply to every section:

- **The CRM ships first and OFF.** A slice's CRM code is behind a flag or an unread
  response field until the n8n edit is made, so the two can be deployed in either order and
  a bad slice is reverted by turning the flag off, not by re-editing n8n under pressure.
- **A cutover has a named precondition.** It is written in the section. "It looks right" is
  not one.

---

## S6a - `sub-resolve-and-gate` moves into the CRM

**CRM side (shipped, inert by default).** `POST /api/v1/external/chat/turn` now returns
`delegate_payload`: exactly the item `sub-resolve-and-gate` returns today - the four
`resolve-exit-*` arms' `_exit_kind` plus `resolved`, `gate`, `ctx_resolved`, `aggregate`,
`tier_gate`, `annotate_incoming` and that arm's own item. It is `null` unless
`CHATBOT_BUSINESS_LANE_ENABLED=true`, and null on every branch kind except the three that
reach the sub.

### Which turns this covers

`sorento-consume-main`'s `route` Switch has three outputs that reach the sub, and the CRM
lane covers exactly those three:

| `route` output | node it feeds | `entry` stamped | CRM `branch_kind` |
| --- | --- | --- | --- |
| 8 `check_promotion` | `tag-entry-access-check` | `access_check` | `check_promotion` |
| 11 `stock_denied` | the SPINE's `Edit Fields2` -> `tag-entry-resolve` | `resolve` | `stock_denied` |
| fallback `business_query` | `tag-entry-resolve` | `resolve` | `business_query` |

**There are TWO nodes called `Edit Fields2`**, one in the spine (row 11 above, which sets
`not_allowed_check_stock` before the tag) and one inside `sub-main-processing` (fed by
`ef2-gate`, which re-sets it from the trigger). Everything below is about
**`sub-main-processing`'s**. It stamps `not_allowed_check_stock: true` and it **STAYS**. `validator` reads it by
name and by node, not off the flowing item:

```js
if ($('Edit Fields2').isExecuted && $('Edit Fields2').first().json.not_allowed_check_stock) {
```

`$('Edit Fields2')` on a node that does not exist THROWS, so deleting it takes the whole
`stock_denied` answer path down. The CRM therefore does NOT stamp the field: nothing
downstream of the sub reads the item for it, and a CRM-side copy would be a second writer
of a value n8n still owns.

### Step 1 - shadow window (no wiring change)

1. Set `CHATBOT_BUSINESS_LANE_ENABLED=true` on the CRM. Nothing in n8n changes: it still
   calls `sub-resolve-and-gate` itself and still answers from it.
2. For a week of live traffic, compare each turn's `delegate_payload` with what
   `Call 'sub-resolve-and-gate'` returned on the same turn. The CRM writes the payload to
   `chatbot.turns.trace` under the `looked_up` record, so this is a query, not an
   instrumentation project.

**Precondition for step 2, and it is not negotiable:** zero `looked_up` records with
`status = failed`, and zero payload mismatches outside the two keys
`tests/chatbot/_corpus.py::CAPTURE_BODY_ADDITIONS` names. The shadow costs one extra
resolver call per business turn - that is the price of the window and the reason it is a
window and not the permanent state.

### Step 2 - the wiring change, in `sub-main-processing` (`53RxDSON8P3QSN22`)

The sub keeps its shape; only its FRONT changes. Today:

```
When Executed by Another Workflow -> build-ctx -> ef2-gate -> Edit Fields2 / item-restore
item-restore -> Call 'sub-resolve-and-gate' -> resolve-gate -> ... -> resolve-item -> resolve-arm
```

After:

1. **Add** a trigger input `resolve_payload` (type object) to
   `When Executed by Another Workflow`, beside the existing `ctx`, `item`,
   `not_allowed_check_stock`, `is_test`.
2. **Replace the body of `resolve-item`** (Code node, already the chain's item carrier)
   with a read of the trigger instead of the call:

   ```js
   return [{ json: $('When Executed by Another Workflow').first().json.resolve_payload }];
   ```

3. **Repoint the four presence gates and the five name-preserving stand-ins** from
   `$("Call 'sub-resolve-and-gate'").first().json.<key>` to
   `$('When Executed by Another Workflow').first().json.resolve_payload.<key>`. They are:

   | node | key it reads |
   | --- | --- |
   | `resolve-gate` (If) | `resolved` |
   | `aggregate-gate` (If) | `aggregate` |
   | `annotate-incoming-gate` (If) | `annotate_incoming` |
   | `resolve-entity` (Code stand-in) | `resolved` |
   | `disallowed-entity-gate` (Code stand-in) | `gate` |
   | `build-ctx-resolved` (Code stand-in) | `ctx_resolved` |
   | `Aggregate` (Code stand-in) | `aggregate` |
   | `tier-gate` (Code stand-in) | `tier_gate` |
   | `annotate-incoming-picker` (Code stand-in) | `annotate_incoming` |

   Rewiring alone does NOT redirect these - they are by-name reads (`TOPOLOGY.md`, "Read BY
   NAME"). The expression has to be edited too. This is the one step where a missed node
   fails silently: a stand-in that never executes makes every downstream
   `$('<name>').first()` throw, and the turn dies with a node-not-executed error rather
   than a wrong answer.

4. **Delete ONLY** `Call 'sub-resolve-and-gate'` (executeWorkflow) and `item-restore`
   (Code). Wire `Edit Fields2[0] -> resolve-gate` and `ef2-gate[1] -> resolve-gate`, so the
   stand-in chain still runs and still dominates its readers (LESSONS 91: a sibling has no
   ordering relation, so the chain cannot become a branch).

   **`ef2-gate` and `Edit Fields2` STAY.** `validator` reads `$('Edit Fields2').isExecuted`
   and `$('Edit Fields2').first().json.not_allowed_check_stock`, and `$('<name>')` on a
   node that does not exist throws - deleting the Set node takes the `stock_denied` answer
   path down with it, several nodes away from the edit, which is the worst shape a mistake
   here can have. `ef2-gate` is what decides whether it runs, so it stays for the same
   reason. Both are deleted at S6c with the rest of the lane (AC-610), when `validator`
   goes too.

### Step 3 - the caller, in `sorento-consume-main` (`S4N1LiisAqA4hpMC`)

5. On both `Call 'sub-main-processing'` call sites, add the input
   `resolve_payload: {{ $json.delegate_payload }}` (the CRM `/chat/turn` response the two
   re-emitters already read `ctx` and `item` from).
6. `tag-entry-resolve` / `tag-entry-access-check` stay for now: `entry` is inert once the
   CRM decides it, and leaving them costs nothing and keeps step 2 revertible. They are
   deleted at S6c with the rest of the lane (AC-610).

### Step 4 - unpublish

7. `sub-resolve-and-gate` (`tKeQUkZK5cFK9BFa`) is unpublished ONLY after a week with no
   rollback. Until then it stays published and unreferenced, which is what makes the
   rollback a one-field edit (`resolve_payload` back to the call's output).

### Rollback

Turn `CHATBOT_BUSINESS_LANE_ENABLED` off. The CRM returns `delegate_payload: null`, so
`resolve-gate` / `aggregate-gate` / `annotate-incoming-gate` all take their FALSE arms and
`resolve-arm` receives an item with no `_exit_kind`. **That is a dead turn, not a fallback**
- so if step 2 has already landed, the rollback is to re-add the
`Call 'sub-resolve-and-gate'` node and repoint the nine expressions back. Keep a copy of
the workflow JSON from before step 2; that is the actual rollback artefact.

### Not covered by this slice

- `probe-incoming` and `probe-customer-orders` still run in n8n's `sub-get-results` when
  the CRM lane is off. With it ON, the CRM's own probe seam raises (it needs S6b's
  `entity-ids-transformer` and `output-structurer`), which both annotators render as their
  documented UNPROBED arm: the customer picker ships bare with
  `customer_probe_skip_reason: 'probe_unavailable'`, and the incoming picker ships today's
  "None of these have incoming stock right now." **This is a real behaviour difference on
  picker turns and it is why step 1's shadow window must include picker traffic**; if it
  matters to the owner before S6b, S6a stays in shadow until S6b lands.
- The `resolve-exit-access-ask` arm has zero captured executions, in any slug (see
  `tests/chatbot/COVERAGE.md`). It is covered by unit tests, not by replay.
- **For S6b, one detail that will look like a port bug and is not:** `probe-incoming`'s
  `contact_id` parameter is `={{ $('build-ctx').first().json.ctx.contact.id }} ` with a
  TRAILING SPACE, and `probe-customer-orders`' is not. Whatever S6b builds the tool
  arguments with has to decide whether to reproduce that or normalise it, and say which;
  today it reaches `sub-get-results` as a string with a space on the end.
- **`resolve-entity` carries `retryOnFail` in n8n and the port has no retry.** A transient
  resolver failure that n8n survived is a shadow-lane failure here. Named in the plan's S6a
  section; the shadow window is what says whether it matters.

---

## S6b - `sub-fetch-results`, `sub-get-rag` and `sub-get-results` move into the CRM

**CRM side (shipped, inert by default).** The fetch step is
`app/services/chatbot/lanes/business/fetch.py` plus `run_fetch`, behind the SAME
`CHATBOT_BUSINESS_LANE_ENABLED` flag S6a introduced. Nothing new to turn on: a turn that
does not run S6a's resolve+gate never reaches the fetch either.

Three subs are replaced at once because they are one straight line in n8n:
`sub-fetch-results` calls `sub-get-rag` for the tool and `sub-get-results` for the answer,
and neither is called from anywhere else on the turn path.

### What the CRM does instead

| n8n | CRM |
| --- | --- |
| `Execute 'sub-get-rag'` -> `HTTP Request` (embeddings) -> `Execute a SQL query` (pgvector) -> two Code nodes | `FetchServices.embed` + `EmbeddingReadService.search_tool_chunks` + `fetch.collapse_tool_rows` |
| `tool-filter` | `fetch.tool_filter` -> `ToolPick(items, outcome)` |
| `if-tier-ask` / `tier-probe-plan` / `tier-probe` / `tier-probe-collect` / `if-tier-has-any` | `fetch.tier_probe_plan` / `tier_probe_collect`, dispatched by `run_fetch` |
| `Call 'sub-get-results'` -> `entity-ids-transformer` -> `MCP Client1` -> `output-structurer` | `fetch.entity_ids_transformer` -> `FetchServices.mcp_call` -> `fetch.output_structurer` |
| `fetch-result` | `fetch.fetch_result` |

**Two things stop being n8n's problem, and both are catalogued hazards.** `sub-get-rag`
holds a POSTGRES CREDENTIAL and runs a hand-written pgvector query against production
(H53); the CRM does the same read through `EmbeddingReadService`, so that credential can be
removed from the n8n instance entirely once the sub is unpublished. And `MCP Client` /
`MCP Client1` both hard-code a raw IP endpoint (H52); the CRM reads
`settings.ai_assistant_mcp_url`, so moving the MCP server is a config change rather than a
workflow promote.

### Step 1 - shadow window

Same shape as S6a's, and it runs on the same flag, so in practice S6a's window IS this
window once S6b is deployed: compare `delegate_payload.fetch` against what
`Call 'sub-fetch-results'` returned on the same turn.

**Precondition for step 2:** zero `looked_up` failures, and the picked TOOL identical on
every turn. The tool is the thing to watch rather than the rendered text: an embedding
model or a tool-registry change moves the pick, and a different tool is a different answer.

### Step 2 - the wiring change, in `sub-main-processing` (`53RxDSON8P3QSN22`)

1. **Add** a trigger input `fetch_payload` (type object) beside `resolve_payload` (S6a).
2. **Replace the body of `fetch-result-clean`** - already the node that strips `tool` and
   `tier_probe` back off before `validator` sees them - so it reads the trigger instead of
   the call:

   ```js
   const j = $('When Executed by Another Workflow').first().json.fetch_payload;
   const { tool, tier_probe, _fetch_arm, ...rest } = j;
   return [{ json: rest }];
   ```

3. **Repoint `build-result`**, which reads `$("Call 'sub-fetch-results'").first().json.{tool,tier_probe}`
   BY NAME, to the same trigger key. This is the one by-name read in this cut and it is the
   one a rewire does not redirect.
4. **Delete** `Call 'sub-fetch-results'` and `fetch-arm` (the Switch on `_fetch_arm`);
   `run_fetch` has already taken that decision and the CRM returns the arm it chose. Wire
   `ef2-gate`'s converged output straight to `fetch-result-clean`.

**`access-level-choice-message` STAYS** and keeps its `fetch-arm` predecessor edge replaced
by a small If on `fetch_payload._fetch_arm === 'tier-ask'`: S6b decides the arm, S6c renders
its copy, and deleting the renderer now would take the tier ask down between the two slices.

### Step 3 - unpublish

`sub-fetch-results` (`8Nlm3XmY4dJvBrPO`), `sub-get-rag` (`tWP33QOFT7SxThfT`) and
`sub-get-results` (`rysSPgUssLDf6xJc`) are unpublished only after a week with no rollback.
**`sub-get-results` is called from FOUR places, not one** - the two S6a pickers'
`probe-incoming` / `probe-customer-orders`, `tier-probe`, and the answer path - so it can be
unpublished only when S6a's probes are also in-process (they are today's known S6b
dependency, see the S6a section's "Not covered"). Until then it stays published and the two
picker probes keep calling it.

### Rollback

Turn `CHATBOT_BUSINESS_LANE_ENABLED` off: with no `resolve_payload` there is no
`fetch_payload` either, and both arms fall back together. After step 2 has landed the
rollback is re-adding `Call 'sub-fetch-results'` and repointing `build-result` - keep the
workflow JSON from before that edit, which is the actual rollback artefact.

### H49, and why there is no per-tool branch

`crm_order_management_orders_by_product_list` has never been selected in ANY capture graded
so far - 39 `tool-filter` captures on the live sub, plus the earlier fork's. The port
therefore carries no branch keyed on that tool. What it DOES carry is the JS's own
`DATE_PARAMS` and `ORDER_TOOLS` lookup tables, verbatim including that tool's row: those are
tables, not branches, and dropping a row would be a silent behaviour change on the day the
tool is first picked. The measurement that would justify an actual branch has not been
taken, and the module's docstring says so.

### Not covered by this slice

- **The picker probes still need S6a's seam filled.** `run_fetch` supplies the answer path's
  MCP call; `probe-incoming` / `probe-customer-orders` are the SAME `sub-get-results` call
  with different arguments, and S6a's `services._probe` still raises. Wiring it to
  `entity_ids_transformer` + `mcp_call` is a small follow-up and is what lets `sub-get-results`
  be unpublished.
- **`fetch-result`'s `result` arm does not render an answer.** S6c owns `validator`,
  `promo-picker` and `build-result`; until then the turn still delegates to n8n's business
  lane with the fetch output attached, so nothing is re-fetched.
- **The orphaned `AI Agent` + `MCP Client` tool nodes in `sub-get-results` are NOT ported**
  and never ran in the capture pool (H7). They are deleted with the sub.
