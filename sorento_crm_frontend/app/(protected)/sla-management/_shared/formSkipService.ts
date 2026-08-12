import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { FormSLASourceType } from './formSLAService';

/* -------------------------------------------------------------------------------------
 * Skip the next SLA stage (UAC-form-sla-skip-stage.md) - PHASE 1 CONTRACT.
 *
 * A form-SLA stage may declare itself SKIPPABLE. Taking the skip action resolves the
 * current stage, prevents the next stage from spawning, and moves the entity to a
 * terminal status owned by its per-entity adapter.
 *
 * The engine needs no changes to support this: `_resolve_for_active` only spawns
 * `next_config_id` when the resolving event equals `advance_on_event`, so a skip event
 * that is in `resolve_event` but NOT in `advance_on_event` resolves without advancing.
 *
 * Complaint is the only wired consumer: "Settled on site" - the technician fixed the
 * issue during the visit, so no replacement is arranged and CS is never assigned.
 *
 *   GET /api/v1/sla-management/form-sla-tracking?source_entity_type=&source_entity_id=
 *     The active stage row gains three fields:
 *       skip_event: string | null         // null = this stage is not skippable
 *       skip_action_label: string | null  // "Settled on site" - the gear item's label
 *       can_skip: boolean                 // stage is skippable AND viewer holds the perm
 *
 *   POST /api/v1/sla-management/form/{source_entity_type}/{source_entity_id}/skip
 *     req:  { note?: string }             // optional, appended to the contact's message
 *     res:  200 { status, resolved_at, message }
 *     403   permission denied, or the handling lock is held by another user
 *     422   the entity type is not a form-SLA type / has no registered adapter
 *           (route-level, before the service runs)
 *     400   no active tracker | stage not skippable | entity is in a status the
 *           adapter does not allow skipping from. 400 rather than 422 because that is
 *           what `handle_validation_error` returns, and it is the code the sibling
 *           approve/reject actions already give for their own wrong-status guard.
 *
 * Server-side ordering (the FE relies on it): guards run BEFORE any write, the terminal
 * status commits on its own, and the contact message / SLA emit / automation dispatch are
 * best-effort AFTER the commit. So a 200 always means the status moved, and a notify
 * failure never rolls it back or 500s an action that already succeeded.
 *
 * The label comes from config so entity #2 needs no FE code; the consequence sentence
 * does NOT - that is domain truth supplied by the adapter (see FormSkipDialog).
 * ----------------------------------------------------------------------------------- */

export interface FormSkipResult {
  /** The terminal status the entity now holds (e.g. 'settled_on_site'). */
  status: string;
  /** Naive-UTC ISO stamp of the resolution. */
  resolved_at: string | null;
  /** Human-readable confirmation, safe to toast. */
  message: string;
}

export interface FormSkipRequest {
  note?: string;
}

/**
 * Skip the active stage and move the entity to its adapter-defined terminal status.
 * Throws with the backend's message on any non-2xx (403 lock/permission, 422 guard).
 */
export async function skipFormStage(
  sourceEntityType: FormSLASourceType,
  sourceEntityId: string,
  body: FormSkipRequest = {},
): Promise<FormSkipResult> {
  const r = await apiFetch(
    `/api/v1/sla-management/form/${sourceEntityType}/${sourceEntityId}/skip`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to complete this action'));
  return r.json();
}
