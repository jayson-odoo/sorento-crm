/**
 * SPARE-PART-ORDER-REQUEST F1 (UAC P3): the Order Inquiries header list carries a Type
 * column - "Spare part request" / "Sales order", off the header's `inquiry_type` - and the
 * S/O no cell reads "-" for a spare part request (it has no sales order).
 *
 * TEST-FIRST (Phase 2): the Type column does not exist yet, so a red here is "Unable to find
 * an element with the text: Type / Spare part request", never a harness error. Harness copied
 * from `OrderInquiryHeadersList.consignment.test.tsx`.
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

function rowOf(inquiryNo: string): HTMLElement {
  return screen.getByText(inquiryNo).closest('tr') as HTMLElement;
}

function cellUnder(row: HTMLElement, headerText: string): HTMLElement {
  const headerCells = screen.getAllByRole('columnheader');
  const index = headerCells.findIndex((cell) => (cell.textContent ?? '').trim() === headerText);
  expect(index, `a "${headerText}" column`).toBeGreaterThanOrEqual(0);
  return within(row).getAllByRole('cell')[index];
}

describe('F1 / UAC P3: Type column and the S/O no of a spare part request', () => {
  it('shows a Type column', () => {
    headers = [SPARE, SALES];
    renderList();
    expect(
      screen.getAllByRole('columnheader').some((cell) => (cell.textContent ?? '').trim() === 'Type'),
    ).toBe(true);
  });

  it('reads "Order request" and "Sales order" in the Type cell', () => {
    headers = [SPARE, SALES];
    renderList();
    expect(cellUnder(rowOf('OI-2611-0007'), 'Type')).toHaveTextContent(/^Order request$/);
    expect(cellUnder(rowOf('OI-2611-0001'), 'Type')).toHaveTextContent(/^Sales order$/);
  });

  it('a header with no inquiry_type (older payload) reads Sales order', () => {
    const legacy: Record<string, unknown> = { ...SALES };
    delete legacy.inquiry_type;
    headers = [legacy];
    renderList();
    expect(cellUnder(rowOf('OI-2611-0001'), 'Type')).toHaveTextContent(/^Sales order$/);
  });

  it('the S/O no cell of a spare part request reads "-"', () => {
    headers = [SPARE, SALES];
    renderList();
    expect(cellUnder(rowOf('OI-2611-0007'), 'S/O no')).toHaveTextContent(/^-$/);
    expect(cellUnder(rowOf('OI-2611-0001'), 'S/O no')).toHaveTextContent('SO000123');
  });
});
