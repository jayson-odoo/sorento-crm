/**
 * The packing-list dialog, which INHERITED a behaviour change it never asked for.
 *
 * It drives `useTwoStepUpload`, and that hook stopped reading on file-select: picking a file
 * now runs nothing and Test is the explicit read. This dialog is not one of the five order-book
 * channels, so nobody looked at it while that change was made - which is exactly why the flow
 * it now has is pinned here.
 *
 * The other half is pinned honestly rather than aspirationally: **this channel's Confirm is
 * still SYNCHRONOUS.** It is not an order-book feed, it has no queued task, and it renders the
 * shipments it created in the dialog itself. So there is no job id, no drawer and no toast, and
 * a test asserting otherwise would be describing a feature that does not exist.
 *
 * Self-serve supplier picker (Deviations lane A, purchasing consolidation batch 6 Sep 2026;
 * review round 1 S4): R3 moves this dialog onto the Packing Lists page, which - unlike
 * `/scm/incoming` - carries no persistent supplier filter to source `supplierId` from. Rather
 * than build a second, page-level picker, the dialog itself manages an internal
 * `internalSupplierId` when its `supplierId` prop is left `undefined`; a caller that passes an
 * explicit `supplierId` (even `null`) keeps deciding it, unchanged (`IncomingContainersView.tsx`,
 * exercised below by every `openDialog()` test in this file - all of them pass a supplierId).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

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

const previewPackingList = vi.fn();
const applyPackingList = vi.fn();

vi.mock('@/app/(protected)/scm/services/fulfilmentService', () => ({
  previewPackingList: (...a: unknown[]) => previewPackingList(...a),
  applyPackingList: (...a: unknown[]) => applyPackingList(...a),
}));

vi.mock('@/app/(protected)/scm/reorder/services/outstandingImportService', () => ({
  getOutstandingUploadConfig: async () => ({ allowed_extensions: ['.xlsx', '.xls'] }),
}));

// A mutable mock (not a static object) so the self-serve describe block below can give
// it real supplier options, while every other test in this file keeps the original
// empty-data behaviour untouched (they all pass an explicit `supplierId`, so the picker
// never renders for them and this hook's data is irrelevant).
const useFulfilmentSuppliers = vi.fn(() => ({ data: [] as { value: string; label: string }[], isLoading: false }));
vi.mock('@/app/(protected)/scm/hooks/useFulfilment', () => ({
  useFulfilmentSuppliers: () => useFulfilmentSuppliers(),
}));

import { PackingListUploadDialog } from './PackingListUploadDialog';

const PREVIEW = {
  ok: true,
  blocks: [
    {
      index: 0,
      shipment_number: 'SH-0001',
      container_no: 'TEMU1234567',
      bl_no: 'BL-991',
      lines: 7,
      qty: 340,
      cartons: 40,
      unmatched_items: [],
    },
    {
      index: 1,
      shipment_number: 'SH-0002',
      container_no: null,
      bl_no: null,
      lines: 4,
      qty: 120,
      cartons: 12,
      unmatched_items: ['NOPE-1'],
    },
  ],
  block_count: 2,
  line_count: 11,
  rows_read: 13,
  unmatched_item_codes: ['NOPE-1'],
  unmatched_items: 1,
  unmapped_headers: [],
  missing_columns: [],
  problems: [],
};

function openDialog(
  supplierId: string | null = 'sup-1',
  supplierName: string | null = 'KAILU HARDWARE FACTORY',
) {
  const onImported = vi.fn();
  render(
    <PackingListUploadDialog
      open
      onOpenChange={() => {}}
      supplierId={supplierId}
      supplierName={supplierName}
      onImported={onImported}
    />,
  );
  return { onImported };
}

/** No `supplierId`/`supplierName` prop at all - the self-serve branch (R3 deviation). */
function openDialogSelfServe() {
  const onImported = vi.fn();
  render(<PackingListUploadDialog open onOpenChange={() => {}} onImported={onImported} />);
  return { onImported };
}

function fileInput(): HTMLInputElement {
  return document.querySelector('input[type="file"]') as HTMLInputElement;
}

function xlsx(name = 'packing-list.xlsx'): File {
  return new File([new Uint8Array([1, 2, 3])], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

function pickFile(file = xlsx()) {
  fireEvent.change(fileInput(), { target: { files: [file] } });
  return file;
}

function testButton() {
  return screen.getByRole('button', { name: /^Test$/i });
}

function confirmButton() {
  return screen.getByRole('button', { name: 'Import packing list' });
}

function supplierSelect(): HTMLElement | null {
  return screen.queryByLabelText('Supplier');
}

beforeEach(() => {
  previewPackingList.mockReset().mockResolvedValue(PREVIEW);
  applyPackingList.mockReset();
  useFulfilmentSuppliers.mockReset().mockReturnValue({ data: [], isLoading: false });
});

describe('PackingListUploadDialog - the inherited two-step flow', () => {
  it('reads NOTHING when a file is picked: no request until Test is pressed', async () => {
    openDialog();

    pickFile();

    // Flushed on purpose: an immediate assertion would also pass against a dialog that
    // starts the read from an effect, which is the way read-on-drop comes back.
    await Promise.resolve();
    expect(previewPackingList).not.toHaveBeenCalled();
    expect(applyPackingList).not.toHaveBeenCalled();
    expect(testButton()).toBeEnabled();
  });

  it('Test is disabled until a file is chosen, and reads the file when pressed', async () => {
    openDialog();
    expect(testButton()).toBeDisabled();

    const file = pickFile();
    fireEvent.click(testButton());

    await waitFor(() =>
      expect(previewPackingList).toHaveBeenCalledWith(file, {
        supplierId: 'sup-1',
        currency: null,
      }),
    );
    // Test runs the `validate_only` read too - it writes nothing - and never the real apply.
    await waitFor(() =>
      expect(applyPackingList).toHaveBeenCalledWith(file, {
        supplierId: 'sup-1',
        currency: null,
        validateOnly: true,
      }),
    );
    expect(applyPackingList).toHaveBeenCalledTimes(1);
  });

  it('lists every container block, because a line count would hide that there are several',
    async () => {
      openDialog();
      pickFile();
      fireEvent.click(testButton());

      expect(await screen.findByText('TEMU1234567')).toBeInTheDocument();
      // A block whose container number has not been assigned yet says so rather than
      // rendering an empty row.
      expect(screen.getByText('No container number yet')).toBeInTheDocument();
      expect(screen.getByText(/is not in the catalogue/)).toBeInTheDocument();
    });

  it('refuses to confirm a file it could not read, and names the column', async () => {
    previewPackingList.mockResolvedValue({
      ...PREVIEW,
      ok: false,
      blocks: [],
      block_count: 0,
      missing_columns: ['container_no'],
    });
    openDialog();
    pickFile();
    fireEvent.click(testButton());

    expect(await screen.findByText(/no container_no column/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import packing list' })).toBeDisabled();
  });
});

describe('PackingListUploadDialog - whose lines these are', () => {
  it('names the factory the file will be filed under', () => {
    openDialog();

    expect(screen.getByText(/Uploading as KAILU HARDWARE FACTORY\./)).toBeInTheDocument();
  });

  it('offers no Supplier picker when the caller already supplies one', () => {
    openDialog();

    expect(supplierSelect()).not.toBeInTheDocument();
  });

  it('offers neither Test nor Confirm with no supplier, rather than sending an unowned file',
    () => {
      // An upload that does not say whose lines it is speaks for the WHOLE container, which
      // is how the other factory's lines used to disappear. The server refuses it with a 422;
      // this dialog does not get that far.
      openDialog(null, null);
      pickFile();

      expect(testButton()).toBeDisabled();
      expect(screen.getByRole('button', { name: 'Import packing list' })).toBeDisabled();
      expect(testButton()).toHaveAttribute('title', 'Choose a supplier first');
      expect(applyPackingList).not.toHaveBeenCalled();
      expect(previewPackingList).not.toHaveBeenCalled();
    });
});

describe('PackingListUploadDialog - Confirm, which is still synchronous here', () => {
  const RESULT = {
    shipments_created: 2,
    shipments_updated: 0,
    lines_skipped: 1,
    results: [
      {
        shipment_id: 'ship-1',
        shipment_number: 'SH-0001',
        container_no: 'TEMU1234567',
        lines: 7,
        created: true,
      },
      { shipment_number: 'SH-0002', container_no: null, lines: 4, created: true },
    ],
  };

  it('applies the file and renders what it created, in this dialog', async () => {
    // No job id and no upload drawer: this channel writes inside the request. Asserted as it
    // IS, not as the order-book channels are - the two behave differently and pretending
    // otherwise here would hide the day one of them changes.
    applyPackingList.mockResolvedValue(RESULT);
    const { onImported } = openDialog();
    const file = pickFile();

    fireEvent.click(screen.getByRole('button', { name: 'Import packing list' }));

    await waitFor(() =>
      expect(applyPackingList).toHaveBeenCalledWith(file, {
        supplierId: 'sup-1',
        currency: null,
      }),
    );
    expect(await screen.findByText(/Created 2 containers/)).toBeInTheDocument();
    expect(screen.getByText(/1 line skipped for having no product we hold/)).toBeInTheDocument();
    // Only the blocks that became a shipment are handed back: the caller opens them.
    expect(onImported).toHaveBeenCalledWith([
      { shipment_id: 'ship-1', shipment_number: 'SH-0001', container_no: 'TEMU1234567', lines: 7 },
    ]);
  });

  it('confirms a file that was never tested - Test is a tool, not a gate', async () => {
    applyPackingList.mockResolvedValue(RESULT);
    openDialog();
    pickFile();

    expect(screen.getByRole('button', { name: 'Import packing list' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Import packing list' }));

    await waitFor(() => expect(applyPackingList).toHaveBeenCalledTimes(1));
    expect(previewPackingList).not.toHaveBeenCalled();
  });

  it('shows the failure and leaves the dialog open when the apply is refused, 422 included',
    async () => {
      // The server's own message, whatever it says - including the 422 an upload with no
      // supplier earns - reaches the user through this one path.
      applyPackingList.mockRejectedValue(new Error('supplier_id is required'));
      openDialog();
      pickFile();

      fireEvent.click(screen.getByRole('button', { name: 'Import packing list' }));

      expect(await screen.findByText('supplier_id is required')).toBeInTheDocument();
    });

  it('shows the failure and leaves the dialog open when the apply is refused', async () => {
    applyPackingList.mockRejectedValue(new Error('Select a single company before uploading.'));
    openDialog();
    pickFile();

    fireEvent.click(screen.getByRole('button', { name: 'Import packing list' }));

    expect(
      await screen.findByText('Select a single company before uploading.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import packing list' })).toBeInTheDocument();
  });
});

describe('PackingListUploadDialog - the currency, asked for only when nothing else says', () => {
  function currencyField(): HTMLInputElement {
    return screen.getByLabelText('Currency') as HTMLInputElement;
  }

  it('sends no currency at all when the field is left empty', async () => {
    // Empty must not travel as an empty string: the file usually states its own currency
    // ("RMB", "单价(元)") and a blank form value would be a value that overrides nothing.
    applyPackingList.mockResolvedValue({ shipments_created: 1, shipments_updated: 0, lines_skipped: 0, results: [] });
    openDialog();
    const file = pickFile();

    fireEvent.click(screen.getByRole('button', { name: 'Import packing list' }));

    await waitFor(() =>
      expect(applyPackingList).toHaveBeenCalledWith(file, {
        supplierId: 'sup-1',
        currency: null,
      }),
    );
  });

  it('upper-cases what is typed and caps it at a three-letter code', () => {
    openDialog();

    fireEvent.change(currencyField(), { target: { value: 'cnyx' } });

    expect(currencyField().value).toBe('CNY');
  });

  it('carries the typed currency on the read, the test and the apply', async () => {
    // One mock for both jobs the endpoint does: `validate_only` answers with the standard
    // verdict, the real apply with what it wrote.
    applyPackingList.mockImplementation((_file: File, opts: { validateOnly?: boolean }) =>
      opts?.validateOnly
        ? new Promise((r) => setTimeout(() => r({ valid: true, errors: [], warnings: [], summary: {} }), 300))
        : Promise.resolve({
            shipments_created: 1,
            shipments_updated: 0,
            lines_skipped: 0,
            results: [],
          }),
    );
    openDialog();
    const file = pickFile();
    fireEvent.change(currencyField(), { target: { value: 'usd' } });

    fireEvent.click(testButton());
    await waitFor(() =>
      expect(previewPackingList).toHaveBeenCalledWith(file, {
        supplierId: 'sup-1',
        currency: 'USD',
      }),
    );
    await waitFor(() =>
      expect(applyPackingList).toHaveBeenCalledWith(file, {
        supplierId: 'sup-1',
        currency: 'USD',
        validateOnly: true,
      }),
    );

    // Confirm stays disabled until BOTH the read and the validate-only apply have
    // resolved (`canConfirm` is false while `testing`). Being called is not being
    // resolved: under CI load the click landed on a disabled button and was a no-op.
    const confirm = screen.getByRole('button', { name: 'Import packing list' });
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(applyPackingList).toHaveBeenLastCalledWith(file, {
        supplierId: 'sup-1',
        currency: 'USD',
      }),
    );
  });

  it('says which currency the read resolved, and where it came from', async () => {
    previewPackingList.mockResolvedValue({
      ...PREVIEW,
      priced_lines: 11,
      currency: 'CNY',
      currency_source: 'document',
    });
    openDialog();
    pickFile();

    fireEvent.click(testButton());

    expect(await screen.findByText(/Priced in CNY \(stated by the file\)/)).toBeInTheDocument();
  });

  it('says so when the file is priced and nothing states the money', async () => {
    previewPackingList.mockResolvedValue({
      ...PREVIEW,
      priced_lines: 11,
      currency: null,
      currency_source: 'none',
    });
    openDialog();
    pickFile();

    fireEvent.click(testButton());

    expect(
      await screen.findByText(/Nothing states which money these prices are in/),
    ).toBeInTheDocument();
  });

  it('says nothing about currency for a file with no prices in it', async () => {
    previewPackingList.mockResolvedValue({ ...PREVIEW, priced_lines: 0, currency: null, currency_source: 'none' });
    openDialog();
    pickFile();

    fireEvent.click(testButton());

    expect(await screen.findByText('TEMU1234567')).toBeInTheDocument();
    expect(screen.queryByText(/Priced in/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Nothing states which money/)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Self-serve supplier picker (no supplierId prop) - review round 1 S4
// ---------------------------------------------------------------------------

describe('PackingListUploadDialog - self-serve supplier picker (no supplierId prop)', () => {
  beforeEach(() => {
    useFulfilmentSuppliers.mockReturnValue({
      data: [{ value: 'sup-1', label: 'Kailu Hardware Factory' }],
      isLoading: false,
    });
  });

  it('offers a Supplier picker when no supplierId/supplierName is passed', () => {
    openDialogSelfServe();

    expect(supplierSelect()).toBeInTheDocument();
  });

  it('refuses Test and Confirm until a supplier is chosen', () => {
    openDialogSelfServe();
    pickFile();

    expect(testButton()).toBeDisabled();
    expect(confirmButton()).toBeDisabled();
    expect(testButton()).toHaveAttribute('title', 'Choose a supplier first');
  });

  it('enables Test and Confirm once a supplier is picked and a file chosen', () => {
    openDialogSelfServe();
    fireEvent.click(supplierSelect()!);
    fireEvent.click(screen.getByRole('option', { name: 'Kailu Hardware Factory' }));
    pickFile();

    expect(testButton()).toBeEnabled();
    expect(confirmButton()).toBeEnabled();
  });

  it('carries the picked supplier on Confirm', async () => {
    applyPackingList.mockResolvedValue({ shipments_created: 1, shipments_updated: 0, lines_skipped: 0, results: [] });
    openDialogSelfServe();
    fireEvent.click(supplierSelect()!);
    fireEvent.click(screen.getByRole('option', { name: 'Kailu Hardware Factory' }));
    const file = pickFile();

    fireEvent.click(confirmButton());

    await waitFor(() => expect(applyPackingList).toHaveBeenCalledTimes(1));
    expect(applyPackingList).toHaveBeenCalledWith(
      file,
      expect.objectContaining({ supplierId: 'sup-1' }),
    );
  });

  it('names the chosen supplier in the header once picked', () => {
    openDialogSelfServe();
    fireEvent.click(supplierSelect()!);
    fireEvent.click(screen.getByRole('option', { name: 'Kailu Hardware Factory' }));

    expect(screen.getByText(/Uploading as Kailu Hardware Factory/)).toBeInTheDocument();
  });
});
