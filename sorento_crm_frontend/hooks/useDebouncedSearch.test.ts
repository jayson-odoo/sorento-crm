/**
 * S7-02 - the one debounce behind every list's search box.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useDebouncedSearch, SEARCH_DEBOUNCE_MS } from './useDebouncedSearch';

describe('useDebouncedSearch (S7-02)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('waits 200ms before the debounced value follows a typed value', () => {
    const { result } = renderHook(() => useDebouncedSearch());

    act(() => {
      result.current.setValue('ada');
    });

    // Not yet - the box is ahead of the query.
    expect(result.current.debouncedValue).toBe('');
    expect(result.current.value).toBe('ada');

    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 1);
    });
    expect(result.current.debouncedValue).toBe('');

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current.debouncedValue).toBe('ada');
  });

  it('reports isSettling true exactly while the box and the query disagree', () => {
    const { result } = renderHook(() => useDebouncedSearch());

    expect(result.current.isSettling).toBe(false);

    act(() => {
      result.current.setValue('ac');
    });
    expect(result.current.isSettling).toBe(true);

    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    });
    expect(result.current.isSettling).toBe(false);
  });

  it('reset() sets both halves immediately, with no debounce wait', () => {
    const { result } = renderHook(() => useDebouncedSearch());

    act(() => {
      result.current.reset('restored search');
    });

    expect(result.current.value).toBe('restored search');
    expect(result.current.debouncedValue).toBe('restored search');
    expect(result.current.isSettling).toBe(false);

    // Confirm no pending timer sneaks a second update in later.
    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS * 2);
    });
    expect(result.current.value).toBe('restored search');
    expect(result.current.debouncedValue).toBe('restored search');
  });

  it('trims the debounced value but leaves the box text alone', () => {
    const { result } = renderHook(() => useDebouncedSearch());

    act(() => {
      result.current.setValue('ada ');
    });
    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    });

    expect(result.current.value).toBe('ada ');
    expect(result.current.debouncedValue).toBe('ada');
  });
});
