/**
 * Feature service — Form Void (R3).
 *
 * ============================================================================
 * EXPECTED API CONTRACT (Phase 2 wiring target — NOT yet implemented)
 * ============================================================================
 * A form (purchase request / sponsorship form / complaint / stock inquiry) can
 * be VOIDED: an administrative cancellation that makes the record permanently
 * read-only. Voiding is NOT deletion (the row is retained) and NOT rejection
 * (no approval semantics) — hence the neutral gray banner, not red.
 *
 *   POST /api/v1/<resourcePath>/{id}/void
 *     resourcePath ∈ {
 *       'procurement/purchase-requests',
 *       'procurement/purchase-requests'   // sponsorship forms share the PR resource
 *       'complaint-management/complaints',
 *       'procurement/stock-inquiries',
 *     }
 *     request body:  { void_reason: string }   // required, trimmed, min 3 chars
 *     200 response:  {
 *       id: string,
 *       status: 'voided',
 *       voided_by: string,          // internal user id (UUID) — never shown in UI
 *       voided_by_name: string,     // human-readable, shown in the banner
 *       voided_at: string,          // ISO-8601 naive UTC (rendered in Malaysia tz)
 *       void_reason: string,
 *     }
 *     Permission: gated on the per-domain `<form>.void` permission slug
 *       (e.g. 'procurement.purchase_requests.void').
 *     Errors: 403 (no permission), 409 (already voided / terminal state),
 *             422 (missing/blank reason) — surfaced via extractApiError().
 *
 * A voided record echoes these fields back on its detail GET so the FE can
 * render the banner and force full read-only.
 * ============================================================================
 *
 * PHASE 1 (current): the mutation is MOCKED — it returns synthetic data after a
 * Phase 2: wired to the real FastAPI `/void` endpoint.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export type VoidableResource =
  | 'procurement/purchase-requests'
  | 'complaints-management/complaints'
  | 'procurement/stock-inquiries';

export interface VoidFormPayload {
  void_reason: string;
}

/** The void audit fields a voided form carries (and the void mutation returns). */
export interface VoidedFormFields {
  status: string;
  voided_by?: string | null;
  voided_by_name?: string | null;
  voided_at?: string | null;
  void_reason?: string | null;
}

export interface VoidFormResult extends VoidedFormFields {
  id: string;
  status: 'voided';
}

/** Void a form via the real FastAPI endpoint. Returns the voided record. */
export async function voidForm(
  resource: VoidableResource,
  id: string,
  payload: VoidFormPayload,
): Promise<VoidFormResult> {
  const reason = payload.void_reason.trim();
  if (reason.length < 3) {
    throw new Error('A void reason of at least 3 characters is required.');
  }
  const r = await apiFetch(`/api/v1/${resource}/${id}/void`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ void_reason: reason }),
  });
  if (!r.ok) {
    throw new Error(await extractApiError(r, 'Failed to void form'));
  }
  return r.json();
}
