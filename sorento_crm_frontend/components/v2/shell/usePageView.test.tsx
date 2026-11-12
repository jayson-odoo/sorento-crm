/**
 * UI v2 phase 0, slice S3 (red first). UAC D-5 (decision D10).
 *
 * EXPORT CONTRACT:
 *   components/v2/shell/usePageView.ts : usePageView(): void
 *     Records each route change (the first route on mount counts) from next/navigation `usePathname()`. An item is
 *       { route: string (pathname only: any ?query or #hash dropped, nothing else normalised client-side),
 *         viewport: 'phone' | 'tablet' | 'desktop'   (window.innerWidth <= 720 phone, <= 1024 tablet, else desktop),
 *         ms_to_first_data: number | null (0..600000),
 *         ui_version: 'v2',
 *         at: ISO-8601 string }
 *     Items are queued and flushed as ONE batch body `{ "items": [...] }` (shape assumed by the S1 backend tests):
 *       - when the queue reaches 10 items  : apiFetch('/api/v1/system/page-views', { method: 'POST', body })
 *       - 15 s after the first queued item : the same
 *       - on `pagehide`                    : plain global fetch (not apiFetch, not sendBeacon), like
                                            lib/client-error-report.ts: first GET `<base>/api/auth/token` for
                                            `{token}`, then POST `<base>/api/v1/system/page-views` with
                                            `keepalive: true`, header `Authorization: Bearer <token>`,
                                            `Content-Type: application/json` and the same `{items}` body.
                                            No token (non-ok or empty) sends nothing. navigator.sendBeacon is
                                            never used.
 *     A flushed item is never sent twice. An unchanged pathname adds no item. Nothing is sent for an empty queue.
 *   "Mounted once in AppShell" and "no importer outside components/v2/shell" are the S4 AppShell test and the S5
 *   inventory guard (D-6); they are not asserted here.
 * import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, renderHook } from '@testing-library/react';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

let pathname = '/project-sales/order-inquiries';
vi.mock('next/navigation', () => ({
  usePathname: () => pathname,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { usePageView } from './usePageView';

const URL_RE = /\/api\/v1\/system\/page-views$/;
const fetchMock = vi.fn();
const sendBeacon = vi.fn((..._a: unknown[]) => true);

type Item = { route: string; viewport: string; ms_to_first_data: number | null; ui_version: string; at: string };

function postedBatches(): Item[][] {
  return apiFetch.mock.calls
    .filter(([u, init]) => URL_RE.test(String(u)) && init?.method === 'POST')
    .map(([, init]) => JSON.parse(init.body).items as Item[]);
}

function pageViewFetches() {
  return fetchMock.mock.calls.filter(([u]) => URL_RE.test(String(u)));
}

function setWidth(w: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: w });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  pathname = '/p0';
  setWidth(1280);
  apiFetch.mockResolvedValue({ ok: true, status: 204, json: async () => ({}) });
  fetchMock.mockImplementation(async (u: unknown) =>
    String(u).includes('/api/auth/token')
      ? { ok: true, status: 200, json: async () => ({ token: 'tok-123' }) }
      : { ok: true, status: 204, json: async () => ({}) },
  );
  vi.stubGlobal('fetch', fetchMock);
  Object.defineProperty(navigator, 'sendBeacon', { configurable: true, writable: true, value: sendBeacon });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function walk(rerender: () => void, from: number, to: number) {
  for (let i = from; i <= to; i++) {
    pathname = `/p${i}`;
    act(() => rerender());
  }
}

describe('usePageView', () => {
  it('sends nothing until a threshold is met', () => {
    renderHook(() => usePageView());
    expect(postedBatches()).toHaveLength(0);
    expect(pageViewFetches()).toHaveLength(0);
    expect(sendBeacon).not.toHaveBeenCalled();
  });

  it('flushes one batch of 10 when the tenth route is recorded', () => {
    const { rerender } = renderHook(() => usePageView());
    walk(rerender, 1, 8); // 9 items so far (p0..p8)
    expect(postedBatches()).toHaveLength(0);
    walk(rerender, 9, 9);
    const batches = postedBatches();
    expect(batches).toHaveLength(1);
    expect(batches[0].map((i) => i.route)).toEqual(Array.from({ length: 10 }, (_, i) => `/p${i}`));
  });

  it('an item has the contract shape', () => {
    const { rerender } = renderHook(() => usePageView());
    walk(rerender, 1, 9);
    const item = postedBatches()[0][0];
    expect(item.viewport).toBe('desktop');
    expect(item.ui_version).toBe('v2');
    expect(Number.isNaN(Date.parse(item.at))).toBe(false);
    if (item.ms_to_first_data !== null) {
      expect(item.ms_to_first_data).toBeGreaterThanOrEqual(0);
      expect(item.ms_to_first_data).toBeLessThanOrEqual(600000);
    }
    expect(Object.keys(item).sort()).toEqual(['at', 'ms_to_first_data', 'route', 'ui_version', 'viewport']);
  });

  it('viewport class follows the width', () => {
    setWidth(375);
    const { rerender } = renderHook(() => usePageView());
    walk(rerender, 1, 9);
    expect(postedBatches()[0][0].viewport).toBe('phone');
  });

  it('flushes what it has 15 s after the first queued item', () => {
    renderHook(() => usePageView());
    act(() => {
      vi.advanceTimersByTime(14_900);
    });
    expect(postedBatches()).toHaveLength(0);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    const batches = postedBatches();
    expect(batches).toHaveLength(1);
    expect(batches[0].map((i) => i.route)).toEqual(['/p0']);
  });

  it('never sends a flushed item twice', () => {
    renderHook(() => usePageView());
    act(() => {
      vi.advanceTimersByTime(15_100);
    });
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(postedBatches()).toHaveLength(1);
  });

  it('an unchanged pathname adds no item', () => {
    const { rerender } = renderHook(() => usePageView());
    act(() => rerender());
    act(() => rerender());
    act(() => {
      vi.advanceTimersByTime(15_100);
    });
    expect(postedBatches()[0]).toHaveLength(1);
  });

  it('drops a query or hash and normalises nothing else', () => {
    pathname = '/project-sales/order-inquiries/3f2b8a52-1c3d-4e5f-8a9b-0c1d2e3f4a5b?token=abc#top';
    renderHook(() => usePageView());
    act(() => {
      vi.advanceTimersByTime(15_100);
    });
    expect(postedBatches()[0][0].route).toBe('/project-sales/order-inquiries/3f2b8a52-1c3d-4e5f-8a9b-0c1d2e3f4a5b');
  });

 
  it('on pagehide sends the queue with fetch keepalive and the Bearer token, never sendBeacon', async () => {
    const { rerender } = renderHook(() => usePageView());
    walk(rerender, 1, 2);
    await act(async () => {
      window.dispatchEvent(new Event('pagehide'));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(sendBeacon).not.toHaveBeenCalled();
    expect(apiFetch.mock.calls.filter(([u]) => URL_RE.test(String(u)))).toHaveLength(0);
    const calls = pageViewFetches();
    expect(calls).toHaveLength(1);
    const init = calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(init.keepalive).toBe(true);
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer tok-123');
    expect(headers['Content-Type']).toBe('application/json');
    const body = JSON.parse(String(init.body)) as { items: Item[] };
    expect(body.items.map((i) => i.route)).toEqual(['/p0', '/p1', '/p2']);
    // flushed items are gone: the timer must not send them again
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000);
    });
    expect(pageViewFetches()).toHaveLength(1);
    expect(postedBatches()).toHaveLength(0);
  });

  it('pagehide without a token sends nothing', async () => {
    fetchMock.mockImplementation(async () => ({ ok: false, status: 401, json: async () => ({}) }));
    renderHook(() => usePageView());
    await act(async () => {
      window.dispatchEvent(new Event('pagehide'));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(pageViewFetches()).toHaveLength(0);
    expect(sendBeacon).not.toHaveBeenCalled();
  });
});
    expect(beacon).toHaveBeenCalledTimes(1);
    expect(String(beacon.mock.calls[0][0])).toMatch(URL_RE);
    const body = await beaconBody();
    expect(body.items.map((i) => i.route)).toEqual(['/p0', '/p1', '/p2']);
    // those items are gone: the timer must not send them again
    act(() => {
      vi.advanceTimersByTime(20_000);
    });
    expect(postedBatches()).toHaveLength(0);
  });
});
