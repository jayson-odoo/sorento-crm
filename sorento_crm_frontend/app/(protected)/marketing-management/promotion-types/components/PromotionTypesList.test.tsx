/**
 * PromotionTypesList — the admin screen behind per-type expiry behaviour.
 *
 * Covers loading / empty / error / data, the rule wording each row shows, and the
 * delete confirmation copy (which has to name the promotions that lose their type).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/marketing-management/promotion-types',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

// DataGrid persists column prefs via this hook (fires network) — stub it, or the
// grid renders skeletons forever and no row can be asserted.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const getPromotionTypes = vi.fn();
const deletePromotionType = vi.fn();
vi.mock('../services/promotionTypeService', () => ({
  getPromotionTypes: (...a: unknown[]) => getPromotionTypes(...a),
  deletePromotionType: (...a: unknown[]) => deletePromotionType(...a),
  createPromotionType: vi.fn(),
  updatePromotionType: vi.fn(),
  getPromotionType: vi.fn(),
}));

import PromotionTypesList from './PromotionTypesList';

const ROWS = [
  {
    id: 'type-special',
    type_code: 'special',
    type_name: 'Special Promo',
    description: 'Clearance',
    show_expired: false,
    expired_valid_until_year_end: false,
    expired_max_age_days: null,
    match_markers: ['special'],
    match_priority: 10,
    is_default: false,
    sort_order: 10,
    promotions_count: 3,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
  },
  {
    id: 'type-standard',
    type_code: 'standard',
    type_name: 'Standard Promo',
    description: null,
    show_expired: true,
    expired_valid_until_year_end: true,
    expired_max_age_days: null,
    match_markers: [],
    match_priority: 99,
    is_default: true,
    sort_order: 99,
    promotions_count: 0,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
  },
];

function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(
    <QueryClientProvider client={client}>
      <PromotionTypesList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  getPromotionTypes.mockResolvedValue({ data: ROWS, pagination: { total: ROWS.length } });
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('PromotionTypesList', () => {
  it('renders each type with its post-expiry rule in words', async () => {
    render();

    expect(await screen.findByText('Special Promo')).toBeInTheDocument();
    expect(screen.getByText('Standard Promo')).toBeInTheDocument();
    expect(screen.getByText('Not served')).toBeInTheDocument();
    expect(screen.getByText('Still served')).toBeInTheDocument();
    expect(screen.getByText('Not served once expired')).toBeInTheDocument();
    expect(screen.getByText('Still applies until end of year')).toBeInTheDocument();
  });

  it('marks the default type, since it is the rule unclassified promotions follow', async () => {
    render();
    expect(await screen.findByText('Default')).toBeInTheDocument();
  });

  it('shows an empty state that says what the screen is for', async () => {
    getPromotionTypes.mockResolvedValue({ data: [], pagination: { total: 0 } });
    render();
    expect(
      await screen.findByText(/No promotion types yet/i),
    ).toBeInTheDocument();
  });

  it('renders without rows when the fetch fails', async () => {
    getPromotionTypes.mockRejectedValue(new Error('boom'));
    render();
    await waitFor(() => expect(getPromotionTypes).toHaveBeenCalled());
    expect(screen.queryByText('Special Promo')).not.toBeInTheDocument();
  });

  it('Add opens the create modal', async () => {
    render();
    fireEvent.click(await screen.findByRole('button', { name: /add promotion type/i }));
    expect(await screen.findByText('Add promotion type')).toBeInTheDocument();
  });

  it('sorting reorders the rows, it does not just flip the arrow', async () => {
    render();
    await screen.findByText('Special Promo');

    const rowOrder = () =>
      screen
        .getAllByRole('row')
        .map((row) => row.textContent || '')
        .filter((text) => text.includes('Special Promo') || text.includes('Standard Promo'));

    expect(rowOrder()[0]).toContain('Special Promo');

    // Promotions: Special has 3, Standard has 0 — ascending must put Standard first.
    fireEvent.click(screen.getByRole('button', { name: /^Promotions$/i }));

    await waitFor(() => expect(rowOrder()[0]).toContain('Standard Promo'));
    expect(rowOrder()[1]).toContain('Special Promo');
  });

  it('delete confirmation names the promotions that lose their type', async () => {
    render();
    fireEvent.click(await screen.findByRole('button', { name: /delete special promo/i }));

    expect(await screen.findByText('Confirm delete')).toBeInTheDocument();
    expect(
      screen.getByText(/3 promotions will become unclassified/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/This action cannot be undone/i)).toBeInTheDocument();
  });
});
