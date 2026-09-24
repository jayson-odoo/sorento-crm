# PLAN - Chatbot dealer stock verdict: site-pool availability, per-product quantity, incoming and PO disclaimers

Status: BUILT 22 Sep 2026, DRAFT PR #1118; S0 to S4 files on the lane, review round 1 (reviewer +
security reviewer, Opus) being applied; live journey pass and owner steps pending. Approved by the
owner 22 Sep 2026 on `.lavish/chatbot-dealer-stock-verdict-plan.html` after six markup rounds;
D1 to D26 ruled. Round 6 additions: the ideation lane is wrapped as the second task kind (D26), a
tie between open tasks asks the dealer through a `task_pick` roster (D24), the backend owns
validation (D25). Branch `feat/chatbot-dealer-stock-verdict`, worktree
`sorento_crm-dealer-stock-verdict`, test DB `sorento_ai_automation_rearch_test` (reused from the
merged #952 lane); live pass DB `sorento_ai_automation_rearch`.
UAC: `chatbot-dealer-stock-verdict-acceptance-criteria.md` (AC-1720 to AC-1788, rulings D1 to D26).
Base: `main` at 2280975f9 (includes #952). Branch `feat/chatbot-dealer-stock-verdict`, one lane,
one PR. Owner ruling 22 Sep 2026: "build this full suite now".
Precedents copied, each with the justification that earned it: the `availability` visibility
mode (`PLAN-stock-visibility-policy.md`, archived: enforced in the backend, presented by MCP);
the PO-book site-pool filter (`po_book_service._po_book_sql`: PO counted only where its
destination is an allowed warehouse); the `open_so_qty_by_product_warehouse` split (A2: open SO
subtracted per warehouse, never spread).

## Journey

See the UAC's Journey section (seven steps). Decisions asked of the dealer: only the quantity of a
product they did not give one for, and only once per product. Everything else is derived: the
location set from the policy, the ETA from the book, the lead time from settings, the threshold
from settings.

## What exists, and what is broken

The whole read path already ships and is unreachable:

- `StockService.list_stock(contact_id, space_id, requested_qty)` resolves the contact's policy,
  filters every stock row by `warehouse_criterion(policy, Stock.warehouse_id)`, and under
  `availability` mode emits `stock_availability[]` with `needs_quantity` / `available` and NO rows
  (`app/services/inventory_service.py:1182-1370`). Tests: `tests/test_stock_visibility_policy.py`
  B6 to B9.
- The MCP presenter renders that block as yes / no / ask with an empty field list
  (`sorento_crm_mcp/sorento_crm_mcp/presenters.py:117-120, 1387-1421`).
- The catalog tells the caller to pass `requested_qty` (`catalog.py:471`).
- The engine never does: 0 write sites for `requested_qty` under `app/services/chatbot/`. The
  parser's `demand_qty` is one scalar per turn and feeds only the stock-denial branch
  (`engine.py:1711`, dead when `chatbot_stock_denial_enabled` is off). So an `availability` contact
  is always asked "How many units do you need?" and never answered.

Three things are missing, not broken: `available` ignores open SO, incoming and PO; the quantity is
one number per turn, not one per product; the presenter's intro is one line for the whole reply, so
"noted these, still need those" cannot be said.

## Design

### The verdict, one pure function (S0)

`app/services/stock_verdict.py`:

```
@dataclass(frozen=True)
class Verdict:
    answer: Literal["available", "not_available"]
    running_low: bool                 # answer == available and ask >= T * available
    sources: tuple[str, ...]          # () | ("incoming",) | ("purchase",) | ("incoming", "purchase")
    limited: bool                     # deficit >= T * (sum of the named sources)

def verdict(*, available: int, ask: int, incoming: int, purchase: int, threshold_pct: int) -> Verdict
```

Rule D6, incoming first; T is the configurable threshold (D7). No I/O, no dates: the ETA is data the caller attaches. The 18 owner rows
are the parametrized test (AC-1720). This is the one decision seam every arm passes through.

### The server block (S1)

`_apply_stock_visibility`, `availability` branch only, gains four reads per page of products, all
filtered by the SAME `warehouse_criterion(policy, <table>.warehouse_id)`:

| figure | source | predicate |
|---|---|---|
| on hand | `stock.quantity_on_hand` | today's `policy_q` |
| open SO | `sales_order_lines`, `qty_ordered - qty_delivered` | `line_status = 'open'`, delta > 0, `warehouse_id` in the set (lines with no warehouse are not subtracted, D2) |
| incoming | `spo_allocations`, `allocated_quantity - COALESCE(quantity_received, 0)` | the `scm.on_order_v` predicate verbatim (open line, not received, shipment not in a received state, `warehouse_id` not null) plus the policy set; ETA = `MIN(expected_date)` (D10) |
| purchase | `purchase_order_lines`, `qty_ordered - qty_received` | `line_status = 'open'`, delta > 0, PO status in the PO-book set, `warehouse_id` not null (D8) and in the policy set |

`requested_quantities` (JSON object, product UUID to int) joins `requested_qty` on the route and
the service; per product the map wins, the scalar fills the rest (D20). A product with neither
keeps today's `needs_quantity: true, available: null`. A product with an ask gets:

```
{
  "product_id", "product_code", "product_name",
  "needs_quantity": false, "requested_qty": 110,
  "available": false,                       # kept: the presenter's existing key
  "verdict": "not_available", "running_low": false,
  "disclaimer": {"sources": ["incoming"], "limited": true,
                 "incoming_eta": "2026-10-12", "purchase_eta_days": null}
}
```

`purchase_eta_days` is set only when `purchase` is itself a named source; here `sources` names
`incoming` alone, so it stays `null` even though a purchase line may also exist.

`disclaimer` is `null` when `sources` is empty. No quantity of ours is in the block; the existing
`_assert_no_quantity_anywhere` sweep guards it (AC-1740 to AC-1752). `detailed` and `compact`
paths do not read the new param (AC-1750).

Setting: `system_settings.chatbot_stock_low_threshold_pct` (int, 1 to 100, default 50), migration
`dsv_0001`, added to `SystemSettingUpdate`, the `get_settings()` dict and the lane's `Policy`
load. Not on `get_app_config()` (not public). `default_product_standard_lead_time_days` is read as
it stands for `purchase_eta_days` (D3).

### The presenter (S2)

`_stock_availability` renders one line per entry from the flags (AC-1755, AC-1756):

```
MWT5727SS-CR x 5: Yes, available.
MHS1028 x 60: Yes, available, but running low.
MSK11A-QT x 110: Not available, but there is limited incoming, ETA 12/10/2026 and limited purchase, ETA in 90 days.
```

`_availability_intro` keeps its three whole-reply lines and gains the question shape when any
entry needs a quantity (AC-1757): `Noted: A x 5, B x 60` then `How many units do you need for C
and D?`. Copy stays in the presenter, where the availability copy already lives; the engine's
composer folds the rendered lines as it does for every stock item today. The catalog gains
`requested_quantities` (AC-1759).

### The engine (S3)

Four small seams, all on the new `turn/` package, none adding a table:

1. **Parser schema** (`head/parser.py`): `entities[].quantity: number | null` and a generic
   `proceed_anyway: boolean | null`. Both `required`, both named in the fallback prompt text and
   in the published prompt (owner publishes, D13). The schema guard test extends (AC-1760).
   `demand_qty` stays for the denial branch and for the single-product fallback.
2. **Focus** (`turn/state.py`): entity dicts gain a `quantity` key. `focus_to_wire` /
   `focus_from_wire` pass entity dicts through `_entity()` opaquely, so no wire change; one test
   pins the round trip (AC-1769). Merge rule in `_focus_rules`: same product (uuid or
   canonical_code) replaces `quantity` when the new entity carries one (D16).
3. **The open task on the focus** (`turn/task.py`, new; `Focus.task`; D21 to D23). The
   owner's requirement is a collection that survives a detour: "I can jump out, ask other
   things, and jump back in", and it belongs on the context: "I thought we have focus and it is
   meant for this". Focus is the context. It holds what the conversation is ABOUT (products,
   customer, dates, document, status, ...); it does not hold what is still OWED. Neither does
   `pending`: a genuine new ask clears it (`apply.py:1562`, `new_ask_closes_stale_roster`), and
   that rule is right for a roster, pinned by `handpass5-stale-roster-forms`. A detour also
   rewrites `focus.products` by same-axis replace ("any promotion on MSK11A-QT?" leaves only
   that product), so the owed list cannot ride on `focus.products` alone. Hence one new axis:

   ```
   @dataclass(frozen=True)
   class Task:
       kind: str                 # "stock_qty", the only production kind
       domain: str               # "inventory"
       slots: tuple[Slot, ...]   # Slot(key=product uuid, label=code, value=quantity | None)
       status: Literal["open", "parked"]
       opened_at_turn: int

   class TaskKind(Protocol):     # one implementation today, the contract for the next
       def missing(self, task) -> tuple[Slot, ...]
       def fill(self, task, verdict) -> Task          # pure: reads entities[].quantity, proceed_anyway, demand_qty fallback
       def to_fetch(self, task) -> FetchSpec           # the domain fetch once complete
       def question(self, task) -> str                 # "Noted: ... Still needs a quantity for: ..."
   TASK_KINDS = {"stock_qty": StockQtyTask()}
   ```

   `Focus.tasks: tuple[Task, ...]`, at most one per kind, carried by `focus_to_wire` /
   `focus_from_wire` like the other axes (no new session key). A list from day one, not a
   single slot: the owner's second case is real today (the ideation lane already collects across
   turns in its own opaque `session.ideation`), and the concurrency rules are D24. `TaskKind`
   gains `claims(verdict) -> bool` so a value is routed to the task that owns it.

   Where it slots into the seven-stage turn (`engine.py`, A to G of the rearch plan):

   ```
   A INTAKE   load state: focus (with tasks), pending, profile
   B PARSER   hint block gains one "Open task: ..." line per open task (most recently touched first)
   C APPLY    task rules run BEFORE decide's four outcomes: claims -> fill; complete -> to_fetch; park / resume
   D ROUTE    unchanged: a completed task's fetch is a business fetch
   E FETCH    unchanged: requested_quantities from the task's slots
   F COMPOSE  Answer.task = the ONE task to ask for this turn (opened or touched)
   G TAIL     focus_to_wire persists tasks; pending untouched
   ``` It is semantic: the parser reads it every turn as one hint line
   and the dealer's words drive it (add a product, change a quantity, drop one, proceed, never
   mind), never a switch or a timer. Lifecycle, each a named rule in `apply` and a replay case:
   - **open**: the composer's `Answer.task` when the stock tool reply has any `needs_quantity`
     entry; the engine never decides who is a dealer, the server's block does (D12).
   - **fill** (before `decide`'s four outcomes, independent of domain): any verdict whose
     `entities[]` carry a quantity for a slot key, or `proceed_anyway`, or the D13 single-slot
     `demand_qty` fallback. A quantity for a product not in the task, on the task's domain,
     adds a slot (D16). Complete: `plan.fetch = [kind.to_fetch(task)]` (the `domain_locked`
     precedent, `apply.py:1414-1431`), task cleared after the answer.
   - **park**: a `NEW_ASK` or a `topic_reset` for another domain sets `status = parked`; the
     reset's wipe of the focus keeps `task` (added to `RESET_KEEPS` when aimed elsewhere); the
     other answer runs as today; the reply says nothing about the task (D22).
   - **resume**: a verdict on the task's domain with no entities and no quantity while a task
     is parked re-asks `kind.question(task)` and sets `status = open` (D22).
   - **close**: only through the dealer's own words: complete; `proceed_anyway`;
     `scope_exclusive` new product set on the task's domain; `topic_reset` aimed at the task's
     own domain (D23). Never a TTL, never a Respond.io conversation close, never a manual
     action: the task is continuous.
   - **hint**: `build_user_block` adds `Open task: stock check. Noted: A x 5. Still needs a
     quantity for: C, D.`; the system prompt gains one rule so the LLM fills `entities[].quantity`
     for a named task product whatever the current subject, and reads add / drop / change /
     proceed / never mind as instructions on the task (AC-1778).
   The roster `pending` and a task can be open at once (an ambiguous code inside a stock ask):
   `decide` handles the roster first, the picked product joins the task as a slot (AC-1773).
   Two tasks at once follow D24: each value to the kind that claims it; a tie the parser does
   not settle asks the dealer through a `task_pick` roster (the existing pending roster
   mechanism, options = the open tasks); one task asked per turn; resume by the named domain
   (AC-1779).

   **Ideation, the second kind (D26).** Measured: the lane is a passthrough to
   `crm_ideation_turn`, its state is the opaque `session.ideation` pointer the tail re-persists
   every turn, it runs whenever the parser routes `ideate`, its media menu answers by
   `reference_positions`. So the state already survives a detour and already resumes on
   routing. `IdeationTask` adds only what is missing: open / parked status on `Focus.tasks`, the
   parser hint (`Open task: idea in progress.`), the D24 tie, close on the tool's `complete` or
   a reset aimed at ideation. No slots of its own, no copy of the pointer, same single writer
   (AC-1784 to AC-1788). It is the second kind that proves the seam; a throwaway third kind in
   a test proves no engine change is needed for the next (AC-1777).
4. **Fetch args** (`lanes/business/fetch.py`, the `crm_inventory_stock_balance_list` branch that
   already sets `include_sellable`): `requested_quantities` = `{uuid: quantity}` over the fetch
   spec's entities that carry one. On `proceed_anyway`, slots without a quantity are dropped
   from the call and the composer appends `Not checked: C, D` (D15).

Nothing reads `message.text`; `apply()` stays pure (AC-1768).

### Who validates (D25)

```
BACKEND endpoint      owns the rule       "for THIS contact, under THIS policy, a quantity is
                                           required": replies needs_quantity per product
MCP catalog ToolSpec  declares contract   param requested_quantities in, key needs_quantity out;
                                           sync_catalog -> mcp_tools; never validates
ENGINE TaskKind       generic             gap key -> slots, param <- slot values; no domain rule
```

The MCP is not the place for validation: it is a stateless read-only HTTP wrapper shared with
n8n and direct callers, and the rule depends on the contact's policy row and live data that only
the backend holds. The MCP is the right place to DECLARE the contract, and it already is
(`ToolSpec` params + `restricted_fields`, synced into `mcp_tools`). `StockQtyTask` binds
`needs_quantity` to `requested_quantities` by name in this lane; a `ToolSpec.collects`
declaration that a generic kind could read is the named trigger for the second form.

### Simplest thing that works, checked

- No new table. One column. One pure function. One new focus axis (a list, two kinds). Two
  parser keys. No new session key; `session.ideation` untouched.
- The task is an axis on the focus, not a change to `pending`, because the two have opposite
  rules on a new ask (a roster must close, a task must park) and both are pinned by journeys.
  The `TaskKind` protocol is the owner's asked-for scalability seam; its registry has one entry
  and the second kind pays for nothing more than its own class.
- No per-domain rule config: the verdict rule has exactly one arm (inventory) and one threshold.
  Trigger for a table: a second domain wanting a threshold of its own.
- The dealer's location set is the policy that already exists and already has an admin page.
  No `site_pool` flag is read: the owner named the allowed set, and the policy stores it.
- No engine-side knowledge of policy mode: the ask is armed because the server said
  `needs_quantity`, which is what the mode already means.
- Incoming and PO are not netted against each other: measured disjoint (0 overlap rows). Trigger
  for netting: a PO line that carries an open allocation.
- Copy lives where the availability copy lives today (MCP presenter). No copy registry entry.

## Slices

| slice | scope | ACs |
|---|---|---|
| S0 | `stock_verdict.py` + 18-row tests; migration `dsv_0001` + setting on both builders; Settings > Chatbot card (Phase 1 mock, then real in the same slice since the endpoint exists) | AC-1720 to 1733 |
| S1 | `inventory_service.py` availability block: open SO, incoming, PO at policy warehouses; `requested_quantities` on route + service; response model keys | AC-1740 to 1752 |
| S2 | MCP catalog param; presenter per-item lines and the noted / missing question; `sync_catalog` | AC-1755 to 1759 |
| S3 | parser schema + fallback prompt + guard + task hint; Focus quantity; `turn/task.py` (Task, TaskKind, StockQtyTask, IdeationTask, `task_pick` roster) on `Focus.tasks`; apply rules open / fill / park / resume / close / tie; fetch args; composer `Not checked`; replay fixtures and chains | AC-1760 to 1779, 1784 to 1788 |
| S4 | journey JSON + console YAML, one live pass on the lane stack; guide; PR with owner steps (publish prompt, three policy rows) | AC-1780 to 1783 |

Phase 1 (frontend-first) for this lane is the settings card only; the chat reply contract above is
the Phase 1 contract for S1 to S3 and is fixed before any backend code.

## Testing seams (agreed before Phase 2)

- `verdict()` is pure: a table of `(available, ask, incoming, purchase, T)` to `Verdict`.
- The server block is tested through `StockService.list_stock` with seeded rows, the pattern of
  `tests/test_stock_visibility_policy.py` (fixtures `_three_warehouses`, `_contact`,
  `_policy_row`, `_assert_no_quantity_anywhere`), plus seeded `spo_allocations`,
  `inbound_shipments`, `purchase_orders`, `purchase_order_lines`, `sales_order_lines`.
- The presenter is tested on payload dicts (MCP pytest), text asserted exactly.
- The engine is tested with the parser verdict supplied and the MCP tool stubbed
  (`tests/chatbot/replay_turns/console/*.json`, `test_turn_replay.py`) and by `apply` table
  tests. No live parser in CI (owner rule 20 Sep 2026).
- One live pass at the end: `scripts/chatbot_journey.py` on the lane stack, then the console YAML,
  then the owner.

### Captain's test list (one line per AC, for the tester)

- AC-1720 `test_verdict_matches_owner_matrix[row]`: the 18 rows, tuple equality.
- AC-1721 `test_verdict_zero_available_incoming_only` / `_both_limited`.
- AC-1722 `test_verdict_rejects_non_positive_ask`.
- AC-1723 `test_verdict_threshold_is_inclusive`.
- AC-1730 `test_dsv_0001_adds_threshold_column_default_50`.
- AC-1731 `test_settings_put_threshold_roundtrip_and_bounds`.
- AC-1732 `StockLowThresholdCard.test.tsx`: renders value, saves, error toast.
- AC-1740 `test_availability_subtracts_open_so_inside_policy_only`.
- AC-1741 `test_availability_running_low_at_threshold`.
- AC-1742 `test_availability_incoming_covers_deficit_po_ignored`.
- AC-1743 `test_availability_incoming_plus_po_both_limited`.
- AC-1744 `test_availability_po_only_not_limited`.
- AC-1745 `test_availability_supply_outside_policy_not_named`.
- AC-1746 `test_availability_null_destination_not_counted`.
- AC-1747 `test_availability_incoming_eta_is_earliest_or_null`.
- AC-1748 `test_availability_reads_lead_time_and_threshold_settings`.
- AC-1749 `test_availability_per_product_map_wins_scalar_fills`.
- AC-1750 `test_detailed_and_compact_ignore_requested_quantities`.
- AC-1751 `test_availability_received_or_closed_supply_not_counted`.
- AC-1752 `test_route_rejects_bad_requested_quantities_and_declares_keys`.
- AC-1755 to 1758 `test_presenters_availability_lines.py`: one test per sentence; regex sweep.
- AC-1759 `test_catalog_stock_balance_requested_quantities`.
- AC-1760 `test_parser_schema_declares_quantity_and_proceed`.
- AC-1761 `case-dsv-01-four-products-two-quantities-asks.json`.
- AC-1762 `case-dsv-02-quantities-complete-answers.json`.
- AC-1763 `case-dsv-03-proceed-anyway-not-checked.json`.
- AC-1764 `case-dsv-04-restated-quantity-replaces.json`.
- AC-1765 `test_apply_stock_qty_bare_number_single_missing` / `_two_missing_reasks`.
- AC-1766 `test_apply_stock_qty_cleared_on_topic_reset`.
- AC-1767 `case-dsv-05-detailed-contact-unchanged.json`.
- AC-1768 existing `test_rearch_s2_apply_is_pure.py` stays green.
- AC-1769 `test_focus_entity_quantity_round_trip`.
- AC-1770 `test_focus_task_wire_round_trip`.
- AC-1771 `case-dsv-06-detour-parks-then-fills.json` (three turns).
- AC-1772 `case-dsv-07-resume-by-naming-reasks-missing.json`.
- AC-1773 `case-dsv-08-roster-inside-form.json`.
- AC-1774 `case-dsv-09-proceed-while-parked.json`.
- AC-1775 `test_apply_task_survives_twelve_carry_turns`.
- AC-1776 existing journeys + replay corpus green (CI).
- AC-1777 `test_task_kind_protocol_second_kind_drives_same_seams`.
- AC-1778 `test_parser_block_open_task_line` + schema guard.
- AC-1779 `test_apply_two_tasks_claims_and_task_pick_tie` + `case-dsv-10-tie-asks-which-task.json`.
- AC-1784 `case-dsv-11-ideation-opens-task.json`.
- AC-1785 `case-dsv-12-ideation-parks-on-stock-ask-resumes-by-naming.json`.
- AC-1786 `test_apply_ideation_task_closes_on_complete_or_reset`.
- AC-1787 `test_parser_block_open_task_idea_line`.
- AC-1788 existing ideate tests green (CI).

## Owner steps after merge

1. Publish the parser prompt version that names `entities[].quantity` and `proceed_anyway`
   (Prompts page; the lane ships the new fallback text and a draft version).
2. Create three access-type policy rows on the stock visibility admin page: `dealer`,
   `cabana_dealer`, `mocha_dealer`; mode `availability`; warehouses BRW + MWH (D12).
3. Deploy with go; run the console YAML on prod per `chatbot-verification.md`.

## Found by the live pass (22 Sep, three runs)

Every unit, replay, presenter and CI gate was green and two reviews said READY before the one
live pass ran; it failed 23 of 28 turns from causes no stub could see:

1. `requested_quantities` never reached the backend: FastMCP pre-parses a JSON-looking string
   argument into a dict before validation and the compiled tool's scalar-only union rejected it
   (D28; fixed MCP-side in review round 4, `TOOL_OBJECT_QUERY_PARAMS`).
2. The verdict sentence lived only in the presenter item `title`, which the shared composer never
   printed (review round 3: `_item_line` falls back to the title; the numbered list is
   suppressed while any product still needs a quantity).
3. The same product code in two of the dealer's companies produced two entries and a doubled
   question (D27; review round 5).
4. The block never reached the engine: the presenter built the sentence from `stock_availability`
   and dropped it from the render envelope, so no task survived a turn while every reply looked
   right (D30; review round 6, `_PASSTHROUGH_KEYS`). Six task-seam rules were then pinned from
   the real traces (fill never drops open slots, ask order kept, exact code for a quantity-bearing
   entity D29, `demand_qty` on open, resume makes no call, close clears the products axis).

The lesson is recorded in `LESSONS-LEARNT.md`: a new MCP tool parameter needs a test through the
COMPILED tool with the real value shape, and a chatbot lane keeps its one live pass at the end.

## Risks

- Until the prompt is published, only single-product asks capture a quantity (the D13 fallback).
  Multi-product asks are asked per product until then. Named in the PR.
- 24% of open PO lines have no destination and are invisible to dealers under D8. If the owner
  flips D8, the change is one predicate in S1.
- The lane's replay fixtures record verdicts by hand (no live parser); the one live journey pass
  is what checks the parser actually emits `quantity` per entity.

## Backlog (documentation/backlogs/backlog.md)

- Per-product threshold or per-domain rule table: build when a second arm needs one.
- Dealer ETA from the PO line's `expected_date` instead of the lead-time phrase: owner declined
  for v1 (D3).
