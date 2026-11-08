'use client';

/**
 * Undo/redo hook for the tag canvas editor.
 *
 * Maintains a stack of layer snapshots. Every layer mutation calls `pushState`
 * with the new layers array. `undo` / `redo` restore the previous / next
 * snapshot. History is capped at 50 entries.
 */

import { useCallback, useRef, useState } from 'react';
import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';

const MAX_HISTORY = 50;

export interface CanvasHistory {
  /** Push the current layers state onto the history stack. */
  pushState: (layers: TagLayer[]) => void;
  /** Restore the previous state. Returns the restored layers, or null. */
  undo: () => TagLayer[] | null;
  /** Restore the next state. Returns the restored layers, or null. */
  redo: () => TagLayer[] | null;
  /**
   * Rewrite the current state AND every undo/redo snapshot in place, with no new step: for a correction
   * from outside (a linked box following its template) that no Undo may bring back.
   */
  amend: (fn: (layers: TagLayer[]) => TagLayer[]) => void;
  canUndo: boolean;
  canRedo: boolean;
}

export function useCanvasHistory(initialLayers: TagLayer[]): CanvasHistory {
  // Past states (most recent at end), not including the current state.
  const pastRef = useRef<TagLayer[][]>([]);
  // Future states (for redo), most recent at end.
  const futureRef = useRef<TagLayer[][]>([]);
  // Current snapshot, used to push onto past when a new state arrives.
  const currentRef = useRef<TagLayer[]>(structuredClone(initialLayers));

  // Trigger re-renders when undo/redo availability changes.
  const [, forceRender] = useState(0);
  const bump = useCallback(() => forceRender((n) => n + 1), []);

  const pushState = useCallback(
    (layers: TagLayer[]) => {
      // Nothing changed: no undo step. This is also what keeps one action one
      // step on `next dev`, where StrictMode replays the `setLayers` updaters
      // that push from inside (`addLayer`, the paste paths) with the same input.
      if (JSON.stringify(layers) === JSON.stringify(currentRef.current)) return;
      const snapshot = structuredClone(layers);
      pastRef.current = [
        ...pastRef.current.slice(-(MAX_HISTORY - 1)),
        structuredClone(currentRef.current),
      ];
      currentRef.current = snapshot;
      // Any new mutation clears the redo stack.
      futureRef.current = [];
      bump();
    },
    [bump],
  );

  const undo = useCallback((): TagLayer[] | null => {
    if (pastRef.current.length === 0) return null;
    const prev = pastRef.current.pop()!;
    futureRef.current.push(structuredClone(currentRef.current));
    currentRef.current = prev;
    bump();
    return structuredClone(prev);
  }, [bump]);

  const redo = useCallback((): TagLayer[] | null => {
    if (futureRef.current.length === 0) return null;
    const next = futureRef.current.pop()!;
    pastRef.current.push(structuredClone(currentRef.current));
    currentRef.current = next;
    bump();
    return structuredClone(next);
  }, [bump]);

  const amend = useCallback(
    (fn: (layers: TagLayer[]) => TagLayer[]) => {
      currentRef.current = fn(currentRef.current);
      pastRef.current = pastRef.current.map(fn);
      futureRef.current = futureRef.current.map(fn);
      bump();
    },
    [bump],
  );

  return {
    pushState,
    amend,
    undo,
    redo,
    canUndo: pastRef.current.length > 0,
    canRedo: futureRef.current.length > 0,
  };
}
