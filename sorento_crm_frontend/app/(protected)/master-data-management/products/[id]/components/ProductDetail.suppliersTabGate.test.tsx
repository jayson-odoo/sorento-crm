/**
 * ProductDetail (#1305 reviewer pass, Lane A FE rows, S1): a role holding
 * `master_data.products.view` but not `procurement.product_suppliers.view` must not see the
 * Suppliers tab at all - today it always renders and the tab's own query 403s, which the
 * tab then degrades to "No suppliers configured for this product."
 *
 * Same stubbing technique as `ProductDetail.priceTagDescription.test.tsx`: only Overview's
 * own dependencies need to be real, everything else is a safe no-op stub.
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

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/master-data-management/products/prod-1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/components/common/BackToList', () => ({
  useBackToListHref: () => '/master-data-management/products',
}));

const purchaseHistoryCalls = vi.hoisted(() => ({ ids: [] as (string | null)[] }));
vi.mock('../../hooks/useProducts', () => ({
  useProduct: () => ({ data: PRODUCT, isLoading: false }),
  useProductPurchaseHistory: (id: string | null) => {
    purchaseHistoryCalls.ids.push(id);
    return { data: undefined };
  },
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
  cost_price: 77.5,
  invoice_price: 88,
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

describe('S1: the Suppliers tab is gated on procurement.product_suppliers.view', () => {
  it('renders no Suppliers tab for a caller without the permission', async () => {
    grantedPerms.granted.clear();
    renderDetail();

    await screen.findAllByText('ZZT Kitchen Sink');
    expect(screen.queryByRole('tab', { name: /Suppliers/i })).not.toBeInTheDocument();
  });

  it('renders the Suppliers tab for a caller with the permission and the cost permission', async () => {
    grantedPerms.granted = new Set(['procurement.product_suppliers.view', 'products.cost.view']);
    renderDetail();

    await screen.findAllByText('ZZT Kitchen Sink');
    expect(screen.getByRole('tab', { name: /Suppliers/i })).toBeInTheDocument();
  });
});

describe('SUPPLIER-COST-ACCESS: cost is for products.cost.view only', () => {
  it('hides Suppliers, Purchase History, Cost Price and the last purchase price without it', async () => {
    // A sales role today: it holds the product-suppliers slug through the cpc1 sweep.
    grantedPerms.granted = new Set(['procurement.product_suppliers.view']);
    purchaseHistoryCalls.ids = [];
    renderDetail();

    await screen.findAllByText('ZZT Kitchen Sink');
    expect(screen.queryByRole('tab', { name: /Suppliers/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Purchase History/i })).not.toBeInTheDocument();
    expect(screen.queryByText('Cost Price')).not.toBeInTheDocument();
    expect(screen.queryByText('Last purchase price')).not.toBeInTheDocument();
    expect(screen.queryByText('RM77.50')).not.toBeInTheDocument();
    // The purchase-history query is never fired (the API would refuse it).
    expect(purchaseHistoryCalls.ids.every((id) => id === null)).toBe(true);
    // List and invoice price stay (crew Q3).
    expect(screen.getAllByText('List Price').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Invoice Price').length).toBeGreaterThan(0);
  });

  it('shows them with it', async () => {
    grantedPerms.granted = new Set(['procurement.product_suppliers.view', 'products.cost.view']);
    purchaseHistoryCalls.ids = [];
    renderDetail();

    await screen.findAllByText('ZZT Kitchen Sink');
    expect(screen.getByRole('tab', { name: /Purchase History/i })).toBeInTheDocument();
    expect(screen.getByText('Cost Price')).toBeInTheDocument();
    expect(screen.getByText('Last purchase price')).toBeInTheDocument();
    expect(purchaseHistoryCalls.ids).toContain('prod-1');
  });
});
