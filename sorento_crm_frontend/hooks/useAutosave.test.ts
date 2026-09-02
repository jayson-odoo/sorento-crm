/**
 * The one debounce behind every committed-change autosave (D22, S8).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useAutosave, AUTOSAVE_DEBOUNCE_MS } from './useAutosave';

describe('useAutosave (D22, S8)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('collapses rapid edits into a single save, ~1s after the LAST one', async () => {
    const onSave = vi.fn(async () => {});
    const { result } = renderHook(() => useAutosave(onSave));

    act(() => {
      result.current.schedule('a');
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS - 1);
    });
    expect(onSave).not.toHaveBeenCalled();

    // A second edit lands before the first would have fired - the clock
    // resets, not adds a second save.
    act(() => {
      result.current.schedule('b');
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS - 1);
    });
    expect(onSave).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith('b');
    expect(result.current.status).toBe('saved');
    expect(result.current.savedAt).not.toBeNull();
  });

  it('shows Saving the instant an edit is scheduled, before the debounce fires', () => {
    const onSave = vi.fn(async () => {});
    const { result } = renderHook(() => useAutosave(onSave));

    expect(result.current.status).toBe('idle');
    act(() => {
      result.current.schedule('a');
    });
    expect(result.current.status).toBe('saving');
  });

  it('flush() saves the pending value immediately, cutting the debounce short', async () => {
    const onSave = vi.fn(async () => {});
    const { result } = renderHook(() => useAutosave(onSave));

    act(() => {
      result.current.schedule('a');
    });
    expect(onSave).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.flush();
    });
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith('a');
    expect(result.current.status).toBe('saved');

    // The debounce that flush() cut short must not ALSO fire later.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS);
    });
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it('flush() with nothing pending is a no-op', async () => {
    const onSave = vi.fn(async () => {});
    const { result } = renderHook(() => useAutosave(onSave));

    await act(async () => {
      await result.current.flush();
    });
    expect(onSave).not.toHaveBeenCalled();
    expect(result.current.status).toBe('idle');
  });

  // -------------------------------------------------------------------------
  // Serialised saves (B5). Two overlapping PUTs of the same document can land
  // in either order and the LOSER is what the server keeps, so a flush fired a
  // moment after an autosave could persist the older document and silently
  // undo the newer edit.
  // -------------------------------------------------------------------------

  it('runs overlapping saves one after another, in the order they were asked for', async () => {
    const started: string[] = [];
    const finished: string[] = [];
    const releases: Array<() => void> = [];
    const onSave = vi.fn(
      (value: string) =>
        new Promise<void>((resolve) => {
          started.push(value);
          releases.push(() => {
            finished.push(value);
            resolve();
          });
        }),
    );
    const { result } = renderHook(() => useAutosave(onSave));

    act(() => {
      result.current.schedule('a');
    });
    let firstFlush!: Promise<void>;
    act(() => {
      firstFlush = result.current.flush();
    });
    // The save is chained onto the (empty) in-flight slot, so it begins on the
    // next microtask rather than synchronously.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(started).toEqual(['a']);

    // A second save asked for while the first is still in flight must WAIT,
    // not start alongside it.
    act(() => {
      result.current.schedule('b');
    });
    let secondFlush!: Promise<void>;
    act(() => {
      secondFlush = result.current.flush();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(started).toEqual(['a']);

    await act(async () => {
      releases[0]();
      await firstFlush;
    });
    expect(started).toEqual(['a', 'b']);

    await act(async () => {
      releases[1]();
      await secondFlush;
    });
    expect(finished).toEqual(['a', 'b']);
    expect(result.current.status).toBe('saved');
  });

  it('flush() waits for a save already in flight even with nothing new pending', async () => {
    let release!: () => void;
    const onSave = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          release = resolve;
        }),
    );
    const { result } = renderHook(() => useAutosave(onSave));

    act(() => {
      result.current.schedule('a');
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS);
    });
    expect(onSave).toHaveBeenCalledTimes(1);

    let settled = false;
    let pendingFlush!: Promise<void>;
    act(() => {
      pendingFlush = result.current.flush().then(() => {
        settled = true;
      });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    // Nothing new to send, but the save on the wire has not landed - a caller
    // that is about to navigate away is waiting for exactly this.
    expect(settled).toBe(false);

    await act(async () => {
      release();
      await pendingFlush;
    });
    expect(settled).toBe(true);
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it('a failed save shows error, and retry() resends the same value', async () => {
    const onSave = vi.fn().mockRejectedValueOnce(new Error('network down')).mockResolvedValueOnce(undefined);
    const { result } = renderHook(() => useAutosave(onSave));

    act(() => {
      result.current.schedule('a');
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS);
    });
    expect(result.current.status).toBe('error');
    expect(onSave).toHaveBeenCalledTimes(1);

    await act(async () => {
      result.current.retry();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(onSave).toHaveBeenCalledTimes(2);
    expect(onSave).toHaveBeenNthCalledWith(2, 'a');
    expect(result.current.status).toBe('saved');
  });
});
