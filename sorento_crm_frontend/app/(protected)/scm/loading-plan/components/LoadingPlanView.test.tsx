/**
 * S7b - the loading plan screen.
 *
 * The CBM-fit half of this page (container size, packed-stock tiles, the loading plan table)
 * was cut on the captain's 20 Aug live-test ruling ("don't need stage 2") - see
 * LoadingPlanView.tsx's own docstring. What is left to assert here is the supplier picker
 * itself: nothing is shown before a supplier is chosen, choosing one renders the request
 * section, the "View uploaded list" control only appears once a stock-list file exists, and
 * both upload routes (stock list, proforma invoice) wait on a supplier being chosen.
 * Everything the request section itself does (the deferred-line reasoning, the ranked table,
 * sending to the supplier) is covered in ContainerRequestSection.test.tsx.
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

// The supplier picker is server-searched now (S8-followup, same fix as the proforma upload
// dialog): `SearchableSelect` calls `fetchOptions('', 0)` on open, so the real component is
// kept (not stubbed) and only `getFulfilmentSuppliers` is overridden here - `importOriginal`
// keeps every other export real, since `StockListUploadDialog` / `ContainerRequestSection`
// import other functions off this same module and neither is exercised by this suite.
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

const state = {
  stockListFile: undefined as { attachment_id: string; filename: string } | undefined,
};

vi.mock('../../hooks/useFulfilment', () => ({
  useSupplierStockListFile: () => ({ data: state.stockListFile, isLoading: false }),
  useStockListApplied: () => vi.fn(),
}));

// The request section renders inside this view too. Its own behaviour is covered in
// ContainerRequestSection.test.tsx; here it only has to prove it mounted for the chosen
// supplier, so this stub keeps the suite from also depending on that component's own hooks.
// The proforma dialog is the other way to answer "what do they hold" (Q2), opened from this
// toolbar. Its own behaviour is covered in ProformaUploadDialog.test.tsx; here it only has to
// prove it opened for the supplier already chosen on this screen.
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

vi.mock('./ContainerRequestSection', () => ({
  ContainerRequestSection: ({ supplierName }: { supplierName: string }) => (
    <div data-testid="container-request-section">Request section for {supplierName}</div>
  ),
}));

import { LoadingPlanView } from './LoadingPlanView';

function renderView() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LoadingPlanView />
    </QueryClientProvider>,
  );
}

/** The supplier select is a combobox; pick the only option in it. */
async function chooseSupplier() {
  const trigger = screen.getByRole('combobox', { name: /Supplier/i });
  fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
  fireEvent.click(trigger);
  fireEvent.click(await screen.findByText('Foshan Ceramics'));
}

beforeEach(() => {
  getFulfilmentSuppliers.mockClear();
  state.stockListFile = undefined;
});

describe('LoadingPlanView - before a supplier is chosen', () => {
  it('says what to do rather than showing an empty request', async () => {
    renderView();

    expect(await screen.findByText('Choose a supplier to plan a container.')).toBeInTheDocument();
    expect(screen.queryByTestId('container-request-section')).not.toBeInTheDocument();
  });

  it('has no view-uploaded-list control since no supplier is chosen yet', () => {
    renderView();

    expect(screen.queryByRole('button', { name: /view uploaded list/i })).not.toBeInTheDocument();
  });
});

describe('LoadingPlanView - a supplier is chosen', () => {
  it('renders the request section for the chosen supplier', async () => {
    renderView();
    await chooseSupplier();

    expect(await screen.findByTestId('container-request-section')).toBeInTheDocument();
    expect(screen.getByText('Request section for Foshan Ceramics')).toBeInTheDocument();
  });

  it('hides the view-uploaded-list control until a stock list has been uploaded', async () => {
    renderView();
    await chooseSupplier();

    await screen.findByTestId('container-request-section');
    expect(screen.queryByRole('button', { name: /view uploaded list/i })).not.toBeInTheDocument();
  });

  it('offers to view the uploaded list once a stock-list file exists', async () => {
    state.stockListFile = { attachment_id: 'att-1', filename: 'foshan-stock.xlsx' };
    renderView();
    await chooseSupplier();

    expect(
      await screen.findByRole('button', { name: /view uploaded list/i }),
    ).toBeInTheDocument();
  });

  it('enables the upload-stock-list toolbar button once a supplier is chosen', async () => {
    renderView();
    expect(screen.getByTestId('open-stock-upload')).toBeDisabled();

    await chooseSupplier();

    expect(screen.getByTestId('open-stock-upload')).toBeEnabled();
  });

  it('enables the upload-proforma toolbar button once a supplier is chosen', async () => {
    renderView();
    // Whose invoice it is has no answer yet, so there is nothing to file it against.
    expect(screen.getByTestId('open-proforma-upload')).toBeDisabled();

    await chooseSupplier();

    expect(screen.getByTestId('open-proforma-upload')).toBeEnabled();
  });

  it('opens the proforma upload against the supplier already chosen here', async () => {
    renderView();
    await chooseSupplier();

    expect(screen.queryByTestId('proforma-upload-dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('open-proforma-upload'));

    expect(await screen.findByTestId('proforma-upload-dialog')).toHaveTextContent(
      'Proforma upload for Foshan Ceramics',
    );
  });
});
