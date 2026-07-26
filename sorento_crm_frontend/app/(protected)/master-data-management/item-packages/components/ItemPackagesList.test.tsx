/**
 * ItemPackagesList — read-only AutoCount mirror listing (Slice 3).
 *   - data rows render (package code, item count, source badge);
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
  usePathname: () => '/master-data-management/item-packages',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const mockHook = vi.fn();
vi.mock('../hooks/useItemPackages', () => ({
  useItemPackages: (p: unknown) => mockHook(p),
}));

import ItemPackagesList from './ItemPackagesList';

const ROW = {
  id: 'ip-1',
  package_code: 'ZZT BUNDLE A',
  description: 'Starter bundle',
  expiry_date: null,
  limited_qty: null,
  opening_qty: null,
  user_uom: 'PCS',
  bar_code: 'ZZT001',
  further_description: null,
  is_active: true,
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
      qty: 15,
      unit_price: 15.99,
    },
  ],
};

beforeEach(() => {
  cleanup();
  mockHook.mockReset();
});

describe('ItemPackagesList', () => {
  it('renders rows with package code, item count and source badge', () => {
    mockHook.mockReturnValue({
      data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<ItemPackagesList />);
    expect(screen.getByText('ZZT BUNDLE A')).toBeInTheDocument();
    expect(screen.getByText('Starter bundle')).toBeInTheDocument();
    expect(screen.getByText('AutoCount')).toBeInTheDocument();
    // item count cell
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('has no create/add button — the mirror is read-only', () => {
    mockHook.mockReturnValue({
      data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<ItemPackagesList />);
    expect(screen.queryByRole('button', { name: /create|add package|add item/i })).toBeNull();
  });

  it('renders empty + loading without crashing', () => {
    mockHook.mockReturnValue({
      data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<ItemPackagesList />);
    expect(screen.getByPlaceholderText('Search item packages...')).toBeInTheDocument();
    cleanup();

    mockHook.mockReturnValue({ data: undefined, isLoading: true, isFetching: true, refetch: vi.fn() });
    render(<ItemPackagesList />);
    expect(screen.getByPlaceholderText('Search item packages...')).toBeInTheDocument();
  });
});
