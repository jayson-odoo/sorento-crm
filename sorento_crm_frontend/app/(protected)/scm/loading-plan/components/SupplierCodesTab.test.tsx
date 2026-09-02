/**
 * S3 (`PLAN-scm-loading-plan-feedback-2sep.md` 3.3, UAC section C) - the Supplier codes tab
 * replaces `UnmatchedSupplierCodesPanel`: a pick or a dismiss keeps the row where it is, with
 * Undo, and the supplier's whole memory (matched and dismissed alike) is visible below it,
 * where before only dismissals were - and only on request.
 *
 * What is pinned here: AC-C1 (stay + Undo on a match), AC-C2 (stay + Undo on a dismiss),
 * AC-C3 (two groups, the picker never invalidates on its own, so the decided row is still
 * showing when the test ends), the Remembered columns and their sort, and both empty states
 * (AC-B4). Undo/the tab-leave invalidation is `useSupplierCodeAliases.ts`'s own contract -
 * this file proves the component reaches it and never invalidates on pick or dismiss.
 *
 * It is the shared DataGrid, so `useListingColumnPreferences` is stubbed - under jsdom
 * nothing answers its fetch and the grid renders skeletons instead of rows (CLAUDE.md).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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

// Forget (the Remembered list's own action) is still the deferred row action - unchanged
// from the old panel. Its own hook is covered by `hooks/useDeferredRowAction.test.tsx`; what
// this file owns is that the button reaches it, with the ALIAS row as the record.
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
  undo: vi.fn(),
  rematch: vi.fn(),
};

vi.mock('../../hooks/useSupplierCodeAliases', () => ({
  useUnmatchedSupplierCodes: () => ({ data: state.rows, isLoading: false }),
  useSupplierCodeAliases: () => ({ data: state.aliases, isLoading: false }),
  useMatchSupplierCodeInPlace: () => ({ mutateAsync: state.match, isPending: false }),
  useDismissSupplierCodeInPlace: () => ({ mutateAsync: state.dismiss, isPending: false }),
  useUndoSupplierCodeDecision: () => ({ mutate: state.undo, isPending: false }),
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
 *  PICK - `onOptionChange` (the label the row shows after the pick) is wired the same way
 *  the real component wires it. */
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    onOptionChange,
    disabled,
    fetchOptions,
  }: {
    id?: string;
    value?: string;
    onChange?: (v: string) => void;
    onOptionChange?: (opt: { value: string; label: string } | null) => void;
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
        onChange={(e) => {
          const opt = options.find((o) => o.value === e.target.value) ?? null;
          onChange?.(e.target.value);
          onOptionChange?.(opt);
        }}
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

import { SupplierCodesTab } from './SupplierCodesTab';

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

const alias = (over: Record<string, unknown> = {}) => ({
  id: 'a-1',
  supplier_code: 'SRTWC8357-RL-300',
  product_code: 'SRTWC8357-300-RL',
  product_name: 'One piece toilet',
  set_code: null,
  set_name: null,
  source: 'manual',
  matched_by: 'manual',
  created_by: 'Ms Tee',
  created_at: '2026-08-27T02:00:00',
  ...over,
});

function renderTab(documentLabel = 'Stock list 27/07/2026') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const utils = render(
    <QueryClientProvider client={qc}>
      <SupplierCodesTab supplierId="sup-1" documentLabel={documentLabel} />
    </QueryClientProvider>,
  );
  return { ...utils, invalidateSpy };
}

beforeEach(() => {
  state.rows = [row()];
  state.aliases = [];
  state.match = vi.fn().mockResolvedValue({
    id: 'a-9',
    supplier_code: 'SRTWC286-SH-250UF',
    product_id: 'p-1',
    product_code: 'SRTWC286-SH',
    product_set_id: null,
    set_code: null,
    set_name: null,
    source: 'manual',
    matched_by: 'manual',
    rebound_stock_rows: 1,
    rebound_invoice_lines: 0,
  });
  state.dismiss = vi.fn().mockResolvedValue({
    id: 'a-8',
    supplier_code: 'SRTWC286-SH-250UF',
    product_id: null,
    product_code: null,
    product_set_id: null,
    set_code: null,
    set_name: null,
    source: 'dismissed',
    matched_by: 'dismissed',
    rebound_stock_rows: 1,
    rebound_invoice_lines: 0,
  });
  state.undo = vi.fn((_id: string, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());
  state.rematch = vi.fn();
  deferred.inputs.length = 0;
  deferred.run.mockClear();
});

describe('SupplierCodesTab - names the statement (AC-G2 stub)', () => {
  it('names the plan\'s own document', () => {
    renderTab('Stock list 27/07/2026');
    expect(screen.getByText('Codes read off Stock list 27/07/2026')).toBeInTheDocument();
  });
});

describe('SupplierCodesTab - Needs a decision', () => {
  it('names the code, what the supplier called it, and what is behind it', () => {
    renderTab();

    expect(screen.getByText('Needs a decision (1)')).toBeInTheDocument();
    expect(screen.getByText('SRTWC286-SH-250UF')).toBeInTheDocument();
    expect(screen.getByText(/连体马桶 · SORENTO/)).toBeInTheDocument();
    expect(screen.getAllByText(/400/).length).toBeGreaterThanOrEqual(1);
  });

  it('says every code binds when the queue is empty (AC-B4)', () => {
    state.rows = [];
    renderTab();

    expect(screen.getByText('Every code on file is matched')).toBeInTheDocument();
    expect(screen.queryByLabelText('Product')).not.toBeInTheDocument();
  });

  it('offers to run the ladder again beside the queue it would shorten', () => {
    renderTab();

    fireEvent.click(screen.getByTestId('refresh-matching'));

    expect(state.rematch).toHaveBeenCalledWith({ supplier_id: 'sup-1' });
  });

  it('picking a product keeps the row in place with Undo, and never invalidates (AC-C1)', async () => {
    const { invalidateSpy } = renderTab();

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

    // The row stays: the code is still on screen, the picker is gone, the answer and Undo
    // are there instead.
    await waitFor(() =>
      expect(screen.getByText(/SRTWC286-SH - One piece toilet/)).toBeInTheDocument(),
    );
    expect(screen.getByText('SRTWC286-SH-250UF')).toBeInTheDocument();
    expect(screen.queryByLabelText('Product')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /undo/i })).toBeInTheDocument();

    // AC-C3: the pick itself invalidates nothing.
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('Undo on a fresh match deletes the alias and returns the picker (AC-C1)', async () => {
    const { invalidateSpy } = renderTab();

    const select = screen.getByLabelText('Product') as HTMLSelectElement;
    await waitFor(() =>
      expect(select.querySelector('option[value="p-1"]')).toBeInTheDocument(),
    );
    fireEvent.change(select, { target: { value: 'p-1' } });
    await waitFor(() => expect(screen.getByRole('button', { name: /undo/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /undo/i }));

    expect(state.undo).toHaveBeenCalledWith('a-9', expect.objectContaining({
      onSuccess: expect.any(Function),
    }));
    // The picker is back.
    expect(await screen.findByLabelText('Product')).toBeInTheDocument();
    // Undo is the one moment this queue's own state is invalidated.
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['scm', 'supplier-code-aliases'] }),
    );
  });

  it('dismissing keeps the row in place reading Dismissed, with Undo (AC-C2)', async () => {
    const { invalidateSpy } = renderTab();

    fireEvent.click(screen.getByRole('button', { name: /^dismiss$/i }));

    await waitFor(() => expect(state.dismiss).toHaveBeenCalledTimes(1));
    expect(state.dismiss).toHaveBeenCalledWith({
      supplier_id: 'sup-1',
      supplier_code: 'SRTWC286-SH-250UF',
    });
    expect(screen.getByText('Dismissed')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^dismiss$/i })).not.toBeInTheDocument();
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('Undo on a fresh dismissal deletes the alias and returns the picker (AC-C2)', async () => {
    renderTab();

    fireEvent.click(screen.getByRole('button', { name: /^dismiss$/i }));
    await waitFor(() => expect(screen.getByText('Dismissed')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /undo/i }));

    expect(state.undo).toHaveBeenCalledWith('a-8', expect.any(Object));
    expect(await screen.findByRole('button', { name: /^dismiss$/i })).toBeInTheDocument();
  });

  it('invalidates on unmount only when something was decided this visit (AC-C3)', async () => {
    const { unmount, invalidateSpy } = renderTab();

    unmount();
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('a decision left un-undone invalidates when the tab is left (AC-C3)', async () => {
    const { unmount, invalidateSpy } = renderTab();

    fireEvent.click(screen.getByRole('button', { name: /^dismiss$/i }));
    await waitFor(() => expect(screen.getByText('Dismissed')).toBeInTheDocument());
    expect(invalidateSpy).not.toHaveBeenCalled();

    unmount();
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['scm', 'supplier-code-aliases'] }),
    );
  });
});

describe('SupplierCodesTab - Remembered', () => {
  it('says nothing is remembered yet when there is no history (AC-B4)', () => {
    renderTab();
    expect(screen.getByText('Nothing remembered for this supplier yet')).toBeInTheDocument();
  });

  it('lists a product match, a set match and a dismissal with the right columns', () => {
    state.aliases = [
      alias(),
      alias({
        id: 'a-2',
        supplier_code: 'CWC605-RL-180',
        product_code: null,
        product_name: null,
        set_code: 'CWC605-RL',
        set_name: 'Close-coupled WC',
        matched_by: 'set_token_set',
      }),
      alias({
        id: 'a-3',
        supplier_code: 'THEIR-OWN-SPARE',
        product_code: null,
        product_name: null,
        source: 'dismissed',
        matched_by: 'dismissed',
      }),
    ];
    renderTab();

    expect(screen.getByText('Remembered (3)')).toBeInTheDocument();
    expect(screen.getByText('SRTWC8357-300-RL - One piece toilet')).toBeInTheDocument();
    expect(screen.getByText('Manual')).toBeInTheDocument();

    expect(screen.getByText('CWC605-RL - Close-coupled WC')).toBeInTheDocument();
    expect(screen.getByText('Same tokens')).toBeInTheDocument();

    expect(screen.getByText('THEIR-OWN-SPARE')).toBeInTheDocument();
    expect(screen.getAllByText('Dismissed').length).toBeGreaterThanOrEqual(1);

    expect(screen.getAllByText('Ms Tee').length).toBeGreaterThanOrEqual(1);
  });

  it('orders newest ruling first regardless of what the backend returns', () => {
    state.aliases = [
      alias({ id: 'a-old', supplier_code: 'OLD-CODE', created_at: '2026-01-01T00:00:00' }),
      alias({ id: 'a-new', supplier_code: 'NEW-CODE', created_at: '2026-08-30T00:00:00' }),
    ];
    const { container } = renderTab();

    const text = container.textContent ?? '';
    expect(text.indexOf('NEW-CODE')).toBeLessThan(text.indexOf('OLD-CODE'));
  });

  it('forgets a remembered code through the deferred row action', () => {
    state.aliases = [alias()];
    renderTab();

    fireEvent.click(screen.getByRole('button', { name: /^forget$/i }));

    expect(deferred.run).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'a-1', subject: 'SRTWC8357-RL-300' }),
    );
    expect(deferred.inputs[0]).toMatchObject({
      actionKey: 'supplier_code_alias.forget',
      entityType: 'supplier_code_alias',
    });
  });
});
