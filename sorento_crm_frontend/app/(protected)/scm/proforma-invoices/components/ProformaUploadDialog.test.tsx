/**
 * The proforma-invoice upload dialog, AFTER R24: the same two-step shape as the
 * purchase-order and sales-order uploads.
 *
 * What this pins, and what each pin replaces:
 *
 * - Picking a file runs NOTHING. The old dialog read the file on drop to find a revision
 *   candidate, which made this the only channel that fetched before it was asked to.
 * - Test renders the STANDARD `{valid, errors, warnings, summary}` card, derived from the
 *   preview, in place of the per-invoice card list with a currency box and a tickbox on each.
 * - There is no Currency field at all. The document or the price list answers it; where
 *   NEITHER does, the verdict names the invoices and Confirm is refused.
 * - Revision candidates are filed as revisions BY DEFAULT, and Confirm takes the read it
 *   needs for that itself when the operator never pressed Test.
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

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

// The real SearchableSelect drives a cmdk popover; this test cares which supplier ends up
// picked, not popover mechanics, so it stands in for a native <select>. The supplier picker
// is server-searched (S8-followup): the stub resolves `fetchOptions('', 0)` once, the same as
// the real component's own eager first-page fetch on open.
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
    const [asyncOptions, setAsyncOptions] = React.useState<
      Array<{ value: string; label: string }>
    >([]);
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

vi.mock('../../services/proformaInvoiceService', () => ({
  previewProformaInvoice: (...a: unknown[]) => previewProformaInvoice(...a),
  applyProformaInvoice: (...a: unknown[]) => applyProformaInvoice(...a),
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

import { ProformaUploadDialog, verdictFromPreview } from './ProformaUploadDialog';

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
      revision_candidate: null,
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

const CANDIDATE = {
  invoice_id: 'pi-earlier',
  pi_number: 'PI-2026-7-31-1',
  invoice_date: '2026-07-31',
  overlap_pct: 100,
  matched_items: 5,
  lines: 5,
};

function previewWithCandidate(candidate: typeof CANDIDATE | null = CANDIDATE) {
  return {
    ...PREVIEW,
    documents: [{ ...PREVIEW.documents[0], revision_candidate: candidate }],
  };
}

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
  return screen.getByRole('button', { name: /^Import proforma invoice$/i });
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

// The supplier list is server-searched (async `fetchOptions`) - the mocked promise resolves
// after a microtask, so this waits for the option to land before picking it.
async function chooseSupplier() {
  await waitFor(() =>
    expect(supplierSelect().querySelector('option[value="sup-1"]')).toBeInTheDocument(),
  );
  fireEvent.change(supplierSelect(), { target: { value: 'sup-1' } });
}

const APPLIED_ONE = {
  documents_created: 1,
  documents_updated: 0,
  results: [],
  summary: {},
};

beforeEach(() => {
  previewProformaInvoice.mockReset().mockResolvedValue(PREVIEW);
  applyProformaInvoice.mockReset().mockResolvedValue(APPLIED_ONE);
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
});

describe('ProformaUploadDialog - the same three presses as every other upload (R24)', () => {
  it('reads NOTHING when a file is picked', async () => {
    openDialog();
    await chooseSupplier();
    pickFile();

    // Deliberately not `waitFor`: a read that has not started is the assertion, and a
    // read that starts one microtask later would still be a read on pick.
    await Promise.resolve();
    expect(previewProformaInvoice).not.toHaveBeenCalled();
  });

  it('reads the file on Test, carrying the chosen supplier and no currency', async () => {
    openDialog();
    await chooseSupplier();
    const file = pickFile();

    fireEvent.click(testButton());

    await waitFor(() => expect(previewProformaInvoice).toHaveBeenCalledWith(file, 'sup-1'));
  });

  it('asks for no currency at all - the document or the price list answers it', async () => {
    openDialog();
    await chooseSupplier();
    pickFile();

    expect(screen.queryByLabelText('Currency')).not.toBeInTheDocument();
  });

  it('prints the standard verdict rather than a card per invoice', async () => {
    openDialog();
    await chooseSupplier();
    pickFile();
    fireEvent.click(testButton());

    expect(await screen.findByText('No errors')).toBeInTheDocument();
    expect(screen.getByText(/Invoices: 1/)).toBeInTheDocument();
    expect(screen.getByText(/Rows: 5/)).toBeInTheDocument();
    // The old per-invoice list is gone: no tickbox, no "(derived)", no container line.
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByText('(derived)')).not.toBeInTheDocument();
  });
});

describe('verdictFromPreview - what Test says about the file', () => {
  it('is valid, with nothing to report, on a clean file', () => {
    const v = verdictFromPreview(PREVIEW);

    expect(v.valid).toBe(true);
    expect(v.errors).toEqual([]);
    expect(v.warnings).toEqual([]);
    expect(v.summary).toMatchObject({ document_count: 1, total_rows: 5, would_apply: 5 });
  });

  it('names a missing column as an error that blocks the file', () => {
    const v = verdictFromPreview({ ...PREVIEW, ok: false, missing_columns: ['unit_price'] });

    expect(v.valid).toBe(false);
    expect(v.errors[0]).toContain('unit_price');
  });

  it('says so when the workbook holds no invoice at all', () => {
    const v = verdictFromPreview({ ...PREVIEW, ok: false, documents: [], document_count: 0 });

    expect(v.valid).toBe(false);
    expect(v.errors).toContain('No proforma invoice was found in this file.');
  });

  it('NAMES the invoices nothing can price, rather than asking for a currency', () => {
    const v = verdictFromPreview({
      ...PREVIEW,
      priced_lines_without_currency: 5,
      documents: [
        { ...PREVIEW.documents[0], currency: null, currency_source: 'none' as const },
      ],
    });

    expect(v.valid).toBe(false);
    expect(v.errors[0]).toContain('PI-2026-001');
  });

  it('leaves an UNPRICED document alone - it has nothing to denominate', () => {
    const v = verdictFromPreview({
      ...PREVIEW,
      priced_lines: 0,
      documents: [
        {
          ...PREVIEW.documents[0],
          total: null,
          stated_total: null,
          currency: null,
          currency_source: 'none' as const,
        },
      ],
    });

    expect(v.valid).toBe(true);
  });

  it('counts codes that bind to nothing as a WARNING, never an error', () => {
    const v = verdictFromPreview({
      ...PREVIEW,
      unmatched_items: 2,
      unmatched_item_codes: ['ZZ-NOPE', 'ZZ-ALSO'],
    });

    expect(v.valid).toBe(true);
    expect(v.warnings[0]).toContain('ZZ-NOPE');
    expect(v.warnings[0]).toContain('2 codes are');
  });

  it('says which invoices will supersede an earlier version', () => {
    const v = verdictFromPreview(previewWithCandidate());

    expect(v.warnings.some((w) => /1 invoice updates an earlier version: PI-2026-001/.test(w))).toBe(
      true,
    );
  });

  it('carries the reader\'s own row complaints through as warnings', () => {
    const v = verdictFromPreview({ ...PREVIEW, problems: ['Row 12: skipped ABC'] });

    expect(v.warnings).toContain('Row 12: skipped ABC');
    expect(v.valid).toBe(true);
  });
});

describe('ProformaUploadDialog - a file the verdict blocks', () => {
  it('disables Confirm and says why, once Test has read it as unusable', async () => {
    previewProformaInvoice.mockResolvedValue({
      ...PREVIEW,
      ok: false,
      missing_columns: ['unit_price'],
    });
    openDialog();
    await chooseSupplier();
    pickFile();
    fireEvent.click(testButton());

    // Confirm is also disabled while the preview is still in flight, so the
    // verdict's own reason is the signal to wait on, not the disabled state. Both
    // assertions live inside the SAME waitFor: the disabled flip and the title
    // update land in separate re-renders, so checking one outside the wait races
    // the other on a slow runner (seen in CI, not locally).
    await waitFor(() => {
      expect(confirmButton()).toBeDisabled();
      expect(confirmButton()).toHaveAttribute(
        'title',
        expect.stringContaining('no unit_price column'),
      );
    });
  });

  it('refuses a priced file nothing can price, naming the invoice', async () => {
    previewProformaInvoice.mockResolvedValue({
      ...PREVIEW,
      priced_lines_without_currency: 5,
      documents: [
        { ...PREVIEW.documents[0], currency: null, currency_source: 'none' as const },
      ],
    });
    openDialog();
    await chooseSupplier();
    pickFile();
    fireEvent.click(testButton());

    expect(await screen.findByText(/Nothing says which money this invoice is in/)).toBeInTheDocument();
    expect(confirmButton()).toBeDisabled();
  });
});

describe('ProformaUploadDialog - revisions are the default, not a question', () => {
  it('files the candidate as a revision without asking, on a Confirm with no Test', async () => {
    previewProformaInvoice.mockResolvedValue(previewWithCandidate());
    openDialog();
    await chooseSupplier();
    const file = pickFile();

    fireEvent.click(confirmButton());

    await waitFor(() => expect(applyProformaInvoice).toHaveBeenCalledTimes(1));
    expect(applyProformaInvoice).toHaveBeenCalledWith(file, 'sup-1', { '0': 'pi-earlier' });
    // The read Confirm needed, taken on the Confirm press - never on the file being picked.
    expect(previewProformaInvoice).toHaveBeenCalledTimes(1);
  });

  it('reuses the read Test already took rather than reading the file twice', async () => {
    previewProformaInvoice.mockResolvedValue(previewWithCandidate());
    openDialog();
    await chooseSupplier();
    const file = pickFile();

    fireEvent.click(testButton());
    // Wait for the read to LAND, not just to start: Confirm is disabled while the preview
    // is in flight, and a click on a disabled button is a silent no-op (CI flaked here).
    await waitFor(() => expect(confirmButton()).toBeEnabled());
    expect(previewProformaInvoice).toHaveBeenCalledTimes(1);
    fireEvent.click(confirmButton());

    await waitFor(() => expect(applyProformaInvoice).toHaveBeenCalledTimes(1));
    expect(applyProformaInvoice).toHaveBeenCalledWith(file, 'sup-1', { '0': 'pi-earlier' });
    expect(previewProformaInvoice).toHaveBeenCalledTimes(1);
  });

  it('sends an empty selection when the file revises nothing on record', async () => {
    openDialog();
    await chooseSupplier();
    const file = pickFile();

    fireEvent.click(confirmButton());

    await waitFor(() => expect(applyProformaInvoice).toHaveBeenCalledWith(file, 'sup-1', {}));
  });
});

describe('ProformaUploadDialog - what the apply reports', () => {
  it('reports invoices created', async () => {
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

    expect(
      await screen.findByText(/Created 1 invoice\. Updated 2 in place\./),
    ).toBeInTheDocument();
  });

  it('names the invoice a re-upload landed on, rather than "nothing new"', async () => {
    applyProformaInvoice.mockResolvedValue({
      documents_created: 0,
      documents_updated: 1,
      results: [
        {
          index: 0,
          invoice_id: 'pi-1',
          pi_number: 'PI-2026-7-31-1',
          invoice_date: '2026-07-31',
          currency: 'CNY',
          currency_source: 'document',
          lines: 5,
          revision_no: 1,
          revision_of_id: null,
          total_amount: 1000,
          unmatched_items: [],
          created: false,
        },
      ],
      summary: {},
    });
    openDialog();
    await chooseSupplier();
    pickFile();

    fireEvent.click(confirmButton());

    expect(await screen.findByText(/Updated PI-2026-7-31-1/)).toBeInTheDocument();
  });

  it('says how many landed as revisions', async () => {
    applyProformaInvoice.mockResolvedValue({
      documents_created: 1,
      documents_updated: 0,
      results: [
        {
          index: 0,
          invoice_id: 'pi-new',
          pi_number: 'PI-2026-001-R2',
          invoice_date: '2026-08-01',
          currency: 'CNY',
          currency_source: 'document',
          lines: 5,
          revision_no: 2,
          revision_of_id: 'pi-earlier',
          total_amount: 1000,
          unmatched_items: [],
          created: true,
        },
      ],
      summary: {},
    });
    openDialog();
    await chooseSupplier();
    pickFile();

    fireEvent.click(confirmButton());

    expect(await screen.findByText(/1 filed as a revision/)).toBeInTheDocument();
  });

  it('replaces the verdict with the result rather than showing both', async () => {
    openDialog();
    await chooseSupplier();
    pickFile();
    fireEvent.click(testButton());
    await screen.findByText('No errors');

    fireEvent.click(confirmButton());

    await screen.findByText(/Created 1 invoice/);
    expect(screen.queryByText('No errors')).not.toBeInTheDocument();
    // And the footer is done: Cancel becomes Close, and Test and Confirm are gone.
    expect(screen.queryByRole('button', { name: /^Import proforma invoice$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Test$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Cancel$/i })).not.toBeInTheDocument();
  });

  it("shows the server's refusal and keeps the dialog open", async () => {
    applyProformaInvoice.mockRejectedValue(new Error('supplier_id is required'));
    openDialog();
    await chooseSupplier();
    pickFile();

    fireEvent.click(confirmButton());

    expect(await screen.findByText('supplier_id is required')).toBeInTheDocument();
    expect(confirmButton()).toBeInTheDocument();
  });
});

/**
 * Opened from the loading plan, the supplier is already known - the plan was built for it,
 * and the proforma is what stands in for a missing stock list (Q2). Asking again would let
 * the document be filed against a supplier the plan behind the dialog knows nothing about.
 */
describe('ProformaUploadDialog - a supplier the caller already knows', () => {
  function openDialogForSupplier() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onApplied = vi.fn();
    render(
      <QueryClientProvider client={qc}>
        <ProformaUploadDialog
          open
          onOpenChange={() => {}}
          onApplied={onApplied}
          supplierId="sup-1"
          supplierOption={{ value: 'sup-1', label: 'Kailu Hardware Factory' }}
        />
      </QueryClientProvider>,
    );
    return { onApplied };
  }

  it('states the supplier instead of offering the picker', () => {
    openDialogForSupplier();

    expect(screen.queryByLabelText('Supplier')).not.toBeInTheDocument();
    expect(screen.getByTestId('proforma-fixed-supplier')).toHaveTextContent(
      'Kailu Hardware Factory',
    );
  });

  it('lets the file be dropped straight away, with no pick to make first', () => {
    openDialogForSupplier();
    pickFile();

    expect(testButton()).toBeEnabled();
    expect(confirmButton()).toBeEnabled();
  });

  it('still reads nothing on pick, and carries that supplier on the apply', async () => {
    openDialogForSupplier();
    const file = pickFile();

    await Promise.resolve();
    expect(previewProformaInvoice).not.toHaveBeenCalled();

    fireEvent.click(confirmButton());

    await waitFor(() => expect(applyProformaInvoice).toHaveBeenCalledWith(file, 'sup-1', {}));
  });
});
