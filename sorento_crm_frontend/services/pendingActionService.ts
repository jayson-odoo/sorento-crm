/**
 * ============================================================================
 * Pending actions - the deferred-action service (D7, S6)
 * ============================================================================
 * Layering: UI (DeferredActionButton, deferredToast) -> hook (useDeferredAction)
 * -> THIS service -> lib/api -> backend.
 *
 * The product has no confirmation dialogs. A destructive or reversible action is
 * parked on the SERVER with a grace window; the button becomes a countdown with a
 * Cancel, and the server commits when the window lapses - even if the tab is
 * closed. The three routes below are the whole contract:
 *
 *   POST /api/v1/pending-actions
 *     { action_key, entity_type, entity_id, payload }
 *     202 -> { id, commit_at, window_seconds }
 *     A second POST for the same entity + action while one is pending answers
 *     with the existing row (S6-01).
 *
 *   POST /api/v1/pending-actions/{id}/cancel
 *     200 before commit_at, 409 after (S6-02).
 *
 *   GET /api/v1/pending-actions/current?entity_type&entity_id
 *     200 -> { pending, last_outcome } so a second browser shows the same
 *     countdown, and a commit that FAILED can say so (S6-03, S6-05).
 *
 * `commit_at` is naive UTC, as every backend timestamp is.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

const PENDING_ACTIONS = '/api/v1/pending-actions';

/** An action parked on the server, waiting out its grace window. */
export interface PendingAction {
  id: string;
  /** `<entity>.<verb>` - `product.delete`, `order.set_status`, `user.delete`. */
  action_key: string;
  entity_type: string;
  entity_id: string;
  /** Naive UTC. The clock is the server's, so a refresh cannot restart it. */
  commit_at: string;
  window_seconds: number;
  requested_by_id?: string | null;
  requested_by_name?: string | null;
}

/** How the most recent action on this entity ended. */
export interface PendingActionOutcome {
  id: string;
  action_key: string;
  status: 'committed' | 'failed' | 'cancelled';
  error_text?: string | null;
  ended_at: string;
}

export interface CurrentPendingActionResponse {
  pending: PendingAction | null;
  last_outcome: PendingActionOutcome | null;
}

export interface CreatePendingActionInput {
  actionKey: string;
  entityType: string;
  entityId: string;
  /** Whatever the handler needs at commit time (a status id, a target row). */
  payload?: Record<string, unknown>;
}

/**
 * Park the action. Nothing is applied until the window lapses (S6-01).
 *
 * The route answers with the three fields the countdown needs; the entity and the
 * key are echoed back from the request so callers hold one whole `PendingAction`.
 */
export async function createPendingAction(
  input: CreatePendingActionInput,
): Promise<PendingAction> {
  const body = {
    action_key: input.actionKey,
    entity_type: input.entityType,
    entity_id: input.entityId,
    payload: input.payload ?? {},
  };

  const response = await apiFetch(PENDING_ACTIONS, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not start the action'));
  }
  const created = (await response.json()) as Pick<
    PendingAction,
    'id' | 'commit_at' | 'window_seconds'
  >;
  // The route answers with the three fields the countdown needs; the entity and the
  // key are echoed from the request so callers hold one whole `PendingAction`. The
  // payload is NOT one of its fields - it is the handler's, not the countdown's.
  return {
    id: created.id,
    action_key: body.action_key,
    entity_type: body.entity_type,
    entity_id: body.entity_id,
    commit_at: created.commit_at,
    window_seconds: created.window_seconds,
  };
}

/** Withdraw a parked action before it commits. Nothing ran, so nobody is told. */
export async function cancelPendingAction(id: string): Promise<void> {
  const response = await apiFetch(`${PENDING_ACTIONS}/${id}/cancel`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not cancel the action'));
  }
}

/** What is parked on this record right now, and how the last one ended. */
export async function getCurrentPendingAction(
  entityType: string,
  entityId: string,
): Promise<CurrentPendingActionResponse> {
  const params = new URLSearchParams({
    entity_type: entityType,
    entity_id: entityId,
  });
  const response = await apiFetch(`${PENDING_ACTIONS}/current?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load the pending action'));
  }
  return response.json();
}
