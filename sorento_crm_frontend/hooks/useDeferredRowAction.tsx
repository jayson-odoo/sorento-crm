'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { useDeferredAction } from '@/hooks/useDeferredAction';
import {
  pendingEntityKey,
  usePendingEntityKeys,
} from '@/lib/pending-entity-store';

/**
 * The grace window for an action started from a LIST ROW or a panel row (S6-07).
 *
 * `useDeferredAction` is written for a record page: it knows which record it is
 * about before anything is clicked, because the page is that record. A list does
 * not - the record is whichever row the reader just pressed - and the shape every
 * list reached for instead was a `deleting` state plus one dialog mounted at the
 * bottom of the file. This keeps the first half of that shape and drops the
 * second: `run(row)` parks the action, and the countdown appears in a toast while
 * the row dims.
 *
 * Built here rather than inline per list because S6b migrates roughly thirty of
 * them and they are the same three lines each; the alternative is a per-row
 * component in every list, which is a component to mount, name and test for a
 * button that already exists.
 */

export interface DeferredRowTarget {
  id: string;
  /** What the reader calls the record. It is the toast's second line, never a UUID. */
  subject: string;
  /** Whatever the handler needs at commit time beyond the id. */
  payload?: Record<string, unknown>;
}

export interface UseDeferredRowActionInput {
  /** `<entity>.<verb>`, e.g. `market_topic.delete`. */
  actionKey: string;
  /** The registry's entity type, e.g. `market_topic`. */
  entityType: string;
  /** Verb-first copy for the countdown: "Deleting" reads as "Deleting in 8s". */
  verb?: string;
  /** Said once the server has applied it. */
  successMessage: string;
  /** Lists to refetch once the action has committed. */
  invalidateKeys?: readonly unknown[][];
  /** Called after the server applied it, for a caller that has to move on. */
  onCommitted?: () => void;
}

export interface UseDeferredRowActionResult {
  /** Park the action on one row. This is what the row's delete button now calls. */
  run: (target: DeferredRowTarget) => void;
  /** The row currently counting down, so a caller can disable its own control. */
  targetId: string | null;
  isPending: boolean;
}

export function useDeferredRowAction(
  input: UseDeferredRowActionInput,
): UseDeferredRowActionResult {
  const {
    actionKey,
    entityType,
    verb = 'Deleting',
    successMessage,
    invalidateKeys,
    onCommitted,
  } = input;

  // The nonce, not the id, is what says "this click has not been parked yet": a
  // cancelled action leaves the same row on screen, and pressing it again has to
  // start a second window rather than be swallowed as a repeat.
  const [target, setTarget] = useState<(DeferredRowTarget & { nonce: number }) | null>(
    null,
  );
  const nonceRef = useRef(0);
  const startedRef = useRef<number | null>(null);

  const action = useDeferredAction({
    actionKey,
    entityType,
    entityId: target?.id,
    verb,
    subject: target?.subject ?? '',
    surface: 'toast',
    successMessage,
    payload: target?.payload,
    invalidateKeys,
    onCommitted,
  });

  const { start } = action;

  // Parked from an effect rather than from the click, because the hook above needs
  // the row's id in its own props before it can park anything, and that id only
  // arrives on the render the click causes.
  useEffect(() => {
    if (!target || startedRef.current === target.nonce) return;
    startedRef.current = target.nonce;
    start(target.payload);
  }, [target, start]);

  const run = useCallback((next: DeferredRowTarget) => {
    nonceRef.current += 1;
    setTarget({ ...next, nonce: nonceRef.current });
  }, []);

  return { run, targetId: target?.id ?? null, isPending: action.isPending };
}

/**
 * `rowPending` for a DataGrid, for the rows of one entity type.
 *
 * The row dims while its action counts down (S6-07) and the grid learns which
 * rows those are from the tab-local store, because the action lives in a cell and
 * the `<tr>` is the grid's.
 */
export function useRowPending<T extends { id: string }>(
  entityType: string,
): (row: T) => boolean {
  const keys = usePendingEntityKeys();
  return useCallback(
    (row: T) => keys.has(pendingEntityKey(entityType, row.id)),
    [keys, entityType],
  );
}

export default useDeferredRowAction;
