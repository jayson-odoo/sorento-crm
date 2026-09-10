# PLAN: stock visibility "all except these" locations, and the picker's 50-row cap

Status: Phase 3 (review fixes landed; browser verification)
Lane: `.claude/worktrees/stock-visibility-exclude`, branch `feat/stock-visibility-exclude-locations`, base `origin/main` (043c2fbd3), stack :3080/:8080, DB `sorento_ai_automation_svx` (copy of `sorento_ai_automation_0907`)
UAC: `stock-visibility-exclude-locations-acceptance-criteria.md` (alongside)
Prior plan: `documentation/plans/_archive/inventory/PLAN-stock-visibility-policy.md` (migration 416, S7 hide-zero)

## Journey

Owner, on a contact's detail page (User Management > Contacts > contact > Profile > Stock
visibility), wants one contact to be told about every location EXCEPT a handful (10 Sep,
screenshots). Today the Locations picker is an include list only: with 77 active warehouses the
admin would have to tick 70 one by one, and a warehouse created next month would then be
invisible to that contact until somebody remembers to add it. The owner also noticed the picker
lists 50 locations and stops.

After this lane: the Locations row carries an Include / Exclude rule. Under Exclude the admin
ticks the few locations to withhold and saves; every other active warehouse, including ones
created later, stays visible. The picker lists every active warehouse.

## Evidence (measured on origin/main, 10 Sep)

- `warehouses`: 77 active / 104 total. Picker fetches `pageSize: 50`
  (`services/stockVisibilityService.ts::searchStockVisibilityWarehouses`), one page, so the
  dropdown shows the first 50 by code and the rest are reachable only by typing. The Dealer
  pool preset already uses 200; the route caps at `MAX_PAGE_LIMIT = 1000`.
- `stock_visibility_policies.warehouse_ids` (ARRAY UUID, NULL = all, `[]` = none) is the ONLY
  location rule. No exclusion reading exists in model, schema, service or UI.
- The policy's warehouse set is consumed in exactly three places, all in
  `app/services/inventory_service.py`: the main balance filter (~748), the empty-path
  alternatives gate (`_stock_entity_alternatives`, `allowed_warehouse_ids`, ~1002 / ~1368),
  and the warehouse-code naming for the compact block (~1186). The chatbot head
  (`chatbot/head/access.py`) and `miss_suggest.py` read the MODE only.
- Access-type merge (`_merge_access_type_rows`): most restrictive mode, INTERSECTION of
  include sets, hide-zero OR-ed. The contact tier wins whole when present.

## Decisions

| Question | Decision |
|---|---|
| Storage | One new column `excluded_warehouse_ids ARRAY(UUID) NULL` beside `warehouse_ids`, CHECK `warehouse_ids IS NULL OR excluded_warehouse_ids IS NULL` (`ck_stock_visibility_policies_one_location_rule`). Migration `508_stock_visibility_excl_wh` (id must stay <= 32 chars), `down_revision = "507_pi_link_packing_row"` (main head after the #793 merge, fix round 1 re-parent). |
| Meaning | `warehouse_ids` NULL + `excluded` NULL = all. `warehouse_ids` list = only these (unchanged). `excluded` list = every active warehouse except these; a warehouse created after the save is visible. `excluded = []` is stored as sent and means all (the card reopens under Exclude with nothing ticked). |
| Resolution | `Policy` gains `excluded_warehouse_ids: Optional[frozenset[str]] = None`. Across access types: include = intersection of non-null includes (as today), excluded = UNION of non-null excludes; both carried. Contact override row wins whole (as today). |
| Enforcement | One helper in `app/services/stock_visibility.py`, `warehouse_criterion(policy, column)`, returns a SQLAlchemy criterion: `column.in_(include)` / `sa_false()` for `[]` / `column.notin_(excluded)` / no-op, combined with AND. The three call sites in `inventory_service.py` use it; `_stock_entity_alternatives` takes the policy instead of `allowed_warehouse_ids`. Three existing copies today is the evidence for the helper. |
| API | `StockVisibilityInput.excluded_warehouse_ids: Optional[List[str]]` REQUIRED and nullable, same reasoning as `warehouse_ids` (an omitted key must not silently widen a stored exclusion). Both non-null = 422 `Pick locations to include or to exclude, not both.` Validated through `validated_warehouse_ids` (malformed = unknown = 422). `StockVisibilityPolicyOut.excluded_warehouses: Optional[List[StockVisibilityWarehouse]]` resolved by `policy_warehouses`. |
| Card UI | Under the Locations label, a two-item `ToggleGroup` (`components/ui/toggle-group.tsx`, single, non-deselectable) Include / Exclude, on the same row as the existing Dealer pool / All locations buttons. Label reads "Locations" under Include, "Excluded locations" under Exclude. Placeholder: Include + null "All locations", Include + [] "No locations", Exclude + [] "All locations". No explanatory copy. |
| Rule flips | Include -> Exclude: the ticked ids carry over as the excluded set (null carries as []). Exclude -> Include: a non-empty set carries over as the include set; an empty set becomes null (all), never `[]`. |
| Presets | "Dealer pool" sets Include + the pool ids. "All locations" sets Include + null; disabled when already all (Include + null, or Exclude + []). |
| Save body | Include: `{warehouse_ids: ids-or-null, excluded_warehouse_ids: null}`. Exclude: `{warehouse_ids: null, excluded_warehouse_ids: ids}`. `mode` and `hide_zero_locations` as today. |
| Picker cap | `searchStockVisibilityWarehouses` pageSize 50 -> 200. Still server-searched. |
| Out of scope | Paging the picker beyond 200, MCP presenter, n8n, the access-type and default admin surfaces beyond what the shared card already gives them. |

## Slices

- **S1 FE** (`components/stock-visibility/StockVisibilitySection.tsx`, `services/stockVisibilityService.ts`): rule toggle, draft shape, save body, placeholders, cap 200. Types first, mocked API second, then the real wiring lands with S2.
- **S2 BE**: migration 505, model column + CHECK, `Policy` field, merge, `warehouse_criterion`, three call sites, schema in/out, routes pass the new field to `upsert_policy`.
- **S3** review + security-review + browser verification in parallel, once.

## Tests (land in Phase 2, `tester` writes them red first)

Backend, `tests/test_stock_visibility_policy.py`: AC-1 .. AC-12 in the UAC. Frontend:
`services/stockVisibilityService.test.ts` (AC-13, AC-14), `components/stock-visibility/
StockVisibilitySection.test.tsx` (AC-15 .. AC-21). Every existing PUT body in both suites
gains `excluded_warehouse_ids: null` (19 backend, 21 frontend occurrences to check).
