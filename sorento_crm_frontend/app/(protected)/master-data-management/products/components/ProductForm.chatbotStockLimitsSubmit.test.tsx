/**
 * Blocking 1 (reviewer pass, PR #1221, 85c2e9e7) - `ProductForm`'s zod schema
 * (`product-schema.ts`) turned an empty/unset X or Y into an explicit `0` on submit:
 * `z.union([z.coerce.number()..., z.null()])` tries the coerce branch first, and
 * `Number(null)` is `0`, so both the field's default `null` and a cleared value passed
 * validation as `0` before the resolver ever tried the `z.null()` branch. R2: unset must
 * stay unset so the category can opt the product in later; an explicit `0` is a real
 * value that overrides the category's own X/Y.
 *
 * Harness copied from the sibling `ProductForm.chatbotStockLimitsPlaceholder.test.tsx`.
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
const PRODUCT_ID = '33333333-3333-3333-3333-333333333333';

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
  useRouter: () => ({ push: pushMock, back: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

const createMutateAsync = vi.fn().mockResolvedValue({});
const updateMutateAsync = vi.fn().mockResolvedValue({});
const useProductMock = vi.fn();
vi.mock('../hooks/useProducts', () => ({
  useCreateProduct: () => ({ mutateAsync: createMutateAsync, isPending: false }),
  useUpdateProduct: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
  useProduct: (id: string | null) => useProductMock(id),
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

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

const useCategoryMock = vi.fn();
vi.mock('../../product-categories/hooks/useProductCategories', () => ({
  useCategory: (id: string | null) => useCategoryMock(id),
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

function selectCategory() {
  fireEvent.change(screen.getByLabelText('Search category...'), { target: { value: CAT_ID } });
}

function goToSpecificationsTab() {
  fireEvent.mouseDown(screen.getByRole('tab', { name: /Specifications/i }));
}

function selectBaseUom() {
  fireEvent.change(screen.getByLabelText('Select base UOM'), { target: { value: UOM_ID } });
}

beforeEach(() => {
  vi.clearAllMocks();
  useCategoryMock.mockReturnValue({ data: undefined });
  useProductMock.mockReturnValue({ data: undefined });
});

describe('ProductForm - chatbot stock-limit submit payload (Blocking 1)', () => {
  it('create: leaving both fields empty submits null, not 0', async () => {
    render(<ProductForm />);

    fireEvent.change(screen.getByLabelText('Product Code *'), { target: { value: 'PROD-1' } });
    fireEvent.change(screen.getByLabelText('Product Name *'), { target: { value: 'Product One' } });
    selectCategory();
    goToSpecificationsTab();
    selectBaseUom();

    fireEvent.click(screen.getByRole('button', { name: /Create Product/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const payload = createMutateAsync.mock.calls[0][0];
    expect(payload.chatbot_max_qty).toBeUndefined();
    expect(payload.chatbot_eta_offset_days).toBeUndefined();
  });

  it('create: typing 0 in both fields submits 0, not null/undefined', async () => {
    render(<ProductForm />);

    fireEvent.change(screen.getByLabelText('Product Code *'), { target: { value: 'PROD-2' } });
    fireEvent.change(screen.getByLabelText('Product Name *'), { target: { value: 'Product Two' } });
    selectCategory();
    goToSpecificationsTab();
    selectBaseUom();
    fireEvent.change(screen.getByLabelText('Max quantity (assistant)'), { target: { value: '0' } });
    fireEvent.change(screen.getByLabelText('ETA offset (days)'), { target: { value: '0' } });

    fireEvent.click(screen.getByRole('button', { name: /Create Product/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const payload = createMutateAsync.mock.calls[0][0];
    expect(payload.chatbot_max_qty).toBe(0);
    expect(payload.chatbot_eta_offset_days).toBe(0);
  });

  it('edit: clearing both fields on a product that had values submits null, not 0', async () => {
    useProductMock.mockReturnValue({
      data: {
        id: PRODUCT_ID,
        product_code: 'PROD-3',
        product_name: 'Product Three',
        category_id: CAT_ID,
        base_uom_id: UOM_ID,
        list_price: 10,
        is_active: true,
        is_searchable: true,
        exclude_from_planning: false,
        has_serial_tracking: false,
        has_batch_tracking: false,
        reorder_level: 10,
        reorder_quantity: 50,
        chatbot_max_qty: 40,
        chatbot_eta_offset_days: 6,
      },
    });

    render(<ProductForm productId={PRODUCT_ID} />);
    goToSpecificationsTab();

    fireEvent.change(screen.getByLabelText('Max quantity (assistant)'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('ETA offset (days)'), { target: { value: '' } });

    fireEvent.click(screen.getByRole('button', { name: /Update Product/i }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const call = updateMutateAsync.mock.calls[0][0];
    const payload = call.data ?? call;
    expect(payload.chatbot_max_qty).toBeNull();
    expect(payload.chatbot_eta_offset_days).toBeNull();
  });

  it('edit: saving with the existing 0 values untouched submits 0, not null', async () => {
    useProductMock.mockReturnValue({
      data: {
        id: PRODUCT_ID,
        product_code: 'PROD-4',
        product_name: 'Product Four',
        category_id: CAT_ID,
        base_uom_id: UOM_ID,
        list_price: 10,
        is_active: true,
        is_searchable: true,
        exclude_from_planning: false,
        has_serial_tracking: false,
        has_batch_tracking: false,
        reorder_level: 10,
        reorder_quantity: 50,
        chatbot_max_qty: 0,
        chatbot_eta_offset_days: 0,
      },
    });

    render(<ProductForm productId={PRODUCT_ID} />);
    goToSpecificationsTab();

    fireEvent.click(screen.getByRole('button', { name: /Update Product/i }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const call = updateMutateAsync.mock.calls[0][0];
    const payload = call.data ?? call;
    expect(payload.chatbot_max_qty).toBe(0);
    expect(payload.chatbot_eta_offset_days).toBe(0);
  });
});
