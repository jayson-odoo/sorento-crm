/**
 * AC-S4-3 amended (PLAN-price-tag-r10.md S11, owner amendment 21 Sep): the
 * Overview edit form's "Price tag description" textarea is REMOVED - the
 * field has exactly one home now, the Specifications tab
 * (`ProductSpecificationsTab.priceTagDescription.test.tsx`), where it is a
 * per-product TEMPLATE with its own Insert field picker and live preview,
 * not a second plain-text copy of Description.
 *
 * Flipped test-FIRST from the ORIGINAL S4 version of this file (which
 * asserted the textarea's presence): `ProductForm.tsx` still HAS the field
 * today (S4 shipped it), so every test here is red until the coder deletes
 * it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  });
}

const CAT_ID = '11111111-1111-1111-1111-111111111111';
const UOM_ID = '22222222-2222-2222-2222-222222222222';

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="" />
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  ),
}));

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => ({ get: () => null }),
}));

const createMutateAsync = vi.fn().mockResolvedValue({});
const updateMutateAsync = vi.fn().mockResolvedValue({});
vi.mock('../hooks/useProducts', () => ({
  useCreateProduct: () => ({ mutateAsync: createMutateAsync, isPending: false }),
  useUpdateProduct: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
  useProduct: () => ({ data: undefined }),
}));

vi.mock('../../shared/hooks/use-product-category-select-query', () => ({
  useProductCategorySelectQuery: () => ({
    data: [{ id: CAT_ID, category_code: 'CAT1', category_name: 'Category 1' }],
  }),
}));
vi.mock('../../shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [] }),
}));
vi.mock('../../shared/hooks/use-uom-select-query', () => ({
  useUOMSelectQuery: () => ({ data: [{ id: UOM_ID, uom_code: 'PCS' }] }),
}));

// The chatbot stock-limits fields (PLAN-chatbot-stock-ask-v2-24sep.md S1) need
// `useHasPermission`, which needs a NextAuth `<SessionProvider>` this file does not
// set up, and `useCategory`, a real react-query hook with no `QueryClientProvider`
// here either - stub both at their own module, same idiom as
// `ProductsList.discontinued.test.tsx`.
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
}));
vi.mock('../../product-categories/hooks/useProductCategories', () => ({
  useCategory: () => ({ data: undefined }),
}));

vi.mock('@/app/(protected)/project-sales/_shared/components/PriceFloorPanel', () => ({
  PriceFloorPanel: () => <div data-testid="price-floor-stub" />,
}));
vi.mock('./ProductSuppliersSection', () => ({
  default: () => <div data-testid="suppliers-stub" />,
}));
vi.mock('./ProductAttachmentsTab', () => ({
  default: () => <div data-testid="attachments-stub" />,
}));
vi.mock('@/components/common/ListPager', () => ({
  default: () => <div data-testid="list-pager-stub" />,
}));

import ProductForm from './ProductForm';

async function fillRequiredFields() {
  fireEvent.change(screen.getByLabelText(/Product Code/i), { target: { value: 'ZZTX-002' } });
  fireEvent.change(screen.getByLabelText(/Product Name/i), { target: { value: 'Price tag description test' } });
  fireEvent.change(screen.getByLabelText('Search category...'), { target: { value: CAT_ID } });
  fireEvent.mouseDown(screen.getByRole('tab', { name: /Specifications/i }));
  fireEvent.change(await screen.findByLabelText('Select base UOM'), { target: { value: UOM_ID } });
  fireEvent.mouseDown(screen.getByRole('tab', { name: /Basic Information/i }));
}

beforeEach(() => vi.clearAllMocks());

describe('ProductForm - Price tag description is GONE from Overview (AC-S4-3 amended, S11)', () => {
  it('renders no "Price tag description" label and no textarea by that name anywhere on the form', () => {
    render(<ProductForm />);

    expect(screen.queryByText('Price tag description')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Price tag description')).not.toBeInTheDocument();
  });

  it('the create payload carries no price_tag_description key at all', async () => {
    render(<ProductForm />);
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /Save|Create/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const [payload] = createMutateAsync.mock.calls[0];
    expect(Object.prototype.hasOwnProperty.call(payload, 'price_tag_description')).toBe(false);
  });
});
