/**
 * ProductSetDetail - the set's own page.
 *
 * The defect this covers: the members table rendered a `Checkbox` and an
 * `Input` with `defaultChecked`/`defaultValue` and no `onChange` at all -
 * decorative, nothing reached the API - and there was no view/edit
 * distinction, so an input-shaped control sat on screen even when nothing
 * about the page was editable.
 *
 * UAC groups A and B: `documentation/plans/master-data/product-sets-acceptance-criteria.md`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);

// The pager has its own tests (hooks/useListPager.test.ts).
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));

const useProductSet = vi.hoisted(() => vi.fn());
const useProductSets = vi.hoisted(() => vi.fn());
const useUpdateProductSet = vi.hoisted(() => vi.fn());

vi.mock('../hooks/useProductSets', () => ({
  // The pager reads the list page through the entity's shared key + fetch (S3-03).
  productSetsPagerQuery: {
    listQueryKey: () => ['product-sets'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  useProductSet,
  useProductSets,
  useUpdateProductSet,
}));

const getProductSetMemberOptions = vi.hoisted(() => vi.fn());
vi.mock('../services/productSetService', () => ({ getProductSetMemberOptions }));

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

import ProductSetDetail from './ProductSetDetail';
import type { ProductSetDetail as ProductSetDetailType } from '../types/productSet.types';

function member(overrides: Partial<ProductSetDetailType['members'][number]> = {}) {
  return {
    id: 'member-1',
    product_id: 'product-1',
    product_code: 'SRTWCX8608-RL',
    product_name: 'Sorento pedestal',
    description: 'Close coupled pedestal',
    list_price: 1180,
    is_discontinued: false,
    quantity: 1,
    contributes_to_price: false,
    sort_order: 0,
    available: 40,
    ...overrides,
  };
}

function set(overrides: Partial<ProductSetDetailType> = {}): ProductSetDetailType {
  return {
    id: 'set-1',
    set_code: 'SRTWC8608-RL',
    name: 'Sorento close coupled set',
    is_active: true,
    company_name: 'Sorento',
    price: {
      computed: null,
      override: null,
      resolved: null,
      is_overridden: false,
      reason: 'no_member_contributes',
    },
    member_count: 1,
    complete_sets: 7,
    limiting_member_code: null,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    members: [member()],
    ...overrides,
  };
}

function renderDetail(data: ProductSetDetailType) {
  useProductSet.mockReturnValue({ data, isLoading: false, isError: false, error: null });
  useProductSets.mockReturnValue({
    data: { data: [data], pagination: { total: 1, page: 1, limit: 500 }, empty: false },
    isLoading: false,
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(ProductSetDetail, { id: data.id }),
    ),
  );
}

function enterEdit() {
  fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
}

beforeEach(() => {
  useProductSet.mockReset();
  useProductSets.mockReset();
  useUpdateProductSet.mockReset();
  getProductSetMemberOptions.mockReset();
  getProductSetMemberOptions.mockResolvedValue([]);
  useUpdateProductSet.mockReturnValue({ mutateAsync: vi.fn().mockResolvedValue(set()), isPending: false });
});

describe('ProductSetDetail - view vs edit', () => {
  it('view mode renders no inputs or checkboxes; edit mode renders them', () => {
    const { container } = renderDetail(
      set({ members: [member({ contributes_to_price: true }), member({ id: 'm2', product_code: 'SRTWCY8608' })] }),
    );

    expect(container.querySelectorAll('input')).toHaveLength(0);
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);

    enterEdit();

    expect(container.querySelectorAll('input').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('checkbox').length).toBe(2);
  });
});

describe('ProductSetDetail - editing members', () => {
  it('ticking a member and saving PUTs contributes_to_price for that member, others unchanged', async () => {
    const mutateAsync = vi.fn().mockResolvedValue(set());
    useUpdateProductSet.mockReturnValue({ mutateAsync, isPending: false });

    renderDetail(
      set({
        members: [
          member({ id: 'm1', product_code: 'SRTWCX8608-RL', contributes_to_price: false }),
          member({ id: 'm2', product_code: 'SRTWCY8608', contributes_to_price: false }),
        ],
      }),
    );

    enterEdit();
    fireEvent.click(screen.getByRole('checkbox', { name: /SRTWCX8608-RL sets the price/i }));
    fireEvent.click(screen.getByRole('button', { name: /^Save product set$/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const [{ data: payload }] = mutateAsync.mock.calls[0];
    const byCode = Object.fromEntries(payload.members.map((m: { product_code: string }) => [m.product_code, m]));
    expect(byCode['SRTWCX8608-RL'].contributes_to_price).toBe(true);
    expect(byCode['SRTWCY8608'].contributes_to_price).toBe(false);
  });

  it('changing a quantity and saving PUTs the new quantity as a number', async () => {
    const mutateAsync = vi.fn().mockResolvedValue(set());
    useUpdateProductSet.mockReturnValue({ mutateAsync, isPending: false });

    renderDetail(set({ members: [member({ product_code: 'SRTWCX8608-RL', quantity: 1 })] }));

    enterEdit();
    const qtyInput = screen.getByRole('spinbutton', { name: /quantity for SRTWCX8608-RL/i });
    fireEvent.change(qtyInput, { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save product set$/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const [{ data: payload }] = mutateAsync.mock.calls[0];
    expect(payload.members[0].quantity).toBe(3);
    expect(typeof payload.members[0].quantity).toBe('number');
  });

  it('Cancel after edits issues no write at all', () => {
    const mutateAsync = vi.fn().mockResolvedValue(set());
    useUpdateProductSet.mockReturnValue({ mutateAsync, isPending: false });

    renderDetail(set({ members: [member({ product_code: 'SRTWCX8608-RL', contributes_to_price: false })] }));

    enterEdit();
    fireEvent.click(screen.getByRole('checkbox', { name: /SRTWCX8608-RL sets the price/i }));
    const qtyInput = screen.getByRole('spinbutton', { name: /quantity for SRTWCX8608-RL/i });
    fireEvent.change(qtyInput, { target: { value: '9' } });

    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));

    expect(mutateAsync).not.toHaveBeenCalled();
    // Back in view mode: the untouched original values render, not the edits.
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('removing a member still goes through the confirmation dialog', async () => {
    const mutateAsync = vi.fn().mockResolvedValue(set());
    useUpdateProductSet.mockReturnValue({ mutateAsync, isPending: false });

    renderDetail(set({ members: [member({ product_code: 'SRTWCX8608-RL' })] }));

    enterEdit();
    fireEvent.click(screen.getByRole('button', { name: /remove srtwcx8608-rl from set/i }));

    const dialog = await screen.findByText('Remove this member from the set?');
    expect(dialog).toBeInTheDocument();
    // Not removed from the table yet - the dialog has not been confirmed.
    expect(screen.getByText('SRTWCX8608-RL')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));

    await waitFor(() => expect(screen.queryByText('SRTWCX8608-RL')).not.toBeInTheDocument());
    // The removal only lands in the array Save sends; confirming it alone
    // writes nothing on its own.
    expect(mutateAsync).not.toHaveBeenCalled();
  });
});

describe('ProductSetDetail - price override', () => {
  it('setting an override PUTs the number', async () => {
    const mutateAsync = vi.fn().mockResolvedValue(set());
    useUpdateProductSet.mockReturnValue({ mutateAsync, isPending: false });

    renderDetail(
      set({
        price: { computed: 1180, override: null, resolved: 1180, is_overridden: false, reason: null },
        members: [member({ contributes_to_price: true })],
      }),
    );

    enterEdit();
    const overrideInput = screen.getByLabelText('Price override');
    fireEvent.change(overrideInput, { target: { value: '1500' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save product set$/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const [{ data: payload }] = mutateAsync.mock.calls[0];
    expect(payload.list_price_override).toBe(1500);
  });

  it('clearing an existing override PUTs explicit null', async () => {
    const mutateAsync = vi.fn().mockResolvedValue(set());
    useUpdateProductSet.mockReturnValue({ mutateAsync, isPending: false });

    renderDetail(
      set({
        price: {
          computed: 1180,
          override: 1150,
          resolved: 1150,
          is_overridden: true,
          reason: null,
          override_set_by_name: 'Jane Tan',
        },
        members: [member({ contributes_to_price: true })],
      }),
    );

    enterEdit();
    const overrideInput = screen.getByLabelText('Price override') as HTMLInputElement;
    expect(overrideInput.value).toBe('1150');
    fireEvent.change(overrideInput, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save product set$/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const [{ data: payload }] = mutateAsync.mock.calls[0];
    expect(payload.list_price_override).toBeNull();
  });

  it('nothing ticked renders the price as absent with a reason, not RM 0.00', () => {
    renderDetail(
      set({
        price: {
          computed: null,
          override: null,
          resolved: null,
          is_overridden: false,
          reason: 'no_member_contributes',
        },
        members: [member({ contributes_to_price: false })],
      }),
    );

    expect(screen.getByText('No member sets the price')).toBeInTheDocument();
    expect(screen.queryByText(/RM\s*0\.00/)).not.toBeInTheDocument();
  });
});
