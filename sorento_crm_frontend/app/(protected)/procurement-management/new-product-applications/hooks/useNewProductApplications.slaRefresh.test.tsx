/**
 * Owner re-test 9 Nov ~03:05: after Update & Reply the NPA's SLA tab still showed the purchasing
 * stage open. The backend had moved it; the page never re-read its trackers. Like the stock inquiry
 * page (StockInquiryDetail.tsx refreshes ['form-sla-trackers'] after its response actions), every
 * NPA move refreshes the SLA tab and the handling lock.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../services/newProductApplicationService', async (orig) => {
  const actual = await orig<Record<string, unknown>>();
  const ok = vi.fn(async () => ({ id: 'a-1' }));
  return {
    ...actual,
    replyNewProductApplicationPurchasingResponse: ok,
    saveNewProductApplicationPurchasingResponse: ok,
    approveNewProductApplication: ok,
  };
});

import { useNewProductApplicationMutations } from './useNewProductApplications';

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useNewProductApplicationMutations(), { wrapper });
  const keys = () => spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));
  return { result, keys };
}

describe('NPA moves refresh the SLA tab and the handling lock', () => {
  it.each(['purchasingReply', 'purchasingResponse'] as const)('%s', async (name) => {
    const { result, keys } = setup();
    await act(async () => {
      await result.current[name].mutateAsync({ id: 'a-1', data: { purchasing_response: 'x' } });
    });
    expect(keys()).toContain(JSON.stringify(['form-sla-trackers']));
    expect(keys()).toContain(JSON.stringify(['form-handling-tracker']));
  });
});
