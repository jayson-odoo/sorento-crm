/**
 * SO-LINE-DESC AC-7: the product create/edit form carries a "Show SO line description in OI
 * email" switch (default off) beside Serial/Batch Tracking, posting `show_so_line_description`.
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
vi.mock('../../shared/hooks/use-item-class-select-query', () => ({
  useItemClassSelectQuery: () => ({ data: [] }),
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
  fireEvent.change(screen.getByLabelText(/Product Code/i), { target: { value: 'ZZTX-001' } });
  fireEvent.change(screen.getByLabelText(/Product Name/i), { target: { value: 'Exclude test product' } });
  fireEvent.change(screen.getByLabelText('Search category...'), { target: { value: CAT_ID } });
  // Base UOM lives on the Specifications tab. Radix's TabsTrigger in this codebase
  // activates on mousedown (see `PlanRowDialogs.test.tsx`'s own tab-switch idiom).
  fireEvent.mouseDown(screen.getByRole('tab', { name: /Specifications/i }));
  fireEvent.change(await screen.findByLabelText('Select base UOM'), { target: { value: UOM_ID } });
  fireEvent.mouseDown(screen.getByRole('tab', { name: /Basic Information/i }));
}

beforeEach(() => vi.clearAllMocks());


function tickSwitch(): HTMLElement {
  fireEvent.mouseDown(screen.getByRole('tab', { name: /Specifications/i }));
  return screen.getByRole('switch', { name: /Show SO line description in OI email/i });
}

beforeEach(() => vi.clearAllMocks());

describe('ProductForm - Show SO line description in OI email (AC-7)', () => {
  it('renders the switch off by default, beside Serial and Batch Tracking', async () => {
    render(<ProductForm />);
    const toggle = tickSwitch();
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByText('Serial Tracking')).toBeInTheDocument();
    expect(screen.getByText('Batch Tracking')).toBeInTheDocument();
  });

  it('posts show_so_line_description: true when switched on', async () => {
    render(<ProductForm />);
    fireEvent.change(screen.getByLabelText(/Product Code/i), { target: { value: 'RPACC' } });
    fireEvent.change(screen.getByLabelText(/Product Name/i), { target: { value: 'RPACC' } });
    fireEvent.change(screen.getByLabelText('Search category...'), { target: { value: CAT_ID } });
    fireEvent.mouseDown(screen.getByRole('tab', { name: /Specifications/i }));
    fireEvent.change(await screen.findByLabelText('Select base UOM'), { target: { value: UOM_ID } });
    fireEvent.click(tickSwitch());

    fireEvent.click(screen.getByRole('button', { name: /Save|Create/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const [payload] = createMutateAsync.mock.calls[0];
    expect(payload.show_so_line_description).toBe(true);
  });

  it('posts false when left alone', async () => {
    render(<ProductForm />);
    fireEvent.change(screen.getByLabelText(/Product Code/i), { target: { value: 'RPAC' } });
    fireEvent.change(screen.getByLabelText(/Product Name/i), { target: { value: 'RPAC' } });
    fireEvent.change(screen.getByLabelText('Search category...'), { target: { value: CAT_ID } });
    fireEvent.mouseDown(screen.getByRole('tab', { name: /Specifications/i }));
    fireEvent.change(await screen.findByLabelText('Select base UOM'), { target: { value: UOM_ID } });

    fireEvent.click(screen.getByRole('button', { name: /Save|Create/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    expect(createMutateAsync.mock.calls[0][0].show_so_line_description).toBe(false);
  });
});
