/**
 * PromotionsList — the Type column.
 *
 * A promotion's type decides whether it still applies after its end date, so the
 * list has to show it (by NAME, never the id) and has to say something useful for
 * a row that has none rather than a bare dash.
 *
 * Unlike the sibling deep-link spec, this file stubs `useListingColumnPreferences`,
 * which is what keeps the shared DataGrid stuck on skeleton rows under jsdom.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/marketing-management/promotions',
  useSearchParams: () => ({ get: () => null }),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const getPromotions = vi.fn();
vi.mock('../services/promotionService', () => ({
  getPromotions: (...a: unknown[]) => getPromotions(...a),
}));
vi.mock('@/hooks/useTenantModules', () => ({
  useTenantModules: () => ({ enabledModuleKeys: new Set(['marketing']), isLoading: false }),
}));
vi.mock(
  '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes',
  () => ({ useContactAccessTypes: () => ({ data: [] }) }),
);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

import PromotionsList from './PromotionsList';

const ROWS = [
  {
    id: 'promo-typed',
    description: 'JULY SORENTO WC PROMO',
    access_levels: ['sorento_dealer'],
    is_active: false,
    is_expired: true,
    expired_but_usable: true,
    promotion_type_id: 'type-standard',
    promotion_type_code: 'standard',
    promotion_type_name: 'Standard Promo',
    promotion_type_source: 'auto',
    products_count: 2,
    attachments: [],
    created_at: '2026-06-01T00:00:00Z',
    start_date: '2026-05-01',
    end_date: '2026-07-31',
  },
  {
    id: 'promo-untyped',
    description: 'MBF97581 PROMO',
    access_levels: ['sorento_dealer'],
    is_active: true,
    promotion_type_id: null,
    promotion_type_code: null,
    promotion_type_name: null,
    products_count: 0,
    attachments: [],
    created_at: '2026-06-02T00:00:00Z',
    start_date: '2026-06-02',
    end_date: '2026-09-02',
  },
];

function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(
    <QueryClientProvider client={client}>
      <PromotionsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  getPromotions.mockResolvedValue({ data: ROWS, pagination: { total: ROWS.length } });
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('PromotionsList — Type column', () => {
  it('renders the type NAME, never the id', async () => {
    render();

    expect(await screen.findByText('Standard Promo')).toBeInTheDocument();
    expect(screen.queryByText('type-standard')).not.toBeInTheDocument();
  });

  it('says Unclassified for a promotion with no type', async () => {
    render();
    expect(await screen.findByText('Unclassified')).toBeInTheDocument();
  });

  it('has a Type column header', async () => {
    render();
    expect(await screen.findByText('Type')).toBeInTheDocument();
  });
});
