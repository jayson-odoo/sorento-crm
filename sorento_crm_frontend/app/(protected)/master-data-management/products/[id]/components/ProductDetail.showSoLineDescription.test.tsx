/**
 * SO-LINE-DESC AC-7: the product detail's flags row carries a badge "SO line description in
 * OI email: Yes/No".
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

vi.mock('../../hooks/useProducts', () => ({
  useProduct: () => ({ data: PRODUCT, isLoading: false }),
  useProductPurchaseHistory: () => ({ data: undefined }),
}));

// The chatbot stock-limits row (PLAN-chatbot-stock-ask-v2-24sep.md S1) needs
// `useHasPermission`, which needs a NextAuth `<SessionProvider>` this file does not
// set up - stub the hook at its own module, same idiom as
// `ProductsList.discontinued.test.tsx`.
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
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

const PRODUCT = {
  id: 'prod-1',
  product_code: 'ZZT-1234',
  product_name: 'ZZT Kitchen Sink',
  is_active: true,
  description: 'Ordinary catalogue description',
  show_so_line_description: true,
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


describe('ProductDetail - SO line description in OI email badge (AC-7)', () => {
  it('says Yes for a ticked product', async () => {
    renderDetail();
    expect(await screen.findByText('Serial Tracking: No')).toBeInTheDocument();
    expect(await screen.findByText('SO line description in OI email: Yes')).toBeInTheDocument();
  });

  it('says No for an unticked product', async () => {
    PRODUCT.show_so_line_description = false;
    renderDetail();
    expect(await screen.findByText('Serial Tracking: No')).toBeInTheDocument();
    expect(await screen.findByText('SO line description in OI email: No')).toBeInTheDocument();
    PRODUCT.show_so_line_description = true;
  });
});
