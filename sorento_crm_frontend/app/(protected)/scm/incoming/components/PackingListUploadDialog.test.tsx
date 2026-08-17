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

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const previewPackingList = vi.fn();
const applyPackingList = vi.fn();

vi.mock('../../services/fulfilmentService', () => ({
  previewPackingList: (...a: unknown[]) => previewPackingList(...a),
  applyPackingList: (...a: unknown[]) => applyPackingList(...a),
}));

vi.mock('../../reorder/services/outstandingImportService', () => ({
  getOutstandingUploadConfig: async () => ({ allowed_extensions: ['.xlsx', '.xls'] }),
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

beforeEach(() => {
  previewPackingList.mockReset().mockResolvedValue(PREVIEW);
  applyPackingList.mockReset();
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

    await waitFor(() => expect(previewPackingList).toHaveBeenCalledWith(file));
    // Test runs the `validate_only` read too - it writes nothing - and never the real apply.
    await waitFor(() =>
      expect(applyPackingList).toHaveBeenCalledWith(file, {
        supplierId: 'sup-1',
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
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
  });
});

describe('PackingListUploadDialog - whose lines these are', () => {
  it('names the factory the file will be filed under', () => {
    openDialog();

    expect(screen.getByText(/Uploading as KAILU HARDWARE FACTORY\./)).toBeInTheDocument();
  });

  it('offers neither Test nor Confirm with no supplier, rather than sending an unowned file',
    () => {
      // An upload that does not say whose lines it is speaks for the WHOLE container, which
      // is how the other factory's lines used to disappear. The server refuses it with a 422;
      // this dialog does not get that far.
      openDialog(null, null);
      pickFile();

      expect(testButton()).toBeDisabled();
      expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
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

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() =>
      expect(applyPackingList).toHaveBeenCalledWith(file, { supplierId: 'sup-1' }),
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

    expect(screen.getByRole('button', { name: 'Confirm' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

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

      fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

      expect(await screen.findByText('supplier_id is required')).toBeInTheDocument();
    });

  it('shows the failure and leaves the dialog open when the apply is refused', async () => {
    applyPackingList.mockRejectedValue(new Error('Select a single company before uploading.'));
    openDialog();
    pickFile();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    expect(
      await screen.findByText('Select a single company before uploading.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeInTheDocument();
  });
});
