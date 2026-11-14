/**
 * SPARE-PART-OR-B (slice 2 of #2381), red-first (Phase 2). U3.4, header list half: the OI
 * header list's number cell ("Doc no") shows `oi_no` when set, else `inquiry_no`.
 * Contract: documentation/plans/purchasing/spare-part-or-b-14nov-acceptance-criteria.md.
 * Harness copied from `OrderInquiryHeadersList.sparePart.test.tsx`.
 *
 * NAMED CONTRACT CHOICE: the header list row carries `oi_no` (backend U2.7).
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
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

const base = {
  so_number: null,
  sales_order_id: null,
  project_sales_order_id: null,
  status: 'outstanding',
  raised_at: '2026-11-12T00:00:00',
};
const NUMBERED = { ...base, id: 'h-1', inquiry_no: 'OR-2611-0003', oi_no: 'OI-2611-0009', inquiry_type: 'spare_part_request' };
const UNNUMBERED = { ...base, id: 'h-2', inquiry_no: 'OR-2611-0004', oi_no: null, inquiry_type: 'spare_part_request' };
const SALES = {
  ...base,
  id: 'h-3',
  inquiry_no: 'OI-2611-0001',
  oi_no: null,
  inquiry_type: 'sales_order',
  so_number: 'SO000123',
  sales_order_id: 'so-1',
  project_sales_order_id: 'pso-1',
};

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <OrderInquiryHeadersList />
    </QueryClientProvider>,
  );
}

function docNoCells(): string[] {
  const headerCells = screen.getAllByRole('columnheader');
  const index = headerCells.findIndex((c) => (c.textContent ?? '').trim() === 'Doc no');
  expect(index, 'a "Doc no" column').toBeGreaterThanOrEqual(0);
  const rows = screen.getAllByRole('row').filter((r) => within(r).queryAllByRole('cell').length > 0);
  return rows.map((r) => (within(r).getAllByRole('cell')[index].textContent ?? '').trim());
}

describe('U3.4: the OI header list No. cell reads the OI number', () => {
  it('a spare part request with an oi_no shows it, never its OR- number', () => {
    headers = [NUMBERED];
    renderList();
    const [text] = docNoCells();
    expect(text).toContain('OI-2611-0009');
    expect(text).not.toContain('OR-2611-0003');
  });

  it('without an oi_no it falls back to inquiry_no', () => {
    headers = [UNNUMBERED];
    renderList();
    expect(docNoCells()[0]).toContain('OR-2611-0004');
  });

  it('a sales-order OI still shows its inquiry_no', () => {
    headers = [SALES];
    renderList();
    expect(docNoCells()[0]).toContain('OI-2611-0001');
  });
});
