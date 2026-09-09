'use client';

import { useEffect, useState } from 'react';
import { LoaderCircle, TestTube, TriangleAlert } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { FileDropzone } from '@/components/common/FileDropzone';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { MAX_SIZE_MB } from '@/app/(protected)/scm/reorder/hooks/useTwoStepUpload';
import { EM_DASH, fmtInt } from '@/app/(protected)/scm/lib/format';
import {
  applySupplierDocuments,
  getFulfilmentSuppliers,
  previewSupplierDocuments,
  type SupplierDocumentBlockAttach,
  type SupplierDocumentFilePreview,
  type SupplierDocumentsApplyResult,
  type SupplierDocumentsPreview,
  type SupplierDocumentTextItem,
  type SupplierDocumentTranslation,
} from '@/app/(protected)/scm/services/fulfilmentService';
import { listProformaInvoices } from '@/app/(protected)/scm/services/proformaInvoiceService';
import {
  createImportFieldAlias,
  type ImportFieldAliasDocType,
} from '@/app/(protected)/system-management/import-field-aliases/services/importFieldAliasService';

/**
 * Upload supplier documents: a proforma invoice, a packing list, or both at once (R12-R14,
 * purchasing consolidation batch, lane C; relocated here S3, AC-C2/C3).
 *
 * ONE dialog for both documents rather than two, because the same container shows up in
 * both: the invoice prices what the packing list ships, and reading them together is what
 * lets the packing rows land matched to the invoice line they price (S2, later). Proforma
 * Invoices is the dialog's only remaining home - the Packing Lists page has no
 * supplier-document upload of its own (S3): a packing list is born by convert or by hand.
 *
 * Each file is read on Test and classified server-side by its own title cell; the operator
 * never says which kind a file is. Confirm applies every proforma invoice first, then every
 * packing list, whose rows land on the invoice that prices them.
 *
 * Attach a packing list to a proforma invoice (S2, AC-B5/B10/B13): one **Attaches to** line
 * per packing-list BLOCK, answered by the server (`resolve_attach`) and named by its
 * container when the file carries more than one. Changing it posts the pick back and
 * re-runs Test for that file, so the answer on screen is always the server's. Locked when
 * `attachTo` is passed (opened from a PI's own "Attach packing list" button). A block with
 * no invoice to attach to shows its refusal inline (AC-B16) and Confirm stays disabled
 * while any block is refused.
 *
 * Self-serve supplier picker (Deviations lane A, purchasing consolidation batch; carried
 * over unchanged by this lane): this page carries no persistent supplier filter to source
 * `supplierId` from. The dialog manages its own `internalSupplierId` when `supplierId` is
 * left `undefined`; every caller that passes an explicit `supplierId` (even `null`) keeps
 * deciding it, unchanged.
 */

const KIND_LABEL: Record<string, string> = {
  proforma_invoice: 'Proforma invoice',
  packing_list: 'Packing list',
  combined: 'Combined',
  unreadable: 'Unreadable',
};

function blockSummary(f: SupplierDocumentFilePreview): string {
  if (!f.blocks.length) return EM_DASH;
  return f.blocks
    .map((b) => {
      const parts = [
        b.container_no || 'no container',
        b.seal_no ? `seal ${b.seal_no}` : null,
        b.cartons != null ? `${fmtInt(b.cartons)} ctn` : null,
        b.cbm_total != null ? `${b.cbm_total} cbm` : null,
        b.amount != null ? fmtInt(b.amount) : null,
      ].filter(Boolean);
      return parts.join(' · ');
    })
    .join('; ');
}

function linesSummary(f: SupplierDocumentFilePreview): string {
  const lines = f.blocks.reduce((sum, b) => sum + b.line_count, 0);
  const notes = f.blocks.reduce((sum, b) => sum + b.note_count, 0);
  return notes > 0 ? `${fmtInt(lines)} (+ ${fmtInt(notes)} notes)` : fmtInt(lines);
}

function headerSummary(f: SupplierDocumentFilePreview): string {
  const parts = [f.header.pi_number, f.header.invoice_date, f.header.consignee].filter(Boolean);
  return parts.length ? parts.join(' · ') : EM_DASH;
}

/** One phrase in a file's preview worth translating (R16): a line's description, a
 *  line's remark, a block note, or the file's footer - flattened to one shape so the
 *  dialog renders one list rather than four. `key` is the SOURCE (Chinese) text, also
 *  the translation memory's own key - kept SHARED across blocks on purpose (the same
 *  phrase in two blocks is the same memory row, and editing one edits both). `reactKey`
 *  is separate and prefixed with the block index: two blocks stating the identical
 *  Chinese phrase (a real Jiexia shape - "座厕 S-250出水 对冲" repeats) would otherwise
 *  hand React two list items with the SAME key, which is a silent "same identity"
 *  promise React does not keep (review round 1, nit). */
function translationItems(
  f: SupplierDocumentFilePreview,
): { key: string; reactKey: string; item: SupplierDocumentTextItem }[] {
  const out: { key: string; reactKey: string; item: SupplierDocumentTextItem }[] = [];
  f.blocks.forEach((b, bi) => {
    // Optional-chained: a preview read before Phase 2 backend wiring (or a stale test
    // fixture) may not carry `lines`/`notes` at all.
    (b.lines ?? []).forEach((ln, li) => {
      if (ln.description) {
        out.push({
          key: ln.description,
          reactKey: `${bi}-${li}-description`,
          item: { text: ln.description, text_en: ln.description_en, text_en_source: ln.description_en_source },
        });
      }
      if (ln.remark) {
        out.push({
          key: ln.remark,
          reactKey: `${bi}-${li}-remark`,
          item: { text: ln.remark, text_en: ln.remark_en, text_en_source: ln.remark_en_source },
        });
      }
    });
    (b.notes ?? []).forEach((note, ni) => out.push({ key: note.text, reactKey: `${bi}-note-${ni}`, item: note }));
  });
  if (f.footer_note) out.push({ key: f.footer_note.text, reactKey: 'footer', item: f.footer_note });
  return out;
}

/** One editable row: the Chinese on the left, an English input on the right, a
 *  `manual`/`ai` badge once something has translated it. Editing marks the cell
 *  `manual` (R16) - the badge follows the edit immediately, before Confirm is ever
 *  pressed, so the operator sees their own correction take effect. */
function TranslationRow({
  item,
  value,
  onChange,
  disabled,
}: {
  item: SupplierDocumentTextItem;
  value: string;
  onChange: (next: string) => void;
  disabled: boolean;
}) {
  const edited = value !== (item.text_en ?? '');
  const source = edited && value ? 'manual' : item.text_en_source;
  return (
    <div className="flex items-center gap-2">
      <span className="min-w-0 flex-1 truncate text-2xs text-muted-foreground" title={item.text}>
        {item.text}
      </span>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="English"
        className="h-7 flex-1 text-2xs"
        disabled={disabled}
      />
      {source ? (
        <Badge
          variant={source === 'manual' ? 'primary' : 'secondary'}
          appearance="light"
          size="sm"
          className="shrink-0"
        >
          {source === 'manual' ? 'manual' : 'ai'}
        </Badge>
      ) : (
        <span className="w-10 shrink-0" />
      )}
    </div>
  );
}

/** Rough figures for the Confirm label - block counts, split by what each file classified
 *  as. A `combined` file's blocks mix both kinds (rare in practice, neither real fixture
 *  produces one), so it is counted toward both rather than not counted at all. */
function confirmCounts(preview: SupplierDocumentsPreview | null): { invoices: number; packingLists: number } {
  if (!preview) return { invoices: 0, packingLists: 0 };
  let invoices = 0;
  let packingLists = 0;
  for (const f of preview.files) {
    if (f.kind === 'proforma_invoice' || f.kind === 'combined') invoices += f.blocks.length;
    if (f.kind === 'packing_list' || f.kind === 'combined') packingLists += f.blocks.length;
  }
  return { invoices, packingLists };
}

/** The reader assumed when a preview does not say which one missed a header - the shape
 *  the plan measured the unmapped headers on (Jinbaichuan's `尺寸（mm）`, `孔距`,
 *  `认证编码`). A current backend says (`unmapped_header_doc_types`, ruling 24). */
const IMPORT_DOC_TYPE: ImportFieldAliasDocType = 'packing_list';

/** Which readers could not place this header on this file (ruling 24). */
function docTypesFor(
  file: SupplierDocumentFilePreview,
  header: string,
): ImportFieldAliasDocType[] {
  const stated = file.unmapped_header_doc_types?.[header];
  return stated?.length ? (stated as ImportFieldAliasDocType[]) : [IMPORT_DOC_TYPE];
}

/** Ours and theirs, in that order - the operator recognises the supplier's own reference,
 *  and our number is what the invoice is filed under. */
function invoiceLabel(piNumber: string | null, supplierRef: string | null): string {
  if (!piNumber) return supplierRef ?? '';
  return supplierRef ? `${piNumber} · ${supplierRef}` : piNumber;
}

export function SupplierDocumentsUploadDialog({
  open,
  onOpenChange,
  supplierId: supplierIdProp,
  supplierName: supplierNameProp,
  attachTo,
  onImported,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  /**
   * Omit both `supplierId` and `supplierName` to let the dialog ask for the supplier itself
   * (the Proforma Invoices page carries no persistent supplier context to hand it one).
   * Passing `supplierId` (even `null`) keeps that caller in control, unchanged.
   */
  supplierId?: string | null;
  /** Shown in the header so the factory the lines will be filed under is never a guess. */
  supplierName?: string | null;
  /** Opened from a PI's own "Attach packing list" (AC-B10): every packing-list file's
   *  Attaches-to locks to this invoice rather than resolving one. */
  attachTo?: { id: string; pi_number: string } | null;
  onImported?: (result: SupplierDocumentsApplyResult) => void;
}) {
  const selfServe = supplierIdProp === undefined;
  const [internalSupplier, setInternalSupplier] = useState<{ value: string; label: string } | null>(
    null,
  );
  const supplierId = selfServe ? (internalSupplier?.value ?? null) : (supplierIdProp ?? null);
  const supplierName = selfServe ? (internalSupplier?.label ?? null) : (supplierNameProp ?? null);

  const [files, setFiles] = useState<File[]>([]);
  const [currency, setCurrency] = useState('');
  const trimmedCurrency = currency.trim() || null;

  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [preview, setPreview] = useState<SupplierDocumentsPreview | null>(null);
  const [result, setResult] = useState<SupplierDocumentsApplyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Every translation cell the operator has touched this preview (R16), keyed by the
  // SOURCE (Chinese) text - the same key `translationItems` reads off the preview and
  // `translate_service`'s memory reads off the database. Only touched cells are sent on
  // Confirm; an untouched one keeps whatever the memory/AI already said.
  const [translationEdits, setTranslationEdits] = useState<Record<string, string>>({});
  // What the operator picked on a packing-list block's own Attaches-to select (AC-B13),
  // keyed `file name::block index`. Sent back with the next Test and with Confirm, so the
  // SERVER resolves attachment either way - this only records the override.
  const [attachPicks, setAttachPicks] = useState<Record<string, string>>({});
  // Which file is being re-read after a "Map to..." (AC-E4) or an Attaches-to change.
  const [repreviewing, setRepreviewing] = useState<string | null>(null);

  // Cleared on every open, like every other upload dialog here: a file, a verdict or a
  // currency left over from the last upload must never silently apply to the next one.
  useEffect(() => {
    if (!open) return;
    setFiles([]);
    setCurrency('');
    setPreview(null);
    setResult(null);
    setError(null);
    setPreviewing(false);
    setApplying(false);
    setTranslationEdits({});
    setAttachPicks({});
    setRepreviewing(null);
    if (selfServe) setInternalSupplier(null);
  }, [open, selfServe]);

  /** The supplier's invoices for a block's Attaches-to picker - server-searched, so a
   *  supplier with a year of invoices is still reachable by typing. */
  const fetchInvoiceOptions = async (query: string) => {
    if (!supplierId) return [];
    const res = await listProformaInvoices({ supplierId, query, limit: 25 });
    return res.data.map((pi) => ({
      value: pi.id,
      label: invoiceLabel(pi.pi_number, pi.supplier_ref ?? null),
    }));
  };

  /** Every per-block override this dialog is holding, in the shape both routes take. */
  const blockAttachments = (only?: string): SupplierDocumentBlockAttach[] =>
    Object.entries(attachPicks)
      .map(([key, invoiceId]) => {
        const at = key.lastIndexOf('::');
        return { file: key.slice(0, at), block_index: Number(key.slice(at + 2)), invoice_id: invoiceId };
      })
      .filter((entry) => !only || entry.file === only);

  const runTest = async () => {
    if (!files.length || !supplierId) return;
    setPreviewing(true);
    setError(null);
    try {
      const read = await previewSupplierDocuments(files, {
        supplierId,
        currency: trimmedCurrency,
        attachTo,
        attachToBlocks: blockAttachments(),
      });
      setPreview(read);
      setTranslationEdits({});
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to read the files.');
    } finally {
      setPreviewing(false);
    }
  };

  /**
   * Test again for ONE file (AC-E4, AC-B13) - after a header is mapped, and after an
   * Attaches-to pick. The file is re-READ, so a mapping that names a real column fills it
   * in and the chip goes because the server no longer reports it, not because this screen
   * decided to hide it. The other files' rows, and every translation the operator has
   * typed, are left exactly as they are.
   */
  const repreviewFile = async (fileName: string, picks: SupplierDocumentBlockAttach[]) => {
    const file = files.find((f) => f.name === fileName);
    if (!file || !supplierId) return;
    setRepreviewing(fileName);
    setError(null);
    try {
      const read = await previewSupplierDocuments([file], {
        supplierId,
        currency: trimmedCurrency,
        attachTo,
        attachToBlocks: picks,
      });
      const fresh = read.files[0];
      if (!fresh) return;
      setPreview((prev) =>
        prev
          ? { ...prev, files: prev.files.map((f) => (f.name === fileName ? fresh : f)) }
          : prev,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to read that file again.');
    } finally {
      setRepreviewing(null);
    }
  };

  /** The Attaches-to select on one block: record the pick and let the SERVER answer with
   *  it (`how: 'explicit'`), rather than painting the choice on locally. */
  const pickAttachTo = (fileName: string, blockIndex: number, invoiceId: string) => {
    const key = `${fileName}::${blockIndex}`;
    const next = { ...attachPicks, [key]: invoiceId };
    setAttachPicks(next);
    void repreviewFile(
      fileName,
      Object.entries(next)
        .map(([k, id]) => {
          const at = k.lastIndexOf('::');
          return { file: k.slice(0, at), block_index: Number(k.slice(at + 2)), invoice_id: id };
        })
        .filter((entry) => entry.file === fileName),
    );
  };

  const runConfirm = async () => {
    if (!files.length || !supplierId) return;
    setApplying(true);
    setError(null);
    try {
      const translations: SupplierDocumentTranslation[] = Object.entries(translationEdits)
        .filter(([, target]) => target.trim().length > 0)
        .map(([source_text, target_text]) => ({ source_text, target_text: target_text.trim() }));
      const applied = await applySupplierDocuments(files, {
        supplierId,
        currency: trimmedCurrency,
        translations,
        attachTo,
        attachToBlocks: blockAttachments(),
      });
      setResult(applied);
      onImported?.(applied);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to import the supplier documents.');
    } finally {
      setApplying(false);
    }
  };

  /**
   * "Map to..." on an unmapped header chip (S5, AC-E4): write the alias, then read that
   * file again with it. The chip goes because the reader placed the column this time -
   * and the figures under it appear in the same pass, which is the point.
   */
  const mapHeader = async (
    fileName: string,
    header: string,
    field: string,
    docTypes: ImportFieldAliasDocType[],
  ) => {
    // One create per reader that missed the header (ruling 24). A combined sheet is read
    // as an invoice AND as a packing list, so mapping it once left half the file still
    // ignoring the column. A 409 means one of them already had it, which is the outcome
    // asked for, not a failure; only "not one of them landed" is worth saying.
    const outcomes = await Promise.all(
      docTypes.map(async (docType) => {
        try {
          await createImportFieldAlias({ doc_type: docType, field, alias: header });
          return null;
        } catch (e) {
          const status = (e as { status?: number })?.status;
          if (status === 409) return null;
          return e instanceof Error ? e.message : 'Failed to map that header.';
        }
      }),
    );
    const failures = outcomes.filter((m): m is string => m !== null);
    if (failures.length === docTypes.length && failures.length > 0) {
      setError(failures[0]);
      return;
    }
    await repreviewFile(fileName, blockAttachments(fileName));
  };

  const unreadable = preview?.files.filter((f) => f.kind === 'unreadable') ?? [];
  // One refused BLOCK is enough to hold Confirm: half a packing list is not an outcome
  // anybody asked for (AC-B13).
  const refused =
    preview?.files.flatMap((f) => (f.packing_attach ?? []).filter((b) => b.refusal)) ?? [];
  const canConfirm =
    !!supplierId &&
    files.length > 0 &&
    !applying &&
    !repreviewing &&
    unreadable.length === 0 &&
    refused.length === 0;
  const counts = confirmCounts(preview);
  const confirmLabel = preview
    ? `Confirm: ${fmtInt(counts.invoices)} invoice${counts.invoices === 1 ? '' : 's'}, ` +
      `${fmtInt(counts.packingLists)} draft packing list${counts.packingLists === 1 ? '' : 's'}`
    : 'Confirm';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Upload supplier documents</DialogTitle>
          <DialogDescription>
            A proforma invoice, a packing list, or both - each file is read on its own and
            classified automatically.
            {supplierName ? ` Uploading as ${supplierName}.` : ''}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
          {selfServe ? (
            <div>
              <Label htmlFor="supplier-documents-supplier" className="mb-1 block text-xs">
                Supplier
              </Label>
              <SearchableSelect
                id="supplier-documents-supplier"
                className="w-full"
                value={internalSupplier?.value ?? ''}
                onChange={(v: string) => {
                  if (!v) setInternalSupplier(null);
                }}
                onOptionChange={(option) => setInternalSupplier(option)}
                // Server-searched and paged, like the sibling upload dialog next door: an
                // unparameterised fetch returned the first 100 suppliers by name, so a
                // factory further down the alphabet could not be found by typing at all.
                fetchOptions={getFulfilmentSuppliers}
                paginated
                selectedOption={internalSupplier ?? undefined}
                placeholder="Choose a supplier"
                clearable
                disabled={previewing || applying}
              />
            </div>
          ) : null}

          <FileDropzone
            files={files}
            onFilesChange={(next) => {
              setFiles(next);
              setPreview(null);
              setResult(null);
              setError(null);
            }}
            multiple
            accept=".xlsx,.xlsm,.xls"
            maxSizeMb={MAX_SIZE_MB}
            disabled={!supplierId || previewing || applying}
            aria-label="Supplier document files"
          />

          <div>
            <Label htmlFor="supplier-documents-currency" className="mb-1 block text-xs">
              Currency
            </Label>
            <Input
              id="supplier-documents-currency"
              value={currency}
              onChange={(e) => setCurrency(e.target.value.toUpperCase().slice(0, 3))}
              maxLength={3}
              placeholder="MYR"
              autoComplete="off"
              className="w-28 uppercase"
              disabled={previewing || applying}
            />
            <p className="mt-1 text-2xs text-muted-foreground">
              Only needed when none of the files state one.
            </p>
          </div>

          {previewing ? (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <LoaderCircle className="size-3.5 animate-spin" /> Reading the files...
            </p>
          ) : null}

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {preview && !result ? (
            <div className="divide-y divide-border rounded-lg border">
              {preview.files.map((f) => {
                // Straight off the server's last read of this file: a header stops being
                // unmapped when the READER places it, never because this screen hid it
                // (AC-E4).
                const unmappedHeaders = f.unmapped_headers ?? [];
                return (
                <div key={f.name} className="space-y-1 p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate text-xs font-medium" title={f.name}>
                      {f.name}
                    </span>
                    <Badge
                      variant={f.kind === 'unreadable' ? 'destructive' : 'secondary'}
                      appearance="light"
                      size="sm"
                    >
                      {KIND_LABEL[f.kind] ?? f.kind}
                    </Badge>
                  </div>
                  {f.kind === 'unreadable' ? (
                    <p className="flex items-center gap-1.5 text-2xs text-destructive">
                      <TriangleAlert className="size-3.5 shrink-0" />
                      {f.errors[0] ?? 'This file could not be read.'}
                    </p>
                  ) : (
                    <div className="grid grid-cols-1 gap-x-4 gap-y-0.5 text-2xs text-muted-foreground sm:grid-cols-2">
                      <div>
                        <span className="font-medium text-foreground">Blocks: </span>
                        {blockSummary(f)}
                      </div>
                      <div>
                        <span className="font-medium text-foreground">Lines: </span>
                        {linesSummary(f)}
                      </div>
                      <div className="sm:col-span-2">
                        <span className="font-medium text-foreground">Header: </span>
                        {headerSummary(f)}
                      </div>
                      {f.unmatched.length ? (
                        <div className="sm:col-span-2">
                          {f.unmatched.length} code{f.unmatched.length === 1 ? '' : 's'} not in the
                          catalogue: {f.unmatched.slice(0, 8).join(', ')}
                          {f.unmatched.length > 8 ? ` and ${f.unmatched.length - 8} more` : ''}.
                        </div>
                      ) : null}
                    </div>
                  )}
                  {(f.packing_attach ?? []).map((block) => (
                    <div key={block.block_index} className="pt-1">
                      {/* `htmlFor` only where there IS a control to point at: a
                          same-batch answer renders as text, and a label naming an input
                          that is not on the page is a broken promise to a screen reader. */}
                      <Label
                        htmlFor={
                          block.attach_to?.how === 'same_batch'
                            ? undefined
                            : `attach-to-${f.name}-${block.block_index}`
                        }
                        className="mb-1 block text-2xs text-muted-foreground"
                      >
                        {/* Named by container once there is more than one: each container's
                            rows go to that container's own invoice (AC-B13). */}
                        {(f.packing_attach ?? []).length > 1
                          ? `Attaches to (${block.container_no || `block ${block.block_index + 1}`})`
                          : 'Attaches to'}
                      </Label>
                      {block.refusal ? (
                        <p className="flex items-center gap-1.5 text-2xs text-destructive">
                          <TriangleAlert className="size-3.5 shrink-0" />
                          {block.refusal.message}
                        </p>
                      ) : null}
                      {block.attach_to?.how === 'same_batch' ? (
                        // The invoice is a FILE in this upload, not a row: there is nothing
                        // to pick between, and it gets its number when Confirm writes it.
                        <p className="text-2xs text-foreground">
                          {block.attach_to.supplier_ref ?? block.attach_to.file}
                          <span className="text-muted-foreground"> · in this upload</span>
                        </p>
                      ) : (
                        <SearchableSelect
                          id={`attach-to-${f.name}-${block.block_index}`}
                          size="sm"
                          value={block.attach_to?.id ?? ''}
                          onChange={(v: string) => {
                            if (v) pickAttachTo(f.name, block.block_index, v);
                          }}
                          fetchOptions={fetchInvoiceOptions}
                          selectedOption={
                            block.attach_to?.id
                              ? {
                                  value: block.attach_to.id,
                                  label: invoiceLabel(
                                    block.attach_to.pi_number,
                                    block.attach_to.supplier_ref,
                                  ),
                                }
                              : undefined
                          }
                          placeholder="Choose the proforma invoice"
                          disabled={!!attachTo || repreviewing === f.name}
                        />
                      )}
                    </div>
                  ))}
                  {unmappedHeaders.length ? (
                    <div className="space-y-1 pt-1">
                      <p className="text-2xs font-medium text-foreground">Unmapped headers</p>
                      <div className="flex flex-wrap gap-1.5">
                        {unmappedHeaders.map((header) => (
                          <UnmappedHeaderChip
                            key={header}
                            header={header}
                            docTypes={docTypesFor(f, header)}
                            onMap={(fieldValue, forDocTypes) =>
                              void mapHeader(f.name, header, fieldValue, forDocTypes)
                            }
                          />
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {f.kind !== 'unreadable' && translationItems(f).length > 0 ? (
                    <div className="space-y-1 rounded-md border border-dashed p-2">
                      <p className="text-2xs font-medium text-foreground">
                        Translations - English beside the Chinese
                      </p>
                      {translationItems(f).map(({ key, reactKey, item }) => (
                        <TranslationRow
                          key={reactKey}
                          item={item}
                          value={translationEdits[key] ?? item.text_en ?? ''}
                          onChange={(next) =>
                            setTranslationEdits((prev) => ({ ...prev, [key]: next }))
                          }
                          disabled={previewing || applying}
                        />
                      ))}
                    </div>
                  ) : null}
                </div>
                );
              })}
              {preview.price_matches.length ? (
                <div className="p-2.5 text-2xs text-muted-foreground">
                  {preview.price_matches.map((m) => (
                    <div key={m.container_no}>
                      {m.container_no}: {m.matched_lines} line
                      {m.matched_lines === 1 ? '' : 's'} priced from the invoice
                      {m.unmatched_lines
                        ? `, ${m.unmatched_lines} without a match`
                        : ''}
                      .
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {result ? (
            <Alert>
              <AlertDescription>
                Created {fmtInt(result.proforma_invoice_ids.length)} invoice
                {result.proforma_invoice_ids.length === 1 ? '' : 's'} and{' '}
                {fmtInt(result.shipment_ids.length)} draft packing list
                {result.shipment_ids.length === 1 ? '' : 's'}
                {result.links_written > 0
                  ? `, ${fmtInt(result.links_written)} line${result.links_written === 1 ? '' : 's'} priced from an invoice`
                  : ''}
                .
              </AlertDescription>
            </Alert>
          ) : null}
        </DialogBody>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => void runTest()}
            disabled={!supplierId || !files.length || previewing || applying}
            title={!supplierId ? 'Choose a supplier first' : undefined}
          >
            {previewing ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <TestTube className="size-4" />
            )}
            Test
          </Button>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {result ? 'Close' : 'Cancel'}
          </Button>
          {!result ? (
            <Button
              onClick={() => void runConfirm()}
              disabled={!canConfirm}
              title={
                !supplierId
                  ? 'Choose a supplier first'
                  : unreadable.length
                    ? `Could not read ${unreadable.map((f) => f.name).join(', ')}`
                    : refused.length
                      ? `No proforma invoice to attach ${refused
                          .map((b) => b.container_no || `block ${b.block_index + 1}`)
                          .join(', ')} to`
                      : undefined
              }
            >
              {applying ? <LoaderCircle className="size-4 animate-spin" /> : null}
              {confirmLabel}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** One unmapped header (S5, AC-E4): the header text, and "Map to..." over the doc type's
 *  own field list (E1). Picking a field maps it at once - no explanation text on screen. */
function UnmappedHeaderChip({
  header,
  docTypes,
  onMap,
}: {
  header: string;
  /** The readers that could not place this header (ruling 24) - a combined sheet is read
   *  twice, and mapping it for one of them leaves the other still ignoring the column. */
  docTypes: ImportFieldAliasDocType[];
  onMap: (field: string, forDocTypes: ImportFieldAliasDocType[]) => void;
}) {
  const [mapping, setMapping] = useState(false);
  const [fields, setFields] = useState<{ value: string; label: string }[]>([]);
  // Which readers actually ASK for each field. A field only one of them declares is
  // written for that one alone - the other would refuse it, and rightly: an alias naming
  // a field its reader never reads can resolve nothing.
  const [fieldOwners, setFieldOwners] = useState<Record<string, ImportFieldAliasDocType[]>>({});
  const [loadingFields, setLoadingFields] = useState(false);

  const startMapping = async () => {
    setMapping(true);
    setLoadingFields(true);
    try {
      const { listImportFieldAliasFields } = await import(
        '@/app/(protected)/system-management/import-field-aliases/services/importFieldAliasService'
      );
      const owners: Record<string, ImportFieldAliasDocType[]> = {};
      const options: { value: string; label: string }[] = [];
      for (const docType of docTypes) {
        const list = await listImportFieldAliasFields(docType);
        for (const f of list) {
          if (!owners[f.field]) {
            owners[f.field] = [];
            options.push({ value: f.field, label: f.label });
          }
          owners[f.field].push(docType);
        }
      }
      setFieldOwners(owners);
      setFields(options);
    } finally {
      setLoadingFields(false);
    }
  };

  if (!mapping) {
    return (
      <Badge variant="secondary" appearance="light" size="sm" className="gap-1">
        {header}
        <button
          type="button"
          className="ms-1 text-primary underline-offset-2 hover:underline"
          onClick={() => void startMapping()}
        >
          Map to...
        </button>
      </Badge>
    );
  }

  return (
    <div className="flex items-center gap-1">
      <span className="text-2xs text-muted-foreground">{header}</span>
      <SearchableSelect
        size="sm"
        className="w-40"
        value=""
        onChange={(v: string) => v && onMap(v, fieldOwners[v] ?? docTypes)}
        options={fields}
        placeholder={loadingFields ? 'Loading...' : 'Choose a field'}
        disabled={loadingFields}
      />
    </div>
  );
}

export default SupplierDocumentsUploadDialog;
