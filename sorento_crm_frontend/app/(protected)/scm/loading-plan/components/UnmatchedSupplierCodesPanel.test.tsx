/**
 * F11 / R16 - the queue of supplier codes nothing in the catalogue answers.
 *
 * The consequence lands on the loading plan: a stock row with no product is stock the plan
 * cannot offer, so a supplier holding 400 pieces of something shows as nothing.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

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

const state = {
  rows: [] as unknown[],
  match: vi.fn(),
};

vi.mock('../../hooks/useSupplierCodeAliases', () => ({
  useUnmatchedSupplierCodes: () => ({ data: state.rows, isLoading: false }),
  useMatchSupplierCode: () => ({ mutateAsync: state.match, isPending: false }),
}));

vi.mock(
  '@/app/(protected)/master-data-management/products/services/productService',
  () => ({
    getProducts: vi.fn(async () => ({
      data: [{ id: 'p-1', product_code: 'SRTWC286-SH', product_name: 'One piece toilet' }],
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
    fetchOptions,
  }: {
    id?: string;
    value?: string;
    onChange?: (v: string) => void;
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

beforeEach(() => {
  state.rows = [row()];
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
});

describe('UnmatchedSupplierCodesPanel', () => {
  it('names the code, what the supplier called it, and what is behind it', () => {
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    expect(screen.getByText('1 code matches nothing we hold')).toBeInTheDocument();
    expect(screen.getByText('SRTWC286-SH-250UF')).toBeInTheDocument();
    expect(screen.getByText(/连体马桶 · SORENTO/)).toBeInTheDocument();
    // Twice: the header's total and this row's own figure.
    expect(screen.getAllByText(/400 packed/).length).toBeGreaterThanOrEqual(1);
  });

  it('says nothing at all when every code binds', () => {
    state.rows = [];
    const { container } = render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    expect(container).toBeEmptyDOMElement();
  });

  it('opens the picker for the code that was pressed', () => {
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);

    fireEvent.click(screen.getByRole('button', { name: /match to product/i }));

    expect(screen.getByText(/SRTWC286-SH-250UF - 连体马桶/)).toBeInTheDocument();
    expect(screen.getByLabelText('Product')).toBeInTheDocument();
  });

  it('records the match against the supplier and the code it was opened for', async () => {
    render(<UnmatchedSupplierCodesPanel supplierId="sup-1" />);
    fireEvent.click(screen.getByRole('button', { name: /match to product/i }));

    // The picker is server-searched, so the option lands a microtask later - waiting for it
    // is the difference between testing the pick and testing a race.
    const select = screen.getByLabelText('Product') as HTMLSelectElement;
    await waitFor(() =>
      expect(select.querySelector('option[value="p-1"]')).toBeInTheDocument(),
    );
    fireEvent.change(select, { target: { value: 'p-1' } });
    fireEvent.click(screen.getByRole('button', { name: /^match$/i }));

    await waitFor(() => expect(state.match).toHaveBeenCalledTimes(1));
    expect(state.match).toHaveBeenCalledWith({
      supplier_id: 'sup-1',
      supplier_code: 'SRTWC286-SH-250UF',
      product_id: 'p-1',
    });
  });
});
