/**
 * ============================================================================
 * SCM Purchasing and Fulfilment - PO CREATION WORKLIST service (UAC Group E2)
 * ============================================================================
 * Layering: hooks (usePoWorklist) -> THIS service -> lib/api-client -> backend.
 *
 * Phase 1: both branches are present. While `USE_PO_WORKLIST_MOCKS` (in
 * `lib/poWorklistMockStore.ts`) is true every function serves the deterministic
 * fixture and NO request is made. The real `apiFetch` + `extractApiError` branch
 * below is written and unreachable, so Phase 2 is a flag flip plus deleting the
 * mock store - not a rewrite of this file.
 *
 * -- PHASE-2 BACKEND CONTRACT ------------------------------------------------
 * Mounted flat under `require_module_enabled_with_api_key("scm")`, alongside
 * `/order-summary` and the other SCM routes. No nested `reorder/` segment.
 *
 * Params are HUMAN CODES throughout. `run_id` is the single id on the wire and it
 * is opaque: it says which week's decisions are being worked, and is never rendered.
 *
 * 1) The worklist, one row per DECIDED product
 *
 *      GET /api/v1/scm/po-worklist
 *          ?run_id=<opaque>          optional; omitted = the newest COMPLETED run
 *
 *      -> 200  PoWorklist            (see `types/poWorklist.types.ts` - that file is
 *                                     the field-for-field contract and is NOT
 *                                     restated here)
 *      Auth: `scm.dashboard.view` (read-only), matching `/order-summary`.
 *
 *    Rows are the frozen `scm.order_summary_row` rows that carry a decision, and
 *    ONLY those: a product Mr Loo has not decided on belongs on the report, not on
 *    the worklist. A decision of ZERO is included (AC-E2.5) and the screen states
 *    that no PO is needed - filtering it out would make a use-pool decision
 *    indistinguishable from one nobody made.
 *
 *    **The server owns the ordering**, worst first: late rows, then by place-by date
 *    with nulls last, then by product code. Filtering to not-keyed is the primary use
 *    of the screen (AC-E2.4) but urgency is what decides which not-keyed row to do
 *    first, and a client free to re-sort could disagree with the late flag beside it.
 *
 *    Stage 2 adds the run's stamped `decision_grain` to the response and reads ONLY
 *    that grain (AC-F09): a `product` run lists product decisions, each carrying
 *    `location_allocations` (its split back to locations, summing exactly to
 *    `chosen_qty`); a `location` run lists the per-location recommendation
 *    decisions, each naming its `warehouse_code` and carrying no split. Neither
 *    shape gains a channel key, and rows from the comparison grain are never
 *    merged in - keying both would buy the same requirement twice. A legacy run
 *    carries a null grain and no split.
 *
 *    Three nullable fields are load-bearing and must NOT be defaulted by the server.
 *    `need_by` is absent whenever nothing committed is uncovered, which is most of the
 *    book (the committed order book is 17 sales orders); `place_by` and
 *    `lead_time_days` are absent when the lead time is unknown. A fabricated place-by
 *    date is worse than none because it is acted on.
 *
 * 2) Set the keyed-into-AutoCount status
 *
 *      POST /api/v1/scm/po-worklist/{product_code}/keyed-status
 *          { run_id, keyed_status, warehouse_code? }
 *
 *      -> 200  KeyedStatusResult
 *      Auth: `scm.reorder.run` (this one writes), matching the decision route.
 *
 *    Manual because nothing can detect it: no AutoCount integration exists (AC-E2.2).
 *    The server stamps `keyed_by` + `keyed_at` and `keyed_by` is a human NAME, never
 *    a user id - it is rendered beside the row.
 *
 *    Any transition is allowed, including backwards. A person who marked a row keyed
 *    by mistake has to be able to unmark it, and a state machine that only moves
 *    forward would leave them editing the database.
 *
 *    The write lands at the run's own grain (AC-F09). On a LOCATION-grain run every
 *    row is its own purchase order, so `warehouse_code` names which one and the
 *    status is per (product, location); the server 422s a location-grain write that
 *    names none and 404s a location the run never decided for. On a product-grain
 *    run it is omitted and the product row is keyed, exactly as before.
 *
 * -- ERROR SHAPE -------------------------------------------------------------
 * Every failure is the standard `AppException` envelope the global handler in
 * `app/main.py` serialises. Read with `extractApiError(res, fallback)`.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  USE_PO_WORKLIST_MOCKS,
  mockPoWorklist,
  mockSetKeyedStatus,
} from '../lib/poWorklistMockStore';
import type {
  KeyedStatusInput,
  KeyedStatusResult,
  PoWorklist,
} from '../types/poWorklist.types';

/** Which week's decisions to work. Null reads the newest completed plan. */
export interface PoWorklistQuery {
  run_id?: string | null;
}

/** The worklist over one run's decisions (AC-E2.1). */
export async function getPoWorklist(q: PoWorklistQuery = {}): Promise<PoWorklist> {
  if (USE_PO_WORKLIST_MOCKS) return mockPoWorklist();
  const params = new URLSearchParams();
  if (q.run_id) params.set('run_id', q.run_id);
  const qs = params.toString();
  const res = await apiFetch(`/api/v1/scm/po-worklist${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the PO worklist'));
  return (await res.json()) as PoWorklist;
}

/** Record that a PO has been keyed into AutoCount, or un-record it (AC-E2.2). */
export async function setKeyedStatus(
  productCode: string,
  input: KeyedStatusInput,
): Promise<KeyedStatusResult> {
  if (USE_PO_WORKLIST_MOCKS) return mockSetKeyedStatus(productCode, input);
  const res = await apiFetch(
    `/api/v1/scm/po-worklist/${encodeURIComponent(productCode)}/keyed-status`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to set the keyed status'));
  return (await res.json()) as KeyedStatusResult;
}
