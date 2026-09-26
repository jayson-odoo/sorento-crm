# PLAN: PO placed fields and cross-domain rung wording

Status: implemented (PR pending)
Branch: `fix/po-placed-fields-and-rung-wording` (worktree `.claude/worktrees/po-placed-fields`)
UAC: `po-placed-fields-and-rung-wording-acceptance-criteria.md`

## Owner ruling (11 Sep 2026, from a live turn on SRTWC191-G3)

1. `crm_procurement_po_placed_list` renders per row, in order: Company (when present), PO
   Number, Product Code, Ordered Qty, Outstanding Qty, PO Date, Location, Supplier
   (restricted `purchase_orders.supplier`, unchanged). Source (`kind`) and Expected Date
   are dropped from the rendered fields. `kind`, when the row has one, moves to the ITEM's
   own top level (sibling of `title`/`fields`/`flags`) so the chatbot rung can still tell a
   PO row from an SPO row with no rendered Source field.
2. The cross-domain PO rung answers as one field per line per row - `Product Code:`,
   `Ordered:`, `Outstanding:`, `PO date:`, `Location:` - rows separated by ONE blank line.
   A null or empty `ordered_qty`, `po_date` or `location` omits that line entirely (never a
   placeholder); `Product Code:` and `Outstanding:` always print. This retires the old
   `Qty N placed on DATE` shape.
3. `purchase_orders_placed_rows` (backend) adds `ordered_qty` and `location` to every row:
   PO side from the line's own `qty_ordered` and its warehouse code (via a new outerjoin,
   None when the line has no warehouse or the warehouse falls outside the caller's company
   scope); SPO side from the allocation's `allocated_quantity` and its warehouse code, else
   the book's raw `location_code`, else None.

## Files touched

- `sorento_crm_backend/app/services/purchase_order_service.py` - `ordered_qty` + `location`
  on both the PO and SPO row-building loops, plus a `Warehouse` outerjoin on both queries.
- `sorento_crm_mcp/sorento_crm_mcp/presenters.py` - `_purchase_orders_placed` field order,
  drops Source/Expected Date, stamps `kind` on the item's top level.
- `sorento_crm_mcp/sorento_crm_mcp/catalog.py` - `crm_procurement_po_placed_list`
  description's field list and date-window note.
- `sorento_crm_backend/app/services/chatbot/lanes/business/answer.py` -
  `_crossdomain_rung_row` reads `kind` from the item's top level only (no fallback);
  `_crossdomain_rung_text` renders the structured per-row block.
- Tests: `sorento_crm_mcp/tests/test_presenters.py`,
  `sorento_crm_backend/tests/test_purchase_orders_placed.py`,
  `sorento_crm_backend/tests/chatbot/test_crossdomain_ladder.py`,
  `sorento_crm_backend/tests/chatbot/test_foundre_rung_end_to_end.py`,
  `sorento_crm_backend/tests/chatbot/console_cases/2026-09-07-growth-r1.yaml` (expectations
  only, not pytest-collected).

## Not observed live

The multi-row, blank-line-separated block is unit-tested only. Every candidate product in
the lane DB (`sorento_ai_automation_popf`) that carries several open PO lines - e.g.
SRTWCY7405-PJ, named in the review brief - also holds real physical stock at several
locations, so the chatbot answers on the stock rung and the PO rung never fires for it; see
`documentation/plans/chatbot/evidence/po-placed-fields-11sep/console-check.md` section C.
The underlying multi-row data and the single-row live turn (SRTWC191-G3, section B of that
file) both confirm the shape; the multi-block chat rendering itself was confirmed at the
unit-test level (`TestOwner11SepTheRungRendersStructuredFieldsPerRow`), not against a live
turn.

## Slice 2, 11 Sep 2026 (owner ruling, second ruling on the same turn family)

- R1: `crossdomain_probe_args` gains `granted`, stamping `"access": {"attributes": [...]}`
  on the first cross-domain probe's args when non-empty, so `entity_ids_transformer`
  (`fetch.py`) sets `include_sellable` and the stock block carries Outstanding like a
  direct stock ask.
- R2: a code whose stock rows are ALL `Quantity On Hand: 0` is treated as absent, not
  "found" - `crossdomain_zeroset` flags it (`zero: True`) on the stock-origin side,
  `crossdomain_render` detects it fresh on the incoming-origin side, both feeding the SAME
  climb path the first probe's genuine misses already use.
- The rung's wording set (plain vs zero, both directions):

  | Direction | Plain | Zero |
  | --- | --- | --- |
  | stock-origin, rung answers | `No stock and no incoming for X, {header}:` | `Stock is 0 at every location and no incoming for X, {header}:` |
  | stock-origin, rung answers nothing | `No stock, no incoming and nothing on order for X.` | `Stock is 0 at every location, no incoming and nothing on order for X.` |
  | incoming-origin, rung answers | `No incoming and no stock for X, {header}:` | `No incoming and stock is 0 at every location for X, {header}:` |
  | incoming-origin, rung answers nothing | `No incoming, no stock and nothing on order for X.` | `No incoming, stock is 0 at every location and nothing on order for X.` |

- A zero-flagged code, either kind (already known before the cross probe on the
  stock-origin side, or discovered fresh during it on the incoming-origin side), never
  earns AC-820's "no {primary} for X" only-other line (fix round, nit 14) - the zero
  sentence two paragraphs later already says the same thing, so printing both would be a
  duplicate.
- A code with any non-zero row anywhere never climbs; `zero_codes` on `_xdBlock` names
  which of `nothing_codes` were zero rather than genuinely absent (registered as an
  additive-key divergence in `tests/chatbot/divergences.py`, same class as A7's own three).
- Before any further rung runs at all (no ladder configured, or the rung's grant is
  missing), the FIRST probe's own `nothing_note` already carries this same zero wording
  for a zero-flagged code - it is not something only the rung's own sentence adds.

### Fix round, 11 Sep 2026 (delta review of `44834b60f`)

- R1: a probed field's `granted_value` (the compact presenter's "(O/S: n)" suffix) renders
  over `value` when present - this render has no field drop of its own, and is safe only
  because `granted_value` never reaches a row unless the SAME contact's own grant already
  asked `include_sellable`.
- R2: `_row_qty` also reads the COMPACT row's own total (`total_on_hand` / "Total"), so a
  compact "Total: 0" climbs exactly like a detailed reply reading 0 everywhere.
  Availability mode stays unreachable by design (no quantity field at all).
- A zero-flagged entry's cross-probed rows are looked up under every `by_code` key equal
  to or prefixed by its `_n` - the same rule that flagged it from a typed code's family in
  the first place - not the exact key alone (finding 7).
- Nits 10/11: dropped a clause that was always vacuously true (pre-flagged zero only ever
  exists on the stock-origin side, which the incoming-origin-only check already excludes);
  the "no rows at all" branch now copies the zeroset entry into `nothing_missing`, matching
  the R2(b) branch, so neither path can alias `zs`'s own list.

### Parity test conflict, reported and resolved (owner ruling)

`tests/chatbot/test_s6c_engine_paths.py::TestCrossdomainRenderBlockIsByteEqualMinusTheOneSidedLine`
(pre-existing, not part of this slice's red tests) parametrizes over 6 real captures and
hard-asserted the AC-820 "no {primary} for X." line was the ONLY difference from the
historical n8n block. Three of those six captures (`exec-14119800`, `exec-14120400`,
`exec-14122546`) are, in the real data, exactly R2(b)'s target shape - an incoming-origin
ask whose stock probe rows are all 0 - so R2 correctly adds a SECOND sentence (the zero
climb) that the old invariant forbade. Reported rather than resolved unilaterally; owner
ruling: R2 stands, the three captures predate the 11 Sep ruling, so the test is updated,
not the behaviour. Registered `divergences.CROSSDOMAIN_ZERO_EVERYWHERE_CLIMBS` (named,
one-line reason, same pattern as `CROSSDOMAIN_DYM_OFFER_DOMAIN_GUARD`) and the test now
subtracts the zero-climb sentence too, for whichever capture's own probed rows are all
zero (via `answer._rows_all_zero`, never a hard-coded exec id list), before asserting
byte-equality.
