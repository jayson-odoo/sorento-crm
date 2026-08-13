/**
 * FormDetailTabsWithRevisions - the disabled-type history probe must not cost a
 * second network request (round 6 doc comment on the component).
 *
 * It reuses the record's OWN query (`useStockInquiry` / `usePurchaseRequest`),
 * the exact hook + query key the detail page already calls - so when both are
 * mounted under one QueryClient, React Query serves the probe from the same
 * cache entry instead of firing a second fetch. This file keeps the real
 * hooks (unlike FormDetailTabsWithRevisions.test.tsx, which mocks them to pin
 * the gating rule) and only stubs the network boundary, so a regression that
 * swaps in a dedicated lineage endpoint shows up as a second `apiFetch` call.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

vi.mock('./useRevisionEnabledMap', () => ({
  useRevisionEnabledMap: () => ({ data: { stock_inquiry: false } }),
}));

vi.mock('./FormRevisionsTab', () => ({
  __esModule: true,
  default: () => <div data-testid="form-revisions-tab" />,
}));

import { apiFetch } from '@/lib/api';
import { useStockInquiry } from '@/app/(protected)/procurement-management/stock-inquiries/hooks/useStockInquiries';
import FormDetailTabsWithRevisions from './FormDetailTabsWithRevisions';

const apiFetchMock = vi.mocked(apiFetch);

/** Stands in for the detail page, which owns `['stock-inquiry', id]` itself. */
function DetailPageStandIn({ id }: { id: string }) {
  useStockInquiry(id);
  return null;
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  apiFetchMock.mockResolvedValue({
    ok: true,
    headers: { get: () => 'application/json' },
    json: async () => ({ id: 'si-1', revision_no: 0 }),
  } as unknown as Response);
});

describe('FormDetailTabsWithRevisions - shared query with the detail page', () => {
  it('reuses the cache entry the detail page already populated instead of fetching again', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <DetailPageStandIn id="si-1" />
        <FormDetailTabsWithRevisions
          sourceEntityType="stock_inquiry"
          sourceEntityId="si-1"
          revisionsKind="stock_inquiry"
        >
          <div>Details content</div>
        </FormDetailTabsWithRevisions>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled());
    // Both the stand-in's own read and this component's disabled-type probe
    // key on the identical `['stock-inquiry', 'si-1']` query, so React Query
    // dedupes the two subscriptions to ONE network fetch, not two.
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    expect(apiFetchMock).toHaveBeenCalledWith(
      '/api/v1/procurement/stock-inquiries/si-1',
    );
  });
});
