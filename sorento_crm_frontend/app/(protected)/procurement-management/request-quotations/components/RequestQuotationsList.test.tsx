/**
 * RequestQuotationsList — read-only AutoCount mirror listing (Slice 7).
 *   - data rows render (rq number, supplier, source badge);
 *   - no create/add affordance (read-only mirror);
 *   - empty + loading render without crashing.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

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
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/request-quotations',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const mockHook = vi.fn();
vi.mock('../hooks/useRequestQuotations', () => ({
  useRequestQuotations: (p: unknown) => mockHook(p),
}));

import RequestQuotationsList from './RequestQuotationsList';

const ROW = {
  id: 'rq-1',
  rq_number: 'AC-SMOKE-RQ-1',
  source_doc_no: 'RQ-0001',
  supplier_id: 's1',
  supplier_code: 'DEFAULT',
  supplier_name: 'Smoke Supplier Sdn Bhd',
  creditor_code: 'C-100',
  creditor_name: 'Smoke Creditor',
  doc_date: '2026-07-26',
  purchase_agent: 'AGENT-1',
  internal_note: null,
  follow_up: false,
  source: 'autocount' as const,
  created_at: '2026-07-26T00:00:00',
  updated_at: null,
  lines: [
    {
      id: 'l1',
      product_id: 'p1',
      product_code: 'BRACD7799CP-ENG',
      product_name: 'A product',
      line_sequence: 1,
      uom: 'PCS',
      location: 'WH-1',
      qty: 15,
      unit_price: 15.99,
      sub_total: 239.85,
    },
  ],
};

beforeEach(() => {
  cleanup();
  mockHook.mockReset();
});

describe('RequestQuotationsList', () => {
  it('renders rows with rq number, supplier and source badge', () => {
    mockHook.mockReturnValue({
      data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<RequestQuotationsList />);
    expect(screen.getByText('AC-SMOKE-RQ-1')).toBeInTheDocument();
    expect(screen.getByText('Smoke Supplier Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('AutoCount')).toBeInTheDocument();
  });

  it('has no create/add button — the mirror is read-only', () => {
    mockHook.mockReturnValue({
      data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<RequestQuotationsList />);
    expect(
      screen.queryByRole('button', {
        name: /create|add request|add quotation|new request|new quotation/i,
      }),
    ).toBeNull();
  });

  it('renders empty + loading without crashing', () => {
    mockHook.mockReturnValue({
      data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<RequestQuotationsList />);
    expect(screen.getByPlaceholderText('Search request quotations...')).toBeInTheDocument();
    cleanup();

    mockHook.mockReturnValue({
      data: undefined,
      isLoading: true,
      isFetching: true,
      refetch: vi.fn(),
    });
    render(<RequestQuotationsList />);
    expect(screen.getByPlaceholderText('Search request quotations...')).toBeInTheDocument();
  });
});
