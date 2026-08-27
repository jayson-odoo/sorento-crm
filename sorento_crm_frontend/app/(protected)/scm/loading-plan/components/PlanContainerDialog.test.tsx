/**
 * The one popup that starts a loading plan (captain, 27 Aug).
 *
 * Two steps, and the split is the whole point: step 1 asks the two things the plan cannot
 * derive (whose container, how far ahead) plus which document is being sent, and step 2 is
 * the SAME upload dialog used everywhere else, in fixed-supplier mode. So what is asserted
 * here is the wiring - nothing acts without a supplier, "Plan without a file" is a real
 * third answer for a supplier already on file, and Continue lands on the document that was
 * chosen with the supplier already fixed to it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const getFulfilmentSuppliers = vi.fn(
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async (_query?: string) => [{ value: 'sup-1', label: 'Foshan Ceramics' }],
);
vi.mock('../../services/fulfilmentService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/fulfilmentService')>();
  return {
    ...actual,
    getFulfilmentSuppliers: (query?: string) => getFulfilmentSuppliers(query),
  };
});

vi.mock('../../proforma-invoices/components/ProformaUploadDialog', () => ({
  ProformaUploadDialog: ({
    open,
    supplierId,
    supplierOption,
  }: {
    open: boolean;
    supplierId?: string | null;
    supplierOption?: { value: string; label: string } | null;
  }) =>
    open ? (
      <div data-testid="proforma-upload-dialog">
        Proforma upload for {supplierOption?.label ?? supplierId}
      </div>
    ) : null,
}));

/** The stub's own `onApplied`, so the "an upload landed" path can be fired from a test
 *  without reimplementing the upload dialog. */
const captured: { onApplied?: () => void } = {};
vi.mock('./StockListUploadDialog', () => ({
  StockListUploadDialog: ({
    open,
    supplierName,
    onApplied,
  }: {
    open: boolean;
    supplierName: string;
    onApplied?: () => void;
  }) => {
    captured.onApplied = onApplied;
    return open ? (
      <div data-testid="stock-upload-dialog">Stock list upload for {supplierName}</div>
    ) : null;
  },
}));

import { PlanContainerDialog, type PlanDocumentKind } from './PlanContainerDialog';

function renderDialog(
  props: Partial<React.ComponentProps<typeof PlanContainerDialog>> = {},
) {
  const onApply = vi.fn();
  const onOpenChange = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <PlanContainerDialog
        open
        onOpenChange={onOpenChange}
        supplierId=""
        supplierOption={null}
        planHorizonDate=""
        onApply={onApply}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { ...view, onApply, onOpenChange };
}

async function chooseSupplier() {
  const trigger = screen.getByRole('combobox', { name: /Supplier/i });
  fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
  fireEvent.click(trigger);
  fireEvent.click(await screen.findByText('Foshan Ceramics'));
}

beforeEach(() => {
  getFulfilmentSuppliers.mockClear();
});

describe('PlanContainerDialog - step 1', () => {
  it('asks for the supplier, the horizon and the document, in that order', () => {
    renderDialog();

    expect(screen.getByText('Plan a container')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /Supplier/i })).toBeInTheDocument();
    expect(screen.getByLabelText('Plan until')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Stock list' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Proforma invoice' })).toBeInTheDocument();
  });

  it('acts on nothing until a supplier is chosen', () => {
    renderDialog();

    // Both routes forward need somebody to plan FOR - a stock list applied to the wrong
    // supplier deletes one snapshot and invents another.
    expect(screen.getByTestId('plan-container-continue')).toBeDisabled();
    expect(screen.getByTestId('plan-without-file')).toBeDisabled();
  });

  it('enables both routes forward once a supplier is chosen', async () => {
    renderDialog();
    await chooseSupplier();

    expect(screen.getByTestId('plan-container-continue')).toBeEnabled();
    expect(screen.getByTestId('plan-without-file')).toBeEnabled();
  });

  it('plans without a file for a supplier whose document is already on file', async () => {
    const { onApply, onOpenChange } = renderDialog();
    await chooseSupplier();
    fireEvent.change(screen.getByLabelText('Plan until'), {
      target: { value: '2026-09-30' },
    });

    fireEvent.click(screen.getByTestId('plan-without-file'));

    expect(onApply).toHaveBeenCalledWith({
      supplierId: 'sup-1',
      supplierOption: expect.objectContaining({ value: 'sup-1', label: 'Foshan Ceramics' }),
      planHorizonDate: '2026-09-30',
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('lets the horizon be unset again', async () => {
    renderDialog();
    await chooseSupplier();
    fireEvent.change(screen.getByLabelText('Plan until'), {
      target: { value: '2026-09-30' },
    });

    fireEvent.click(screen.getByTestId('clear-plan-horizon'));

    expect(screen.getByLabelText('Plan until')).toHaveValue('');
  });
});

describe('PlanContainerDialog - step 2', () => {
  it('continues to the stock-list upload with the supplier already fixed', async () => {
    renderDialog();
    await chooseSupplier();

    fireEvent.click(screen.getByTestId('plan-container-continue'));

    expect(await screen.findByTestId('stock-upload-dialog')).toHaveTextContent(
      'Stock list upload for Foshan Ceramics',
    );
    // Step 1 is gone, not stacked underneath.
    expect(screen.queryByText('Plan a container')).not.toBeInTheDocument();
  });

  it('continues to the proforma upload when that is the document being sent', async () => {
    renderDialog();
    await chooseSupplier();
    fireEvent.click(screen.getByRole('radio', { name: 'Proforma invoice' }));

    fireEvent.click(screen.getByTestId('plan-container-continue'));

    expect(await screen.findByTestId('proforma-upload-dialog')).toHaveTextContent(
      'Proforma upload for Foshan Ceramics',
    );
  });

  it('skips step 1 when the caller already knows the supplier and the document', async () => {
    renderDialog({
      supplierId: 'sup-9',
      supplierOption: { value: 'sup-9', label: 'Guangdong Tiles' },
      planHorizonDate: '2026-10-15',
      openTo: 'proforma' as PlanDocumentKind,
    });

    expect(await screen.findByTestId('proforma-upload-dialog')).toHaveTextContent(
      'Proforma upload for Guangdong Tiles',
    );
    expect(screen.queryByText('Plan a container')).not.toBeInTheDocument();
  });

  it('hands the page its picks once the upload applies', async () => {
    // The upload dialogs are stubbed here, so the apply is exercised through the same
    // callback they fire: what matters is that the page ends up planning for the supplier
    // that was just uploaded for, without a second confirmation.
    const { onApply } = renderDialog({
      supplierId: 'sup-9',
      supplierOption: { value: 'sup-9', label: 'Guangdong Tiles' },
      planHorizonDate: '2026-10-15',
      openTo: 'stock-list' as PlanDocumentKind,
    });

    await screen.findByTestId('stock-upload-dialog');
    captured.onApplied?.();

    expect(onApply).toHaveBeenCalledWith({
      supplierId: 'sup-9',
      supplierOption: { value: 'sup-9', label: 'Guangdong Tiles' },
      planHorizonDate: '2026-10-15',
    });
  });
});
