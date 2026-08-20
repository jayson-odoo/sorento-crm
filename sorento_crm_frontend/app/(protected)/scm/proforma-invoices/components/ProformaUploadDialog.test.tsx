/**
 * The proforma-invoice upload dialog: supplier chosen HERE (not read off the page behind it,
 * see the file header on the component), currency asked for last and only when nothing else
 * says (AC-P3.1), and the preview names a derived PI number and a stated-vs-computed total
 * mismatch rather than letting either pass silently.
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

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

// The real SearchableSelect drives a cmdk popover; this test cares which supplier ends up
// picked, not popover mechanics, so it stands in for a native <select> (same pattern as
// PlanLinesGrid.test.tsx / AdjustRecommendationModal.test.tsx). The supplier picker is
// server-searched now (S8-followup): the stub resolves `fetchOptions('', 0)` once, the same
// as the real component's own eager first-page fetch on open, so `options` callers and
// `fetchOptions` callers both render a populated <select> without reproducing the real
// debounce/pagination machinery.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    onOptionChange,
    options,
    fetchOptions,
    placeholder,
  }: {
    id?: string;
    value?: string;
    onChange?: (v: string) => void;
    onOptionChange?: (opt: { value: string; label: string } | null) => void;
    options?: Array<{ value: string; label: string }>;
    fetchOptions?: (
      query: string,
      pageIndex: number,
    ) => Promise<Array<{ value: string; label: string }>>;
    placeholder?: string;
  }) => {
    const [asyncOptions, setAsyncOptions] = React.useState<Array<{ value: string; label: string }>>([]);
    React.useEffect(() => {
      if (!fetchOptions) return;
      void fetchOptions('', 0).then(setAsyncOptions);
    }, [fetchOptions]);
    const opts = options ?? asyncOptions;
    return (
      <select
        id={id}
        aria-label="Supplier"
        value={value}
        onChange={(e) => {
          onChange?.(e.target.value);
          onOptionChange?.(opts.find((o) => o.value === e.target.value) ?? null);
        }}
      >
        <option value="">{placeholder}</option>
        {opts.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  },
}));

const previewProformaInvoice = vi.fn();
const applyProformaInvoice = vi.fn();
const testProformaInvoice = vi.fn();

vi.mock('../../services/proformaInvoiceService', () => ({
  previewProformaInvoice: (...a: unknown[]) => previewProformaInvoice(...a),
  applyProformaInvoice: (...a: unknown[]) => applyProformaInvoice(...a),
  testProformaInvoice: (...a: unknown[]) => testProformaInvoice(...a),
}));

vi.mock('../../reorder/services/outstandingImportService', () => ({
  getOutstandingUploadConfig: async () => ({ allowed_extensions: ['.xlsx', '.xls'] }),
}));

const getFulfilmentSuppliers = vi.fn(
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async (_query?: string) => [{ value: 'sup-1', label: 'Kailu Hardware Factory' }],
);
vi.mock('../../services/fulfilmentService', () => ({
  getFulfilmentSuppliers: (query?: string) => getFulfilmentSuppliers(query),
}));

import { ProformaUploadDialog } from './ProformaUploadDialog';

const PREVIEW = {
  ok: true,
  missing_columns: [],
  problems: [],
  supplier_id: 'sup-1',
  supplier_code: 'KAILU',
  supplier_name: 'Kailu Hardware Factory',
  documents: [
    {
      index: 0,
      pi_number: 'PI-2026-001',
      pi_number_stated: true,
      invoice_date: '2026-08-01',
      container_no: 'TEMU1234567',
      bl_no: 'BL-991',
      lines: 5,
      qty: 200,
      total: 1000,
      stated_total: 1000,
      unmatched_items: [],
      currency: 'CNY',
      currency_source: 'document' as const,
    },
  ],
  document_count: 1,
  line_count: 5,
  priced_lines: 5,
  rows_read: 5,
  unmatched_item_codes: [],
  unmatched_items: 0,
  unmapped_headers: [],
  currency: 'CNY',
  currency_source: 'document' as const,
  priced_lines_without_currency: 0,
};

function xlsx(name = 'proforma.xlsx'): File {
  return new File([new Uint8Array([1, 2, 3])], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

function fileInput(): HTMLInputElement {
  return document.querySelector('input[type="file"]') as HTMLInputElement;
}

function pickFile(file = xlsx()) {
  fireEvent.change(fileInput(), { target: { files: [file] } });
  return file;
}

function testButton() {
  return screen.getByRole('button', { name: /^Test$/i });
}

function confirmButton() {
  return screen.getByRole('button', { name: /^Confirm$/i });
}

function supplierSelect(): HTMLSelectElement {
  return screen.getByLabelText('Supplier') as HTMLSelectElement;
}

function openDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onApplied = vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <ProformaUploadDialog open onOpenChange={() => {}} onApplied={onApplied} />
    </QueryClientProvider>,
  );
  return { onApplied };
}

// The supplier list is server-searched (S8-followup, async `fetchOptions`) - the mocked
// promise resolves after a microtask, so this waits for the option to actually land before
// picking it, rather than racing the resolve like a synchronous `options` list never did.
async function chooseSupplier() {
  await waitFor(() =>
    expect(supplierSelect().querySelector('option[value="sup-1"]')).toBeInTheDocument(),
  );
  fireEvent.change(supplierSelect(), { target: { value: 'sup-1' } });
}

beforeEach(() => {
  previewProformaInvoice.mockReset().mockResolvedValue(PREVIEW);
  applyProformaInvoice.mockReset();
  testProformaInvoice.mockReset().mockResolvedValue(null);
});

describe('ProformaUploadDialog - supplier gates everything (AC journey step 1)', () => {
  it('offers neither Test nor Confirm before a supplier is chosen', () => {
    openDialog();

    expect(testButton()).toBeDisabled();
    expect(confirmButton()).toBeDisabled();
    expect(testButton()).toHaveAttribute('title', 'Choose a supplier first');
  });

  it('enables Test and Confirm once a supplier is chosen and a file is picked', async () => {
    openDialog();
    await chooseSupplier();
    pickFile();

    expect(testButton()).toBeEnabled();
    expect(confirmButton()).toBeEnabled();
  });

  it('carries the chosen supplier on the preview/test/apply calls', async () => {
    openDialog();
    await chooseSupplier();
    const file = pickFile();

    fireEvent.click(testButton());

    await waitFor(() => expect(previewProformaInvoice).toHaveBeenCalledWith(file, 'sup-1', null));
    expect(testProformaInvoice).toHaveBeenCalledWith(file, 'sup-1', null);
  });
});

describe('ProformaUploadDialog - the preview names what the file left ambiguous', () => {
  it('marks a PI number the file never stated as derived', async () => {
    previewProformaInvoice.mockResolvedValue({
      ...PREVIEW,
      documents: [{ ...PREVIEW.documents[0], pi_number_stated: false }],
    });
    openDialog();
    await chooseSupplier();
    pickFile();
    fireEvent.click(testButton());

    expect(await screen.findByText('PI-2026-001')).toBeInTheDocument();
    expect(screen.getByText('(derived)')).toBeInTheDocument();
  });

  it('does not mark a PI number the file actually stated', async () => {
    openDialog();
    await chooseSupplier();
    pickFile();
    fireEvent.click(testButton());

    expect(await screen.findByText('PI-2026-001')).toBeInTheDocument();
    expect(screen.queryByText('(derived)')).not.toBeInTheDocument();
  });

  it('says which currency was resolved and names its source in words', async () => {
    openDialog();
    await chooseSupplier();
    pickFile();
    fireEvent.click(testButton());

    expect(await screen.findByText(/Priced in CNY \(stated by the file\)/)).toBeInTheDocument();
  });

  it('says nothing states the currency when the document left it ambiguous', async () => {
    previewProformaInvoice.mockResolvedValue({
      ...PREVIEW,
      documents: [{ ...PREVIEW.documents[0], currency: null, currency_source: 'none' as const }],
    });
    openDialog();
    await chooseSupplier();
    pickFile();
    fireEvent.click(testButton());

    expect(
      await screen.findByText(/Nothing states which money this invoice is in/),
    ).toBeInTheDocument();
  });

  it('flags a document total that does not match the summed lines', async () => {
    previewProformaInvoice.mockResolvedValue({
      ...PREVIEW,
      documents: [{ ...PREVIEW.documents[0], total: 950, stated_total: 1000 }],
    });
    openDialog();
    await chooseSupplier();
    pickFile();
    fireEvent.click(testButton());

    expect(await screen.findByText(/does not match the lines/)).toBeInTheDocument();
    expect(screen.getByText(/stated RMB 1,000\.00|stated.*1,000/)).toBeInTheDocument();
  });

  it('does not flag a document total that matches the summed lines', async () => {
    openDialog();
    await chooseSupplier();
    pickFile();
    fireEvent.click(testButton());

    expect(await screen.findByText(/Total/)).toBeInTheDocument();
    expect(screen.queryByText(/does not match the lines/)).not.toBeInTheDocument();
  });

  it('names unmatched item codes rather than dropping them silently', async () => {
    previewProformaInvoice.mockResolvedValue({
      ...PREVIEW,
      unmatched_items: 1,
      unmatched_item_codes: ['ZZ-NOPE'],
      documents: [{ ...PREVIEW.documents[0], unmatched_items: ['ZZ-NOPE'] }],
    });
    openDialog();
    await chooseSupplier();
    pickFile();
    fireEvent.click(testButton());

    expect((await screen.findAllByText(/ZZ-NOPE/)).length).toBeGreaterThan(0);
  });
});

describe('ProformaUploadDialog - apply', () => {
  it('reports invoices created', async () => {
    applyProformaInvoice.mockResolvedValue({
      documents_created: 1,
      documents_updated: 0,
      results: [],
      summary: {},
    });
    const { onApplied } = openDialog();
    await chooseSupplier();
    pickFile();

    fireEvent.click(confirmButton());

    expect(await screen.findByText(/Created 1 invoice\./)).toBeInTheDocument();
    await waitFor(() => expect(onApplied).toHaveBeenCalledTimes(1));
  });

  it('reports invoices created AND updated together on a re-upload', async () => {
    applyProformaInvoice.mockResolvedValue({
      documents_created: 1,
      documents_updated: 2,
      results: [],
      summary: {},
    });
    openDialog();
    await chooseSupplier();
    pickFile();

    fireEvent.click(confirmButton());

    expect(await screen.findByText(/Created 1 invoice, updated 2\./)).toBeInTheDocument();
  });

  it('reports nothing new when every document in the file already existed', async () => {
    applyProformaInvoice.mockResolvedValue({
      documents_created: 0,
      documents_updated: 3,
      results: [],
      summary: {},
    });
    openDialog();
    await chooseSupplier();
    pickFile();

    fireEvent.click(confirmButton());

    expect(await screen.findByText(/Nothing new was created, updated 3\./)).toBeInTheDocument();
  });

  it('shows the server\'s refusal and keeps the dialog open', async () => {
    applyProformaInvoice.mockRejectedValue(new Error('supplier_id is required'));
    openDialog();
    await chooseSupplier();
    pickFile();

    fireEvent.click(confirmButton());

    expect(await screen.findByText('supplier_id is required')).toBeInTheDocument();
    expect(confirmButton()).toBeInTheDocument();
  });
});

describe('ProformaUploadDialog - currency, the last resort (AC-P3.1)', () => {
  function currencyField(): HTMLInputElement {
    return screen.getByLabelText('Currency') as HTMLInputElement;
  }

  it('sends no currency at all when the field is left empty', async () => {
    openDialog();
    await chooseSupplier();
    const file = pickFile();

    fireEvent.click(testButton());

    await waitFor(() => expect(previewProformaInvoice).toHaveBeenCalledWith(file, 'sup-1', null));
  });

  it('upper-cases what is typed and caps it at three letters', () => {
    openDialog();

    fireEvent.change(currencyField(), { target: { value: 'usdx' } });

    expect(currencyField().value).toBe('USD');
  });

  it('carries the typed currency on preview, test and apply', async () => {
    applyProformaInvoice.mockResolvedValue({
      documents_created: 1,
      documents_updated: 0,
      results: [],
      summary: {},
    });
    openDialog();
    await chooseSupplier();
    const file = pickFile();
    fireEvent.change(currencyField(), { target: { value: 'usd' } });

    fireEvent.click(testButton());
    await waitFor(() =>
      expect(previewProformaInvoice).toHaveBeenCalledWith(file, 'sup-1', 'USD'),
    );

    fireEvent.click(confirmButton());
    await waitFor(() =>
      expect(applyProformaInvoice).toHaveBeenCalledWith(file, 'sup-1', 'USD'),
    );
  });
});
