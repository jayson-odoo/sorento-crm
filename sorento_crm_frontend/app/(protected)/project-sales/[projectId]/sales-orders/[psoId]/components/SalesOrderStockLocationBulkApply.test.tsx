/**
 * Sets one warehouse on every line of a draft in one confirmed action (captain, 19 Aug 2026).
 *
 * Pinned here: the control is absent with no lines, the confirm names the code and the
 * count before anything is written, and confirming writes every line id through the bulk
 * mutation - never a per-cell edit disguised as a bulk one.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProjectSalesOrderLine } from '../../../../_shared/types/projectSalesOrder.types';

const bulkSetLinesStockLocation = vi.fn();
const toastSuccess = vi.fn();

vi.mock('../../../../_shared/services/projectSalesOrderService', () => ({
  bulkSetLinesStockLocation: (...args: unknown[]) => bulkSetLinesStockLocation(...args),
}));

vi.mock('sonner', () => ({
  toast: { success: (...args: unknown[]) => toastSuccess(...args), error: vi.fn() },
}));

vi.mock('../../../../_shared/services/warehouseSelectService', () => ({
  fetchWarehouseOptions: vi.fn(async () => [
    { value: 'BRW-BB', label: 'BRW-BB - Bukit Beruntung' },
  ]),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    onOptionChange,
    placeholder,
  }: {
    value: string;
    onChange: (next: string) => void;
    onOptionChange?: (option: { value: string; label: string } | null) => void;
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => {
        const next = event.target.value;
        onChange(next);
        onOptionChange?.(next ? { value: next, label: `${next} - Bukit Beruntung` } : null);
      }}
    >
      <option value="">{placeholder ?? ''}</option>
      <option value="BRW-BB">BRW-BB - Bukit Beruntung</option>
    </select>
  ),
}));

import { SalesOrderStockLocationBulkApply } from './SalesOrderStockLocationBulkApply';

const LINES: ProjectSalesOrderLine[] = [
  {
    id: 'l1',
    line_no: 1,
    qty: '1',
    unit_price: '1.00',
    amount: '1.00',
    explosion_source: 'none',
  },
  {
    id: 'l2',
    line_no: 2,
    qty: '1',
    unit_price: '1.00',
    amount: '1.00',
    explosion_source: 'none',
  },
];

function renderControl(lines: ProjectSalesOrderLine[] = LINES) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrderStockLocationBulkApply
        projectId="p1"
        psoId="so-1"
        lines={lines}
        reference="PSO-000123"
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SalesOrderStockLocationBulkApply', () => {
  it('renders nothing when the order has no lines', () => {
    const { container } = renderControl([]);
    expect(container).toBeEmptyDOMElement();
  });

  it('disables Apply until a warehouse is chosen', () => {
    renderControl();
    expect(screen.getByRole('button', { name: 'Apply to all lines' })).toBeDisabled();
  });

  it('names the code and the line count before writing anything', async () => {
    renderControl();
    fireEvent.change(screen.getByLabelText('Select warehouse'), {
      target: { value: 'BRW-BB' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Apply to all lines' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText('Set BRW-BB on 2 lines?')).toBeInTheDocument();
    expect(bulkSetLinesStockLocation).not.toHaveBeenCalled();
  });

  it('writes every line id through the bulk mutation once confirmed', async () => {
    bulkSetLinesStockLocation.mockResolvedValue({ applied: 2 });
    renderControl();
    fireEvent.change(screen.getByLabelText('Select warehouse'), {
      target: { value: 'BRW-BB' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Apply to all lines' }));
    const dialog = await screen.findByRole('alertdialog');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply' }));

    await waitFor(() =>
      expect(bulkSetLinesStockLocation).toHaveBeenCalledWith('so-1', ['l1', 'l2'], 'BRW-BB'),
    );
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Stock location set on 2 lines'));
  });
});
