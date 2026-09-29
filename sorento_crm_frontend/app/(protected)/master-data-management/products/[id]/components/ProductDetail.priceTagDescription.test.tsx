/**
 * AC-S4-3 amended (PLAN-price-tag-r10.md S11, owner amendment 21 Sep): the
 * product detail's Overview tab no longer renders a "Price tag description"
 * row at all - the field moved to the Specifications tab
 * (`ProductSpecificationsTab.priceTagDescription.test.tsx`), one home, not
 * two.
 *
 * Only the "overview" tab's own content mounts (Radix `TabsContent`
 * unmounts inactive tabs by default), so every OTHER tab component is a
 * safe no-op import; what has to be stubbed is what `ProductDetail` itself
 * calls directly and what renders inside Overview.
 *
 * Flipped test-FIRST from the ORIGINAL S4 version of this file (which
 * asserted the row's presence): `ProductDetail.tsx` still renders the row
 * today (S4 shipped it), so the test is red until the coder deletes it.
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
  price_tag_description: 'Made in Malaysia\nStainless steel',
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

describe('ProductDetail - Overview - Price tag description is GONE (AC-S4-3 amended, S11)', () => {
  it('renders no "Price tag description" row and no price-tag-description-value node', async () => {
    renderDetail();

    await screen.findAllByText('ZZT Kitchen Sink');

    expect(screen.queryByText('Price tag description')).not.toBeInTheDocument();
    expect(screen.queryByTestId('price-tag-description-value')).not.toBeInTheDocument();
  });
});
