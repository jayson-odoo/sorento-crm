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
