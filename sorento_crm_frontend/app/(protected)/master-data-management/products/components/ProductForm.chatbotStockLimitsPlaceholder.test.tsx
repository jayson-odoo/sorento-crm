/**
 * AC-SA110 (PLAN-chatbot-stock-ask-v2-24sep.md S1) - `ProductForm`'s two chatbot
 * stock-limit inputs (Specifications tab, beside Reorder Level / Reorder Quantity per
 * `product-schema.ts`'s own tab comment) show the SELECTED CATEGORY's X / Y as their
 * placeholder whenever the product's own value is empty.
 *
 * Tests against the LIVE shape the real `useCategory` hook and `useHasPermission` hook
 * will carry once S1 lands (`chatbot_max_qty` / `chatbot_eta_offset_days` as plain
 * fields on the category object) - NOT through `categoryService.ts`'s Phase-1
 * in-memory overlay, which Phase 2 deletes as part of greening this slice.
 *
 * Harness copied from the sibling `ProductForm.excludeFromPlanning.test.tsx` - every
 * heavy dependency is stubbed to the minimum that lets the Basic Information +
 * Specifications tabs mount, since this file's only subject is the two chatbot inputs'
 * placeholder text.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

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

// `useHasPermission('master_data.chatbot_stock_limits.view')` gates rendering the two
// inputs at all (AC-SA109's rule, shared by both forms) - true here, since this file's
// subject is the placeholder, not the gate itself.
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

// `useCategory` is the LIVE data shape S1 ships: a plain `chatbot_max_qty` /
// `chatbot_eta_offset_days` field on the category object returned for whichever id the
// form is currently watching - no Phase-1 overlay in between.
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

beforeEach(() => {
  vi.clearAllMocks();
  useCategoryMock.mockReturnValue({ data: undefined });
});

describe('ProductForm - chatbot stock-limit placeholders (AC-SA110)', () => {
  it("shows the selected category's X as the Max quantity placeholder when the product's own value is empty", () => {
    useCategoryMock.mockReturnValue({
      data: {
        id: CAT_ID,
        category_code: 'CAT1',
        category_name: 'Category 1',
        chatbot_max_qty: 75,
        chatbot_eta_offset_days: 5,
      },
    });

    render(<ProductForm />);
    selectCategory();
    goToSpecificationsTab();

    const maxQtyInput = screen.getByLabelText('Max quantity (assistant)') as HTMLInputElement;
    expect(maxQtyInput.placeholder).toBe('75');
  });

  it("shows the selected category's Y as the ETA offset placeholder when the product's own value is empty", () => {
    useCategoryMock.mockReturnValue({
      data: {
        id: CAT_ID,
        category_code: 'CAT1',
        category_name: 'Category 1',
        chatbot_max_qty: 75,
        chatbot_eta_offset_days: 5,
      },
    });

    render(<ProductForm />);
    selectCategory();
    goToSpecificationsTab();

    const etaInput = screen.getByLabelText('ETA offset (days)') as HTMLInputElement;
    expect(etaInput.placeholder).toBe('5');
  });

  it('shows no placeholder when the selected category itself has no X/Y set', () => {
    useCategoryMock.mockReturnValue({
      data: {
        id: CAT_ID,
        category_code: 'CAT1',
        category_name: 'Category 1',
        chatbot_max_qty: null,
        chatbot_eta_offset_days: null,
      },
    });

    render(<ProductForm />);
    selectCategory();
    goToSpecificationsTab();

    const maxQtyInput = screen.getByLabelText('Max quantity (assistant)') as HTMLInputElement;
    const etaInput = screen.getByLabelText('ETA offset (days)') as HTMLInputElement;
    expect(maxQtyInput.placeholder).toBe('');
    expect(etaInput.placeholder).toBe('');
  });
});
