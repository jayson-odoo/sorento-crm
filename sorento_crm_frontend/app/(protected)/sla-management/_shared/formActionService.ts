import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

import type {
  FormUndoEligibility,
  LastFormActionOutcome,
  PendingFormAction,
} from './formAction';
import type { FormSLASourceType } from './formSLAService';

/* -------------------------------------------------------------------------------------
 * Form SLA Undo API (PLAN-form-sla-undo.md).
 *
 * The domain routes keep their own URLs - approve is still POST
 * /procurement/purchase-requests/{id}/approval-decision. What changes is that it may
 * answer 202 with a pending action instead of 200 with the updated row:
 *
 *   202 { deferred, pending_action_id, action_key, commit_at, window_seconds }
 *
 * These three endpoints cover only what the domain routes cannot express.
 * ----------------------------------------------------------------------------------- */

export interface CurrentFormActionResponse {
  pending: PendingFormAction | null;
  /** Most recent action that ended `ineligible`/`failed` - see watchedOutcome(). */
  last_outcome?: LastFormActionOutcome | null;
}

export async function getCurrentFormAction(
  sourceEntityType: FormSLASourceType,
  sourceEntityId: string,
): Promise<CurrentFormActionResponse> {
  const sp = new URLSearchParams({
    source_entity_type: sourceEntityType,
    source_entity_id: sourceEntityId,
  });
  const r = await apiFetch(`/api/v1/sla-management/form-actions/current?${sp.toString()}`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load pending action'));
  return r.json();
}

export async function getUndoEligibility(
  sourceEntityType: FormSLASourceType,
  sourceEntityId: string,
): Promise<FormUndoEligibility> {
  const sp = new URLSearchParams({
    source_entity_type: sourceEntityType,
    source_entity_id: sourceEntityId,
  });
  const r = await apiFetch(
    `/api/v1/sla-management/form-actions/eligibility?${sp.toString()}`,
  );
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load undo eligibility'));
  return r.json();
}

/** In-grace: withdraw a pending action. Nothing ran, so nobody is told. */
export async function cancelFormAction(actionId: string): Promise<void> {
  const r = await apiFetch(`/api/v1/sla-management/form-actions/${actionId}/cancel`, {
    method: 'POST',
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to undo the action'));
}

/** Post-grace: reverse the last committed action. Reason is mandatory server-side too. */
export async function undoFormAction(
  sourceEntityType: FormSLASourceType,
  sourceEntityId: string,
  reason: string,
): Promise<void> {
  const r = await apiFetch('/api/v1/sla-management/form-actions/undo', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source_entity_type: sourceEntityType,
      source_entity_id: sourceEntityId,
      reason,
    }),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to undo the action'));
}
