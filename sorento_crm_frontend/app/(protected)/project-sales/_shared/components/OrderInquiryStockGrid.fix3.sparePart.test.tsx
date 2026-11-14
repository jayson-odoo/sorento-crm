/**
 * SPARE-PART-ORDER-REQUEST fix round 3, B3 (browser pass): the line stock panel never shows a raw
 * permission slug. A requester without projects.projects.view saw a red "Permission required:
 * projects.projects.view" under the line. The lead's pick is that the stock read answers for the
 * create-slug holder (backend `tests/test_spare_part_request_fix3.py::test_B3_*`). Whatever a
 * refused read says, the panel shows plain words: no text matching /Permission required|\.view\b/.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

const apiFetch = vi.fn(async (url: string) => {
  if (url.includes('/fulfilment-planning/stock-detail'))
    return json({ detail: 'Permission required: projects.projects.view' }, 403);
  return json({});
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string]) => apiFetch(...a) }));

import { OrderInquiryStockGrid } from './OrderInquiryStockGrid';

const RAW_SLUG = /Permission required|\.view\b/;

describe('B3: a refused stock read never prints a permission slug', () => {
  it('shows plain words, not "Permission required: projects.projects.view"', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={client}>
        <OrderInquiryStockGrid productId="prod-1" location="BRW-IB" />
      </QueryClientProvider>,
    );
    await waitFor(
      () => {
        expect(apiFetch.mock.calls.some(([url]) => String(url).includes('stock-detail'))).toBe(true);
        expect(screen.queryByTestId('oi-stock-grid-loading')).toBeNull();
      },
      { timeout: 8000 },
    );
    expect(container.textContent ?? '').not.toMatch(RAW_SLUG);
    expect((container.textContent ?? '').trim().length).toBeGreaterThan(0);
  }, 15000);
});
