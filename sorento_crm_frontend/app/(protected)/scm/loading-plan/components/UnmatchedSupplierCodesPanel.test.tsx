/**
 * F11 / R16 / R17 - the queue of supplier codes nothing in the catalogue answers.
 *
 * The consequence lands on the loading plan: a stock row with no product is stock the plan
 * cannot offer, so a supplier holding 400 pieces of something shows as nothing.
 *
 * What is pinned here is the FORMAT, because it is the one the delivery-schedule review
 * already uses and the two must not drift: a grid, the product picked in the row itself
 * rather than through a dialog, and a Dismiss beside it for the codes that are not ours at
 * all - reversible, so it asks nothing before it acts.
 *
 * It is the shared DataGrid, so `useListingColumnPreferences` is stubbed - under jsdom
 * nothing answers its fetch and the grid renders skeletons instead of rows (CLAUDE.md).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), custom: vi.fn() },
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

// Undo on a dismissed code is `supplier_code_alias.forget` - the same action the proforma
// detail parks (D7), so it counts down instead of applying on the press. The hook itself
// is covered by `hooks/useDeferredRowAction.test.tsx`; what this file owns is that the
// button reaches it, with the ALIAS row as the record.
const deferred = vi.hoisted(() => ({
  inputs: [] as Record<string, unknown>[],
  run: vi.fn(),
}));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: (input: Record<string, unknown>) => {
    deferred.inputs.push(input);
    return { run: deferred.run, targetId: null, isPending: false };
  },
  useRowPending: () => () => false,
}));

const state = {
  rows: [] as unknown[],
  aliases: [] as unknown[],
  match: vi.fn(),
  dismiss: vi.fn(),
  rematch: vi.fn(),
};

vi.mock('../../hooks/useSupplierCodeAliases', () => ({
  useUnmatchedSupplierCodes: () => ({ data: state.rows, isLoading: false }),
  useSupplierCodeAliases: () => ({ data: state.aliases, isLoading: false }),
  useMatchSupplierCode: () => ({ mutateAsync: state.match, isPending: false }),
  useDismissSupplierCode: () => ({ mutateAsync: state.dismiss, isPending: false }),
  useRematchSupplierCodes: () => ({ mutate: state.rematch, isPending: false }),
}));

vi.mock(
  '@/app/(protected)/master-data-management/products/services/productService',
  () => ({
    getProducts: vi.fn(async () => ({
      data: [{ id: 'p-1', product_code: 'SRTWC286-SH', product_name: 'One piece toilet' }],
    })),
  }),
);

// The picker offers our product SETS beside the products (F12, R20): the supplier sells the
// whole WC under a code no product carries.
vi.mock(
  '@/app/(protected)/master-data-management/product-sets/services/productSetService',
  () => ({
    getProductSets: vi.fn(async () => ({
      data: [{ id: 's-1', set_code: 'CWC605-RL', name: 'Close-coupled WC' }],
    })),
  }),
);

/** The real picker is a server-searched combobox; a plain select is enough to express the
 *  PICK, which is what these tests are about. `fetchOptions` is called so the async path is
 *  still exercised rather than replaced. */
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    disabled,
    fetchOptions,
  }: {
    id?: string;
    value?: string;
    onChange?: (v: string) => void;
    disabled?: boolean;
    fetchOptions?: (q: string, p: number) => Promise<{ value: string; label: string }[]>;
  }) => {
    const [options, setOptions] = React.useState<{ value: string; label: string }[]>([]);
    React.useEffect(() => {
      void fetchOptions?.('', 0).then(setOptions);
    }, [fetchOptions]);
    return (
      <select
        id={id}
        aria-label="Product"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange?.(e.target.value)}
      >
        <option value="">Choose</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  },
}));

import { UnmatchedSupplierCodesPanel } from './UnmatchedSupplierCodesPanel';

const row = (over: Record<string, unknown> = {}) => ({
  item_code: 'SRTWC286-SH-250UF',
  product_name: '连体马桶',
  brand: 'SORENTO',
  spec: '纸箱包装',
  qty_packed: 400,
  qty_unfinished: 0,
  as_of: '2026-08-20',
  ...over,
});

const dismissedAlias = (over: Record<string, unknown> = {}) => ({
  id: 'a-9',
  supplier_code: 'THEIR-OWN-SPARE',
  product_code: null,
  product_name: null,
  source: 'dismissed',
  matched_by: 'dismissed',
  created_by: 'Ms Tee',
  created_at: '2026-08-27T02:00:00',
  ...over,
});

beforeEach(() => {
  state.rows = [row()];
  state.aliases = [];
  state.match = vi.fn().mockResolvedValue({
    id: 'a-1',
    supplier_code: 'SRTWC286-SH-250UF',
    product_id: 'p-1',
    product_code: 'SRTWC286-SH',
    source: 'manual',
    matched_by: 'manual',
    rebound_stock_rows: 1,
    rebound_invoice_lines: 0,
  });
  state.dismiss = vi.fn().mockResolvedValue({
    id: 'a-2',
    supplier_code: 'SRTWC286-SH-250UF',
    product_id: null,
    product_code: null,
    source: 'dismissed',
    matched_by: 'dismissed',
    rebound_stock_rows: 1,
    rebound_invoice_lines: 0,
  });
  state.rematch = vi.fn();
  deferred.inputs.length = 0;
  deferred.run.mockClear();
  // The collapse choice is per viewer and persisted (R23), so it has to be cleared between
  // tests or the first collapse leaks into every one after it.
  window.localStorage.clear();
});

describe('UnmatchedSupplierCodesPanel', () => {
  it('names the code, what the supplier called it, and what is behind it', () => {
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    expect(screen.getByText('1 code matches nothing we hold')).toBeInTheDocument();
    expect(screen.getByText('SRTWC286-SH-250UF')).toBeInTheDocument();
    expect(screen.getByText(/连体马桶 · SORENTO/)).toBeInTheDocument();
    expect(screen.getAllByText(/400/).length).toBeGreaterThanOrEqual(1);
  });

  it('says nothing at all when every code binds and nothing was dismissed', () => {
    state.rows = [];
    const { container } = render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    expect(container).toBeEmptyDOMElement();
  });

  it('offers to run the ladder again beside the queue it would shorten', () => {
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    fireEvent.click(screen.getByTestId('refresh-matching'));

    expect(state.rematch).toHaveBeenCalledWith({ supplier_id: 'sup-1' });
  });

  it('records the match from the row itself, against that row s code', async () => {
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    // The picker is server-searched, so the option lands a microtask later - waiting for it
    // is the difference between testing the pick and testing a race.
    const select = screen.getByLabelText('Product') as HTMLSelectElement;
    await waitFor(() =>
      expect(select.querySelector('option[value="p-1"]')).toBeInTheDocument(),
    );
    fireEvent.change(select, { target: { value: 'p-1' } });

    await waitFor(() => expect(state.match).toHaveBeenCalledTimes(1));
    expect(state.match).toHaveBeenCalledWith({
      supplier_id: 'sup-1',
      supplier_code: 'SRTWC286-SH-250UF',
      product_id: 'p-1',
    });
  });

  it('records a SET the same way, from the same list', async () => {
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    const select = screen.getByLabelText('Product') as HTMLSelectElement;
    await waitFor(() =>
      expect(select.querySelector('option[value="set:s-1"]')).toBeInTheDocument(),
    );
    fireEvent.change(select, { target: { value: 'set:s-1' } });

    await waitFor(() => expect(state.match).toHaveBeenCalledTimes(1));
    expect(state.match).toHaveBeenCalledWith({
      supplier_id: 'sup-1',
      supplier_code: 'SRTWC286-SH-250UF',
      product_set_id: 's-1',
    });
  });

  it('dismisses the code it was pressed for, and asks nothing first', async () => {
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    fireEvent.click(screen.getByRole('button', { name: /^dismiss$/i }));

    await waitFor(() => expect(state.dismiss).toHaveBeenCalledTimes(1));
    expect(state.dismiss).toHaveBeenCalledWith({
      supplier_id: 'sup-1',
      supplier_code: 'SRTWC286-SH-250UF',
    });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('counts what was dismissed, shows it on demand, and undoes it', () => {
    state.aliases = [
      dismissedAlias(),
      // A real match is not a dismissal and is not counted here.
      {
        id: 'a-3',
        supplier_code: 'SRTWC8357-RL-300',
        product_code: 'SRTWC8357-300-RL',
        product_name: 'One piece toilet',
        source: 'manual',
        matched_by: 'manual',
        created_by: 'Ms Tee',
        created_at: '2026-08-27T02:00:00',
      },
    ];
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    expect(screen.getByText('1 dismissed')).toBeInTheDocument();
    expect(screen.queryByText('THEIR-OWN-SPARE')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /show/i }));
    const listed = screen.getByText('THEIR-OWN-SPARE');
    expect(listed).toBeInTheDocument();

    fireEvent.click(
      within(listed.parentElement as HTMLElement).getByRole('button', { name: /undo/i }),
    );

    expect(deferred.run).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'a-9', subject: 'THEIR-OWN-SPARE' }),
    );
    expect(deferred.inputs[0]).toMatchObject({
      actionKey: 'supplier_code_alias.forget',
      entityType: 'supplier_code_alias',
    });
  });

  it('keeps the dismissed line when the queue itself is empty', () => {
    state.rows = [];
    state.aliases = [dismissedAlias()];
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    expect(screen.getByText('1 dismissed')).toBeInTheDocument();
  });
});

describe('UnmatchedSupplierCodesPanel - collapsing it (R23)', () => {
  it('opens on a queue that has something in it', () => {
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    expect(screen.getByText('SRTWC286-SH-250UF')).toBeInTheDocument();
    expect(screen.getByTestId('unmatched-codes-toggle')).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('the header hides the grid, and shows it again', () => {
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    fireEvent.click(screen.getByTestId('unmatched-codes-toggle'));

    // The header itself stays - the count is the reason to come back to it.
    expect(screen.getByText('1 code matches nothing we hold')).toBeInTheDocument();
    expect(screen.queryByText('SRTWC286-SH-250UF')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('unmatched-codes-toggle'));
    expect(screen.getByText('SRTWC286-SH-250UF')).toBeInTheDocument();
  });

  it('collapsing hides the dismissed line too, and Refresh matching stays reachable', () => {
    state.aliases = [dismissedAlias()];
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    fireEvent.click(screen.getByTestId('unmatched-codes-toggle'));

    expect(screen.queryByText('1 dismissed')).not.toBeInTheDocument();
    expect(screen.getByTestId('refresh-matching')).toBeInTheDocument();
  });

  it('remembers the choice for this viewer', () => {
    window.localStorage.setItem('scm.loadingPlan.unmatchedCollapsed', '1');
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    expect(screen.queryByText('SRTWC286-SH-250UF')).not.toBeInTheDocument();
  });

  it('writes the choice down when it changes', () => {
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    fireEvent.click(screen.getByTestId('unmatched-codes-toggle'));

    expect(window.localStorage.getItem('scm.loadingPlan.unmatchedCollapsed')).toBe('1');
  });

  it('a store that refuses to answer leaves the queue open rather than failing', () => {
    const getItem = vi
      .spyOn(Storage.prototype, 'getItem')
      .mockImplementation(() => {
        throw new Error('denied');
      });
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    expect(screen.getByText('SRTWC286-SH-250UF')).toBeInTheDocument();
    getItem.mockRestore();
  });
});
