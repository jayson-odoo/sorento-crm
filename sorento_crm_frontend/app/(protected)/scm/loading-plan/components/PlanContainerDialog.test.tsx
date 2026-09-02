/**
 * "Plan a container" - the ONE popup that starts a loading plan (part 4, R4 / AC-A4, A5, A6).
 *
 * ONE dialog, not two: the dropzone and the existing two-step Test / Confirm run INSIDE it,
 * so what is asserted here is that nothing acts without a supplier, that choosing a document
 * reveals the dropzone in place (and "No file" hides it), and that Confirm does the three
 * things in the order the record depends on - apply the file, find the sheet it was retained
 * as, create the plan and open it.
 *
 * The reads themselves belong to the upload channels' own suites; they are stubbed here.
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

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/loading-plan',
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const getFulfilmentSuppliers = vi.fn(
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async (_query?: string) => [{ value: 'sup-1', label: 'Foshan Ceramics' }],
);
const applyStockList = vi.fn();
const previewStockList = vi.fn();
const testStockList = vi.fn();
const getSupplierStockListFile = vi.fn();
const createLoadingPlanRecord = vi.fn();

vi.mock('../../services/fulfilmentService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/fulfilmentService')>();
  return {
    ...actual,
    getFulfilmentSuppliers: (query?: string) => getFulfilmentSuppliers(query),
    applyStockList: (...a: unknown[]) => applyStockList(...a),
    previewStockList: (...a: unknown[]) => previewStockList(...a),
    testStockList: (...a: unknown[]) => testStockList(...a),
    getSupplierStockListFile: (...a: unknown[]) => getSupplierStockListFile(...a),
    createLoadingPlanRecord: (...a: unknown[]) => createLoadingPlanRecord(...a),
  };
});

// The upload config the shared two-step hook reads on open (server-owned accept list).
vi.mock('../../reorder/services/outstandingImportService', () => ({
  getOutstandingUploadConfig: async () => ({ allowed_extensions: ['.xlsx'] }),
}));

import { PlanContainerDialog } from './PlanContainerDialog';

function renderDialog() {
  const onOpenChange = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <PlanContainerDialog open onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
  return { ...view, onOpenChange };
}

/** The supplier select is a combobox; pick the only option it offers. */
async function chooseSupplier() {
  const trigger = screen.getByRole('combobox', { name: /Supplier/i });
  fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
  fireEvent.click(trigger);
  fireEvent.click(await screen.findByText('Foshan Ceramics'));
}

describe('PlanContainerDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    applyStockList.mockResolvedValue({ rows_written: 3, rows_replaced: 0 });
    previewStockList.mockResolvedValue({ ok: true, readable: true, summary: {} });
    testStockList.mockResolvedValue({ valid: true, errors: [], warnings: [] });
    getSupplierStockListFile.mockResolvedValue({ attachment_id: 'att-9', filename: 's.xlsx' });
    createLoadingPlanRecord.mockResolvedValue({ id: 'plan-9' });
  });

  it('asks for the supplier, the sales order cut-off and the document, and nothing else', async () => {
    renderDialog();

    expect(screen.getByRole('heading', { name: 'Plan a container' })).toBeTruthy();
    expect(screen.getByRole('combobox', { name: /Supplier/i })).toBeTruthy();
    expect(screen.getByLabelText('Sales order cut-off')).toBeTruthy();
    expect(screen.getByText('Empty = every open order counts.')).toBeTruthy();
    for (const kind of ['Stock list', 'Proforma invoice', 'No file']) {
      expect(screen.getByLabelText(kind)).toBeTruthy();
    }
    // The words "Plan until" are gone from the app (AC-A4).
    expect(screen.queryByText(/Plan until/i)).toBeNull();
  });

  it('shows the dropzone INSIDE this dialog, and hides it for "No file"', () => {
    renderDialog();

    expect(screen.getByLabelText('Supplier stock list file')).toBeTruthy();

    fireEvent.click(screen.getByLabelText('No file'));

    expect(screen.queryByLabelText('Supplier stock list file')).toBeNull();
    expect(screen.getByRole('button', { name: /Start plan/ })).toBeTruthy();
  });

  it('does nothing until a supplier is chosen, and says why', () => {
    renderDialog();

    const confirm = screen.getByTestId('plan-container-confirm') as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    expect(confirm.getAttribute('title')).toBe('Choose a supplier first');
  });

  it('"No file" starts the plan and opens it (AC-A6)', async () => {
    renderDialog();
    fireEvent.click(screen.getByLabelText('No file'));
    await chooseSupplier();

    fireEvent.click(screen.getByTestId('plan-container-confirm'));

    await waitFor(() =>
      expect(createLoadingPlanRecord).toHaveBeenCalledWith({
        supplier_id: 'sup-1',
        plan_horizon_date: null,
        document_kind: 'none',
        source_attachment_id: null,
      }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith('/scm/loading-plan/plan-9'));
    // No file means no upload at all.
    expect(applyStockList).not.toHaveBeenCalled();
  });

  it('carries the chosen cut-off onto the plan it creates', async () => {
    renderDialog();
    fireEvent.click(screen.getByLabelText('No file'));
    await chooseSupplier();
    fireEvent.change(screen.getByLabelText('Sales order cut-off'), {
      target: { value: '2026-09-30' },
    });

    fireEvent.click(screen.getByTestId('plan-container-confirm'));

    await waitFor(() =>
      expect(createLoadingPlanRecord).toHaveBeenCalledWith(
        expect.objectContaining({ plan_horizon_date: '2026-09-30' }),
      ),
    );
  });

  it('applies the stock list FIRST, then names the sheet the plan was started from', async () => {
    renderDialog();
    await chooseSupplier();
    const file = new File(['x'], 'stock.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    const dropzone = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(dropzone, { target: { files: [file] } });

    fireEvent.click(await screen.findByTestId('plan-container-confirm'));

    await waitFor(() => expect(applyStockList).toHaveBeenCalled());
    await waitFor(() =>
      expect(createLoadingPlanRecord).toHaveBeenCalledWith({
        supplier_id: 'sup-1',
        plan_horizon_date: null,
        document_kind: 'stock_list',
        source_attachment_id: 'att-9',
      }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith('/scm/loading-plan/plan-9'));
  });

  it('a plan is still started when the retained sheet cannot be found', async () => {
    getSupplierStockListFile.mockRejectedValue(new Error('gone'));
    renderDialog();
    await chooseSupplier();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'stock.xlsx')] } });

    fireEvent.click(await screen.findByTestId('plan-container-confirm'));

    await waitFor(() =>
      expect(createLoadingPlanRecord).toHaveBeenCalledWith(
        expect.objectContaining({ source_attachment_id: null }),
      ),
    );
  });
});
