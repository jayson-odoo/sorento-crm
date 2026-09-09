/**
 * AC-S5.4 (PLAN-reorder-feedback-9sep.md, S5) - the product create/edit form gets an
 * "Exclude from reorder planning" switch under the existing status fields (Active
 * Status / Chat Search), and it round-trips `exclude_from_planning` on submit.
 *
 * NEW file (no `ProductForm.test.tsx` exists to extend) - every heavy dependency
 * (mutation hooks, select queries, the Pricing-tab price-floor panel, Suppliers/
 * Attachments tab bodies, the list pager) is stubbed to the minimum that lets the
 * "Basic Information" + "Specifications" tabs mount and submit, since this test's only
 * subject is the new switch and its payload.
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

describe('ProductForm - Exclude from reorder planning switch (AC-S5.4)', () => {
  it('renders under the existing status fields, alongside Active Status and Chat Search', () => {
    render(<ProductForm />);
    expect(screen.getByText('Active Status')).toBeInTheDocument();
    expect(screen.getByText('Chat Search')).toBeInTheDocument();
    expect(screen.getByText('Exclude from reorder planning')).toBeInTheDocument();
  });

  it('round-trips exclude_from_planning: true into the create payload on submit', async () => {
    render(<ProductForm />);
    await fillRequiredFields();

    const switchLabel = screen.getByText('Exclude from reorder planning');
    const toggle = switchLabel.closest('div')?.parentElement?.querySelector('button[role="switch"]');
    expect(toggle).toBeTruthy();
    fireEvent.click(toggle as Element);

    fireEvent.click(screen.getByRole('button', { name: /Save|Create/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    const [payload] = createMutateAsync.mock.calls[0];
    expect(payload.exclude_from_planning).toBe(true);
  });

  it('AC-S5.7: accepts an AutoCount placeholder code (**NEW) so it can be excluded', async () => {
    // The buyer's own flow: **NEW/**SPARE PART/**REPLACE/**REPAIR are the codes S5 exists
    // to let purchasing opt out of - a product-code validator that rejects `*` blocks the
    // whole slice at the form (found by the browser walk, 9 Sep).
    render(<ProductForm />);
    fireEvent.change(screen.getByLabelText(/Product Code/i), { target: { value: '**NEW' } });
    fireEvent.change(screen.getByLabelText(/Product Name/i), {
      target: { value: 'Placeholder code product' },
    });
    fireEvent.change(screen.getByLabelText('Search category...'), { target: { value: CAT_ID } });
    fireEvent.mouseDown(screen.getByRole('tab', { name: /Specifications/i }));
    fireEvent.change(await screen.findByLabelText('Select base UOM'), { target: { value: UOM_ID } });
    fireEvent.mouseDown(screen.getByRole('tab', { name: /Basic Information/i }));

    fireEvent.click(screen.getByRole('button', { name: /Save|Create/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled());
    expect(screen.queryByText(/may contain letters, numbers, spaces/i)).not.toBeInTheDocument();
    const [payload] = createMutateAsync.mock.calls[0];
    expect(payload.product_code).toBe('**NEW');
  });
});
