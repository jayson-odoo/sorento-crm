/**
 * ============================================================================
 * PHASE 1 DEBT - the in-memory stand-in for /api/v1/pending-actions
 * ============================================================================
 * The deferred-action UI (D7, S6) is built and browser-verified before the routes
 * exist, so this module answers the three calls in `pendingActionService.ts` from
 * memory: it parks the action, keeps the server's clock (`commit_at`), commits when
 * the window lapses, and records how the action ended.
 *
 * Two things it cannot honour, both of which are Phase 2's to prove (S6-08):
 * closing the tab still commits, and a second browser sees the same countdown -
 * this store lives in one tab and dies with it.
 *
 * The effect itself is applied by the `commit` callback the caller hands over: in
 * Phase 1 that is the very delete the confirmation dialog used to run, so the
 * journey is real end to end against real data. In Phase 2 the handler is
 * registered on the server, `USE_PENDING_ACTION_MOCK` goes false and this file is
 * deleted along with every `commit:` argument.
 */

import type {
  CurrentPendingActionResponse,
  PendingAction,
  PendingActionOutcome,
} from './pendingActionService';

/**
 * PHASE 1 SWITCH. Flip to `false` in Phase 2 - that one line moves every screen
 * onto the real routes - then delete this module and its two branches in
 * `pendingActionService.ts`.
 */
export const USE_PENDING_ACTION_MOCK = true;

/** Defaults from S6-04; the real server reads them from system settings. */
const DESTRUCTIVE_WINDOW_SECONDS = 10;
const REVERSIBLE_WINDOW_SECONDS = 5;

interface CreateBody {
  action_key: string;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
}

interface MockRow {
  action: PendingAction;
  commit?: () => Promise<unknown>;
  timer: ReturnType<typeof setTimeout> | null;
}

/** Naive UTC, exactly as the backend serialises a timestamp. */
function naiveUtc(at: number): string {
  return new Date(at).toISOString().replace(/\.\d+Z$/, '');
}

function windowSecondsFor(actionKey: string): number {
  return actionKey.endsWith('.delete')
    ? DESTRUCTIVE_WINDOW_SECONDS
    : REVERSIBLE_WINDOW_SECONDS;
}

function entityKey(entityType: string, entityId: string): string {
  return `${entityType}:${entityId}`;
}

const rows = new Map<string, MockRow>();
const outcomes = new Map<string, PendingActionOutcome>();

function findPending(entityType: string, entityId: string): MockRow | undefined {
  const key = entityKey(entityType, entityId);
  for (const row of rows.values()) {
    if (entityKey(row.action.entity_type, row.action.entity_id) === key) return row;
  }
  return undefined;
}

function settle(row: MockRow, outcome: PendingActionOutcome) {
  rows.delete(row.action.id);
  outcomes.set(entityKey(row.action.entity_type, row.action.entity_id), outcome);
}

async function commitRow(row: MockRow) {
  row.timer = null;
  try {
    await row.commit?.();
    settle(row, {
      id: row.action.id,
      action_key: row.action.action_key,
      status: 'committed',
      error_text: null,
      ended_at: naiveUtc(Date.now()),
    });
  } catch (error) {
    // A handler that fails leaves the entity untouched and says so (S6-03).
    settle(row, {
      id: row.action.id,
      action_key: row.action.action_key,
      status: 'failed',
      error_text: error instanceof Error ? error.message : 'The action could not be applied',
      ended_at: naiveUtc(Date.now()),
    });
  }
}

export const pendingActionMock = {
  async create(body: CreateBody, commit?: () => Promise<unknown>): Promise<PendingAction> {
    // Idempotent while one is pending on the same entity + action (S6-01).
    const existing = findPending(body.entity_type, body.entity_id);
    if (existing) {
      if (existing.action.action_key === body.action_key) return existing.action;
      // `current` answers one action per record, and the screen shows one
      // countdown, so a record holds one at a time.
      throw new Error('Another action on this record is still counting down.');
    }

    const windowSeconds = windowSecondsFor(body.action_key);
    const action: PendingAction = {
      id: `pending-${Math.random().toString(36).slice(2, 10)}`,
      action_key: body.action_key,
      entity_type: body.entity_type,
      entity_id: body.entity_id,
      commit_at: naiveUtc(Date.now() + windowSeconds * 1000),
      window_seconds: windowSeconds,
    };
    const row: MockRow = { action, commit, timer: null };
    rows.set(action.id, row);
    outcomes.delete(entityKey(body.entity_type, body.entity_id));
    row.timer = setTimeout(() => void commitRow(row), windowSeconds * 1000);
    return action;
  },

  async cancel(id: string): Promise<void> {
    const row = rows.get(id);
    // Already committed: the window is gone and so is the chance to withdraw (409).
    if (!row) throw new Error('This action has already been applied');
    if (row.timer) clearTimeout(row.timer);
    settle(row, {
      id: row.action.id,
      action_key: row.action.action_key,
      status: 'cancelled',
      error_text: null,
      ended_at: naiveUtc(Date.now()),
    });
  },

  async current(
    entityType: string,
    entityId: string,
  ): Promise<CurrentPendingActionResponse> {
    const row = findPending(entityType, entityId);
    return {
      pending: row ? row.action : null,
      last_outcome: outcomes.get(entityKey(entityType, entityId)) ?? null,
    };
  },

  /** Test seam: drop everything parked. */
  reset(): void {
    for (const row of rows.values()) if (row.timer) clearTimeout(row.timer);
    rows.clear();
    outcomes.clear();
  },
};
