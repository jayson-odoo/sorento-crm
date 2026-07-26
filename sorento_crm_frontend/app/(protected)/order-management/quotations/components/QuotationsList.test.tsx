/**
 * QuotationsList — read-only AutoCount mirror listing (Slice 6).
 *   - data rows render (quote number, debtor, source badge);
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
  usePathname: () => '/order-management/quotations',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const mockHook = vi.fn();
vi.mock('../hooks/useQuotations', () => ({
  useQuotations: (p: unknown) => mockHook(p),
}));

import QuotationsList from './QuotationsList';

const ROW = {
  id: 'qt-1',
  quote_number: 'AC-SMOKE-QT-1',
  source_doc_no: 'QT-0001',
  debtor_code: 'D-100',
  debtor_name: 'Smoke Debtor Sdn Bhd',
  doc_date: '2026-07-26',
  is_cancelled: false,
  attention: 'Ms Smoke',
  branch_code: 'HQ',
  deliver_addr1: '1 Test Street',
  deliver_addr2: null,
  deliver_addr3: null,
  deliver_addr4: null,
  terms: 'C.O.D',
  sales_agent: 'AGENT-1',
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
      discount_amt: 0,
      tax_code: 'SR',
      tax_rate: 6,
      tax: 14.39,
      description: 'Line description',
      further_description: null,
      package_code: null,
      proj_no: null,
      dept_no: null,
    },
  ],
};

beforeEach(() => {
  cleanup();
  mockHook.mockReset();
});

describe('QuotationsList', () => {
  it('renders rows with quote number, debtor and source badge', () => {
    mockHook.mockReturnValue({
      data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<QuotationsList />);
    expect(screen.getByText('AC-SMOKE-QT-1')).toBeInTheDocument();
    expect(screen.getByText('Smoke Debtor Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('AutoCount')).toBeInTheDocument();
  });

  it('has no create/add button — the mirror is read-only', () => {
    mockHook.mockReturnValue({
      data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<QuotationsList />);
    expect(
      screen.queryByRole('button', { name: /create|add quotation|add quote|new quotation/i }),
    ).toBeNull();
  });

  it('renders empty + loading without crashing', () => {
    mockHook.mockReturnValue({
      data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<QuotationsList />);
    expect(screen.getByPlaceholderText('Search quotations...')).toBeInTheDocument();
    cleanup();

    mockHook.mockReturnValue({ data: undefined, isLoading: true, isFetching: true, refetch: vi.fn() });
    render(<QuotationsList />);
    expect(screen.getByPlaceholderText('Search quotations...')).toBeInTheDocument();
  });
});
