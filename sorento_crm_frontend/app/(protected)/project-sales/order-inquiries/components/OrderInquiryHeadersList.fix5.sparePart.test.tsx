/**
 * SPARE-PART-ORDER-REQUEST fix round 5 (browser pass 2), D7: the Type column fits "Spare part
 * request" at 1280 (the pass saw "Spare part requ..."). The rendered header width must be at
 * least 190 px: 18 characters at ~8 px, the cell's 16 px padding each side and the 20 px drag
 * grip (measured header markup: `px-4` plus the grip icon). Harness copied from
 * `OrderInquiryHeadersList.sparePart.test.tsx`.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/order-inquiries',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => []),
}));

vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => false }));

let headers: Array<Record<string, unknown>> = [];
vi.mock('../../_shared/hooks/useOrderInquiry', () => ({
  useOrderInquiryHeaders: () => ({
    data: { data: headers, total: headers.length },
    isLoading: false,
    isPlaceholderData: false,
    isFetching: false,
    refetch: vi.fn(),
    error: null,
  }),
  useOrderInquiryWorklistSummary: () => ({ data: { agents: [], projects: [] } }),
  useReserveStatusSummary: () => ({ data: undefined }),
  useParkedPreview: () => ({ data: undefined, isLoading: false }),
  useSendParked: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useHandoverResendPreview: () => ({ data: undefined, isLoading: false, error: null }),
  useSendHandoverResend: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import { OrderInquiryHeadersList } from './OrderInquiryHeadersList';

const SPARE = {
  id: 'h-spare',
  inquiry_no: 'OI-2611-0007',
  inquiry_type: 'spare_part_request',
  so_number: null,
  sales_order_id: null,
  project_sales_order_id: null,
  status: 'open',
  raised_at: '2026-11-12T00:00:00',
};
const SALES = {
  id: 'h-sales',
  inquiry_no: 'OI-2611-0001',
  inquiry_type: 'sales_order',
  so_number: 'SO000123',
  sales_order_id: 'so-1',
  project_sales_order_id: 'pso-1',
  status: 'open',
  raised_at: '2026-11-01T00:00:00',
};

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <OrderInquiryHeadersList />
    </QueryClientProvider>,
  );
}

describe('D7: the Type column fits its longest value', () => {
  it('the Type header is at least 190 px wide', () => {
    headers = [SPARE, SALES];
    renderList();
    const th = screen
      .getAllByRole('columnheader')
      .find((cell) => (cell.textContent ?? '').trim() === 'Type') as HTMLElement;
    expect(th, 'a Type column').toBeDefined();
    const width = parseInt(th.style.width || '0', 10);
    expect(width).toBeGreaterThanOrEqual(190);
  });
});
