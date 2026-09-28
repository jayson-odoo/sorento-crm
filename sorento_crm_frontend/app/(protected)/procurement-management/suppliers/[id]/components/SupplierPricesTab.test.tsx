/**
 * SupplierPricesTab (#1305 reviewer pass, Lane A FE rows, S1).
 *
 * A query failure (e.g. the caller lacks `procurement.product_suppliers.view`) must
 * render an error state, never the "No prices recorded" empty state.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
}));

// The system multi-select, stubbed to one button per option (its own tests cover the popover).
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    placeholder,
    options,
    value,
    onChange,
  }: {
    placeholder?: string;
    options: { value: string; label: string }[];
    value: string[];
    onChange: (v: string[]) => void;
  }) => (
    <div data-testid={`multi-select-${placeholder}`}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(value.includes(o.value) ? value.filter((v) => v !== o.value) : [...value, o.value])}
        >
          {o.label}
        </button>
      ))}
    </div>
  ),
}));

const getSupplierCostLists = vi.fn();
vi.mock('@/app/(protected)/procurement-management/cost-price-uploads/services/costPriceService', () => ({
  getSupplierCostLists: (...args: unknown[]) => getSupplierCostLists(...args),
}));

import { SupplierPricesTab } from './SupplierPricesTab';

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SupplierPricesTab supplierId="sup-1" />
    </QueryClientProvider>,
  );
}

describe('S1: a query error renders an error state, not the empty state', () => {
  it('shows the extracted error message and not "No costs recorded"', async () => {
    getSupplierCostLists.mockRejectedValue(new Error('You do not have permission to view this supplier’s prices'));
    renderTab();

    expect(await screen.findByText('You do not have permission to view this supplier’s prices')).toBeInTheDocument();
    expect(screen.queryByText('No costs recorded for this supplier yet')).not.toBeInTheDocument();
  });
});

describe('Round 6 R5: cost, never price', () => {
  it('the empty state says cost and links to the cost list upload', async () => {
    getSupplierCostLists.mockResolvedValue({ data: [], today: '2026-09-28' });
    renderTab();

    expect(await screen.findByText('No costs recorded for this supplier yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Upload cost list' })).toBeInTheDocument();
    expect(screen.queryByText(/price/i)).not.toBeInTheDocument();
  });
});

describe('Round 6 R6: the cost list says which row of the upload it came from', () => {
  it('shows the set code and the row in the Source cell', async () => {
    getSupplierCostLists.mockResolvedValue({
      today: '2026-09-28',
      data: [
        {
          product_supplier_id: 'ps-1',
          packaging_method: 'standard',
          packaging_key: 'standard',
          product: { id: 'p-1', product_code: 'OUR-001', description: 'A product' },
          supplier_code: 'CB2500SS-DIY',
          unit_cost: 8.8,
          currency: 'CNY',
          costs: [
            {
              id: 'c-1', packaging_method: 'standard', unit_cost: 8.8, currency: 'CNY', start_date: null, end_date: null, status: 'in_force',
              source: { change_set_id: 'set-1', code: 'CPC-0002', sheet: '25 series', row_no: 34 },
              created_at: '2026-09-28T00:00:00',
            },
          ],
        },
      ],
    });
    renderTab();

    const link = await screen.findByRole('link', { name: /CPC-0002/ });
    expect(link).toHaveTextContent('CPC-0002 row 34');
    expect(link).toHaveAttribute('title', 'CPC-0002, 25 series row 34');
  });
});

/** The 2500 series after Apply: one entry per product AND packaging (round 8). */
function series2500() {
  const entry = (id: string, code: string, packaging: string, cost: number) => ({
    product_supplier_id: id,
    packaging_method: packaging,
    packaging_key: packaging.toLowerCase(),
    product: { id: `p-${id}`, product_code: code, description: 'A product' },
    supplier_code: null,
    unit_cost: cost,
    currency: 'CNY',
    costs: [
      {
        id: `c-${id}-${packaging}`, packaging_method: packaging, unit_cost: cost, currency: 'CNY',
        start_date: null, end_date: null, status: 'always',
        source: { change_set_id: 'set-1', code: 'CPC-0004', sheet: '25系列', row_no: 5 },
        created_at: '2026-09-28T00:00:00',
      },
    ],
  });
  return {
    today: '2026-09-28',
    packaging_options: ['OPP', '吊卡', '彩盒'],
    data: [
      entry('ps-bl', 'CB2500SS-BL', '彩盒', 9.5),
      entry('ps-diy', 'CB2500SS-BL-DIY', 'OPP', 9.9),
      entry('ps-diy', 'CB2500SS-BL-DIY', '吊卡', 9.4),
    ],
  };
}

function column(name: string): string[] {
  const headers = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');
  const index = headers.findIndex((h) => h.includes(name));
  return screen.getAllByRole('row').slice(1).map((r) => within(r).getAllByRole('cell')[index].textContent ?? '');
}

describe('Round 8 (AC-CL-07, AC-PK-04): the Costs tab shows each packaging beside the code', () => {
  it('one row per product and packaging, three costs for the 2500 series', async () => {
    getSupplierCostLists.mockResolvedValue(series2500());
    renderTab();

    expect(await screen.findAllByText('CB2500SS-BL-DIY')).toHaveLength(2);
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');
    expect(headers.findIndex((h) => h.includes('Packaging'))).toBe(headers.findIndex((h) => h.includes('Product')) + 1);
    expect(column('Packaging')).toEqual(['彩盒', 'OPP', '吊卡']);
    expect(column('Cost')).toEqual(['9.50 CNY', '9.90 CNY', '9.40 CNY']);
  });

  it('sorts by packaging and by cost from the headers', async () => {
    getSupplierCostLists.mockResolvedValue(series2500());
    renderTab();
    await screen.findAllByText('CB2500SS-BL-DIY');

    fireEvent.click(within(screen.getByRole('columnheader', { name: /Cost/ })).getByRole('button', { name: 'Cost' }));
    expect(column('Cost')).toEqual(['9.40 CNY', '9.50 CNY', '9.90 CNY']);
    fireEvent.click(within(screen.getByRole('columnheader', { name: /Packaging/ })).getByRole('button', { name: 'Packaging' }));
    expect(column('Packaging')).toEqual(['OPP', '吊卡', '彩盒']);
  });

  it('the Packaging filter lists the supplier\'s packagings and asks the backend for the picked ones', async () => {
    getSupplierCostLists.mockResolvedValue(series2500());
    renderTab();
    await screen.findAllByText('CB2500SS-BL-DIY');

    const filter = screen.getByTestId('multi-select-Packaging');
    expect(within(filter).getAllByRole('button').map((b) => b.textContent)).toEqual(['OPP', '吊卡', '彩盒']);
    fireEvent.click(within(filter).getByRole('button', { name: 'OPP' }));
    await vi.waitFor(() =>
      expect(getSupplierCostLists).toHaveBeenLastCalledWith('sup-1', expect.objectContaining({ packaging: ['OPP'] })),
    );
  });
});
