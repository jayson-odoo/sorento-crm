/**
 * AC-S4-3 (PLAN-price-tag-r10.md S4): the product Overview edit form shows a
 * "Price tag description" textarea below Description; saving sends the field.
 *
 * NEW file (no `ProductForm.test.tsx` exists to extend) - mirrors
 * `ProductForm.excludeFromPlanning.test.tsx`'s stub stack exactly, the
 * precedent for testing one new field on this form in isolation.
 *
 * Written test-FIRST: `ProductForm.tsx` has no such field at all yet, so
 * every test here is red on a missing element.
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

describe('ProductForm - Price tag description (AC-S4-3)', () => {
  it('renders a "Price tag description" textarea directly below Description', () => {
    render(<ProductForm />);

    const descriptionLabel = screen.getByText('Description');
    const priceTagLabel = screen.getByText('Price tag description');
    expect(priceTagLabel).toBeInTheDocument();
    // Document order: Price tag description comes AFTER Description.
    // eslint-disable-next-line no-bitwise
    expect(
      descriptionLabel.compareDocumentPosition(priceTagLabel) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    const textarea = screen.getByLabelText('Price tag description');
    expect(textarea.tagName).toBe('TEXTAREA');
  });

  it('round-trips price_tag_description into the create payload on submit', async () => {
    render(<ProductForm />);
    await fillRequiredFields();

    fireEvent.change(screen.getByLabelText('Price tag description'), {
      target: { value: 'Made in Malaysia\nStainless steel' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Save|Create/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const [payload] = createMutateAsync.mock.calls[0];
    expect(payload.price_tag_description).toBe('Made in Malaysia\nStainless steel');
  });
});
