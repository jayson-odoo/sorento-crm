/**
 * ============================================================================
 * SCM M4 Slice B — DECISION feature service  (Accept / Adjust / Reject)
 * ============================================================================
 * Layering: hooks (useDecisions) → THIS service → lib/api-client → backend.
 *
 * PHASE 1 (now): `USE_SLICE_B_MOCKS = true` (in `lib/copilotMockStore.ts`) routes
 * every call through the in-memory mock store so the decision → draft-PO loop is
 * demonstrable with no backend. Phase 2 flips the flag to false and the calls hit
 * the endpoints below (all mounted under
 * `require_module_enabled_with_api_key("scm")`, gated on `scm.reorder.run`).
 *
 * ── PHASE-2 BACKEND CONTRACT (NEW) ──────────────────────────────────────────
 *
 *  1) Accept a recommendation → consolidated draft PO per supplier (M4-D4)
 *     POST /api/v1/scm/recommendations/{id}/accept
 *       → 200 { draft_po_number: string, draft_po_id: string, supplier_name: string }
 *              (draft_po_id powers the "View draft PO" deep link)
 *     Upserts a `purchase_order` with status `draft_recommendation` for the
 *     recommendation's supplier (one PO/supplier, one line/SKU), sets the rec's
 *     status → accepted. The draft is NOT on-order (M4-D5).
 *
 *  2) Adjust a recommendation (qty and/or supplier switch) (M4-D7)
 *     POST /api/v1/scm/recommendations/{id}/adjust
 *       body { override_qty: number, override_supplier_id?: string | null,
 *              reason_text: string }
 *       → 200 { draft_po_number: string, draft_po_id: string, supplier_name: string }
 *              (draft_po_id powers the "View draft PO" deep link)
 *     Recomputes lead/qty off the chosen supplier, writes an APPEND-ONLY
 *     `recommendation_override` row (the recommendation itself is never mutated),
 *     sets status → adjusted, and reflects the override in the draft PO line.
 *     `reason_text` is stored raw; LLM classification into a `reason_code` lands
 *     in Slice C (no number is ever touched by the classifier).
 *
 *  3) Reject a recommendation (M4-D8)
 *     POST /api/v1/scm/recommendations/{id}/reject   body { reason_text: string }
 *       → 200 { }   ·   status → dismissed; reason enters the feedback pipeline.
 *
 *  4) Bulk Accept funded recommendations (M4-D9)
 *     POST /api/v1/scm/recommendations/bulk-accept
 *       body { run_id: string, ids: string[] }   // or { run_id, filter: "funded" }
 *       → 200 { accepted_count: number, po_count: number }
 *
 *  5) Bulk Reject funded recommendations with one shared reason (M4-D9)
 *     POST /api/v1/scm/recommendations/bulk-reject
 *       body { run_id: string, ids: string[], reason_text: string }
 *       → 200 { rejected_count: number }
 *
 *  6) Decisions already recorded for a run (drives the per-row status badges)
 *     GET /api/v1/scm/reorder-runs/{run_id}/decisions
 *       → 200 { data: RecDecision[] }   // one per decided recommendation
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  USE_SLICE_B_MOCKS,
  mockAcceptRecommendation,
  mockAdjustRecommendation,
  mockBulkAccept,
  mockBulkReject,
  mockListDecisions,
  mockRejectRecommendation,
} from '../../lib/copilotMockStore';
import type { ReorderRecommendation } from '../types/reorder.types';
import type {
  AcceptResult,
  AdjustPayload,
  BulkAcceptResult,
  RecDecision,
  RejectPayload,
} from '../types/decisions.types';

/** Decisions recorded so far for a run (keyed by recommendation id in the hook). */
export async function getRecommendationDecisions(runId: string): Promise<RecDecision[]> {
  if (USE_SLICE_B_MOCKS) return mockListDecisions();
  const res = await apiFetch(
    `/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}/decisions`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load decisions'));
  const body = (await res.json()) as { data: RecDecision[] };
  return body.data;
}

/** Accept a recommendation as proposed → consolidated draft PO (M4-D4). */
export async function acceptRecommendation(rec: ReorderRecommendation): Promise<AcceptResult> {
  if (USE_SLICE_B_MOCKS) return mockAcceptRecommendation(rec);
  const res = await apiFetch(
    `/api/v1/scm/recommendations/${encodeURIComponent(rec.id)}/accept`,
    { method: 'POST' },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to accept recommendation'));
  return (await res.json()) as AcceptResult;
}

/** Adjust a recommendation (qty override + supplier switch + reason) (M4-D7). */
export async function adjustRecommendation(
  rec: ReorderRecommendation,
  payload: AdjustPayload,
): Promise<AcceptResult> {
  if (USE_SLICE_B_MOCKS) return mockAdjustRecommendation(rec, payload);
  const res = await apiFetch(
    `/api/v1/scm/recommendations/${encodeURIComponent(rec.id)}/adjust`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        override_qty: payload.override_qty,
        override_supplier_id: payload.override_supplier_code,
        reason_text: payload.reason_text,
      }),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to adjust recommendation'));
  return (await res.json()) as AcceptResult;
}

/** Reject a recommendation with a required reason (M4-D8). */
export async function rejectRecommendation(
  rec: ReorderRecommendation,
  payload: RejectPayload,
): Promise<void> {
  if (USE_SLICE_B_MOCKS) {
    mockRejectRecommendation(rec, payload.reason_text);
    return;
  }
  const res = await apiFetch(
    `/api/v1/scm/recommendations/${encodeURIComponent(rec.id)}/reject`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason_text: payload.reason_text }),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to reject recommendation'));
}

/** Bulk-accept a set of funded recommendations (M4-D9). */
export async function bulkAcceptFunded(
  runId: string,
  recs: ReorderRecommendation[],
): Promise<BulkAcceptResult> {
  if (USE_SLICE_B_MOCKS) return mockBulkAccept(recs);
  const res = await apiFetch('/api/v1/scm/recommendations/bulk-accept', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: runId, ids: recs.map((r) => r.id) }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to accept recommendations'));
  return (await res.json()) as BulkAcceptResult;
}

/** Bulk-reject a set of recommendations with one shared reason (M4-D9). */
export async function bulkRejectRecommendations(
  runId: string,
  recs: ReorderRecommendation[],
  reasonText: string,
): Promise<{ rejected_count: number }> {
  if (USE_SLICE_B_MOCKS) return { rejected_count: mockBulkReject(recs, reasonText) };
  const res = await apiFetch('/api/v1/scm/recommendations/bulk-reject', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: runId, ids: recs.map((r) => r.id), reason_text: reasonText }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to reject recommendations'));
  return (await res.json()) as { rejected_count: number };
}
