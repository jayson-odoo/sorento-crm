/**
 * Upload supplier documents (R12-R14, purchasing consolidation batch, lane C; relocated
 * S3 - AC-C2/C3 - onto Proforma Invoices, its only remaining home): a proforma invoice, a
 * packing list, or both, in one multi-file dialog. This file replaces the single-file
 * "Upload packing list" dialog it used to pin - that flow's own contract
 * (`previewPackingList`/`applyPackingList`, single file, one Confirm) is gone, folded into
 * `previewSupplierDocuments`/`applySupplierDocuments`.
 *
 * Self-serve supplier picker (Deviations lane A; unchanged by this lane): the Proforma
 * Invoices page carries no persistent supplier filter to source `supplierId` from. The
 * dialog manages its own `internalSupplierId` when its `supplierId` prop is left
 * `undefined`; a caller that passes an explicit `supplierId` (even `null`) keeps deciding
 * it, unchanged.
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

const previewSupplierDocuments = vi.fn();
const applySupplierDocuments = vi.fn();

const getFulfilmentSuppliers = vi.fn(
  async (): Promise<{ value: string; label: string }[]> => [],
);

vi.mock('@/app/(protected)/scm/services/fulfilmentService', () => ({
  previewSupplierDocuments: (...a: unknown[]) => previewSupplierDocuments(...a),
  applySupplierDocuments: (...a: unknown[]) => applySupplierDocuments(...a),
  // Server-searched supplier picker (fix round 1, item 17): the dialog fetches through the
  // service with the typed query, instead of holding an unparameterised top-100 list.
  getFulfilmentSuppliers: (...a: unknown[]) => getFulfilmentSuppliers(...(a as [])),
}));

const createImportFieldAlias = vi.fn();
const listImportFieldAliasFields = vi.fn();

vi.mock('@/app/(protected)/system-management/import-field-aliases/services/importFieldAliasService', () => ({
  createImportFieldAlias: (...a: unknown[]) => createImportFieldAlias(...a),
  listImportFieldAliasFields: (...a: unknown[]) => listImportFieldAliasFields(...a),
}));

vi.mock('@/app/(protected)/scm/services/proformaInvoiceService', () => ({
  listProformaInvoices: vi.fn(async () => ({ data: [], total: 0 })),
}));

import { SupplierDocumentsUploadDialog } from './SupplierDocumentsUploadDialog';

const PI_FILE_PREVIEW = {
  name: 'invoice.xls',
  kind: 'proforma_invoice',
  blocks: [
    {
      container_no: 'WHSU6243088',
      seal_no: 'WHA4528193',
      cartons: null,
      cbm_total: null,
      amount: 87710,
      line_count: 3,
      note_count: 0,
    },
    {
      container_no: 'WHSU6356079',
      seal_no: 'WHA4528173',
      cartons: null,
      cbm_total: null,
      amount: 122182,
      line_count: 2,
      note_count: 0,
    },
  ],
  header: {
    pi_number: '2026JXL0726',
    invoice_date: '2026-07-26',
    consignee: 'SORENTO SDN BHD',
    shipper: 'CHAOZHOU CHAOAN JIEXIA CERAMICS INDUSTRY CO.,LTD.',
    so_ref: null,
  },
  unmatched: [],
  errors: [],
};

const PL_FILE_PREVIEW = {
  name: 'packing-list.xls',
  kind: 'packing_list',
  blocks: [
    {
      container_no: 'WHSU6243088',
      seal_no: 'WHA4528193',
      cartons: 792,
      cbm_total: 49.41,
      amount: null,
      line_count: 4,
      note_count: 4,
    },
    {
      container_no: 'WHSU6356079',
      seal_no: 'WHA4528173',
      cartons: 1071,
      cbm_total: 68.85,
      amount: null,
      line_count: 3,
      note_count: 0,
    },
  ],
  header: {
    pi_number: null,
    invoice_date: null,
    consignee: 'SORENTO SDN BHD',
    shipper: 'CHAOZHOU CHAOAN JIEXIA CERAMICS INDUSTRY CO.,LTD',
    so_ref: null,
  },
  unmatched: ['NOPE-1'],
  errors: [],
};

const PREVIEW = {
  files: [PI_FILE_PREVIEW, PL_FILE_PREVIEW],
  price_matches: [
    { container_no: 'WHSU6243088', pi_number: '2026JXL0726', matched_lines: 2, unmatched_lines: 2 },
  ],
};

function openDialog(
  supplierId: string | null = 'sup-1',
  supplierName: string | null = 'Jiexia Ceramics',
) {
  const onImported = vi.fn();
  render(
    <SupplierDocumentsUploadDialog
      open
      onOpenChange={() => {}}
      supplierId={supplierId}
      supplierName={supplierName}
      onImported={onImported}
    />,
  );
  return { onImported };
}

function openDialogSelfServe() {
  const onImported = vi.fn();
  render(<SupplierDocumentsUploadDialog open onOpenChange={() => {}} onImported={onImported} />);
  return { onImported };
}

function fileInput(): HTMLInputElement {
  return document.querySelector('input[type="file"]') as HTMLInputElement;
}

function xlsx(name: string): File {
  return new File([new Uint8Array([1, 2, 3])], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

function pickFiles(files: File[]) {
  fireEvent.change(fileInput(), { target: { files } });
  return files;
}

function testButton() {
  return screen.getByRole('button', { name: /^Test$/i });
}

function supplierSelect(): HTMLElement | null {
  return screen.queryByLabelText('Supplier');
}

beforeEach(() => {
  previewSupplierDocuments.mockReset().mockResolvedValue(PREVIEW);
  applySupplierDocuments.mockReset();
  getFulfilmentSuppliers.mockReset().mockResolvedValue([]);
  createImportFieldAlias.mockReset();
  listImportFieldAliasFields.mockReset().mockResolvedValue([]);
});

describe('SupplierDocumentsUploadDialog - the dialog now reads "Upload supplier documents"', () => {
  it('titles itself for both documents, not just packing lists', () => {
    openDialog();

    expect(screen.getByText('Upload supplier documents')).toBeInTheDocument();
  });

  it('accepts several files at once', () => {
    openDialog();

    const files = pickFiles([xlsx('invoice.xls'), xlsx('packing-list.xls')]);

    expect(fileInput().files).toHaveLength(2);
    expect(files).toHaveLength(2);
  });
});

describe('SupplierDocumentsUploadDialog - Test reads every file and classifies it', () => {
  it('is disabled until a file is chosen', () => {
    openDialog();

    expect(testButton()).toBeDisabled();
  });

  it('reads the files and shows what each one is', async () => {
    openDialog();
    pickFiles([xlsx('invoice.xls'), xlsx('packing-list.xls')]);
    fireEvent.click(testButton());

    await waitFor(() =>
      expect(previewSupplierDocuments).toHaveBeenCalledWith(
        [expect.any(File), expect.any(File)],
        { supplierId: 'sup-1', currency: null, attachTo: undefined, attachToBlocks: [] },
      ),
    );

    expect(await screen.findByText('Proforma invoice')).toBeInTheDocument();
    expect(screen.getByText('Packing list')).toBeInTheDocument();
    expect(screen.getByText(/2026JXL0726/)).toBeInTheDocument();
    expect(screen.getByText(/not in the catalogue/)).toBeInTheDocument();
  });

  it('names an unreadable file and disables Confirm', async () => {
    previewSupplierDocuments.mockResolvedValue({
      files: [
        {
          name: 'mystery.xls',
          kind: 'unreadable',
          blocks: [],
          header: { pi_number: null, invoice_date: null, consignee: null, shipper: null, so_ref: null },
          unmatched: [],
          errors: ['Could not tell whether this is a proforma invoice or a packing list.'],
        },
      ],
      price_matches: [],
    });
    openDialog();
    pickFiles([xlsx('mystery.xls')]);
    fireEvent.click(testButton());

    expect(await screen.findByText('mystery.xls')).toBeInTheDocument();
    expect(
      screen.getByText('Could not tell whether this is a proforma invoice or a packing list.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Confirm/ })).toBeDisabled();
  });
});

describe('SupplierDocumentsUploadDialog - Confirm', () => {
  const RESULT = {
    proforma_invoice_ids: ['pi-1', 'pi-2'],
    shipment_ids: ['ship-1', 'ship-2'],
    links_written: 2,
    attachment_ids: ['att-1', 'att-2'],
  };

  it('names how many invoices and draft packing lists it would create, once tested', async () => {
    openDialog();
    pickFiles([xlsx('invoice.xls'), xlsx('packing-list.xls')]);
    fireEvent.click(testButton());

    expect(await screen.findByRole('button', { name: /Confirm: 2 invoices, 2 draft packing lists/ })).toBeInTheDocument();
  });

  it('applies every file and reports what it created', async () => {
    applySupplierDocuments.mockResolvedValue(RESULT);
    const { onImported } = openDialog();
    const files = pickFiles([xlsx('invoice.xls'), xlsx('packing-list.xls')]);

    fireEvent.click(screen.getByRole('button', { name: /^Confirm/ }));

    await waitFor(() =>
      expect(applySupplierDocuments).toHaveBeenCalledWith(files, {
        supplierId: 'sup-1',
        currency: null,
        translations: [],
        attachTo: undefined,
        attachToBlocks: [],
      }),
    );
    expect(await screen.findByText(/Created 2 invoices and 2 draft packing lists/)).toBeInTheDocument();
    expect(screen.getByText(/2 lines priced from an invoice/)).toBeInTheDocument();
    expect(onImported).toHaveBeenCalledWith(RESULT);
  });

  it('confirms without ever pressing Test - Test is a tool, not a gate', async () => {
    applySupplierDocuments.mockResolvedValue(RESULT);
    openDialog();
    pickFiles([xlsx('invoice.xls')]);

    expect(screen.getByRole('button', { name: /^Confirm/ })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: /^Confirm/ }));

    await waitFor(() => expect(applySupplierDocuments).toHaveBeenCalledTimes(1));
    expect(previewSupplierDocuments).not.toHaveBeenCalled();
  });

  it('shows the server refusal and leaves the dialog open', async () => {
    applySupplierDocuments.mockRejectedValue(new Error('supplier_id is required'));
    openDialog();
    pickFiles([xlsx('invoice.xls')]);

    fireEvent.click(screen.getByRole('button', { name: /^Confirm/ }));

    expect(await screen.findByText('supplier_id is required')).toBeInTheDocument();
  });
});

describe('SupplierDocumentsUploadDialog - translations, English beside the Chinese (R16)', () => {
  const PL_WITH_TRANSLATIONS = {
    name: 'packing-list.xls',
    kind: 'packing_list',
    blocks: [
      {
        container_no: 'WHSU6243088',
        seal_no: 'WHA4528193',
        cartons: 792,
        cbm_total: 49.41,
        amount: null,
        line_count: 4,
        note_count: 1,
        lines: [
          {
            item_code: 'NOPE-1',
            matched: false,
            description: '座厕 S-250出水 对冲',
            description_en: null,
            description_en_source: null,
            remark: null,
            remark_en: null,
            remark_en_source: null,
          },
        ],
        notes: [{ text: '纸箱：2个', text_en: 'Carton: 2', text_en_source: 'ai' }],
      },
    ],
    header: { pi_number: null, invoice_date: null, consignee: null, shipper: null, so_ref: null },
    unmatched: ['NOPE-1'],
    errors: [],
    footer_note: null,
  };

  it('shows the English beside the Chinese, with a source badge', async () => {
    previewSupplierDocuments.mockResolvedValue({ files: [PL_WITH_TRANSLATIONS], price_matches: [] });
    openDialog();
    pickFiles([xlsx('packing-list.xls')]);
    fireEvent.click(testButton());

    await screen.findByText('座厕 S-250出水 对冲');
    expect(screen.getByText('纸箱：2个')).toBeInTheDocument();
    expect(screen.getByText('ai')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Carton: 2')).toBeInTheDocument();
  });

  it('editing a cell marks it manual and sends the edit on Confirm', async () => {
    previewSupplierDocuments.mockResolvedValue({ files: [PL_WITH_TRANSLATIONS], price_matches: [] });
    applySupplierDocuments.mockResolvedValue({
      proforma_invoice_ids: [],
      shipment_ids: ['ship-1'],
      links_written: 0,
      attachment_ids: [],
    });
    openDialog();
    const files = pickFiles([xlsx('packing-list.xls')]);
    fireEvent.click(testButton());

    await screen.findByText('座厕 S-250出水 对冲');
    const [descriptionInput] = screen.getAllByPlaceholderText('English');
    fireEvent.change(descriptionInput, { target: { value: 'Toilet bowl S-250' } });
    expect(screen.getByText('manual')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Confirm/ }));

    await waitFor(() =>
      expect(applySupplierDocuments).toHaveBeenCalledWith(files, {
        supplierId: 'sup-1',
        currency: null,
        translations: [{ source_text: '座厕 S-250出水 对冲', target_text: 'Toilet bowl S-250' }],
        attachTo: undefined,
        attachToBlocks: [],
      }),
    );
  });

  it('renders both rows when two blocks state the identical Chinese phrase (key collision, review round 1)', async () => {
    // Two containers, the SAME line description on each - a real Jiexia shape. Without
    // a block-index-prefixed React key, both rows shared one identity and only one
    // English input rendered.
    const line = (descriptionEn: string | null) => ({
      item_code: 'NOPE-1',
      matched: false,
      description: '座厕 S-250出水 对冲',
      description_en: descriptionEn,
      description_en_source: descriptionEn ? 'ai' : null,
      remark: null,
      remark_en: null,
      remark_en_source: null,
    });
    const twoBlocksSamePhrase = {
      name: 'packing-list.xls',
      kind: 'packing_list',
      blocks: [
        {
          container_no: 'WHSU6243088', seal_no: null, cartons: null, cbm_total: null,
          amount: null, line_count: 1, note_count: 0,
          lines: [line('Toilet bowl S-250 (block 1)')], notes: [],
        },
        {
          container_no: 'WHSU6356079', seal_no: null, cartons: null, cbm_total: null,
          amount: null, line_count: 1, note_count: 0,
          lines: [line('Toilet bowl S-250 (block 2)')], notes: [],
        },
      ],
      header: { pi_number: null, invoice_date: null, consignee: null, shipper: null, so_ref: null },
      unmatched: ['NOPE-1'],
      errors: [],
      footer_note: null,
    };
    previewSupplierDocuments.mockResolvedValue({ files: [twoBlocksSamePhrase], price_matches: [] });
    openDialog();
    pickFiles([xlsx('packing-list.xls')]);
    fireEvent.click(testButton());

    await screen.findAllByText('座厕 S-250出水 对冲');

    expect(screen.getAllByText('座厕 S-250出水 对冲')).toHaveLength(2);
    expect(screen.getByDisplayValue('Toilet bowl S-250 (block 1)')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Toilet bowl S-250 (block 2)')).toBeInTheDocument();
  });
});

describe('SupplierDocumentsUploadDialog - self-serve supplier picker (no supplierId prop)', () => {
  beforeEach(() => {
    getFulfilmentSuppliers.mockResolvedValue([
      { value: 'sup-1', label: 'Kailu Hardware Factory' },
    ]);
  });

  it('offers a Supplier picker when no supplierId/supplierName is passed', () => {
    openDialogSelfServe();

    expect(supplierSelect()).toBeInTheDocument();
  });

  it('offers no Supplier picker when the caller already supplies one', () => {
    openDialog();

    expect(supplierSelect()).not.toBeInTheDocument();
  });

  it('refuses Test and Confirm until a supplier is chosen', () => {
    openDialogSelfServe();
    pickFiles([xlsx('invoice.xls')]);

    expect(testButton()).toBeDisabled();
    expect(screen.getByRole('button', { name: /^Confirm/ })).toBeDisabled();
  });

  it('names the chosen supplier in the header once picked', async () => {
    openDialogSelfServe();
    fireEvent.click(supplierSelect()!);
    // Fetched, not held: the options arrive from the server search (item 17).
    fireEvent.click(await screen.findByRole('option', { name: 'Kailu Hardware Factory' }));

    expect(await screen.findByText(/Uploading as Kailu Hardware Factory/)).toBeInTheDocument();
  });
});

describe('SupplierDocumentsUploadDialog - the currency, asked for only when nothing else says', () => {
  it('sends no currency at all when the field is left empty', async () => {
    applySupplierDocuments.mockResolvedValue({
      proforma_invoice_ids: [], shipment_ids: [], links_written: 0, attachment_ids: [],
    });
    openDialog();
    const files = pickFiles([xlsx('invoice.xls')]);

    fireEvent.click(screen.getByRole('button', { name: /^Confirm/ }));

    await waitFor(() =>
      expect(applySupplierDocuments).toHaveBeenCalledWith(files, {
        supplierId: 'sup-1',
        currency: null,
        translations: [],
        attachTo: undefined,
        attachToBlocks: [],
      }),
    );
  });

  it('upper-cases what is typed and caps it at a three-letter code', () => {
    openDialog();

    fireEvent.change(screen.getByLabelText('Currency'), { target: { value: 'cnyx' } });

    expect((screen.getByLabelText('Currency') as HTMLInputElement).value).toBe('CNY');
  });
});

describe('SupplierDocumentsUploadDialog - server-resolved Attaches-to per block (AC-B13, fix round 1 items 4/18)', () => {
  it('prefills Attaches-to from the server resolution and enables Confirm (how = date)', async () => {
    previewSupplierDocuments.mockResolvedValue({
      files: [
        {
          ...PL_FILE_PREVIEW,
          blocks: [PL_FILE_PREVIEW.blocks[0]],
          packing_attach: [
            {
              block_index: 0,
              container_no: null,
              // The server's own answer (`resolve_attach`), never guessed by this dialog -
              // `how: 'date'` is the same-date fallback order, the fourth of the four.
              attach_to: { id: 'pi-1', pi_number: 'PI-2609-001', supplier_ref: null, how: 'date' },
              refusal: null,
            },
          ],
        },
      ],
      price_matches: [],
    });
    openDialog();
    pickFiles([xlsx('packing-list.xls')]);
    fireEvent.click(testButton());

    // Shown WITHOUT the operator picking anything - the SearchableSelect's own
    // trigger text is the server's `attach_to` label.
    expect(await screen.findByText('PI-2609-001')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Confirm/ })).toBeEnabled();
  });

  it('shows the blocks own refusal inline and disables Confirm (AC-B16)', async () => {
    previewSupplierDocuments.mockResolvedValue({
      files: [
        {
          ...PL_FILE_PREVIEW,
          blocks: [PL_FILE_PREVIEW.blocks[0]],
          packing_attach: [
            {
              block_index: 0,
              container_no: null,
              attach_to: null,
              refusal: {
                code: 'proforma_invoice_required',
                message:
                  'No proforma invoice on file for Kailu matches this packing list dated 2026-07-30.',
              },
            },
          ],
        },
      ],
      price_matches: [],
    });
    openDialog();
    pickFiles([xlsx('packing-list.xls')]);
    fireEvent.click(testButton());

    expect(
      await screen.findByText(/No proforma invoice on file for Kailu/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Confirm/ })).toBeDisabled();
  });
});

describe('SupplierDocumentsUploadDialog - "Map to..." re-runs Test for that file automatically (AC-E4, ruling 20)', () => {
  it('writes the alias, then re-previews the SAME file (not an optimistic hide of the chip)', async () => {
    const withUnmapped = {
      files: [{ ...PI_FILE_PREVIEW, name: 'jinbaichuan.xlsx', unmapped_headers: ['尺寸（mm）'] }],
      price_matches: [],
    };
    const afterMapping = {
      files: [{ ...PI_FILE_PREVIEW, name: 'jinbaichuan.xlsx', unmapped_headers: [] }],
      price_matches: [],
    };
    previewSupplierDocuments.mockReset();
    previewSupplierDocuments.mockResolvedValueOnce(withUnmapped).mockResolvedValueOnce(afterMapping);
    listImportFieldAliasFields.mockResolvedValue([{ field: 'carton_dims', label: 'Carton dims' }]);
    createImportFieldAlias.mockResolvedValue({});

    openDialog();
    pickFiles([xlsx('jinbaichuan.xlsx')]);
    fireEvent.click(testButton());

    expect(await screen.findByText('尺寸（mm）')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Map to...' }));

    // The field list is server-sourced (E1), not hand-typed.
    expect(await screen.findByText('Choose a field')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', { name: 'Carton dims' }));

    await waitFor(() =>
      expect(createImportFieldAlias).toHaveBeenCalledWith({
        doc_type: 'packing_list',
        field: 'carton_dims',
        alias: '尺寸（mm）',
      }),
    );
    // The SECOND preview call, for the SAME file - the re-run this AC is about, not just
    // the mapping write.
    await waitFor(() => expect(previewSupplierDocuments).toHaveBeenCalledTimes(2));
    expect(previewSupplierDocuments.mock.calls[1][0][0].name).toBe('jinbaichuan.xlsx');
  });
});
