/**
 * ============================================================================
 * SCM Purchasing and Fulfilment - COVERAGE TIMELINE feature service (UAC Group B)
 * ============================================================================
 * Layering: hooks (useCoverage) -> THIS service -> lib/api-client -> backend.
 *
 * Phase 1: both branches are present. While `USE_COVERAGE_MOCKS` (in
 * `lib/coverageMockStore.ts`) is true every function serves the deterministic
 * fixture and NO request is made. The real `apiFetch` + `extractApiError` branch
 * below is written and unreachable, so Phase 2 is a flag flip plus deleting the
 * mock store - not a rewrite of this file.
 *
 * ── PHASE-2 BACKEND CONTRACT ────────────────────────────────────────────────
 * Mounted under `require_module_enabled_with_api_key("scm")`, alongside the other
 * flat SCM routes (`/reorder-runs`, `/recommendations/{id}/explain-net`,
 * `/outstanding/{kind}/preview`). No nested `reorder/` segment: nothing else in
 * the domain has one.
 *
 * 1) The timeline for one product at one fulfilment pool
 *
 *      GET /api/v1/scm/coverage
 *          ?product_code=<code>      required, e.g. SRTWT7408
 *          &pool_code=<code>         required, e.g. BRW  (see note below)
 *          &floor=<number>           optional, default 0
 *
 *      -> 200  CoverageTimeline        (see `types/coverage.types.ts` - that file
 *                                       is the field-for-field contract and is
 *                                       NOT restated here)
 *      Auth: `scm.dashboard.view` (read-only), matching `explainer.py`.
 *
 *    **The params are human codes, not ids, deliberately.** No UUID may reach the
 *    UI (AC-B2), so a screen that only ever holds `product_code` / a location code
 *    cannot be asked to send `product_id` / `pool_id` - it would have to fetch an
 *    id first, and that id would then be one refresh away from being rendered. The
 *    backend resolves both codes itself.
 *
 *    `pool_code` accepts EITHER a pool code or any location code that points at a
 *    pool: pool membership is a stored pointer per location (AC-B1a) and
 *    `CoverageService.pool_for_location` already resolves a location with no
 *    pointer to itself. So the grid can pass the row's own warehouse code and the
 *    netting still happens over the shared pool.
 *
 *    `floor` is the level the balance must not fall below - 0 for project demand,
 *    the reorder point for a continuous SKU (which is what makes ROP the
 *    one-bucket case of this engine).
 *
 * 2) Accept a cross-site transfer proposal
 *
 *      POST /api/v1/scm/coverage/transfer-proposals/{proposal_ref}/accept
 *      -> 200  CoverageTransferAcceptResult
 *      Auth: `scm.reorder.run` (this one writes).
 *
 *    Cross-site cover is never netted into the balance (AC-B1d): moving it is a
 *    physical transfer with a cost and a lead time, so it is a proposal a person
 *    accepts. `proposal_ref` is opaque to the UI and never rendered.
 *
 * ── ERROR SHAPE ─────────────────────────────────────────────────────────────
 * Every failure is the standard `AppException` envelope the global handler in
 * `app/main.py` serialises (`{ detail | message | error }`, correct HTTP status).
 * It is read with `extractApiError(res, fallback)` and surfaced as an `Error`
 * message, which is what the panel's error state renders beside its retry.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  USE_COVERAGE_MOCKS,
  mockAcceptTransfer,
  mockCoverageTimeline,
} from '../lib/coverageMockStore';
import type {
  CoverageTimeline,
  CoverageTransferAcceptResult,
} from '../types/coverage.types';

/** What the panel knows about the row it was opened from. All human codes. */
export interface CoverageQuery {
  product_code: string;
  /** A pool code, or any location code pointing at one. */
  pool_code: string;
  /** The level the balance must not fall below. */
  floor: number;
  /** Display only - the mock echoes it back so the panel header reads properly. */
  product_name?: string | null;
}

/** The dated coverage timeline for one product at one fulfilment pool (AC-B1). */
export async function getCoverageTimeline(q: CoverageQuery): Promise<CoverageTimeline> {
  if (USE_COVERAGE_MOCKS) return mockCoverageTimeline(q.product_code, q.product_name ?? null);
  const params = new URLSearchParams({
    product_code: q.product_code,
    pool_code: q.pool_code,
    floor: String(q.floor),
  });
  const res = await apiFetch(`/api/v1/scm/coverage?${params}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the coverage timeline'));
  return (await res.json()) as CoverageTimeline;
}

/** Accept a cross-site transfer proposal (AC-B1d). */
export async function acceptCoverageTransfer(
  proposalRef: string,
): Promise<CoverageTransferAcceptResult> {
  if (USE_COVERAGE_MOCKS) return mockAcceptTransfer(proposalRef);
  const res = await apiFetch(
    `/api/v1/scm/coverage/transfer-proposals/${encodeURIComponent(proposalRef)}/accept`,
    { method: 'POST' },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to accept the transfer'));
  return (await res.json()) as CoverageTransferAcceptResult;
}
