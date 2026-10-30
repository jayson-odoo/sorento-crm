/**
 * OI-AUTO-CONFIRM AC-AC-12 (owner, mock v1 note): the Documents list has no Lines column,
 * and its Outstanding empty state reads "Nothing to order".
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

let searchParamsValue = '';
vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/order-inquiries',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(searchParamsValue),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/services/userSelectService', () => ({ getUserLookup: vi.fn(async () => []) }));

let permissions = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => permissions.has(slug),
}));

const SUMMARY = {
  parked: 17,
  needs_reserve: 0,
  notice_parked: 0,
  reserved: 0,
  my_parked_requests: 17,
  my_parked_notices: 3,
};
const getSummarySpy = vi.fn(async () => ({ ...SUMMARY }));
const previewRequestsSpy = vi.fn(async () => ({ emails: [], unresolved: [] }));
const previewNoticesSpy = vi.fn(async () => ({ emails: [], unresolved: [] }));
vi.mock('../../_shared/services/orderInquiryReserveService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/orderInquiryReserveService')
  >();
  return {
    ...actual,
    getReserveStatusSummary: () => getSummarySpy(),
    previewParkedReserveRequests: () => previewRequestsSpy(),
    previewParkedReserveNotices: () => previewNoticesSpy(),
    sendParkedReserveRequests: vi.fn(),
    sendParkedReserveNotices: vi.fn(),
  };
});

let headers: Array<Record<string, unknown>> = [];
const listSpy = vi.fn(async (_params: Record<string, unknown>) => ({
  data: headers,
  total: headers.length,
  page: 1,
  limit: 25,
}));
vi.mock('../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    listOrderInquiryHeaders: (params: Record<string, unknown>) => listSpy(params),
    getOrderInquiryWorklistSummary: vi.fn(async () => ({ agents: [], projects: [] })),
  };
});

import { OrderInquiryHeadersList } from './OrderInquiryHeadersList';


function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <OrderInquiryHeadersList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParamsValue = '';
  permissions = new Set(['projects.order_inquiries.acknowledge', 'projects.order_inquiries.reserve']);
  getSummarySpy.mockImplementation(async () => ({ ...SUMMARY }));
});

describe('AC-AC-12: the Documents list', () => {
  it('has no Lines column', async () => {
    headers = [
      {
        id: 'h-1',
        inquiry_no: 'OI-0001',
        so_number: 'SO000123',
        sales_order_id: 'so-1',
        status: 'outstanding',
        lines_total: 3,
        lines_to_confirm: 1,
        raised_at: '2026-10-01T00:00:00',
        reserve_status: null,
        parked_by_name: null,
      },
    ];
    renderList();
    await screen.findByText('OI-0001');

    const headerTexts = screen.getAllByRole('columnheader').map((el) => el.textContent?.trim());
    expect(headerTexts).not.toContain('Lines');
    expect(screen.queryByText('1 / 3')).not.toBeInTheDocument();
  });

  it('reads "Nothing to order" when Outstanding is empty', async () => {
    headers = [];
    renderList();

    expect(await screen.findByText('Nothing to order')).toBeInTheDocument();
    expect(screen.queryByText('Nothing to confirm')).not.toBeInTheDocument();
  });
});
