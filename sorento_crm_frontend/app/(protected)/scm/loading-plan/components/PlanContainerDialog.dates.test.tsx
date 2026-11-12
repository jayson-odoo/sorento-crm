/**
 * DATE-PICKER-UNIFY slice B: PlanContainerDialog "Sales orders needed" is ONE typeable range
 * field, creating the plan with the same plan_horizon_start / plan_horizon_date.
 * Harness copied from PlanContainerDialog.test.tsx.
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
const createLoadingPlanRecord = vi.fn();
const deleteLoadingPlan = vi.fn();

vi.mock('../../services/fulfilmentService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/fulfilmentService')>();
  return {
    ...actual,
    getFulfilmentSuppliers: (query?: string) => getFulfilmentSuppliers(query),
    applyStockList: (...a: unknown[]) => applyStockList(...a),
    previewStockList: (...a: unknown[]) => previewStockList(...a),
    testStockList: (...a: unknown[]) => testStockList(...a),
    createLoadingPlanRecord: (...a: unknown[]) => createLoadingPlanRecord(...a),
    deleteLoadingPlan: (...a: unknown[]) => deleteLoadingPlan(...a),
  };
});

// The upload config the shared two-step hook reads on open (server-owned accept list).
vi.mock('../../reorder/services/outstandingImportService', () => ({
  getOutstandingUploadConfig: async () => ({ allowed_extensions: ['.xlsx'] }),
}));

// V3 (PLAN-import-column-mapper-24sep.md F2, AC-M9/AC-M10) - the proforma path, so a
// column's `required` label reads "Quantity" (the proforma field list's own label; the
// stock-list path's own is "Packed quantity").
const previewProformaInvoice = vi.fn();
const applyProformaInvoice = vi.fn();
vi.mock('../../services/proformaInvoiceService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/proformaInvoiceService')>();
  return {
    ...actual,
    previewProformaInvoice: (...a: unknown[]) => previewProformaInvoice(...a),
    applyProformaInvoice: (...a: unknown[]) => applyProformaInvoice(...a),
  };
});

const probeImportMapping = vi.fn();
const saveImportMapping = vi.fn();
vi.mock('../../services/importMappingService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/importMappingService')>();
  return {
    ...actual,
    probeImportMapping: (...a: unknown[]) => probeImportMapping(...a),
    saveImportMapping: (...a: unknown[]) => saveImportMapping(...a),
  };
});

import { toast } from '@/lib/toast';

import { PlanContainerDialog } from './PlanContainerDialog';
import type { ImportMappingProbe, ImportMappingField } from '@/components/common/ImportColumnMapper';

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
    createLoadingPlanRecord.mockResolvedValue({ id: 'plan-9' });
    deleteLoadingPlan.mockResolvedValue(undefined);
    previewProformaInvoice.mockResolvedValue({
      ok: true,
      documents: [],
      missing_columns: [],
      problems: [],
      unmapped_headers: [],
      unmatched_items: 0,
      unmatched_item_codes: [],
      supplier_check: null,
    });
    applyProformaInvoice.mockResolvedValue({ ids: [] });
    probeImportMapping.mockResolvedValue(null);
    saveImportMapping.mockResolvedValue(undefined);
  });


  const RANGE_PH = 'DD/MM/YYYY - DD/MM/YYYY';

  it('AC1: the window is one typeable range field and there is no native date input', () => {
    renderDialog();
    expect(document.body.querySelector('input[type="date"]')).toBeNull();
    expect(screen.getAllByPlaceholderText(RANGE_PH)).toHaveLength(1);
  });

  it('AC2/AC9: typing the range and pressing Enter sends both dates to the plan it creates', async () => {
    renderDialog();
    fireEvent.click(screen.getByLabelText('No file'));
    await chooseSupplier();
    const range = screen.getByPlaceholderText(RANGE_PH);
    fireEvent.change(range, { target: { value: '01/11/2026 - 30/11/2026' } });
    fireEvent.keyDown(range, { key: 'Enter' });

    fireEvent.click(screen.getByTestId('plan-container-confirm'));

    await waitFor(() =>
      expect(createLoadingPlanRecord).toHaveBeenCalledWith(
        expect.objectContaining({
          plan_horizon_start: '2026-11-01',
          plan_horizon_date: '2026-11-30',
        }),
      ),
    );
  });
});
