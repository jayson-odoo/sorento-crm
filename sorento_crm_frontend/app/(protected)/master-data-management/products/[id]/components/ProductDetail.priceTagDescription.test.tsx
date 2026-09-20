/**
 * AC-S4-3 (PLAN-price-tag-r10.md S4): the product detail's Overview tab
 * renders `price_tag_description` verbatim, with line breaks preserved.
 *
 * NEW file (no `ProductDetail.test.tsx` exists to extend, per
 * `[id]/page.backHref.test.tsx`'s own "the record itself has its own suite"
 * comment - it did not yet). Only the "overview" tab's own content mounts
 * (Radix `TabsContent` unmounts inactive tabs by default), so every OTHER
 * tab component is a safe no-op import; what has to be stubbed is what
 * `ProductDetail` itself calls directly and what renders inside Overview.
 *
 * Written test-FIRST: `ProductDetail.tsx` has no such field at all yet, so
 * the test is red on a missing element.
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

describe('ProductDetail - Overview - Price tag description (AC-S4-3)', () => {
  it('renders the stored text with line breaks preserved', async () => {
    renderDetail();

    await screen.findAllByText('ZZT Kitchen Sink');
    expect(screen.getByText('Price tag description')).toBeInTheDocument();

    const value = screen.getByTestId('price-tag-description-value');
    expect(value).toHaveTextContent('Made in Malaysia');
    expect(value).toHaveTextContent('Stainless steel');
    // Line breaks must actually be PRESERVED (CSS `white-space: pre-line`,
    // or two literal `<br>`-separated text nodes) - not collapsed into one
    // line the way a plain `<p>{text}</p>` renders whitespace by default.
    const collapsesWhitespace =
      getComputedStyle(value).whiteSpace !== 'pre-line' &&
      getComputedStyle(value).whiteSpace !== 'pre-wrap' &&
      getComputedStyle(value).whiteSpace !== 'pre';
    const hasLineBreakElements = value.querySelectorAll('br').length > 0;
    expect(collapsesWhitespace && !hasLineBreakElements).toBe(false);
  });
});
