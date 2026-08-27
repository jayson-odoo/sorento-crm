/**
 * S7b - the loading plan screen.
 *
 * The CBM-fit half of this page (container size, packed-stock tiles, the loading plan table)
 * was cut on the captain's 20 Aug live-test ruling ("don't need stage 2") - see
 * LoadingPlanView.tsx's own docstring. What is left to assert here is the toolbar the
 * captain's 27 Aug ruling reshaped: ONE Upload CTA opens the popup that owns supplier, plan
 * until and document; what was chosen reads back as text; and the occasional actions (view
 * the uploaded sheet, re-run matching, change the picks) sit behind the gear, which has
 * nothing to act on until a supplier exists.
 *
 * The popup's own two steps are covered in PlanContainerDialog.test.tsx, and everything the
 * request section does (the deferred-line reasoning, the ranked table, sending to the
 * supplier) in ContainerRequestSection.test.tsx.
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

// The gear menu, flattened: Radix opens on pointerdown through a portal, and what this suite
// asks of it is which items it offers, not how it animates. Same stub as
// PurchaseOrdersList.test.tsx uses for the same reason.
/* eslint-disable @typescript-eslint/no-explicit-any */
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: any) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: any) => <>{children}</>,
  DropdownMenuContent: ({ children }: any) => <div data-testid="menu-content">{children}</div>,
  DropdownMenuItem: ({ children, onSelect, disabled, ...rest }: any) => (
    <button type="button" onClick={onSelect} disabled={disabled} {...rest}>
      {children}
    </button>
  ),
  DropdownMenuLabel: ({ children }: any) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuGroup: ({ children }: any) => <div>{children}</div>,
  DropdownMenuPortal: ({ children }: any) => <>{children}</>,
}));
/* eslint-enable @typescript-eslint/no-explicit-any */

// The supplier picker is server-searched (S8-followup, same fix as the proforma upload
// dialog): `SearchableSelect` calls `fetchOptions('', 0)` on open, so the real component is
// kept (not stubbed) and only `getFulfilmentSuppliers` is overridden here - `importOriginal`
// keeps every other export real, since the upload dialogs import other functions off this
// same module.
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

const rematch = vi.fn();
vi.mock('../../hooks/useSupplierCodeAliases', () => ({
  useRematchSupplierCodes: () => ({ mutate: rematch, isPending: false }),
}));

// The queue panel and the request section both render inside this view for a chosen
// supplier. Each has its own suite; here they only have to prove they mounted, and the
// section's empty-state CTAs have to prove they reach the right upload.
vi.mock('./UnmatchedSupplierCodesPanel', () => ({
  UnmatchedSupplierCodesPanel: () => <div data-testid="unmatched-panel" />,
}));

vi.mock('./ContainerRequestSection', () => ({
  ContainerRequestSection: ({
    supplierName,
    onUploadStockList,
    onUploadProforma,
  }: {
    supplierName: string;
    onUploadStockList: () => void;
    onUploadProforma?: () => void;
  }) => (
    <div data-testid="container-request-section">
      Request section for {supplierName}
      <button type="button" onClick={onUploadStockList} data-testid="section-upload-stock">
        Upload stock list
      </button>
      <button type="button" onClick={onUploadProforma} data-testid="section-upload-proforma">
        Upload proforma invoice
      </button>
    </div>
  ),
}));

// Step 2 of the popup. Both are covered by their own suites; here each only has to prove it
// was reached for the supplier chosen on step 1.
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

vi.mock('./StockListUploadDialog', () => ({
  StockListUploadDialog: ({
    open,
    supplierName,
  }: {
    open: boolean;
    supplierName: string;
  }) =>
    open ? (
      <div data-testid="stock-upload-dialog">Stock list upload for {supplierName}</div>
    ) : null,
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

/** The supplier select is a combobox inside the popup; pick the only option in it. */
async function chooseSupplierInDialog() {
  const trigger = screen.getByRole('combobox', { name: /Supplier/i });
  fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
  fireEvent.click(trigger);
  fireEvent.click(await screen.findByText('Foshan Ceramics'));
}

/** The whole journey onto the page: Upload, pick the supplier, plan without a file. */
async function planForFoshan(horizon?: string) {
  fireEvent.click(screen.getByTestId('open-plan-container'));
  await chooseSupplierInDialog();
  if (horizon) {
    fireEvent.change(screen.getByLabelText('Plan until'), { target: { value: horizon } });
  }
  fireEvent.click(screen.getByTestId('plan-without-file'));
}

beforeEach(() => {
  getFulfilmentSuppliers.mockClear();
  rematch.mockClear();
  state.stockListFile = undefined;
});

describe('LoadingPlanView - before a supplier is chosen', () => {
  it('says what to do rather than showing an empty request', async () => {
    renderView();

    expect(await screen.findByText('Choose a supplier to plan a container.')).toBeInTheDocument();
    expect(screen.queryByTestId('container-request-section')).not.toBeInTheDocument();
  });

  it('reads back that nothing is being planned yet', () => {
    renderView();

    expect(screen.getByTestId('plan-supplier-text')).toHaveTextContent('No supplier chosen');
    expect(screen.getByTestId('plan-horizon-text')).toHaveTextContent('Plan until: -');
  });

  it('offers the same Upload CTA from the empty state', () => {
    renderView();

    expect(screen.getByTestId('open-plan-container-empty')).toBeEnabled();
  });

  it('has nothing behind the gear until there is a supplier to act on', () => {
    renderView();

    expect(screen.getByTestId('loading-plan-more')).toBeDisabled();
  });
});

describe('LoadingPlanView - the Upload popup', () => {
  it('opens on the supplier + plan until step', async () => {
    renderView();
    expect(screen.queryByRole('combobox', { name: /Supplier/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('open-plan-container'));

    expect(await screen.findByText('Plan a container')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /Supplier/i })).toBeInTheDocument();
  });

  it('plans without a file once the supplier and the date are picked', async () => {
    renderView();
    await planForFoshan('2026-09-30');

    // The picks are the page's now, and they read back as text rather than as inputs.
    expect(screen.getByTestId('plan-supplier-text')).toHaveTextContent(
      'Supplier: Foshan Ceramics',
    );
    expect(screen.getByTestId('plan-horizon-text')).toHaveTextContent('30/09/2026');
    expect(await screen.findByTestId('container-request-section')).toBeInTheDocument();
    expect(screen.getByText('Request section for Foshan Ceramics')).toBeInTheDocument();
  });

  it('opens the stock-list upload straight from the request section, for that supplier', async () => {
    renderView();
    await planForFoshan();

    fireEvent.click(await screen.findByTestId('section-upload-stock'));

    expect(await screen.findByTestId('stock-upload-dialog')).toHaveTextContent(
      'Stock list upload for Foshan Ceramics',
    );
  });

  it('opens the proforma upload straight from the request section, for that supplier', async () => {
    renderView();
    await planForFoshan();

    fireEvent.click(await screen.findByTestId('section-upload-proforma'));

    expect(await screen.findByTestId('proforma-upload-dialog')).toHaveTextContent(
      'Proforma upload for Foshan Ceramics',
    );
  });
});

describe('LoadingPlanView - the gear menu', () => {
  it('holds the occasional actions once a supplier is chosen', async () => {
    renderView();
    await planForFoshan();

    expect(screen.getByTestId('loading-plan-more')).toBeEnabled();
    expect(screen.getByRole('button', { name: /refresh matching/i })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /change supplier \/ plan until/i }),
    ).toBeInTheDocument();
  });

  it('hides View uploaded list until a stock-list file exists', async () => {
    renderView();
    await planForFoshan();

    expect(screen.queryByRole('button', { name: /view uploaded list/i })).not.toBeInTheDocument();
  });

  it('offers to view the uploaded list once a stock-list file exists', async () => {
    state.stockListFile = { attachment_id: 'att-1', filename: 'foshan-stock.xlsx' };
    renderView();
    await planForFoshan();

    expect(screen.getByRole('button', { name: /view uploaded list/i })).toBeInTheDocument();
  });

  it('re-runs the code matching for the chosen supplier', async () => {
    renderView();
    await planForFoshan();

    // The queue panel hides itself when every code binds, so the gear is the only place
    // this is reachable in exactly the state somebody is trying to reach (R18).
    fireEvent.click(screen.getByRole('button', { name: /refresh matching/i }));

    expect(rematch).toHaveBeenCalledWith({ supplier_id: 'sup-1' });
  });

  it('re-opens the popup on its first step to change the picks', async () => {
    renderView();
    await planForFoshan();

    fireEvent.click(screen.getByRole('button', { name: /change supplier \/ plan until/i }));

    expect(await screen.findByText('Plan a container')).toBeInTheDocument();
  });
});
