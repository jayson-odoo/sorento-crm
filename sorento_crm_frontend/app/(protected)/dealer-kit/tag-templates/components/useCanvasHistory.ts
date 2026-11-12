'use client';

/**
 * Undo/redo for the tag canvas editor: the shared editor history (`@/hooks/useUndoHistory`, which
 * started here and now also serves the project quotation lines editor) over the layers array.
 * Every layer mutation calls `pushState` with the new layers; `undo` / `redo` restore the
 * previous / next snapshot. History is capped at 50 entries.
 */

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { useUndoHistory, type UndoHistory } from '@/hooks/useUndoHistory';

export type CanvasHistory = UndoHistory<TagLayer[]>;

export function useCanvasHistory(initialLayers: TagLayer[]): CanvasHistory {
  return useUndoHistory<TagLayer[]>(initialLayers);
}
