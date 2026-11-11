/**
 * SPEC-SHEET-DESIGNER-PARITY fix round (crew browser pass on #2331): undo -> edit -> undo left the
 * edited layer on screen while the page saved the undone state (a reload showed it gone).
 *
 * The canvas adopts host layers only when the array it is handed is a DIFFERENT array from the one
 * it holds. Undo to the same history step twice handed it the same array both times, so the
 * second undo never reached the screen. Each undo / redo must hand over an array the canvas has
 * not seen, and the canvas echoing it back must not count as a new edit.
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';

const mutateAsync = vi.fn(async () => undefined);
vi.mock('../../../../../../_shared/hooks/useSpecSheet', () => ({
  useSpecSheetMutations: () => ({ autosavePage: { mutateAsync } }),
}));

import { useSheetEditing } from './useSheetEditing';

const layer = (id: string) => ({ id }) as unknown as TagLayer;

describe('useSheetEditing undo after a new edit', () => {
  it('undo -> edit -> undo hands the canvas a new array, and its echo is no new step', () => {
    const { result } = renderHook(() => useSheetEditing('p', 'd', 's'));
    const base = [layer('a')];
    const pasted = [layer('a'), layer('b')];

    act(() => result.current.report('k', base, pasted));
    act(() => result.current.undo('k'));
    const firstUndo = result.current.externalOf('k');
    expect(firstUndo?.map((l) => l.id)).toEqual(['a']);
    // The canvas adopts it and echoes it back: not an edit.
    act(() => result.current.report('k', base, firstUndo!));
    expect(result.current.canRedo('k')).toBe(true);

    const dragged = [layer('a'), layer('c')];
    act(() => result.current.report('k', base, dragged));
    act(() => result.current.undo('k'));
    const secondUndo = result.current.externalOf('k');

    expect(secondUndo?.map((l) => l.id)).toEqual(['a']);
    expect(secondUndo).not.toBe(firstUndo);
    expect(result.current.draftOf('k')).toBe(secondUndo);
    // Its echo is not an edit either: redo still brings the drag back.
    act(() => result.current.report('k', base, secondUndo!));
    act(() => result.current.redo('k'));
    expect(result.current.externalOf('k')?.map((l) => l.id)).toEqual(['a', 'c']);
  });

  it('a canvas remounting after an undo (page left and came back) keeps redo and adds no step', () => {
    const { result } = renderHook(() => useSheetEditing('p', 'd', 's'));
    const base = [layer('a')];
    act(() => result.current.report('k', base, base));
    act(() => result.current.report('k', base, [layer('a'), layer('b')]));
    act(() => result.current.undo('k'));
    const handed = result.current.externalOf('k')!;
    act(() => result.current.report('k', base, handed));
    // The page drops out of the live window and comes back: the new canvas starts from the
    // payload (base) and then adopts the host's layers.
    act(() => result.current.report('k', base, base));
    act(() => result.current.report('k', base, handed));

    expect(result.current.canRedo('k')).toBe(true);
    expect(result.current.canUndo('k')).toBe(false);
  });
});

describe('useSheetEditing forget(key) (B7)', () => {
  it('clears that page draft, history and pending save, and leaves the other pages alone', async () => {
    vi.useFakeTimers();
    mutateAsync.mockClear();
    const { result } = renderHook(() => useSheetEditing('p', 'd', 's'));
    const base = [layer('a')];
    act(() => result.current.report('one', base, [layer('a'), layer('b')]));
    act(() => result.current.report('two', base, [layer('a'), layer('c')]));
    expect(result.current.canUndo('one')).toBe(true);

    act(() => (result.current as unknown as { forget: (k: string) => void }).forget('one'));

    expect(result.current.draftOf('one')).toBeUndefined();
    expect(result.current.canUndo('one')).toBe(false);
    expect(result.current.externalOf('one')).toBeUndefined();
    expect(result.current.draftOf('two')?.map((l) => l.id)).toEqual(['a', 'c']);
    expect(result.current.canUndo('two')).toBe(true);

    // A save runs through a promise chain, so its call lands a microtask after the timer.
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });
    // Only the untouched page saves; the forgotten page's waiting save is gone.
    expect(mutateAsync.mock.calls.map((c) => (c as unknown as [{ key: string }])[0].key)).toEqual(['two']);
    vi.useRealTimers();
  });
});

