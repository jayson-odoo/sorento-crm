/**
 * CreditTermsList — read-only AutoCount mirror listing.
 *   - data rows render (display term, terms, source badge);
 *   - the Source column shows the AutoCount provenance badge;
 *   - there is NO create/add button (mirror is read-only);
 *   - empty + loading states render without crashing.
 *
 * The data hook is mocked; DataGrid's browser-only deps are stubbed inline.
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
  usePathname: () => '/master-data-management/credit-terms',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const mockUseCreditTerms = vi.fn();
vi.mock('../hooks/useCreditTerms', () => ({
  useCreditTerms: (params: unknown) => mockUseCreditTerms(params),
}));

import CreditTermsList from './CreditTermsList';

const ROW = {
  id: 'ct-1',
  display_term: 'ZZT 30 DAYS',
  terms: 'Net 30',
  term_days: 30,
  is_active: true,
  internal_note: null,
  follow_up: false,
  source: 'autocount' as const,
  created_at: '2026-07-26T00:00:00',
  updated_at: null,
};

beforeEach(() => {
  cleanup();
  mockUseCreditTerms.mockReset();
});

describe('CreditTermsList', () => {
  it('renders rows with the AutoCount source badge', () => {
    mockUseCreditTerms.mockReturnValue({
      data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<CreditTermsList />);
    expect(screen.getByText('ZZT 30 DAYS')).toBeInTheDocument();
    expect(screen.getByText('Net 30')).toBeInTheDocument();
    expect(screen.getByText('AutoCount')).toBeInTheDocument();
  });

  it('has no create/add button — the mirror is read-only', () => {
    mockUseCreditTerms.mockReturnValue({
      data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<CreditTermsList />);
    expect(screen.queryByRole('button', { name: /create|add credit/i })).toBeNull();
  });

  it('renders the empty state without crashing', () => {
    mockUseCreditTerms.mockReturnValue({
      data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<CreditTermsList />);
    expect(screen.getByPlaceholderText('Search credit terms...')).toBeInTheDocument();
  });

  it('renders the loading state without crashing', () => {
    mockUseCreditTerms.mockReturnValue({
      data: undefined,
      isLoading: true,
      isFetching: true,
      refetch: vi.fn(),
    });
    render(<CreditTermsList />);
    expect(screen.getByPlaceholderText('Search credit terms...')).toBeInTheDocument();
  });
});
