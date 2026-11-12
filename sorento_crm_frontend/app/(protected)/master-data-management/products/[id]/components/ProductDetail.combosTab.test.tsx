/**
 * COMBO-SETTINGS-UX (owner 10 Nov, mock v2 approval): the combo settings live in their OWN product
 * tab, "Combos", next to the other product tabs, not as a card on Overview. The tab badge counts the
 * combos, like Attachments / Promotions / Variants. The tab lives in the URL (`?tab=combos`).
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  });
}

const nav = vi.hoisted(() => ({ search: '' }));
vi.mock('../../hooks/useProductCombos', () => ({
  useProductCombos: () => ({ data: [{ id: 'c1' }, { id: 'c2' }] }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/master-data-management/products/prod-1',
  useSearchParams: () => new URLSearchParams(nav.search),
}));

vi.mock('@/components/common/BackToList', () => ({
  useBackToListHref: () => '/master-data-management/products',
}));

vi.mock('../../hooks/useProducts', () => ({
  useProduct: () => ({ data: PRODUCT, isLoading: false }),
  useProductPurchaseHistory: () => ({ data: undefined }),
}));

const grantedPerms = vi.hoisted(() => ({ granted: new Set<string>() }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => grantedPerms.granted.has(slug),
}));

vi.mock('../../../product-attachments/hooks/useProductAttachments', () => ({
  useProductAttachmentsByProduct: () => ({ data: [] }),
}));

vi.mock(
  '@/app/(protected)/marketing-management/promotions/services/promotionService',
  () => ({ getPromotionsByProductId: vi.fn(async () => []) }),
);

vi.mock('@/app/(protected)/project-sales/_shared/components/PriceFloorPanel', () => ({
  PriceFloorPanel: () => <div data-testid="price-floor-stub" />,
}));

vi.mock('../../actions', () => ({
  useProductActions: () => ({ actions: [], dialogs: null, pending: false }),
}));

vi.mock('@/hooks/useDeletedRecordGuard', () => ({
  useDeletedRecordGuard: () => false,
}));

vi.mock('@/components/common/DetailActions', () => ({
  __esModule: true,
  default: () => <div data-testid="detail-actions-stub" />,
}));

vi.mock('./ProductCombosSection', () => ({
  __esModule: true,
  default: () => <div data-testid="combos-stub" />,
}));
vi.mock('./ProductSoldWithSection', () => ({
  __esModule: true,
  default: () => <div data-testid="sold-with-stub" />,
}));
vi.mock('./ProductSuppliersTab', () => ({
  __esModule: true,
  default: () => <div data-testid="suppliers-tab-stub" />,
}));

const PRODUCT = {
  id: 'prod-1',
  product_code: 'ZZT-1234',
  product_name: 'ZZT Kitchen Sink',
  is_active: true,
  description: 'Ordinary catalogue description',
  category: null,
  brand: null,
  barcode: null,
  base_uom: null,
  list_price: 100,
  variants: [],
  field_attachments: [],
};

import ProductDetail from './ProductDetail';

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProductDetail productId="prod-1" />
    </QueryClientProvider>,
  );
}

describe('the Combos tab', () => {
  it('is a tab of its own with the combo count, and Overview no longer carries the combos', async () => {
    nav.search = '';
    renderDetail();
    await screen.findAllByText('ZZT Kitchen Sink');
    expect(screen.getByRole('tab', { name: 'Combos (2)' })).toBeInTheDocument();
    expect(screen.queryByTestId('combos-stub')).not.toBeInTheDocument();
  });

  it('?tab=combos opens it on the combos', async () => {
    nav.search = 'tab=combos';
    renderDetail();
    await screen.findAllByText('ZZT Kitchen Sink');
    expect(screen.getByRole('tab', { name: 'Combos (2)' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('combos-stub')).toBeInTheDocument();
  });
});
