/**
 * ============================================================================
 * SCM Purchasing and Fulfilment - PLAN EXCEPTIONS service (UAC Group D)
 * ============================================================================
 * Layering: hooks (usePlanExceptions) -> THIS service -> lib/api-client -> backend.
 *
 * Phase 1: both branches are present. While `USE_PLAN_EXCEPTION_MOCKS` (in
 * `lib/planExceptionMockStore.ts`) is true every function serves the deterministic
 * fixture and NO request is made. The real `apiFetch` + `extractApiError` branch below
 * is written and unreachable, so Phase 2 is a flag flip plus deleting the mock store -
 * not a rewrite of this file.
 *
 * -- PHASE-2 BACKEND CONTRACT ------------------------------------------------
 * Mounted flat under `require_module_enabled_with_api_key("scm")`, alongside
 * `/order-summary` and `/po-worklist`. No nested `reorder/` segment.
 *
 * Codes on the wire throughout. `run_id` and `exception_id` are the only opaque values
 * and neither is ever rendered.
 *
 * 1) The batch produced by one run
 *
 *      GET /api/v1/scm/plan-exceptions
 *          ?run_id=<opaque>          optional; omitted = the newest COMPLETED run
 *          &status=open|approved|rejected   optional; omitted = every status
 *
 *      -> 200  PlanExceptionReport   (see `types/planException.types.ts` - that file is
 *                                     the field-for-field contract and is NOT restated
 *                                     here)
 *      Auth: `scm.dashboard.view` (read-only), matching `/order-summary`.
 *
 *    Exceptions are produced AS A BATCH when a re-uploaded sales-order book is confirmed
 *    (AC-D2a), never as ad-hoc signals: this endpoint reads what that batch wrote and
 *    computes nothing. A GET that recomputed would give two people different answers to
 *    the same question minutes apart.
 *
 *    `counts.delta_count` is the upload's OWN figure carried through unchanged, so the
 *    screen can show the reduction from deltas to exceptions and the two reconcile
 *    (AC-D2b). The server must not recount it from the exceptions - that would make the
 *    two numbers agree by construction and hide a real disagreement.
 *
 *    `last_upload_at` is required, not decorative. The plan is only as current as the
 *    last upload, and the journey is explicit that this belongs on the screen.
 *
 *    **The server owns the ordering**: open rows first, then by the batch's own severity
 *    (a shortfall that moved earlier outranks a surplus), then product code. Each row's
 *    `actions` arrive ordered by `rank` ascending, and that order is the reading's
 *    verdict (AC-D10) - a client that re-sorted them by quantity would silently undo the
 *    one rule this feature exists to enforce.
 *
 * 2) Approve or reject one exception
 *
 *      POST /api/v1/scm/plan-exceptions/{exception_id}/decision
 *          { status, action_code, reason, split_qty }
 *
 *      -> 200  PlanExceptionDecisionResult
 *      Auth: `scm.reorder.run` (this one writes), matching the decision route.
 *
 *    Validation the server owns, because the UI must not be the only thing enforcing it:
 *      - `status: "approved"` requires an `action_code` that is one of THAT exception's
 *        proposed actions. Approving an action the engine never proposed is not a
 *        decision about this exception.
 *      - `status: "rejected"` requires a non-empty `reason` (AC-D6).
 *      - `action_code: "split"` requires `split_qty` strictly between 0 and the
 *        exception's quantity, and the remainder stays on the original line so the two
 *        parts sum to it (AC-D11b).
 *      - An exception that is already decided returns 409. Re-deciding is a different
 *        operation from deciding, and silently overwriting loses who decided what.
 *
 *    Approving a reallocation writes an ALLOCATION DECISION. It does not amend the
 *    purchase order (AC-D7); no placed PO is ever amended by this endpoint.
 *
 * -- ERROR SHAPE -------------------------------------------------------------
 * Every failure is the standard `AppException` envelope the global handler in
 * `app/main.py` serialises. Read with `extractApiError(res, fallback)`.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  USE_PLAN_EXCEPTION_MOCKS,
  mockDecideException,
  mockPlanExceptionReport,
} from '../lib/planExceptionMockStore';
import type {
  PlanExceptionDecisionInput,
  PlanExceptionDecisionResult,
  PlanExceptionReport,
  PlanExceptionStatus,
} from '../types/planException.types';

/** Which batch to read. Null reads the newest completed plan's. */
export interface PlanExceptionQuery {
  run_id?: string | null;
  status?: PlanExceptionStatus | null;
}

/** The exception batch for one run (AC-D2). */
export async function getPlanExceptions(
  q: PlanExceptionQuery = {},
): Promise<PlanExceptionReport> {
  if (USE_PLAN_EXCEPTION_MOCKS) return mockPlanExceptionReport();
  const params = new URLSearchParams();
  if (q.run_id) params.set('run_id', q.run_id);
  if (q.status) params.set('status', q.status);
  const qs = params.toString();
  const res = await apiFetch(`/api/v1/scm/plan-exceptions${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load plan exceptions'));
  return (await res.json()) as PlanExceptionReport;
}

/** Approve or reject one exception (AC-D6). */
export async function decidePlanException(
  input: PlanExceptionDecisionInput,
): Promise<PlanExceptionDecisionResult> {
  if (USE_PLAN_EXCEPTION_MOCKS) return mockDecideException(input);
  const { exception_id, ...body } = input;
  const res = await apiFetch(
    `/api/v1/scm/plan-exceptions/${encodeURIComponent(exception_id)}/decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to record the decision'));
  return (await res.json()) as PlanExceptionDecisionResult;
}
