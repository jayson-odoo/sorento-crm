/**
 * StrictMode replays a `setLayers` updater in development, and the editor
 * pushes history from inside those updaters (`addLayer`, the paste paths), so
 * one action pushed twice and took two Ctrl+Z on `next dev` (DESIGNER-PASTE
 * browser check, 3 Nov). A push identical to the current state is now skipped.
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { defaultShapeProps } from '@/lib/dealer-kit/tag-template-types';

import { useCanvasHistory } from './useCanvasHistory';

function layer(id: string): TagLayer {
  return {
    id,
    type: 'shape',
    x_mm: 0,
    y_mm: 0,
    width_mm: 10,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: defaultShapeProps(),
  };
}

describe('useCanvasHistory', () => {
  it('a push identical to the current state (a StrictMode replay) adds no undo step', () => {
    const { result } = renderHook(() => useCanvasHistory([layer('a')]));
    act(() => {
      result.current.pushState([layer('a'), layer('b')]);
      result.current.pushState([layer('a'), layer('b')]);
    });
    let restored: TagLayer[] | null = null;
    act(() => {
      restored = result.current.undo();
    });
    expect(restored!.map((l) => l.id)).toEqual(['a']);
    expect(result.current.canUndo).toBe(false);
  });

  it('distinct pushes still undo one at a time', () => {
    const { result } = renderHook(() => useCanvasHistory([layer('a')]));
    act(() => {
      result.current.pushState([layer('a'), layer('b')]);
      result.current.pushState([layer('a'), layer('b'), layer('c')]);
    });
    let restored: TagLayer[] | null = null;
    act(() => {
      restored = result.current.undo();
    });
    expect(restored!.map((l) => l.id)).toEqual(['a', 'b']);
    expect(result.current.canUndo).toBe(true);
  });
});
