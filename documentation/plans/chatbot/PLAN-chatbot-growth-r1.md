# PLAN - Chatbot growth r1: richer tools, one dialogue state, field reveal, trace

Status: APPROVED by owner 7 Sep 2026 ("good to go"); lane 1 `feat/chatbot-growth-data` IN PROGRESS. UAC: `chatbot-growth-r1-acceptance-criteria.md`.
Assumed, not picked: the order summary shape is the three-line pipeline (SO outstanding / DO open / delivered); the owner ended the review before choosing, so AC-905b ships that shape and the console pass will show it.
Predecessor: `PLAN-chatbot-turn-engine.md` (parity port, LIVE on prod at 043e2a0be). This plan
grows the engine along the "Growth axes" table that plan names, and stays at the **parity**
stop of the reasoning dial: every answer is built by construction from one tool envelope, no
answer LLM. The owner reaffirmed that on 7 Sep 2026.

## Why

Owner statement, 7 Sep 2026, paraphrased into the four defects it names:

1. **Data breadth.** Specs, SO outstanding, DO open with angles, PO placed, SPO last receipt
   and sellable stock cannot be answered because no read tool exposes them. Foundre's rule
   "no stock, no incoming, but a PO exists: say the PO date and quantity" is unanswerable.
2. **Rigid angle.** A DO question by customer, by transporter, by date or "how many in total"
   is one flat list. The renderer is envelope-agnostic already; the tools do not carry
   `group_by` / `include_summary` uniformly.
3. **Multi-turn understanding goes haywire** around offers, picks, escalation yes/no, and a
   filter change after a result. Cause, measured: carry is decided by TWO writers (the parser
   prompt's "always continue the previous turn" plus ten deterministic rules in
   `head/output_exchange.py`) and dialogue state is five `pending` kinds + an 8-rule
   `dym_offer` ladder + `selection_context` + `picker_*` + `_offer_carry`, each hand-added.
   Nothing ages except member offers (TTL 3).
4. **No way to see why.** `chatbot.turns.trace` records the stages; the console lists rows and
   shows a Lost / Gained / Flags / Parser drift summary. No per-turn view of the carry
   decisions, the tool call, the envelope, or the cross-domain probes.

Deferred by the owner on 7 Sep 2026, with the trigger that reopens each:

| deferred | trigger |
|---|---|
| learning from corrections beyond capture (few-shot retrieval, corpus growth, fine-tune) | this plan's console labelling surface exists AND a measured parse-error class recurs across contacts |
| L2 episodic retrieval ("the one you showed me yesterday") | a measured class of explicit backward references in the corpus that focus TTL cannot serve |
| `agent` strategy per lane, answer LLM | owner changes the dial; never for the business lane under this plan |
| flow builder / rule editor | never; visualisation is a trace viewer, the ladder stays code |

## Measured current state (origin/main 043e2a0be)

- LLM calls per turn: parser (`chatbot_semantic_parser`, strict 26-key schema) and, on
  `low_signal` only, the clarifier. Everything else is Python.
- Business lane: `fetch.select_tool` picks ONE MCP tool by cosine search over the catalog,
  restricted to `CHATBOT_READ_ONLY_TOOLS` (33 names, mirrored from `ToolSpec.read_only` /
  GET in `sorento_crm_mcp/catalog.py`, CI asserts agreement); `fetch.entity_ids_transformer`
  maps typed entities to `product_ids` / `customer_ids` / `transporter_ids` / `shipment_ids`
  and the date window; `fetch.output_structurer` renders the envelope (intro, per-item
  `fields[]`, `summary_items`, `action_links`, `requested_attributes` projection).
- Cross-domain: `lanes/business/answer.py` hard-pairs `inventory` and `incoming` only
  (`answer.py:398-405`): per requested code missing from the primary render, probe the other
  tool, render "But there is INCOMING stock (ETA)..." / "No stock and no incoming for X".
- Memory: `respond_contacts.session_vars` JSONB, 34 allow-listed keys, whole-object
  overwrite per turn by `tail/compile_state.py`. Parser prompt receives the previous reply
  text and the structured previous state. Quoted replies pull a 4-key projection of the
  quoted turn's state.
- Access: `head/access.py::check_access` returns `attributes: None,
  all_attributes_allowed: None` always; grants are agent-level (`contact_agent_access`) plus
  `stock_visibility_policies` per contact (mode, warehouse_ids, hide_zero_locations). There is
  NO field-level reveal today, for any tool.
- DO open list already exists: `crm_order_management_orders_list` with
  `order_status=outstanding`, product / customer / transporter ids, delivery date window,
  `include_summary`, `sort`, `dir`.
- Console: `GET /api/v1/system/chatbot/turns` (list, cursor), `failed-contacts`, `retry`.
  FE `system-management/chat-history` with `TurnPanel`, `StateTracePanel` (Lost / Gained /
  Flags / Parser drift), `ChatThreadDrawer`.
- Replay: `tests/chatbot/test_replay.py` (node captures), `tests/chatbot/worlds.py` +
  `test_worlds.py` (end-to-end worlds derived from 200 captures, multi-turn worlds chain the
  CRM's own session write). 72 test files under `tests/chatbot/`.

## Decisions (owner, 7 Sep 2026)

- D1 Parity stays. Deterministic structured answers. Richer tools and richer parameters, never
  an answer LLM.
- D2 All six data capabilities ship in this iteration, none deferred.
- D3 Sellable stock is per contact, OFF by default. Basis: on hand minus open SO (ordered,
  not yet DO). Open DO is not subtracted: AutoCount deducts stock at DO creation.
- D4 PO answers never reveal the supplier to a dealer; management contacts may see it. A general
  per-contact field reveal control is required, not a PO special case.
- D5 No flow builder. Trace and visualise so the owner can debug and understand a turn alone.
- D6 Memory is the long-term shape (focus, episodes, profile), not the quick fix: one writer per
  layer, per-slot decay, typed values, every read traced. Parser receives structured hints,
  never transcript prose.
- D7 Dialogue state is ONE typed `open_question` slot with a table of kinds, resolved before
  the business parse. Selections, escalation yes/no, team and tier picks and member offers
  all become kinds.
- D8 Learning from corrections: capture only in this plan (the `correction` field already
  exists). Levels B-E deferred, see triggers above.
- D10 One product tool and one order tool: specs extend `crm_master_products_list`, SO
  outstanding is a bucket of `crm_order_management_orders_list` shown beside DO under
  `include_summary`; no `sales_order` domain.
- D11 Focus decays by turns only (`chatbot_focus_ttl_turns`, default 3). Three lanes.
- D9 The per-domain tax (six code places per new domain) is collapsed into one `DOMAIN_SPEC`
  table in code. Evidence: the six places exist today and every new domain in this plan would
  touch all six.

## Design

### Slice A - Six data capabilities (MCP tools + presenters + parser vocabulary)

Every tool is a `ToolSpec` in `sorento_crm_mcp/catalog.py` (GET, so read-only by
construction) backed by one backend GET under `/api/v1/...`, rendered by a presenter in
`sorento_crm_mcp/presenters.py` that emits the envelope `output_structurer` already reads
(`intro`, `items[].fields[]`, `summary_items`, `field_vocabulary`, `result_type`). Adding a
tool = ToolSpec + backend route + presenter + one name in `CHATBOT_READ_ONLY_TOOLS` + an
embedding sync + corpus samples. No renderer change per tool.

**Uniform list parameters** on every list tool this plan touches (new and existing DO list):
`group_by` (one of the tool's declared axes), `include_summary` (bool), `sort`, `dir`,
`limit`. The envelope carries `groups[] {key, label, items[], summary_items}` when `group_by`
is set; `output_structurer` gains ONE branch that renders groups as headed sections. Parser
gains two keys: `group_by` (enum: `product | customer | date | transporter | warehouse |
supplier | null`) and `top_n` (int or null, "last 3", "top 5").

| # | tool | backend | data | axes / params | notes |
|---|---|---|---|---|---|
| A1 | `crm_master_products_list`, extended (owner: one product tool, no spec tool) | existing products route, `include_specs` query param the presenter always sets | `product_specifications.values` joined to `product_spec_registry` (label, unit, synonyms, data_type, rank_weight) | unchanged; `requested_attributes` now also matches registry `synonyms` | Presenter appends every populated spec key as a field `label: value unit` ordered by `rank_weight`. With no `requested_attributes` the renderer shows today's four fields plus ONE compact "Specs: k: v, k: v" line (no overload); with `requested_attributes` only the asked keys, and a key the product lacks answers "no <label> recorded for <code>". Domain `master_products`, intent `check_product`, nothing new in the parser vocabulary. |
| A2 | stock balance, extended | existing stock balance route | add `open_so_qty` = SUM(`sales_order_lines.qty_ordered - qty_delivered`) over open lines per product (per warehouse where the line has one, else product total), `sellable` = `on_hand - open_so_qty` | unchanged | Both fields are `restricted` (Slice C): hidden unless the contact holds `inventory.sellable`. Wording: "Sellable (on hand minus open SO)". Never negative below zero without saying so: render "0 (oversold by N)". |
| A3 | `crm_order_management_orders_list`, extended (owner: one order tool, SO beside DO, no new domain) | existing orders route | new bucket `order_status=so_outstanding` = `sales_order_lines` open with `qty_ordered - qty_delivered > 0` (ordered, no DO yet), header customer, `order_date`, `requested_delivery_date`. Existing buckets stay: `outstanding` = DO created not delivered, `delivered`. | `product_ids`, `customer_ids`, `transporter_ids`, date window, `group_by` in {customer, transporter, date, product}, `include_summary` | The list renders ONE bucket. `include_summary=true` returns a three-line pipeline in `summary_items`: SO outstanding / DO open / delivered, so "how many did ABC take" reads three numbers and "list DO" stays a list. Domain stays `order`; the parser's `order_status` enum gains `so_outstanding` with the vocabulary "SO outstanding", "ordered but no DO", "belum DO", "还没出DO". Summary shape is the one open item, see the review page. |
| A4 | merged into A3 | | | | |
| A5 | `crm_procurement_purchase_orders_placed_list` | `GET /procurement/purchase-orders/placed` | `purchase_order_lines` with `qty_ordered - qty_received > 0`, `line_status = open`, header `status`, `expected_date` (line, else header), supplier | `product_ids`, `expected_date_from/to`, `group_by` in {product, supplier, date}, `include_summary` | New domain `purchase_order`, intent `check_po`. `supplier` field is `restricted` (Slice C, key `purchase_orders.supplier`). Wording "PO placed, not yet shipped". PO and SPO are never netted (`spo_allocations.po_line_id` is NULL on every row, decision 6 Aug 2026), so this tool never subtracts incoming. |
| A6 | `crm_procurement_spo_last_receipt_list` | `GET /procurement/spo-allocations/last-receipt` | `spo_allocations` with `receipt_status = received` joined to `inbound_shipments` (`warehouse_arrival_date`, else `actual_arrival_date`), `quantity_received`, `spo_number`, warehouse | `product_ids`, `top_n` (default 1), `warehouse_ids` | Unblocks domain `spo_allocation` (remove from `DEFAULT_UNSUPPORTED_DOMAINS`), intent `check_spo` gains "last in". Phase 2 first task: measure on the local prod copy that `warehouse_arrival_date` is populated for received allocations; if not, the fallback order is `actual_arrival_date`, then `updated_at`, and the presenter labels which date it shows. |

Cross-domain ladder (Foundre's rule) lives here too: `answer.py`'s hard pair becomes a
per-origin list read from `system_settings.chatbot_crossdomain_ladder` (JSON, default
`{"inventory": ["incoming", "purchase_order"], "incoming": ["inventory"]}`), same probe and
render mechanism, one rung after another until a rung has rows for the missing code. New
wording for the PO rung: "No stock and no incoming for X, but a PO is placed: {qty} expected
{date}." followed by the existing escalate offer. The `nothing_note` becomes "No stock, no
incoming and no PO for X."

`DOMAIN_SPEC` (D9; this plan adds one domain, `purchase_order`, and unblocks `spo_allocation`; the six places are the evidence and every future domain pays them): one frozen table in `app/services/chatbot/contracts.py` keyed by domain
with `intents`, `axis`, `bare_entity_type`, `switch_words`, `tools`, `escalation_team`,
`default_supported`. `AXIS_BY_DOMAIN`, `BARE_ENTITY_TYPE_BY_DOMAIN`, `DOMAIN_SWITCH_WORDS`,
`DEFAULT_UNSUPPORTED_DOMAINS` and the tool filter become views over it; a guardrail test
asserts every `DOMAIN_HINTS` value has a row and every tool in `CHATBOT_READ_ONLY_TOOLS` is
claimed by exactly one domain. The parser schema enums are generated from the same table.

### Slice B - Dialogue state: focus + open question, single writer

New keys inside `SessionVars` (persisted shape stays JSONB, allow-list grows by two):

```
focus: {
  domain:      {value, set_at_turn, set_at, source},
  products:    {value: [entity], set_at_turn, set_at, source},
  customer:    {...}, transporter: {...}, warehouse: {...},
  date_window: {value: {start, end, mode}, set_at_turn, set_at, source},
  attributes:  {...}, tier: {...}, brands: {...}
}
open_question: {
  kind, options: [frozen rows], expects: "pick" | "yes_no" | "free",
  asked_at_turn, asked_at, ttl_turns, payload
} | null
```

`source` is the rule name that set the slot (`current_message`, `reuse`, `pick`,
`quoted`). Every slot decays independently by turns (owner: turns only, no wall-clock TTL):
one new `system_settings` column `chatbot_focus_ttl_turns`, default 3. A dead slot is
dropped at intake, before the parser sees state, and a trace line records it. The `set_at`
timestamp is kept for the trace only.

**Turn order changes** in `engine.py` `_run_stages`:

1. `received` (Python): read session, apply decay, build `focus_hints` (alive slots only)
   and `open_question_hint` (kind, expects, option labels). Deterministic; the parser is the
   only LLM call in the head and it only extracts.
2. `understood`: parser prompt v3 (`chatbot_semantic_parser`, new registry version, promoted
   only after replay). The prompt no longer says "continue the previous turn". It extracts
   the current message and emits three new keys: `answers_open_question: {resolved, picks[],
   yes_no, free_text}`, `anaphora: bool` ("it", "that one", "那个"), `topic_reset: bool`
   ("another", "other", "别的", a decisive domain word). `entities[].current_message` stays
   and is always true under v3. Removed from the prompt: every instruction that tells the
   model to re-emit previous entities or previous domain (`BARE ENTITY CONTINUATION`, "keep
   the previous domain", "downstream re-applies routing" stays).
3. NEW `answered` stage: if `open_question` is alive and `answers_open_question.resolved`,
   `dialogue/open_question.py::resolve(kind, answer, options)` runs the kind's handler and
   the turn proceeds from the handler's outcome (a pick becomes focus.products with
   `source=pick` and the business lane runs; escalate yes runs the escalation lane; team
   pick sets routing). An alive question that is not answered survives until TTL; one that
   is past TTL is cleared with a trace line and never answers silently.
4. `focus` step (replaces the carry half of `output_exchange`): `dialogue/focus.py::apply`
   with exactly these rules, in order, each a named function under pytest:
   - `replace_same_axis`: a current-message entity replaces the slot of its type.
   - `reset_on_topic`: `topic_reset` clears every slot except tier and brands.
   - `reuse_alive`: a message with intent and no entity of a needed type reuses the alive
     slot; dead slots never reuse.
   - `domain_from_switch_word`: a switch word sets domain, keeps product slots.
   - `date_restated_only`: date window is set only from the current message, except the
     `reuse_alive` case of a scope continuation (the one place the executor carries today).
   - `anaphora_reuses`: `anaphora` true and no entity reuses the most recent ALIVE product
     slot; with the slot dead the bot asks which product.
   The axis executor's `clear / reuse / modify / replace / replace_combine` semantics are
   kept as the outputs of these rules, so `compile_state.py`'s reconciled entities and the
   downstream lanes read the same shapes they read today. Rules K2 and K4, the switch-word
   override, `_query_brands_carried`, `_tier_carried` and the date and attribute carry arms
   in `output_exchange.py` are deleted, not shadowed. `confident` is read: an entity with
   `confident=false` never replaces an alive slot without a picker.
5. `compile_state`: writes `focus` and `open_question` from the dialogue module; the five
   `pending` kinds, `dym_offer` ladder, `selection_context`, `picker_*` and `_offer_carry`
   are rewritten as `open_question` kinds with one handler each:

| kind | expects | options | handler outcome |
|---|---|---|---|
| `product_pick` (dym, sibling, partial-miss roster) | pick | frozen rows with uuid, code, label | focus.products set, source `pick`, business lane runs with the pick; issue #708 partial-miss keeps already-resolved siblings via `payload.keep` |
| `customer_pick` | pick | family rows with company codes | focus.customer set |
| `escalate_yes_no` | yes_no | none | yes: escalation lane; no: `escalation_declined` copy |
| `team_pick`, `company_pick` | pick | teams / ledgers | routing set, escalation continues |
| `tier_pick` | pick | tiers | focus.tier set, promotion lane reruns |
| `member_offer` | yes_no | family members | yes: business lane over members; TTL 3 as today |

Quoted replies (`replyTo.id`) resolve against the quoted turn's frozen options first, as
today, then fall back to the alive `open_question`.

`SessionVars` keeps every existing key for one release so the world corpus still grades;
`pending`, `dym_offer`, `selection_context`, `picker_*` become derived mirrors of
`open_question` written by `compile_state` (read by nothing new). Removing the mirrors is a
follow-up once the corpus is re-derived.

### Slice C - Field reveal per contact

One mechanism for D3 and D4. Presenters mark a field `restricted=<key>` in
`field_vocabulary` (keys this plan ships: `inventory.sellable`, `purchase_orders.supplier`).
New table `contact_field_reveals (id, respond_contact_id FK, field_key, granted bool,
created_at, created_by)`, unique on (contact, key). Default for a restricted field is hidden.
`head/access.py::check_access` fills `attributes` with the contact's granted keys (it returns
`None` today, the shape already exists). `output_structurer` drops any field whose
`restricted` key is not in `ctx.access.attributes`, and the envelope's `summary_items` follow
the same rule. The MCP server itself stays unfiltered (in-app assistant and n8n operators are
internal); the chatbot is the only consumer that filters.

UI: Contacts detail page, Access tab, "Field reveals" section: a checklist of the restricted
keys with labels ("Sellable stock", "PO supplier"), off by default, confirm on unchecking.
Keys are listed from a backend `GET /system/chatbot/field-reveal-keys` generated from the
presenters at MCP catalog sync (stored on `mcp_tools` as `restricted_fields` JSONB), so a new
restricted field appears in the UI without a code change here.

### Slice D - Turn detail trace view

Backend: `GET /api/v1/system/chatbot/turns/{id}` returns the row plus a normalised
`trace_detail`:

```
stages[]:       {name, started_at, ms, status}
parse:          {raw, post_processed, prompt_version, model}
decay[]:        {slot, value, set_at_turn, age_turns, age_minutes, reason}
open_question:  {before, answer, after, handler, outcome}
focus[]:        {slot, before, after, rule, source}
tool:           {name, args, envelope (truncated to 8 KB), ms}
crossdomain[]:  {rung, tool, args, rows, rendered}
reveals:        {restricted_fields_seen[], granted[], dropped[]}
session:        {before, after, diff[]}
```

The engine already writes `trace` per stage; this slice adds the structured entries at each
step above (a `trace.add(kind, payload)` helper in `engine.py`, no new table) and the read
endpoint composes them. FE: `TurnDetailDrawer` in `system-management/chat-history` opened
from a row of the existing list, sections in the order above, each collapsible, monospace for
args and envelope, the session diff as a two-column Lost / Gained list reusing
`StateTracePanel`'s summary. Usable at 375px and 1280px, wide JSON scrolls inside its own
container. No feature explanation text on screen.

### Slice E - Corpus, worlds and promotion

- Corpus samples for every tool and every angle in Slice A (`documentation/plans/chatbot/samples/`).
- Multi-turn worlds for the dialogue cases the owner named: pick then next pick, escalate
  yes / no after a result, filter change (product, then date) after a DO result, "what about
  Y" after a stock answer, a product asked two turns ago then a stock question with no
  entity after TTL (must NOT carry), the same within TTL (must carry), quoted reply pick.
- Parser v3 replayed against the existing 200 captures; every divergence registered with a
  reason (expected class: entities no longer re-emitted from context).
- Shadow mode for 3 to 7 days before promoting v3, exit as the predecessor plan: branch
  parity 99%+, reply parity 97%+ on turns with no open question, every mismatch triaged.
- **Owner console pass, per lane** (the S7 Console Pass artifact is the template: 70 cases
  from 3,149 real turns, marked pass / fail / skip on the test clone, cases 1 to 20 = 78% of
  traffic). The four automated gates run first and are what catch regressions; the console
  pass is the owner's own eyes on the reply text, which no replay grades.
  - data lane: the existing 70 re-run as a sanity subset (cases 1 to 20 plus 23 to 27) and a
    NEW section of about 20 cases for what this lane adds: specs full and one-key, sellable
    on and off, SO bucket, the three-line summary, DO by customer / transporter / date, PO
    placed with and without supplier, SPO last in and last 3, the Foundre PO rung, the
    no-stock-no-incoming-no-PO line, a 422 on a bad group_by. Written by the lane, pre-filled
    with the clone results, before hand-off.
  - dialogue lane: the full 70 re-run, section 2 (clarify and picker flows) and every
    multi-turn case mandatory, plus the six owner worlds (AC-940 to AC-946) as console
    cases. This is the lane that changes reply semantics; a fail here blocks promotion of
    parser v3 regardless of the shadow numbers.
  - trace UI lane: no console pass; agent-browser evidence run instead.

## Lanes and PRs

One lane = one PR. Three lanes, in this order, each independently deployable:

| lane | slices | why this grouping |
|---|---|---|
| `feat/chatbot-growth-data` | A, C, D backend `trace.add` for tool / crossdomain / reveals | additive: new tools, new params, new table, ladder; no change to carry semantics, so the world corpus stays green as is |
| `feat/chatbot-growth-dialogue` | B, E worlds, parser v3 in shadow | the one lane that changes reply semantics; ships behind the prompt registry version and shadow mode |
| `feat/chatbot-growth-trace-ui` | D endpoint + FE | reads what the other two wrote; can land alongside lane 1 |

Phase order per lane per `PRINCIPLES.md`: FE mock first where there is FE (C's checklist,
D's drawer), backend test-first, review, DoD. Migrations chain onto the current main head via
`scripts/alembic-reparent.sh` at the pre-PR gate; heads at planning time: 481 chatbot, 487
elsewhere (see `project_do_search_mcp_feedback_7sep`).

## Risks

- **Parser v3 changes behaviour on every continuation turn.** Mitigated by shadow mode and
  registered divergences; the multi-turn worlds are the only test that can catch a wrong
  carry (worlds.py docstring). Promotion is the owner's call.
- **Sellable subtracts open SO across warehouses when the SO line has no warehouse.** State the
  basis in the field label; measure how many open lines lack `warehouse_id` on the prod copy in
  Phase 2 and record the number in the UAC evidence.
- **`spo_allocations` date columns may be sparse.** A6 measures first; the presenter labels
  the date it used.
- **`contact_field_reveals` widens what a contact can see.** Default hidden, grants explicit,
  confirm on change, and the chatbot filter is the only path that reads it. Quoted-state
  projection still excludes access keys (H-series lesson kept).
- **`DOMAIN_SPEC` is a registry.** Justified by six existing places and four new domains in
  this plan; the guardrail test is what stops it drifting.

## Out of scope

Learning levels B-E; L2 episodic retrieval; agent strategy; flow builder; removing the
`pending` / `dym_offer` mirrors from `SessionVars` (follow-up after corpus re-derivation);
MCP-side field filtering for the in-app assistant.

## Evidence run - `feat/chatbot-growth-trace-ui` (AC-963, AC-965, AC-972, AC-973, AC-992), 7 Sep 2026

Agent-browser (isolated session `tester-chatbot-trace-ui`), FE `http://localhost:3080` (dev,
HMR), BE `http://localhost:8080`. Screenshots: `documentation/evidence/chatbot-growth-trace-ui-7sep/`.

**Data prerequisite.** The dev Postgres had zero LIVE (`is_test=false`) `chatbot.turns` rows
tied to a real `chat_histories` message - the only three non-test rows in the DB belonged to a
contact with no `chat_histories`/`respond_contacts` row at all, so nothing surfaced in the UI
(the FE never requests `include_test=true`, by design - H57/D14). To exercise the drawer against
real data rather than mocks, one real turn was posted for the existing dev contact "Jayson
Jayson" (`respond_io_id 437264483`) via the legitimate ingress contract: `POST
/api/v1/external/chat/turn` (X-API-Key, envelope borrowed from that contact's most recent
console-check envelope, `is_test: false`, message "stock for SRTWC8517-SH-UF") followed by
`POST /api/v1/external/chat-history/messages` (the same contract n8n uses to log the incoming
message) so `chat_histories.message_id` matched `chatbot.turns.message_id` and `TurnPanel` had
something to key off. Turn id `e2c0334d-8a81-4e33-82c8-455fd2f5e48b`, status `delegated` (the
business lane is not CRM-completed on this lane's backend, so the turn routes and stops - it
never reaches `failed`). This is now real data in the shared local dev Postgres for that one
contact/message; nothing was written directly to the database.

**Step 1 - Chat History drawer (AC-972, AC-973).** Sidebar: System > Messaging > Chat History
(`/system-management/chat-history`). Widened the Filters date range (default is 1 day) via the
native `datetime-local` inputs. Opened the "Jayson Jayson (+60166753328)" thread, searched
"SRTWC8517-SH-UF", found the injected incoming message with its `TurnPanel` ("In progress /
Business query / 7.1 s / #e2c0"), clicked the "Open full trace" icon button. `TurnDetailDrawer`
opened titled "Turn #e2c0" with all nine sections **in order**: Stages, Parse, Decay, Open
question, Focus, Tool, Cross-domain, Field reveals, Session - matching AC-970/972's contract
(`reveals` renders as "Field reveals", `session` diff as "Session"). Stages was expanded by
default (4 rows: received/understood/access/routed, all `ok`); every other section was
collapsed. Expanded each one by one:
  - Parse: monospace JSON in a `<pre>`, confirmed via `getComputedStyle` - `overflow-y: auto`,
    `scrollHeight 776 > clientHeight 418` (scrolls inside its own container, not the page).
  - Decay: "Nothing decayed this turn."
  - Open question: "No open question this turn."
  - Focus: "No focus rule fired this turn."
  - Tool: "No tool call recorded."
  - Cross-domain: "No cross-domain probe this turn."
  - Field reveals: "No restricted field was on this answer."
  - Session: "Lost: none / Gained: none".
  At 375x812 (`set viewport 375 812`): `document.documentElement.scrollWidth` = 375,
  `window.innerWidth` = 375 - **no horizontal page scroll**. Screenshot
  `01-turn-detail-drawer-1280.png` (collapsed, 1280) and `02-turn-detail-drawer-375.png` (375).
  **AC-973 (failed turn first) not exercised live**: no naturally-occurring LIVE failed turn
  existed to open (the only failed rows in this DB are `is_test=true` console-check runs, which
  the FE never fetches, or on a contact with no chat row), and producing one would need
  flipping `chatbot_business_lane_enabled` / `chatbot_completed_lanes` for the whole lane
  backend - out of scope for a read-only verification pass. Covered instead by
  `TurnDetailDrawer.test.tsx::'a failed turn shows the failing stage first'` - ran green
  (`npx vitest run ".../TurnDetailDrawer.test.tsx"`, 4/4 passed).

**Step 2 - Contacts > Access > Field reveals (AC-963, AC-965).** No sidebar entry for
`/user-management/contacts` exists (by design - `apps-dropdown-menu.tsx` names it the ONLY nav
path). Reached via the topbar grid icon (mislabeled `aria-label="Switch layout"`, an existing
bug) > "Internal Users / Respond contacts" > any contact row > Access tab. The "Field reveals"
card renders under Access Agents: **"No restricted field exists yet - nothing here needs a
grant."** - correct, since `GET /field-reveal-keys` returns `[]` (no presenter has declared a
`restricted=` key yet). No UUIDs on screen, no explanatory/feature-education copy beyond that
one factual sentence. At 375x812 the card itself measured `left 16, right 359, width 343px` -
entirely inside the 375px viewport, not clipped. **However** `document.documentElement.scrollWidth`
= 439 at 375px viewport (> 375) - the page DOES have horizontal scroll, traced via
`el.scrollWidth` walk to the pre-existing "Access Agents" DataGrid/table (`scrollWidth 1090`,
its own `overflow-x-auto` wrapper) whose containing Card is 422-439px wide instead of
constraining to the viewport - a flex/`min-w-0` gap in a component this PR did not touch. Not a
regression from the Field reveals card (measured separately, entirely in-bounds); flagged as a
pre-existing defect, not filed as a new backlog item by this run.

**Step 3 - Backend spot checks (curl, `http://localhost:8080`, JWT from `POST
/api/v1/auth/login` - the `/system/chatbot/*` routes are `require_permission`, JWT only, no
X-API-Key path):**
  - `GET /api/v1/system/chatbot/field-reveal-keys` -> **200**, `{"items":[]}` (no restricted
    keys declared yet - expected, matches Step 2).
  - `GET /api/v1/system/chatbot/turns/e2c0334d-8a81-4e33-82c8-455fd2f5e48b` -> **200**,
    `trace_detail` present with exactly the nine keys: `stages, parse, decay, open_question,
    focus, tool, crossdomain, reveals, session`.
  - `PUT /api/v1/system/chatbot/contacts/96f2e854-acbe-40e5-89ad-6efb29aa3c4d/field-reveals`
    with `{"granted": ["bogus.key"]}` -> **422**,
    `"Unknown field reveal key(s): bogus.key. Allowed keys: none."`.

**Step 4 - Console.** Chat History / drawer pages: one pre-existing `Each child in a list
should have a unique "key" prop` warning traced to `Demo1Layout` (the shared shell, not this
PR's components). A batch of "Maximum update depth exceeded" errors also showed up in
`errors --json` - traced to the synthetic `dispatchEvent(new Event('input'/'change'))` calls
this run used to drive the native `datetime-local` Filters inputs (CDP has no native way to
type into the two-part date/time spinner), not to real user interaction; not treated as a
product defect. No other console errors on either page.

**Overall: PASS** on AC-963, AC-965 (with the pre-existing Access Agents overflow noted, not
this PR's regression), AC-972, AC-992. AC-973 verified via vitest, not browser (no reachable
live failed turn in this dev environment without altering shared settings).
