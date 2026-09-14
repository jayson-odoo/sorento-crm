'use client';

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

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
  invalidateKeys?: readonly (readonly unknown[])[];
  /** Called after the server applied it, for a caller that has to move on. */
  onCommitted?: () => void;
  /**
   * Where the countdown goes. A list row has nowhere to put one, so the default is
   * the toast this hook was written for; `inline` hands it back as `countdown` for a
   * caller whose row HAS the room - the proforma invoice's Product cell, where the
   * control that started it is the same control the countdown replaces.
   */
  surface?: 'inline' | 'toast';
  /** Extra classes on the `inline` countdown, for a slot narrower than its own minimum. */
  countdownClassName?: string;
}

export interface UseDeferredRowActionResult {
  /** Park the action on one row. This is what the row's delete button now calls. */
  run: (target: DeferredRowTarget) => void;
  /** The row currently counting down, so a caller can disable its own control. */
  targetId: string | null;
  isPending: boolean;
  /** The countdown to render in the row, on the `inline` surface. Null otherwise. */
  countdown: ReactNode;
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
    surface = 'toast',
    countdownClassName,
  } = input;

  // The nonce, not the id, is what says "this click has not been parked yet": a
  // cancelled action leaves the same row on screen, and pressing it again has to
  // start a second window rather than be swallowed as a repeat.
  const [target, setTarget] = useState<(DeferredRowTarget & { nonce: number }) | null>(
    null,
  );
  const nonceRef = useRef(0);
  const startedRef = useRef<number | null>(null);
  //: WHICH parked action reached the server, by nonce. The target is only let go once
  //: THIS click has been pending and stopped being pending: without the nonce, a second
  //: row pressed while the first counts down (its own action not yet parked, so nothing
  //: is pending for an instant) reads as the second one having already settled.
  const reachedServerRef = useRef<number | null>(null);

  const action = useDeferredAction({
    actionKey,
    entityType,
    entityId: target?.id,
    verb,
    subject: target?.subject ?? '',
    surface,
    successMessage,
    payload: target?.payload,
    invalidateKeys,
    onCommitted,
    countdownClassName,
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

  const targetId = target?.id ?? null;
  const { isPending, countdown } = action;

  // LET THE TARGET GO once the action has settled - committed, cancelled or refused.
  // The hook used to hold the last row it acted on forever, which a toast surface never
  // noticed (the toast is the countdown, and it dismisses itself) but an `inline` one
  // cannot survive: the cell asks "is this row the target" to decide whether to draw the
  // countdown, and after a Cancel the answer stayed yes with no countdown left to draw,
  // so the cell went blank until the next refetch.
  useEffect(() => {
    if (!target) return;
    if (isPending) {
      reachedServerRef.current = target.nonce;
      return;
    }
    if (reachedServerRef.current !== target.nonce) return;
    reachedServerRef.current = null;
    setTarget(null);
  }, [target, isPending]);

  // Memoised, and load-bearing. Every migrated list reads `run` from inside its
  // `columns` useMemo, so this object is one of that memo's dependencies: a fresh
  // literal per render would rebuild `columns` on every render, and a TanStack table
  // handed new columns every render never settles - the grid renders nothing at all.
  return useMemo(
    () => ({ run, targetId, isPending, countdown }),
    [run, targetId, isPending, countdown],
  );
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
