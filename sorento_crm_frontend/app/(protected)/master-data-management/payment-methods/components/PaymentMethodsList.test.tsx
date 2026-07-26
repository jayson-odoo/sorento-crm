/**
 * PaymentMethodsList — read-only AutoCount mirror listing (Slice 2).
 * Representative of the 3 Slice-2 mirror lists (all identical clones):
 *   - data rows render with the AutoCount source badge;
 *   - no create/add affordance (read-only mirror);
 *   - empty + loading states render without crashing.
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
  usePathname: () => '/master-data-management/payment-methods',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const mockHook = vi.fn();
vi.mock('../hooks/usePaymentMethods', () => ({
  usePaymentMethods: (p: unknown) => mockHook(p),
}));

import PaymentMethodsList from './PaymentMethodsList';

const ROW = {
  id: 'pm-1',
  payment_method: 'ZZT Cash',
  description: 'Cash payment',
  bank_account: '5141-2233',
  journal_type: 'CB',
  is_active: true,
  internal_note: null,
  follow_up: false,
  source: 'autocount' as const,
  created_at: '2026-07-26T00:00:00',
  updated_at: null,
};

beforeEach(() => {
  cleanup();
  mockHook.mockReset();
});

describe('PaymentMethodsList', () => {
  it('renders rows with the AutoCount source badge', () => {
    mockHook.mockReturnValue({
      data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<PaymentMethodsList />);
    expect(screen.getByText('ZZT Cash')).toBeInTheDocument();
    expect(screen.getByText('5141-2233')).toBeInTheDocument();
    expect(screen.getByText('AutoCount')).toBeInTheDocument();
  });

  it('has no create/add button — the mirror is read-only', () => {
    mockHook.mockReturnValue({
      data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<PaymentMethodsList />);
    expect(screen.queryByRole('button', { name: /create|add payment/i })).toBeNull();
  });

  it('renders empty + loading without crashing', () => {
    mockHook.mockReturnValue({
      data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<PaymentMethodsList />);
    expect(screen.getByPlaceholderText('Search payment methods...')).toBeInTheDocument();
    cleanup();

    mockHook.mockReturnValue({ data: undefined, isLoading: true, isFetching: true, refetch: vi.fn() });
    render(<PaymentMethodsList />);
    expect(screen.getByPlaceholderText('Search payment methods...')).toBeInTheDocument();
  });
});
