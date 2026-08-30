'use client';

import { useSyncExternalStore } from 'react';
import type { QueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  getCurrentPendingAction,
  type PendingActionOutcome,
} from '@/services/pendingActionService';

/**
 * The tab's memory of the actions it parked on the server.
 *
 * Two things need it, and both outlive the component that started the action.
 *
 * **The row.** A list row's countdown lives in a toast, but the ROW has to say
 * that it is on its way out (S6-07: "the row stays visible, dimmed, until
 * commit"). The row is the `<tr>` the grid renders and the action lives in one of
 * its cells, so the two cannot talk through props - the grid reads this store
 * instead, through `rowPending` on `DataGrid`.
 *
 * **The follow-through.** The window is the server's and it lapses whether or not
 * the surface that started it is still on screen: the user starts a delete,
 * scrolls away, opens another module and comes back. `useDeferredAction` polls
 * only while it is mounted, so nothing else would ever learn that the record went
 * away, and the list would keep serving the deleted row out of the React Query
 * cache until a hard refresh. So the start also arms ONE timer here, at the
 * server's `commit_at` plus a grace, which asks `current` what happened and
 * invalidates the action's lists no matter what is mounted. A tab that was asleep
 * gets the same reconciliation on focus, because a throttled `setTimeout` can
 * come back long after its moment.
 *
 * The server remains the source of truth: nothing here decides an outcome, it
 * only asks for one. A second browser still learns about the countdown from
 * `GET /pending-actions/current`, never from this.
 */

type Listener = () => void;

/** How long after the server's `commit_at` we ask what actually happened. */
const COMMIT_GRACE_MS = 1500;

/**
 * How recent an outcome has to be to be worth saying out loud.
 *
 * A success toast is the answer to a click. Minutes later the user has forgotten
 * the click, and a page that greets them with "Delivery order updated" on arrival
 * is noise standing in front of the record - the fresh data already says it. A
 * FAILURE is different: nothing was applied and the user has to find that out, so
 * it gets a longer horizon.
 */
export const FRESH_OUTCOME_MS = 10_000;
export const FAILED_OUTCOME_MS = 60_000;

export function pendingEntityKey(entityType: string, entityId: string): string {
  return `${entityType}:${entityId}`;
}

/** Treat a timezone-less ISO timestamp (naive UTC from the backend) as UTC. */
export function parseServerTime(iso: string): number {
  return Date.parse(/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`);
}

/**
 * Is this outcome still worth a toast?
 *
 * An unreadable timestamp counts as fresh: silence is the worse failure of the
 * two, and it is the shape a format change would take.
 */
export function isOutcomeWorthSaying(
  outcome: Pick<PendingActionOutcome, 'status' | 'ended_at'>,
  now: number = Date.now(),
): boolean {
  const endedAt = parseServerTime(outcome.ended_at);
  if (Number.isNaN(endedAt)) return true;
  const horizon = outcome.status === 'failed' ? FAILED_OUTCOME_MS : FRESH_OUTCOME_MS;
  return now - endedAt <= horizon;
}

export interface TrackPendingActionInput {
  /** The pending row's id, so a cancel-and-restart is not mistaken for this one. */
  id: string;
  entityType: string;
  entityId: string;
  actionKey: string;
  /** Naive UTC, from the server. The clock is never the client's. */
  commitAt: string;
  /**
   * Said if the commit is still fresh when it is observed.
   *
   * `null` means the caller answers for it: a bulk delete parks one action per row and
   * owes the reader ONE sentence at the end, not twelve.
   */
  successMessage: string | null;
  /** Lists to refetch once the action has committed. */
  invalidateKeys: readonly (readonly unknown[])[];
  /**
   * How this one ended, for a caller keeping score across several actions. Null when
   * the record settled with no outcome of this action's own.
   */
  onSettled?: (outcome: PendingActionOutcome | null) => void;
}

interface TrackedAction extends Omit<TrackPendingActionInput, 'commitAt'> {
  commitAtMs: number;
  timer: ReturnType<typeof setTimeout> | null;
  /** A read is already in flight; focus must not start a second one. */
  settling: boolean;
}

const EMPTY: ReadonlySet<string> = new Set<string>();

let _keys: ReadonlySet<string> = EMPTY;
const _listeners = new Set<Listener>();
const _tracked = new Map<string, TrackedAction>();
/** Records this tab watched a delete commit on, so a stale link can be quiet. */
const _deletedIds = new Set<string>();
/** Outcomes already said, by pending-action id. One outcome, one toast. */
const _saidOutcomes = new Set<string>();
let _queryClient: QueryClient | null = null;
let _wakeListening = false;

function emit() {
  _listeners.forEach((fn) => fn());
}

function markKey(key: string) {
  if (_keys.has(key)) return;
  _keys = new Set([..._keys, key]);
  emit();
}

function unmarkKey(key: string) {
  if (!_keys.has(key)) return;
  const next = new Set(_keys);
  next.delete(key);
  _keys = next;
  emit();
}

function untrackKey(key: string) {
  const entry = _tracked.get(key);
  if (!entry) return;
  if (entry.timer) clearTimeout(entry.timer);
  _tracked.delete(key);
  if (_tracked.size === 0) detachWakeListeners();
}

/**
 * The countdown toast for one parked action, taken down.
 *
 * Owned here rather than by the surface that raised it, because the surface may be
 * pointed at another record by the time this one settles: a reader deleting three rows
 * in a row re-points ONE hook three times, and each of the three toasts still has to
 * come down when its own action ends. `deferredToast` ids by the action, which is what
 * makes that possible without holding a handle.
 */
function dismissToastFor(actionId: string) {
  toast.dismiss(`pending-action-${actionId}`);
}

/** Stop tracking AND take the dimming off the row, and its countdown with it. */
function releaseKey(key: string) {
  const entry = _tracked.get(key);
  if (entry) dismissToastFor(entry.id);
  untrackKey(key);
  unmarkKey(key);
}

/** The same, for a caller that knows the ACTION (a cancel) rather than the record. */
function releaseById(actionId: string) {
  for (const [key, entry] of _tracked) {
    if (entry.id === actionId) {
      releaseKey(key);
      return;
    }
  }
  dismissToastFor(actionId);
}

function armTimer(entry: TrackedAction, key: string) {
  if (entry.timer) clearTimeout(entry.timer);
  const delay = Math.max(0, entry.commitAtMs - Date.now()) + COMMIT_GRACE_MS;
  entry.timer = setTimeout(() => {
    void settleFromServer(key);
  }, delay);
}

/**
 * Ask the server how the action ended, then answer for it: refetch the lists it
 * named, remember a delete, and say something only if it is still worth saying.
 */
async function settleFromServer(key: string): Promise<void> {
  const entry = _tracked.get(key);
  if (!entry || entry.settling) return;
  entry.settling = true;
  entry.timer = null;

  let current;
  try {
    current = await getCurrentPendingAction(entry.entityType, entry.entityId);
  } catch {
    // A read that failed says nothing about the record. Leave the row as it is
    // and try again when the tab next comes forward.
    entry.settling = false;
    return;
  }
  entry.settling = false;
  // Something settled the action while the read was in flight.
  if (_tracked.get(key) !== entry) return;

  if (current.pending) {
    // Still parked: either the clock has not caught up, or this record was
    // cancelled and restarted. Follow the row that is actually there.
    if (current.pending.id !== entry.id) {
      untrackKey(key);
      return;
    }
    entry.commitAtMs = parseServerTime(current.pending.commit_at);
    armTimer(entry, key);
    return;
  }

  const last = current.last_outcome;
  const outcome = last && last.action_key === entry.actionKey ? last : null;
  releaseKey(key);

  if (outcome?.status === 'committed') {
    if (entry.actionKey.endsWith('.delete')) _deletedIds.add(entry.entityId);
    for (const queryKey of entry.invalidateKeys) {
      _queryClient?.invalidateQueries({ queryKey });
    }
  }
  if (outcome && entry.successMessage !== null) {
    announceOutcome(outcome, entry.successMessage);
  }
  // Always, outcome or not: a caller counting a batch down to zero must not be left
  // waiting on the one row whose record answered with somebody else's action.
  entry.onSettled?.(outcome);
}

/**
 * Say how an action ended - once, and only while it still answers a click.
 *
 * Both the mounted surface and the follow-through timer end up here, and either
 * may be first, so the dedupe is by outcome id rather than by who is asking.
 */
function announceOutcome(
  outcome: PendingActionOutcome,
  successMessage: string,
): void {
  if (_saidOutcomes.has(outcome.id)) return;
  _saidOutcomes.add(outcome.id);
  if (!isOutcomeWorthSaying(outcome)) return;
  const id = `pending-outcome-${outcome.id}`;
  if (outcome.status === 'committed') {
    toast.success(successMessage, { id });
  } else if (outcome.status === 'failed') {
    toast.error(outcome.error_text || 'The action could not be applied.', { id });
  }
}

/** Every tracked action whose moment has passed, asked again. */
function reconcileDue(): void {
  const now = Date.now();
  for (const [key, entry] of _tracked) {
    if (entry.commitAtMs + COMMIT_GRACE_MS <= now) void settleFromServer(key);
  }
}

function onVisibilityChange() {
  if (document.visibilityState === 'visible') reconcileDue();
}

function attachWakeListeners() {
  if (_wakeListening || typeof window === 'undefined') return;
  _wakeListening = true;
  window.addEventListener('focus', reconcileDue);
  document.addEventListener('visibilitychange', onVisibilityChange);
}

function detachWakeListeners() {
  if (!_wakeListening || typeof window === 'undefined') return;
  _wakeListening = false;
  window.removeEventListener('focus', reconcileDue);
  document.removeEventListener('visibilitychange', onVisibilityChange);
}

export const pendingEntityStore = {
  getKeys(): ReadonlySet<string> {
    return _keys;
  },
  mark(entityType: string, entityId: string): void {
    markKey(pendingEntityKey(entityType, entityId));
  },
  /** The action is over: undim the row and put the follow-through timer down. */
  clear(entityType: string, entityId: string): void {
    releaseKey(pendingEntityKey(entityType, entityId));
  },
  /** The same, said by action id - what a cancel knows. */
  releaseById,
  subscribe(fn: Listener): () => void {
    _listeners.add(fn);
    return () => {
      _listeners.delete(fn);
    };
  },

  /**
   * The app's ONE React Query client, so an invalidation can happen with nothing
   * mounted. Registered by `QueryProvider`, the same way the revision fence
   * registers its stale handler - a second client would invalidate a cache no
   * screen is reading.
   */
  registerQueryClient(client: QueryClient | null): void {
    _queryClient = client;
  },

  /** Mark the row and arm the one timer that sees the action through. */
  track(input: TrackPendingActionInput): void {
    const key = pendingEntityKey(input.entityType, input.entityId);
    untrackKey(key);
    const entry: TrackedAction = {
      ...input,
      commitAtMs: parseServerTime(input.commitAt),
      timer: null,
      settling: false,
    };
    _tracked.set(key, entry);
    armTimer(entry, key);
    attachWakeListeners();
    markKey(key);
  },

  announceOutcome,

  /** A delete this tab watched commit. The record is gone, not missing. */
  noteCommittedDelete(entityId: string): void {
    _deletedIds.add(entityId);
  },
  wasDeletedId(entityId: string): boolean {
    return _deletedIds.has(entityId);
  },

  /** Ask again for everything whose window has passed (focus, or a test). */
  reconcileDue,

  /** Tests only - the module-level state is per tab, and a test is one tab. */
  reset(): void {
    for (const key of [..._tracked.keys()]) untrackKey(key);
    _keys = EMPTY;
    _deletedIds.clear();
    _saidOutcomes.clear();
    _queryClient = null;
    emit();
  },
};

/** The keys of every record with an action parked on it, as `entityType:id`. */
export function usePendingEntityKeys(): ReadonlySet<string> {
  return useSyncExternalStore(
    pendingEntityStore.subscribe,
    pendingEntityStore.getKeys,
    () => EMPTY,
  );
}
