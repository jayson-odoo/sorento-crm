'use client';

/**
 * Undo / redo over whole snapshots of an editor's state.
 *
 * Born as the price tag template designer's canvas history (`useCanvasHistory`,
 * dealer-kit/tag-templates/components/useCanvasHistory.ts, which is now this hook typed to its
 * layers) and shared with the project quotation lines editor (PROJECT-QUOTE-LINE-TOOLS, owner
 * 11 Nov: "just need to have an undo / redo function, see can reuse our price tag template
 * designer"). Every change calls `pushState` with the new state; `undo` / `redo` hand back the
 * previous / next snapshot for the caller to apply. History is capped at 50 steps.
 */

import { useCallback, useRef, useState } from 'react';

const MAX_HISTORY = 50;

export interface UndoHistory<T> {
  /**
   * Record a new state. `merge` folds it into the current step instead of adding one (several
   * keystrokes in one field are one step), and still clears redo.
   */
  pushState: (state: T, options?: { merge?: boolean }) => void;
  /** Restore the previous state. Returns the restored state, or null. */
  undo: () => T | null;
  /** Restore the next state. Returns the restored state, or null. */
  redo: () => T | null;
  /**
   * Rewrite the current state AND every undo/redo snapshot in place, with no new step: for a
   * correction from outside (a linked box following its template) that no Undo may bring back.
   */
  amend: (fn: (state: T) => T) => void;
  /** Start over from `state` with nothing to undo or redo: the state was replaced from outside. */
  reset: (state: T) => void;
  canUndo: boolean;
  canRedo: boolean;
}

export function useUndoHistory<T>(initialState: T): UndoHistory<T> {
  // Past states (most recent at end), not including the current state.
  const pastRef = useRef<T[]>([]);
  // Future states (for redo), most recent at end.
  const futureRef = useRef<T[]>([]);
  // Current snapshot, used to push onto past when a new state arrives. Copied once, on mount,
  // not on every render: the quotation editor's state is every staged line.
  const [initialSnapshot] = useState(() => structuredClone(initialState));
  const currentRef = useRef<T>(initialSnapshot);

  // Trigger re-renders when undo/redo availability changes.
  const [, forceRender] = useState(0);
  const bump = useCallback(() => forceRender((n) => n + 1), []);

  const pushState = useCallback(
    (state: T, options?: { merge?: boolean }) => {
      // Nothing changed: no undo step. This is also what keeps one action one
      // step on `next dev`, where StrictMode replays the `setLayers` updaters
      // that push from inside (`addLayer`, the paste paths) with the same input.
      if (JSON.stringify(state) === JSON.stringify(currentRef.current)) return;
      const snapshot = structuredClone(state);
      if (!options?.merge || pastRef.current.length === 0) {
        pastRef.current = [
          ...pastRef.current.slice(-(MAX_HISTORY - 1)),
          structuredClone(currentRef.current),
        ];
      }
      currentRef.current = snapshot;
      // Any new mutation clears the redo stack.
      futureRef.current = [];
      bump();
    },
    [bump],
  );

  const undo = useCallback((): T | null => {
    if (pastRef.current.length === 0) return null;
    const prev = pastRef.current.pop()!;
    futureRef.current.push(structuredClone(currentRef.current));
    currentRef.current = prev;
    bump();
    return structuredClone(prev);
  }, [bump]);

  const redo = useCallback((): T | null => {
    if (futureRef.current.length === 0) return null;
    const next = futureRef.current.pop()!;
    pastRef.current.push(structuredClone(currentRef.current));
    currentRef.current = next;
    bump();
    return structuredClone(next);
  }, [bump]);

  const amend = useCallback(
    (fn: (state: T) => T) => {
      currentRef.current = fn(currentRef.current);
      pastRef.current = pastRef.current.map(fn);
      futureRef.current = futureRef.current.map(fn);
      bump();
    },
    [bump],
  );

  const reset = useCallback(
    (state: T) => {
      currentRef.current = structuredClone(state);
      pastRef.current = [];
      futureRef.current = [];
      bump();
    },
    [bump],
  );

  return {
    pushState,
    amend,
    reset,
    undo,
    redo,
    canUndo: pastRef.current.length > 0,
    canRedo: futureRef.current.length > 0,
  };
}
