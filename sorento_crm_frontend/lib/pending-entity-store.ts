'use client';

import { useSyncExternalStore } from 'react';

/**
 * Which records have an action parked on them, in this tab.
 *
 * A list row's countdown lives in a toast, but the ROW has to say that it is on
 * its way out (S6-07: "the row stays visible, dimmed, until commit"). The row is
 * the `<tr>` the grid renders and the action lives in one of its cells, so the two
 * cannot talk through props - the grid reads this store instead, through
 * `rowPending` on `DataGrid`.
 *
 * It is a tab-local view of what the server is holding, written by
 * `useDeferredAction` when it parks an action and cleared when the action ends.
 * The server remains the source of truth: `GET /pending-actions/current` is what a
 * record page reads, and a second browser learns about the countdown from there,
 * never from here.
 */

type Listener = () => void;

export function pendingEntityKey(entityType: string, entityId: string): string {
  return `${entityType}:${entityId}`;
}

const EMPTY: ReadonlySet<string> = new Set<string>();

let _keys: ReadonlySet<string> = EMPTY;
const _listeners = new Set<Listener>();

function emit() {
  _listeners.forEach((fn) => fn());
}

export const pendingEntityStore = {
  getKeys(): ReadonlySet<string> {
    return _keys;
  },
  mark(entityType: string, entityId: string): void {
    const key = pendingEntityKey(entityType, entityId);
    if (_keys.has(key)) return;
    _keys = new Set([..._keys, key]);
    emit();
  },
  clear(entityType: string, entityId: string): void {
    const key = pendingEntityKey(entityType, entityId);
    if (!_keys.has(key)) return;
    const next = new Set(_keys);
    next.delete(key);
    _keys = next;
    emit();
  },
  subscribe(fn: Listener): () => void {
    _listeners.add(fn);
    return () => {
      _listeners.delete(fn);
    };
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
