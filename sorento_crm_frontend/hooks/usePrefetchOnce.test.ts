/**
 * M4 list latency - `router.prefetch(href)`, at most once per href.
 *
 * Three call sites share this hook rather than each rolling its own `Set`
 * ref: a clickable `DataGrid` row (hover), the detail pager's prev/next
 * neighbours (mount), and the sidebar menu (hover).
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { usePrefetchOnce } from './usePrefetchOnce';

const prefetch = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ prefetch }),
}));

beforeEach(() => {
  prefetch.mockReset();
});

const realMatchMedia = window.matchMedia;
afterEach(() => {
  window.matchMedia = realMatchMedia;
});

/** Answers `matches` for `(hover: none)` and never matches anything else. */
function stubHover(hoverNone: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query.includes('hover: none') ? hoverNone : false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

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

describe('usePrefetchOnce on a touch device', () => {
  it('does not prefetch when (hover: none) matches', () => {
    // `pointerenter` fires on the tap that is ALREADY opening the record, so the
    // prefetch is pure cost: a second request for a page the click is fetching.
    stubHover(true);
    const { result } = renderHook(() => usePrefetchOnce());

    act(() => result.current('/orders/a1'));

    expect(prefetch).not.toHaveBeenCalled();
  });

  it('prefetches when (hover: none) does not match', () => {
    // Asked in the positive on purpose: a stub that answers "no match" to every
    // query - jsdom's, and the one this repo installs in vitest.setup.ts - would
    // read `!(hover: hover)` as "no hover" and switch prefetching off everywhere.
    stubHover(false);
    const { result } = renderHook(() => usePrefetchOnce());

    act(() => result.current('/orders/a1'));

    expect(prefetch).toHaveBeenCalledWith('/orders/a1');
  });

  it('prefetches when the environment has no matchMedia at all', () => {
    (window as { matchMedia?: unknown }).matchMedia = undefined;
    const { result } = renderHook(() => usePrefetchOnce());

    act(() => result.current('/orders/a1'));

    expect(prefetch).toHaveBeenCalledWith('/orders/a1');
  });
});
