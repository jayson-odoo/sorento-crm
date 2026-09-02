/**
 * M4 list latency - `router.prefetch(href)`, at most once per href.
 *
 * Three call sites share this hook rather than each rolling its own `Set`
 * ref: a clickable `DataGrid` row (hover), the detail pager's prev/next
 * neighbours (mount), and the sidebar menu (hover).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { usePrefetchOnce } from './usePrefetchOnce';

const prefetch = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ prefetch }),
}));

beforeEach(() => {
  prefetch.mockReset();
});

describe('usePrefetchOnce', () => {
  it('calls router.prefetch for a new href', () => {
    const { result } = renderHook(() => usePrefetchOnce());

    act(() => result.current('/orders/a1'));

    expect(prefetch).toHaveBeenCalledTimes(1);
    expect(prefetch).toHaveBeenCalledWith('/orders/a1');
  });

  it('calls it only once for the same href across repeated calls', () => {
    const { result } = renderHook(() => usePrefetchOnce());

    act(() => {
      result.current('/orders/a1');
      result.current('/orders/a1');
      result.current('/orders/a1');
    });

    expect(prefetch).toHaveBeenCalledTimes(1);
  });

  it('calls it again for a different href', () => {
    const { result } = renderHook(() => usePrefetchOnce());

    act(() => {
      result.current('/orders/a1');
      result.current('/orders/a2');
    });

    expect(prefetch).toHaveBeenCalledTimes(2);
    expect(prefetch).toHaveBeenNthCalledWith(1, '/orders/a1');
    expect(prefetch).toHaveBeenNthCalledWith(2, '/orders/a2');
  });

  it('keeps the same seen-set across re-renders of the calling component', () => {
    const { result, rerender } = renderHook(() => usePrefetchOnce());
    act(() => result.current('/orders/a1'));
    rerender();

    act(() => result.current('/orders/a1'));

    expect(prefetch).toHaveBeenCalledTimes(1);
  });
});
