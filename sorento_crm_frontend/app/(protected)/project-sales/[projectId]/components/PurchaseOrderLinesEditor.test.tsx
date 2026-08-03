/**
 * PO lines, entered like a spreadsheet (AC-F9).
 *
 * The columns are this screen's own; the spreadsheet behaviour behind them is pinned once,
 * in InlineLineTable.test.tsx. What is pinned HERE is that the columns are the fields the
 * dialog used to collect, and that a save still sends exactly the body the dialog sent, to
 * the same per-line endpoint.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  Project,
  ProjectPurchaseOrder,
  PurchaseOrderLine,
} from '../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const listPurchaseOrderLines = vi.fn();
const createPurchaseOrderLine = vi.fn();
const updatePurchaseOrderLine = vi.fn();
const deletePurchaseOrderLine = vi.fn();

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/projectService')
  >();
  return {
    ...actual,
    listPurchaseOrderLines: (...args: unknown[]) => listPurchaseOrderLines(...args),
    createPurchaseOrderLine: (...args: unknown[]) => createPurchaseOrderLine(...args),
    updatePurchaseOrderLine: (...args: unknown[]) => updatePurchaseOrderLine(...args),
    deletePurchaseOrderLine: (...args: unknown[]) => deletePurchaseOrderLine(...args),
  };
});

// The product picker hits the shared products `/select` endpoint when it opens.
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForVariantSelect: vi.fn(async () => []),
}));

vi.mock('sonner', () => ({
  toast: { custom: vi.fn(), error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

import { PurchaseOrderLinesEditor } from './PurchaseOrderLinesEditor';

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Menara Test',
    outcome: 'open',
    is_critical: false,
    brands: [],
    brand_ids: [],
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    ...overrides,
  };
}

const PO: ProjectPurchaseOrder = {
  id: 'po1',
  project_id: 'p1',
  po_number: 'PO-9001',
  po_source: 'contractor_direct',
  quotation_version_id: 'v2',
  line_count: 1,
  line_total: '9000.00',
  model_mismatch_count: 0,
  price_mismatch_count: 0,
};

function line(overrides: Partial<PurchaseOrderLine> = {}): PurchaseOrderLine {
  return {
    id: 'pl1',
    po_id: 'po1',
    product_code: 'SRT-WC-01',
    description: 'Wall-hung WC',
    unit_price: '900.00',
    quantity: '10.00',
    uom: 'PCS',
    line_total: '9000.00',
    model_mismatch: false,
    price_mismatch: false,
    sort_order: 0,
    ...overrides,
  };
}

function renderEditor(overrides: Partial<Project> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseOrderLinesEditor project={project(overrides)} po={PO} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listPurchaseOrderLines.mockResolvedValue([line()]);
  createPurchaseOrderLine.mockResolvedValue(line({ id: 'pl2' }));
  updatePurchaseOrderLine.mockResolvedValue(line());
  deletePurchaseOrderLine.mockResolvedValue(undefined);
});

describe('PurchaseOrderLinesEditor', () => {
  it('lays every field of a PO line out as a column', async () => {
    renderEditor();

    for (const header of [
      'Our product',
      'Code on the PO',
      'Description',
      'Qty',
      'UOM',
      'Ordered at',
      'Total',
    ]) {
      expect(await screen.findByRole('columnheader', { name: header })).toBeInTheDocument();
    }
    expect(screen.getByRole('button', { name: 'Notes on SRT-WC-01' })).toBeInTheDocument();
  });

  it('keeps its header and its add row when the PO has no lines yet', async () => {
    listPurchaseOrderLines.mockResolvedValue([]);

    renderEditor();

    expect(
      await screen.findByRole('columnheader', { name: 'Code on the PO' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/No lines entered/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add a line' })).toBeInTheDocument();
  });

  it('moves the line total while the quantity is typed, before anything is saved', async () => {
    renderEditor();

    fireEvent.change(await screen.findByRole('textbox', { name: 'Qty on SRT-WC-01' }), {
      target: { value: '3' },
    });

    expect(screen.getByText('RM 2,700.00')).toBeInTheDocument();
    expect(updatePurchaseOrderLine).not.toHaveBeenCalled();
  });

  it('saves an edited line with the body the dialog used to send', async () => {
    renderEditor();

    fireEvent.change(
      await screen.findByRole('textbox', { name: 'Ordered at on SRT-WC-01' }),
      { target: { value: '820.00' } },
    );
    fireEvent.click(screen.getByRole('button', { name: 'Save SRT-WC-01' }));

    await waitFor(() => expect(updatePurchaseOrderLine).toHaveBeenCalledTimes(1));
    expect(updatePurchaseOrderLine).toHaveBeenCalledWith('po1', 'pl1', {
      product_id: null,
      product_code: 'SRT-WC-01',
      description: 'Wall-hung WC',
      unit_price: '820.00',
      quantity: '10.00',
      uom: 'PCS',
      notes: null,
    });
  });

  it('creates an added line with the body the dialog used to send', async () => {
    renderEditor();

    fireEvent.click(await screen.findByRole('button', { name: 'Add a line' }));
    const code = await screen.findByRole('textbox', { name: 'Code on the PO on line 2' });
    fireEvent.change(code, { target: { value: 'THEIR-CODE-7' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Ordered at on line 2' }), {
      target: { value: '410.00' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save line 2' }));

    await waitFor(() => expect(createPurchaseOrderLine).toHaveBeenCalledTimes(1));
    expect(createPurchaseOrderLine).toHaveBeenCalledWith('po1', {
      product_id: null,
      product_code: 'THEIR-CODE-7',
      description: null,
      unit_price: '410.00',
      quantity: '1',
      uom: null,
      notes: null,
      sort_order: 10,
    });
  });

  it('marks the cell that stops an unmatched line from being recorded', async () => {
    renderEditor();

    fireEvent.click(await screen.findByRole('button', { name: 'Add a line' }));
    const code = await screen.findByRole('textbox', { name: 'Code on the PO on line 2' });
    fireEvent.change(screen.getByRole('textbox', { name: 'Description on line 2' }), {
      target: { value: 'Something they wrote' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save line 2' }));

    expect(await screen.findByText('Needed when no product is matched')).toBeInTheDocument();
    expect(code).toHaveAttribute('aria-invalid', 'true');
    expect(createPurchaseOrderLine).not.toHaveBeenCalled();
  });

  it('asks before removing a line, and only then removes it', async () => {
    renderEditor();

    fireEvent.click(await screen.findByRole('button', { name: 'Remove SRT-WC-01' }));

    expect(await screen.findByText(/Remove "SRT-WC-01" from PO-9001/)).toBeInTheDocument();
    expect(deletePurchaseOrderLine).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    await waitFor(() =>
      expect(deletePurchaseOrderLine).toHaveBeenCalledWith('po1', 'pl1'),
    );
  });

  it('offers nothing to type into to a reader', async () => {
    renderEditor({ can_edit: false });

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    // A read-only line still reads as money, not as the raw string the API holds.
    expect(screen.getByText('RM 900.00')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add a line' })).toBeNull();
  });
});
