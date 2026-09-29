# PLAN: chatbot "SPO" routes to SPO allocations; warehouse filter and sort on PO and SPO asks

Status: IN PROGRESS (small fix track, no UI change, one data migration). Lane PO-SPO-WAREHOUSE,
29 Sep 2026, PR #1373 (branch `claude/po-spo-warehouse-chatbot-1tb9b0`, standing in for
`crew/po-spo-warehouse`).
UAC: `po-spo-warehouse-29sep-acceptance-criteria.md`.

## Owner rulings (29 Sep 2026, verbatim intent)

- "SPO should be SPO allocations answer, not considered incoming." The word SPO routes to
  the `spo_allocation` domain, never `incoming`.
- Warehouse/location filtering on PO (`purchase_order`) and SPO (`spo_allocation`) asks.
- "incoming stays as it is": the incoming domain, its tools and its switch words are
  untouched.
- Scope addition (owner, same day): PO and SPO asks also sort "like the top-100 selling
  items ('sort by doc date, quantity etc')". Owner confirmed verbatim: "parser need to be
  able to extract sort field and sort direction yeah just like top selling, yes, correct,
  won't sort by amount". Sort by AMOUNT is out of scope (no amount column on these rows).
- This lane supersedes line 47 of `PLAN-chatbot-warehouse-entity-and-last-in.md`
  ("`purchase_order` stays as is"); its warehouse resolver (exact normalised code, item 3)
  and its AND-probe rule are reused unchanged.

## Measured on this branch (origin/main de8020fb, re-verified in code)

Routing of the word "SPO":

- `services/chatbot/turn/apply.py:65-71` `DOMAIN_BY_DOCUMENT` maps `"PO" -> purchase_order`
  and `"SPO" -> incoming`. It is the D6 fallback only: `apply.py:3255-3277` reads `asks`,
  then `domain_hint`, then the carried `focus.domains`, and only then the document.
- The live parser body itself is inconsistent. Its domain table says
  `spo_allocation / check_spo -> SPO, SPO allocation`, while the OUTSTANDING block says
  `A document word moves the domain to that document's own ("PO" -> purchase_order, "SPO"
  -> incoming)` (`chatbot_parser_prompt.py`, inside `SEMANTIC_PARSER_PROMPT`, the
  sentence after "NEVER emit domain_hint \"inventory\" with a status set"). The DOCUMENT
  section maps `"SPO", "shipment", "container" -> ["SPO"]`.
- `turn/policy_rows.py:267-278`: the `spo_allocation` row already carries
  `switch_words=["spo"]`, `intents=["check_spo"]`, tool
  `crm_procurement_spo_allocations_last_receipt_list`. `incoming` (`:211-226`) carries
  `["incoming", "eta", "shipment", "shipments", "arriving", "container", "containers"]`.
- No separate "SPO allocations list" tool exists. `sorento_crm_mcp/catalog.py` has exactly
  one SPO tool, `crm_procurement_spo_allocations_last_receipt_list` (`:1321-1360`), route
  `/api/v1/procurement/spo-allocations/last-receipt`. The owner's remembered
  `crm_spo_allocations_list` does not exist; the last-receipt tool IS the SPO allocations
  list (open lines per product, one row each, `top_n` rows when unscoped).

Warehouse entity:

- The parser already extracts a warehouse (`contracts.py` entity hint `warehouse`; the
  short-token-is-a-location cue in `GROWTH_R1_ADDENDUM` is scoped to `domain_hint "order"`
  only). The resolver resolves it by exact normalised code (previous plan, item 3).
- `lanes/business/gate.py:71-120` `ALLOWED`: rows for `spo_allocation` (product, warehouse,
  category, brand), `inventory`, `order`, `purchase_cost`; NO `purchase_order` row, so a PO
  ask passes every entity through unscoped (`gate_reason: domain 'purchase_order' not in
  matrix; passing through unscoped`). `ALLOWS_EMPTY` (`:133-142`) has no `purchase_order`
  row either, which today never matters because the empty check only runs for a domain
  with an `ALLOWED` row.
- `lanes/business/fetch.py:306-332` `TYPE_TO_PARAM["warehouse"] = "warehouse_ids"`. Nothing
  pops `warehouse_ids` for the PO tool. The MCP catalog's PO tool (`catalog.py:1272-1320`)
  does NOT declare `warehouse_ids` in its query params, and the MCP server drops
  undeclared params (`server.py:1548`, `query_params`), so the id never reaches the route.
- `api/v1/procurement/purchase_orders.py:84-134` `/placed` takes `limit`, `product_ids`,
  `expected_date_from/to`, `group_by`, `include_summary`, `sort`, `dir`; no warehouse.
  `services/purchase_order_service.py:60-174`: PO arm joins `Warehouse` on
  `PurchaseOrderLine.warehouse_id` and reports it as `location`; the SPO arm
  (`_unshipped_spo_query`, `:213-239`) reports `location` as the warehouse code else
  `SPOAllocation.location_code`. Sort keys `expected_date | product | supplier |
  outstanding_qty` with a SILENT fallback to `expected_date` on an unknown key (`:94-99`,
  `_SORT_KEY_FIELD :177-182`). Rows carry `po_date` and `ordered_qty`, neither sortable.
- `services/spo_last_receipt_service.py:130-269`: `last_receipt_rows(product_ids,
  warehouse_ids, top_n)` filters `SPOAllocation.warehouse_id.in_(warehouse_ids)` (`:185,
  :241`); fixed order `coalesce(expected_date, issue_date, created_at::date) DESC NULLS
  LAST, created_at DESC`; `top_n` 1..50 (`spo_allocations.py:42`).
- `models/procurement.py:457-472`: `spo_allocations.warehouse_id` is nullable and, per the
  model's own docstring, absent on 6,520 of the captain's own SPO lines; the book's raw
  code is kept in `location_code`. A warehouse filter by id alone therefore misses every
  line whose location we do not hold as a warehouse row.
- `purchase_order_lines.warehouse_id` exists (`models/procurement.py:828`), indexed
  (`:883-884`).

Sort (top selling precedent):

- Parser slots `rank_by`, `basis`, `rank_group`, `rank_direction`, `top_n`
  (`head/parser.py:236-261`), taught by `TOP_SELLING_ADDENDUM`, carried on
  `focus.top_selling` by `turn/apply.py::_top_selling_rules` (`TOP_SELLING_KEYS :1132`),
  mapped to the tool in `fetch.py:812-867`. Only `top_n` is generic: `-> limit` for the PO
  tool, `-> top_n` for the SPO tool (`fetch.py:1064-1076`, `TOP_N_DIRECT_TOOLS :505`).
- Focus axes are carried through `turn/state.py::Focus` + `focus_to_wire`/`focus_from_wire`
  (`:108-160`, `:229-300`); `turn_runtime.lane_parse_output` (`:1440-1530`) is the seam that
  projects a focus axis the message did not name (`sales_channel`, `top_selling`) onto the
  lane's `semantic_input`.
- A message that names no entity, no domain and is `business_query` is planned over the
  carried focus (`apply.py:3255-3260`, `_is_idle_chat :1816` only fires for casual types).

Warehouse coverage, measured read-only by the orchestrator on the shared dev DB
`sorento_cagent_stack` (data as of 2026-09-18, UAC AC-0):

| Table                                          | rows   | with `warehouse_id` | `location_code` only | no location |
| ---------------------------------------------- | ------ | ------------------- | -------------------- | ----------- |
| `purchase_order_lines` open, outstanding > 0   | 3,919  | 2,975 (~76%)        | n/a                  | 944         |
| `spo_allocations`                              | 77,666 | 76,985              | 681                  | 0           |

Coverage is enough to build both halves (orchestrator ruling, 29 Sep 2026). The 681 SPO
lines with a code and no warehouse row are why both PO arms and the SPO tool filter by
`warehouse_id` OR the book's `location_code` (see W3/W4). The ~24% of open PO lines with no
warehouse cannot match any warehouse filter and are correctly absent from a "PO to BRW"
answer. `PLAN-scm-reorder-revamp.md:31`'s "12,928 of 12,940 imported PO lines had no
warehouse" describes an older import, not today's open book.

Alembic on origin/main de8020fb has TWO heads: `eml_0002_seed_layouts` (#1350) and
`mem_0003_parser_history` (#1304). `alembic heads` prints both; `scripts.bootstrap_env`
fails at its final stamp step for the same reason. This lane's migration is a MERGE
revision over both (see M1) so the branch has exactly one head.

## Contract after this plan

### S. "SPO" routes to SPO allocations

- S1. `apply.DOMAIN_BY_DOCUMENT["SPO"] = "spo_allocation"`. `PO -> purchase_order`,
  `SO/DO -> order`, `GRN -> goods_receive` unchanged; `incoming` no longer appears as a
  value of that dict. The `incoming` policy row (tools, switch words, narrowing, ladder)
  is byte-identical.
- S2. Two in-body prompt edits (the same shape as the Known-brands bullet, PR #1301):
  the OUTSTANDING block's `"SPO" ->\nincoming)` becomes `"SPO" ->\nspo_allocation)` (+6),
  and the DOCUMENT section's `"SPO", "shipment", "container" -> ["SPO"]` becomes `"SPO",
  "SPO allocation" -> ["SPO"]` with "shipment" and "container" naming no paper (+74;
  review round: with the SPO document routing to `spo_allocation`, a shipment or
  container turn with no domain and no carry must not fall back there - those are
  incoming's own words). Both recorded on `CONSTANT_CHARS`
  (`test_parser_prompt_is_live.py`) in the same commit.
- S3. New addendum `PO_SPO_WAREHOUSE_ADDENDUM` in `chatbot_parser_prompt.py`, appended
  AFTER `ESCALATION_CONFIRMATION_ADDENDUM` and BEFORE `MEMORY_ADDENDUM` (three tests pin
  `SEMANTIC_PARSER_PROMPT.endswith(MEMORY_ADDENDUM)`), and peeled by
  `_without_growth_r1_addendum` right after `MEMORY_ADDENDUM`. It teaches, with worked
  examples:
  - THE WORD SPO IS AN SPO ALLOCATION ASK: "SPO", "SPO for X", "SPO SRT79-SS", "any SPO",
    "SPO allocations", "SPO at BRW", "SPO for BRW-BB" -> `domain_hint "spo_allocation"`,
    `intent_hint "check_spo"`, `document ["SPO"]`, NEVER `incoming`. `incoming` needs an
    arrival word (ETA, arriving, shipment, container, incoming). "last in" keeps its
    existing cue.
  - A SHORT TOKEN IS A LOCATION UNDER PO AND SPO TOO: the same two shapes the order rule
    names ((a) at most 4 characters, letters or letters with one digit; (b) a hyphenated
    site code of at most 10 characters), after "to", "at", "in", "for" or beside the
    product, is a warehouse entity under `domain_hint "purchase_order"` or
    `"spo_allocation"`. "PO to BRW" -> warehouse BRW, no product; "SPO for BRW-BB" ->
    warehouse BRW-BB; "last in SRTWC286 at BRW" -> product SRTWC286 + warehouse BRW.
  - TWO NEW OUTPUT KEYS on every object: `"sort_by": "date|expected_date|quantity|
    outstanding|received_date|received_quantity|product|supplier|null"` and `"sort_dir":
    "asc|desc|null"`, from the CURRENT message only. Words: "latest first", "newest",
    "most recent", "latest PO" -> `date`/`desc`; "oldest first" -> `date`/`asc`; "by PO
    date", "by SPO date", "by doc date", "by date" -> `date` (dir null unless said);
    "by expected date", "by ETA" -> `expected_date`; "biggest quantity first", "largest
    qty", "most quantity" -> `quantity`/`desc`; "smallest quantity first" ->
    `quantity`/`asc`; "most outstanding", "by outstanding" -> `outstanding`; "by GR date",
    "last received first" -> `received_date`/`desc`; "by received qty" ->
    `received_quantity`; "by product", "by product code" -> `product`; "by supplier" ->
    `supplier`. "by amount", "by value", "by RM" on a PO or SPO ask -> `sort_by` null
    (never `rank_by`). A message that only names a sort under a PO or SPO answer on screen
    ("biggest quantity first", "sort by date") is a refinement: `business_query`,
    `domain_hint` null, `domain_in_message` false, entities [], only the two sort keys set.
    Every other ask leaves both null; never carried by the parser (the engine carries).
- S4. Parser schema (`head/parser.py`): `sort_by` and `sort_dir` as nullable enums,
  in `required` (strict mode) and in `TOLERATED_ABSENT` (no recorded emission carries them).
  `_IDLE_CHAT_DISQUALIFIERS` gains `sort_by`.
- S5. Engine carry: `Focus.sort: dict | None` = `{"by": <sort_by>, "dir": <sort_dir or
  None>}`, on the wire as `"sort"` (`focus_to_wire`/`focus_from_wire`; an old wire with no
  key reads None). `_focus_rules` writes it whenever the verdict names `sort_by`; a
  message that says WHAT it is asking (a NEW ASK, `decision.starts_fresh`, or a domain
  word of its own with no entity, `domain_in_message` true, which `decide()` files as a
  CARRY) and names no sort drops it (rule `new_ask_drops_sort`; review round, blocker 2:
  "PO oldest first" then "any SPO?" must not answer the oldest SPO line); a refinement or
  a sort-only re-sort keeps it; `topic_reset` clears it with the rest.
  `turn_runtime.lane_parse_output` projects `focus.sort` onto `out["sort_by"]` /
  `out["sort_dir"]` when the verdict names none (a DEFAULT, never an override, N2's
  rule), and `lanes/business._fetch_semantic_input` names both keys on the fetch's input
  (review round, blocker 1: without them the transformer read None on every live turn).
- S6. Fetch (`lanes/business/fetch.py::entity_ids_transformer`): a per-tool key map
  `SORT_KEY_BY_TOOL` and a per-key default direction `SORT_DEFAULT_DIR`:

  | parser `sort_by`    | PO tool `sort`   | SPO tool `sort` | default `dir` |
  | ------------------- | ---------------- | --------------- | ------------- |
  | date                | po_date          | spo_date        | desc          |
  | expected_date       | expected_date    | spo_date        | asc           |
  | quantity            | ordered_qty      | spo_quantity    | desc          |
  | outstanding         | outstanding_qty  | (none)          | desc          |
  | received_date       | (none)           | gr_date         | desc          |
  | received_quantity   | (none)           | gr_quantity     | desc          |
  | product             | product          | (none)          | asc           |
  | supplier            | supplier         | (none)          | asc           |

  `sort`/`dir` are emitted only for those two tools and only when the key maps; an unmapped
  key sends nothing (the tool's own default order). `sort_dir` from the parser wins over
  the default. A sort on a RESTRICTED field (`supplier`, key `purchase_orders.supplier`,
  `fetch.RESTRICTED_SORT_KEYS`) is not sent without the grant, the same rule the
  restricted-field drop applies to `group_by=supplier` (security review, finding 1). Row order in the reply is the tool's order (the presenters never re-sort;
  `sorento_crm_mcp/presenters.py:465-530`).
- S7. SPO ask with no product: owner ruling (29 Sep 2026, verbatim) "for SPO question with
  no product name, keep it as it is". The lane adds NO row default: an SPO ask scoped only
  by a warehouse or a sort reaches the tool with no `top_n` and the tool's own unscoped
  default (one row, the newest by the chosen sort) answers. A named count ("last 3",
  "top 20") still travels as `top_n`, exactly as today. (Option (a), a lane-side
  `top_n = 10`, was proposed and declined.)

### W. Warehouse filter

- W1. `gate.ALLOWED["purchase_order"] = ["product", "warehouse", "category", "brand"]`
  (the same row shape as `spo_allocation`) and `gate.ALLOWS_EMPTY["purchase_order"] =
  True`, so a bare "PO" keeps listing the open book exactly as today's unscoped
  pass-through does, while a customer or transporter token no longer rides into the PO
  tool. `answer._SCOPE_WORD["purchase_order"] = "purchase order"` for the miss line the
  new row can now produce. Deliberate behaviour change, pinned by
  `tests/chatbot/test_warehouse_entity.py::TestACustomerOnlyPurchaseOrderAskIsAsked`: a
  PO ask whose only entity is a customer (carried from an order ask) used to list the
  whole open book as if it were that customer's; it now asks for a product code or
  warehouse. Measured on the replay suite (`tests/chatbot/test_replay.py`, 65 passed):
  no graded capture moves on the new row, so no `divergences.py` entry was needed.
- W2. MCP catalog: `crm_procurement_po_placed_list` declares `warehouse_ids`;
  `crm_procurement_spo_allocations_last_receipt_list` declares `sort` and `dir`. Tool
  descriptions name the new params and the sort keys. `mcp_tool_capability_service`
  ToolIntent descriptions mention the warehouse filter and the sort.
- W3. PO `/placed` takes `warehouse_ids` (csv / JSON / repeated, `parse_uuid_list`) and
  passes it to `purchase_orders_placed_rows` and `purchase_orders_placed_summary`. PO arm:
  `PurchaseOrderLine.warehouse_id IN ids`. SPO arm: `SPOAllocation.warehouse_id IN ids OR
  SPOAllocation.location_code IN codes`, where `codes` are the `warehouse_code`s of those
  ids (one company-scoped read of `Warehouse`, done once per call in a helper
  `_warehouse_codes(db, ids)`). The summary applies the identical predicates.
- W4. SPO `/last-receipt`: `warehouse_ids` filters by the same `warehouse_id OR
  location_code` predicate in both branches (helper shared with W3 by importing it from
  `purchase_order_service`), and the row's `warehouse` falls back to `location_code` when
  the line has no warehouse row, so a matched line is not printed without its location.
  Everything else about the tool (window, tiebreak, visible-line clauses, company scope)
  is unchanged.

### O. Sort on the two routes

- O1. PO `/placed`: `sort` in `{expected_date, product, supplier, outstanding_qty, po_date,
  ordered_qty}`, `dir` in `{asc, desc}`; any other value is a 422 `AppException`
  (`code="invalid_sort"` / `"invalid_dir"`, detail naming the allowed set) instead of the
  silent fallback. `po_date` sorts the PO arm on `PurchaseOrder.issue_date` and the SPO arm
  on `SPOAllocation.issue_date`; `ordered_qty` on `PurchaseOrderLine.qty_ordered` /
  `SPOAllocation.allocated_quantity`; `_merge_sorted`'s `_SORT_KEY_FIELD` gains both keys.
  `PO_SORT_KEYS` / `PO_SORT_DIRS` are module constants in `purchase_order_service.py`,
  read by the route.
- O2. SPO `/last-receipt`: new `sort` in `{spo_date, spo_quantity, gr_date, gr_quantity}`
  (default `spo_date`) and `dir` in `{asc, desc}` (default `desc`); unknown -> 422
  (`invalid_sort` / `invalid_dir`). `last_receipt_rows(sort=, dir=)`: the ordering key
  becomes the chosen column (`_key_expr()` for `spo_date`, `allocated_quantity`,
  `gr.c.gr_date`, `quantity_received`), NULLS LAST in either direction, `created_at DESC`
  the tiebreak. The per-product window (`row_number` partition) orders by the same key,
  so "top_n per product" honours the sort; the GR subquery is outer-joined inside the
  windowed query so `gr_date` can order it. `SPO_SORT_KEYS` / `SPO_SORT_DIRS` are module
  constants.

### M. Migration and publish

- M1. `alembic/versions/chatbot_po_spo_warehouse_vocab.py`, `revision =
  "chatbot_po_spo_warehouse_vocab"` (30 chars), `down_revision = "merge_29sep_batch7"`
  (main joined its two heads in #1374; the lane's first cut was a merge revision over
  both and was re-parented onto that join). Body: the `publish()` pattern of
  `chatbot_top_selling_vocab_r6.py` (publish `SEMANTIC_PARSER_PROMPT` as the next
  `chatbot_semantic_parser` version unless a version already carries that exact body;
  never move a label). Re-parent with `scripts/alembic-reparent.sh` before merge if
  main's head moves again.
- M2. `scripts/publish_parser_prompt.py`: the same idempotent publish as a standalone
  script (reads `DATABASE_URL` from the backend env; prints the version it published or
  found). Crew's hand-test copy does not run alembic data migrations, so the orchestrator
  runs this script against the test copy and selects the printed version in the Chatbot
  Console.
- M3. `tests/chatbot/test_parser_prompt_budget.py::CEILING` is raised to the new measured
  value in the same commit, named the way that file names it.

### Out of scope

Sort by amount (owner ruling). Any change to the incoming domain, its tools or its
switch words. A new SPO list tool (the existing one is the list). A UI change (none; no
Lavish mock).

## Work

Backend + MCP catalog, one lane, tester-first (the UAC lists the red tests per AC).

- `app/services/chatbot/turn/apply.py` (`DOMAIN_BY_DOCUMENT`, `_focus_rules`,
  `_IDLE_CHAT_DISQUALIFIERS`), `turn/state.py` (`Focus.sort`, wire),
  `turn_runtime.py` (`lane_parse_output`), `head/parser.py` (schema),
  `chatbot_parser_prompt.py` (S2 edit, `PO_SPO_WAREHOUSE_ADDENDUM`),
  `lanes/business/gate.py` (`ALLOWED`, `ALLOWS_EMPTY`), `lanes/business/answer.py`
  (`_SCOPE_WORD`), `lanes/business/fetch.py` (sort map, SPO list default),
  `api/v1/procurement/purchase_orders.py`, `services/purchase_order_service.py`,
  `api/v1/procurement/spo_allocations.py`, `services/spo_last_receipt_service.py`,
  `services/mcp_tool_capability_service.py`, `sorento_crm_mcp/sorento_crm_mcp/catalog.py`,
  `alembic/versions/chatbot_po_spo_warehouse_vocab.py`, `scripts/publish_parser_prompt.py`,
  `tests/chatbot/divergences.py`, `tests/chatbot/test_parser_prompt_is_live.py`
  (`CONSTANT_CHARS`, peel order), `tests/chatbot/test_parser_prompt_budget.py` (`CEILING`).
- Hand test: `laneboard/scripts/1373.md` (Chatbot Console steps) and
  `tests/chatbot/console_cases/2026-09-29-po-spo-warehouse.yaml` (live-only, not collected
  by pytest).
