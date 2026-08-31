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

  return {
    pushState,
    undo,
    redo,
    canUndo: pastRef.current.length > 0,
    canRedo: futureRef.current.length > 0,
  };
}
