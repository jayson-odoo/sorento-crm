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
import { useFulfilmentSuppliers } from '@/app/(protected)/scm/hooks/useFulfilment';
import {
  applySupplierDocuments,
  previewSupplierDocuments,
  type SupplierDocumentFilePreview,
  type SupplierDocumentsApplyResult,
  type SupplierDocumentsPreview,
  type SupplierDocumentTextItem,
  type SupplierDocumentTranslation,
} from '@/app/(protected)/scm/services/fulfilmentService';

/**
 * Upload supplier documents: a proforma invoice, a packing list, or both at once (R12-R14,
 * purchasing consolidation batch, lane C).
 *
 * ONE dialog for both documents rather than two, because the same container shows up in
 * both: the invoice prices what the packing list ships, and reading them together is what
 * lets the packing list's draft shipment arrive with its container, seal, consignee, shipper
 * and a price on every line that matches - the whole reason this dialog replaced a plain
 * "upload packing list" (this file's own former name and role, kept here so every existing
 * import - `procurement-management/packing-lists`, `scm/incoming` - needs no path change).
 *
 * Each file is read on Test and classified server-side by its own title cell; the operator
 * never says which kind a file is. Confirm applies every proforma invoice first, then every
 * packing list (one draft shipment per container block, same as the reader always did), then
 * matches invoice prices onto the shipment lines they price, in whichever order the files
 * came in.
 *
 * Self-serve supplier picker (Deviations lane A, purchasing consolidation batch; carried
 * over unchanged by this lane): R3 moved this dialog onto the Packing Lists page, which -
 * unlike `/scm/incoming` - carries no persistent supplier filter to source `supplierId`
 * from. The dialog manages its own `internalSupplierId` when `supplierId` is left
 * `undefined`; every caller that passes an explicit `supplierId` (even `null`) keeps
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

export function PackingListUploadDialog({
  open,
  onOpenChange,
  supplierId: supplierIdProp,
  supplierName: supplierNameProp,
  onImported,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  /**
   * Omit both `supplierId` and `supplierName` to let the dialog ask for the supplier itself
   * (the Packing Lists and Proforma Invoices pages have no persistent supplier context to
   * hand it one). Passing `supplierId` (even `null`) keeps that caller in control, unchanged.
   */
  supplierId?: string | null;
  /** Shown in the header so the factory the lines will be filed under is never a guess. */
  supplierName?: string | null;
  onImported?: (result: SupplierDocumentsApplyResult) => void;
}) {
  const selfServe = supplierIdProp === undefined;
  const suppliers = useFulfilmentSuppliers();
  const [internalSupplierId, setInternalSupplierId] = useState<string | null>(null);
  const supplierId = selfServe ? internalSupplierId : (supplierIdProp ?? null);
  const supplierName = selfServe
    ? ((suppliers.data ?? []).find((o) => o.value === internalSupplierId)?.label ?? null)
    : (supplierNameProp ?? null);

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
    if (selfServe) setInternalSupplierId(null);
  }, [open, selfServe]);

  const runTest = async () => {
    if (!files.length || !supplierId) return;
    setPreviewing(true);
    setError(null);
    try {
      const read = await previewSupplierDocuments(files, {
        supplierId,
        currency: trimmedCurrency,
      });
      setPreview(read);
      setTranslationEdits({});
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to read the files.');
    } finally {
      setPreviewing(false);
    }
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
      });
      setResult(applied);
      onImported?.(applied);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to import the supplier documents.');
    } finally {
      setApplying(false);
    }
  };

  const unreadable = preview?.files.filter((f) => f.kind === 'unreadable') ?? [];
  const canConfirm = !!supplierId && files.length > 0 && !applying && unreadable.length === 0;
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
                value={internalSupplierId ?? ''}
                onChange={(v: string) => setInternalSupplierId(v || null)}
                options={suppliers.data ?? []}
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
              {preview.files.map((f) => (
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
              ))}
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
