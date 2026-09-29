# UAC: chatbot "SPO" routes to SPO allocations; warehouse filter and sort on PO and SPO asks

Plan: `PLAN-po-spo-warehouse-29sep.md`. Lane PO-SPO-WAREHOUSE, PR #1373.

Every AC names the red test that proves it. Parser ACs are graded OFFLINE against the
prompt text, the schema and the code (the repo's corpus mechanism,
`tests/chatbot/fixtures/parser_growth_r1_phrases.json` + its reachability test); whether
the model obeys is the console case's job (AC-14), never pytest's.

## AC-0 Coverage measurement (orchestrator, read-only on the dev DB)

Run and paste the numbers into the PLAN's "Measured" section:

```sql
SELECT count(*) AS po_lines,
       count(*) FILTER (WHERE warehouse_id IS NOT NULL) AS po_lines_with_warehouse
FROM purchase_order_lines WHERE line_status = 'open' AND qty_ordered - qty_received > 0;

SELECT count(*) AS spo_lines,
       count(*) FILTER (WHERE warehouse_id IS NOT NULL) AS spo_with_warehouse_id,
       count(*) FILTER (WHERE warehouse_id IS NULL AND location_code IS NOT NULL) AS spo_code_only,
       count(*) FILTER (WHERE warehouse_id IS NULL AND location_code IS NULL) AS spo_no_location
FROM spo_allocations;
```

Not a gate on the build: both filters match by `warehouse_id` OR `location_code` (W3/W4).

## Routing (S1..S4)

- AC-1 `DOMAIN_BY_DOCUMENT["SPO"] == "spo_allocation"`; `PO`, `SO`, `DO`, `GRN` unchanged;
  `"incoming"` is not a value of the dict. `apply()` over a verdict carrying
  `document: ["SPO"]`, no `domain_hint`, no `asks`, empty focus plans
  `domains == ["spo_allocation"]` with `domain_follows_document` fired; the same with
  `["PO"]` plans `purchase_order`.
  Test: `tests/chatbot/test_po_spo_warehouse_routing.py::TestSpoDocumentRoutesToSpoAllocation`.
- AC-2 The `incoming` policy row is byte-identical to main (tools, switch words, narrowing,
  ladder pinned as literals); `spo_allocation`'s switch words still contain `"spo"`.
  Test: `test_po_spo_warehouse_routing.py::TestIncomingIsUntouched`.
- AC-3 The prompt no longer says `"SPO" ->\nincoming` anywhere and does say `"SPO" ->\n
  spo_allocation` once (in-body edit S2). `CONSTANT_CHARS` in
  `test_parser_prompt_is_live.py` records the +6.
  Test: `tests/chatbot/test_parser_po_spo_warehouse_words.py::TestTheBodyNoLongerSendsSpoToIncoming`.
- AC-4 `PO_SPO_WAREHOUSE_ADDENDUM` exists, is appended to `SEMANTIC_PARSER_PROMPT` after
  `ESCALATION_CONFIRMATION_ADDENDUM` and before `MEMORY_ADDENDUM` (the prompt still ends
  with `MEMORY_ADDENDUM`), and every `cue` in
  `tests/chatbot/fixtures/parser_po_spo_warehouse_phrases.json` is present verbatim in
  it. Every `expect.domain_hint` / `expect.intent_hint` in that corpus is declared
  vocabulary (`contracts.DOMAIN_HINTS` / `INTENT_HINTS`); every `expect.sort_by` /
  `expect.sort_dir` is in the schema enum. The corpus includes at least: "PO to BRW",
  "SPO for BRW-BB", "SPO SRT79-SS", "last in SRTWC286 at BRW", "latest PO for SRT79-SS",
  "SPO biggest quantity first at BRW", "oldest PO first", "SPO by GR date", "PO by
  supplier", "SPO by amount" (sort_by null), "biggest quantity first" (refinement: no
  domain, no entities).
  Test: `test_parser_po_spo_warehouse_words.py::TestTheAddendumIsTaught` (+ `_bodies` /
  stacking-order test pinning the peel order in `_without_growth_r1_addendum`).
- AC-5 `head/parser.PARSE_OUTPUT_JSON_SCHEMA` declares `sort_by` (enum: date,
  expected_date, quantity, outstanding, received_date, received_quantity, product,
  supplier, null) and `sort_dir` (asc, desc, null); both in `required`, both in
  `TOLERATED_ABSENT`; the prompt's OUTPUT text names both keys; `_IDLE_CHAT_DISQUALIFIERS`
  contains `sort_by`.
  Test: `test_parser_po_spo_warehouse_words.py::TestTheSchemaDeclaresTheSortKeys`.

## Engine carry (S5)

- AC-6 `Focus` has `sort: dict | None` (default None); `focus_to_wire` writes `"sort"`;
  `focus_from_wire` reads it back and reads None from a wire without the key.
  Test: `tests/chatbot/test_po_spo_sort_focus.py::TestFocusSortWire`.
- AC-7 Through `apply()`: (a) a purchase_order verdict with `sort_by: "quantity",
  sort_dir: "desc"` writes `focus.sort == {"by": "quantity", "dir": "desc"}`; (b) a later
  sort-only verdict (`business_query`, `domain_hint` None, entities [],
  `domain_in_message` False, `sort_by: "date"`) over that focus plans a
  `purchase_order` fetch (not idle chat) and replaces the sort; (c) a NEW ASK
  (`domain_in_message` True with an entity, another domain) drops `focus.sort`
  (`new_ask_drops_sort` fired); (d) a refinement (entity only, `domain_in_message`
  False) keeps it; (e) `topic_reset` clears it.
  Test: `test_po_spo_sort_focus.py::TestSortCarriesLikeTheDateWindow`.
- AC-8 `turn_runtime.lane_parse_output(verdict, focus=...)` sets `sort_by`/`sort_dir` from
  `focus.sort` when the verdict names none, and leaves the verdict's own values when it
  does.
  Test: `test_po_spo_sort_focus.py::TestLaneParseOutputProjectsTheSort`.

## Fetch (S6, S7) and gate (W1)

- AC-9 `fetch.entity_ids_transformer`: for `crm_procurement_po_placed_list`,
  `sort_by` date/expected_date/quantity/outstanding/product/supplier map to
  po_date/expected_date/ordered_qty/outstanding_qty/product/supplier with the default
  dirs of the PLAN table; for `crm_procurement_spo_allocations_last_receipt_list`,
  date/expected_date/quantity/received_date/received_quantity map to
  spo_date/spo_date/spo_quantity/gr_date/gr_quantity; a parser `sort_dir` wins over the
  default; an unmapped key (`supplier` on the SPO tool, `received_date` on the PO tool)
  sends neither `sort` nor `dir`; a tool outside the two (`crm_inventory_stock_balance_list`)
  never gets `sort`/`dir`.
  Test: `tests/chatbot/test_po_spo_sort_fetch.py::TestSortMapsPerTool`.
- AC-10 A resolved warehouse entity on the PO tool becomes `warehouse_ids`; on the SPO
  tool with no `product_ids` and no `top_n`, the args carry `top_n == 10`; a named `top_n`
  wins; with `product_ids` present no default is added.
  Test: `test_po_spo_sort_fetch.py::TestWarehouseAndListDefault`.
- AC-11 `run_gate` under `domain_hint "purchase_order"` keeps product + warehouse, drops a
  customer, and passes a zero-entity ask (`gate_passed` True, reason names `permits
  broad query`); `answer._SCOPE_WORD["purchase_order"]` exists.
  Test: `tests/chatbot/test_warehouse_entity.py::TestGateKeepsWarehouseOnPurchaseOrder`.
  The replay suite (`tests/chatbot/test_replay.py`) stays green with fixture-scoped
  divergences for the 8 purchase_order captures.

## Routes and services (W2..W4, O1, O2)

- AC-12 PO `/placed` and `purchase_orders_placed_rows`: (a) `warehouse_ids` keeps only PO
  lines at those warehouses; (b) an SPO allocation with `warehouse_id` set matches by id,
  and one with `warehouse_id` NULL and `location_code` equal to that warehouse's code
  matches by code; (c) `purchase_orders_placed_summary` counts exactly the filtered rows;
  (d) `sort=po_date&dir=desc` orders PO and SPO rows together by document date, and
  `sort=ordered_qty` by ordered quantity; (e) `sort=bogus` -> 422 `invalid_sort`,
  `dir=sideways` -> 422 `invalid_dir`; (f) the route passes `warehouse_ids` through.
  Test: `tests/test_purchase_orders_placed.py::test_po_warehouse_filter_*`,
  `::test_po_sort_po_date_and_ordered_qty`, `::test_route_rejects_unknown_sort_and_dir`.
- AC-13 SPO `/last-receipt` and `last_receipt_rows`: (a) `sort=spo_quantity&dir=desc` puts
  the largest line first (per product, and unscoped); (b) `sort=gr_quantity`,
  `sort=gr_date`, `sort=spo_date&dir=asc` order as named, nulls last; (c) default is
  unchanged (spo_date desc); (d) `sort=bogus` / `dir=bogus` -> 422; (e) a `warehouse_ids`
  filter matches a line with `warehouse_id` NULL and `location_code` equal to the
  warehouse's code, and that row's `warehouse` reads the code.
  Test: `tests/test_spo_last_receipt.py::test_sort_*`, `::test_warehouse_filter_matches_location_code`.
- AC-14 MCP catalog: `crm_procurement_po_placed_list.query_params` contains
  `warehouse_ids`; `crm_procurement_spo_allocations_last_receipt_list.query_params`
  contains `sort` and `dir`.
  Test: `sorento_crm_mcp/tests/test_catalog_po_spo_warehouse.py`.

## Migration and publish (M1..M3)

- AC-15 `alembic/versions/chatbot_po_spo_warehouse_vocab.py` exists, `revision ==
  "chatbot_po_spo_warehouse_vocab"`, its `down_revision` is exactly the set of heads the
  graph has without it (a merge revision; the graph with it has ONE head), `publish()`
  publishes `SEMANTIC_PARSER_PROMPT` (carrying `PO_SPO_WAREHOUSE_ADDENDUM`) as the next
  version on a blank database, a second call publishes nothing, and no `production`
  label moves.
  Test: `tests/chatbot/test_po_spo_warehouse_publish.py` (Postgres, `blank_session`).
- AC-16 `scripts/publish_parser_prompt.py` publishes the same body idempotently and prints
  the version.
  Test: `test_po_spo_warehouse_publish.py::test_the_script_publishes_the_same_body`.
- AC-17 `test_parser_prompt_budget.py` CEILING raised to the new measured value in the same
  commit (the addendum is new content that must land).

## Hand test (owner, Chatbot Console on the crew test copy)

- AC-18 `laneboard/scripts/1373.md` and
  `tests/chatbot/console_cases/2026-09-29-po-spo-warehouse.yaml` carry: "PO to BRW"
  (PO placed rows, every `Location` BRW), "SPO for BRW-BB" (SPO lines at BRW-BB, up to
  10), "SPO SRT79-SS" (SPO line(s) for that product, not incoming), "last in SRTWC286 at
  BRW" (unchanged behaviour, one row per product at BRW), "latest PO for SRT79-SS"
  (PO rows newest PO Date first), "SPO biggest quantity first at BRW" (SPO Quantity
  descending), then "oldest first" alone (same list re-sorted).
