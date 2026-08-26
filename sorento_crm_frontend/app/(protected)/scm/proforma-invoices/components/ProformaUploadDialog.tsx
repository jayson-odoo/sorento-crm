'use client';

import { useEffect, useState } from 'react';
import { LoaderCircle, TestTube } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
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
import { Checkbox } from '@/components/ui/checkbox';
import { FileDropzone } from '@/components/common/FileDropzone';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { MAX_SIZE_MB, useTwoStepUpload } from '../../reorder/hooks/useTwoStepUpload';
import { CountTile } from '../../reorder/components/UploadCountTile';
import { UploadTestVerdict } from '../../reorder/components/UploadTestVerdict';
import { EM_DASH, fmtSupplierCost } from '../../lib/format';
import { getFulfilmentSuppliers } from '../../services/fulfilmentService';
import { useProformaInvoicesApplied } from '../../hooks/useProformaInvoices';
import {
  applyProformaInvoice,
  previewProformaInvoice,
  testProformaInvoice,
  type ProformaApplyResult,
  type ProformaInvoicePreview,
  type RevisionSelection,
} from '../../services/proformaInvoiceService';

/**
 * The supplier's proforma invoice, uploaded and held.
 *
 * Unlike the packing-list dialog, the supplier is chosen HERE rather than on the page
 * behind it: the list's own supplier filter is what to READ, and the upload's supplier is
 * whose document this is - two different questions that happen to often share an answer.
 * The dropzone stays closed until one is picked, because the file never says reliably who
 * wrote it (AC journey step 1).
 *
 * Currency is asked for LAST and usually not at all - the document usually states it
 * (`RMB`, `单价(元)`) and the supplier's price list often does too, so the field is the last
 * resort rather than the first question (AC-P3.1). Where one of them answered, the preview
 * says which.
 */

/** Where the currency came from, in the words the operator would use. */
const CURRENCY_SOURCE: Record<string, string> = {
  form: 'as entered above',
  document: 'stated by the file',
  supplier_price_list: "from the supplier's price list",
};

const TOTAL_TOLERANCE = 0.01;

export function ProformaUploadDialog({
  open,
  onOpenChange,
  onApplied,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  onApplied?: (result: ProformaApplyResult) => void;
}) {
  const [supplierId, setSupplierId] = useState<string | null>(null);
  // The picked option's own label, alongside the id - server-searched (below), so the
  // trigger and the "Uploading as ..." line cannot assume the chosen supplier is sitting in
  // whatever unfiltered first page happens to be cached (S8-followup: KAILU HARDWARE
  // FACTORY, picked by search, is well past the `/select` endpoint's 100-row cap).
  const [supplierOption, setSupplierOption] = useState<SearchableSelectOption | null>(null);
  const [currency, setCurrency] = useState('');
  const trimmedCurrency = currency.trim() || null;
  // Which of this file's documents supersede one already on file. Pre-selected from the
  // preview's own proposal (AC-E6) and unticked by anyone who disagrees - the pre-loading
  // list carries no invoice number, so the match is a suggestion and the operator decides.
  const [revisionOf, setRevisionOf] = useState<RevisionSelection>({});
  const invalidateLists = useProformaInvoicesApplied();

  // Cleared on every open, like the file and the verdict: a supplier or currency left over
  // from the last upload would silently file - or price - the next one under it.
  useEffect(() => {
    if (open) {
      setSupplierId(null);
      setSupplierOption(null);
      setCurrency('');
      setRevisionOf({});
    }
  }, [open]);

  const upload = useTwoStepUpload<ProformaInvoicePreview, ProformaApplyResult>({
    open,
    preview: (file) => previewProformaInvoice(file, supplierId as string, trimmedCurrency),
    apply: (file) =>
      applyProformaInvoice(file, supplierId as string, trimmedCurrency, revisionOf),
    test: (file) => testProformaInvoice(file, supplierId as string, trimmedCurrency),
    onApplied: (result) => {
      invalidateLists();
      onApplied?.(result);
    },
  });

  const { preview, result } = upload;
  const supplierName = supplierOption?.label ?? null;

  // A fresh preview replaces the proposal wholesale: a tick left over from the last file
  // would file THIS one as a revision of a document it has nothing to do with.
  useEffect(() => {
    if (!preview) {
      setRevisionOf({});
      return;
    }
    setRevisionOf(
      Object.fromEntries(
        preview.documents
          .filter((doc) => doc.revision_candidate)
          .map((doc) => [String(doc.index), doc.revision_candidate!.invoice_id]),
      ),
    );
  }, [preview]);

  // A Test verdict/preview describes the prices AS READ IN THE OLD CURRENCY - changing the
  // currency mid-flow must not leave that stale verdict on screen looking current. Re-chooses
  // the SAME file, which is what `useTwoStepUpload.choose` already clears preview/test state
  // for. Left alone once `result` exists (post-apply) - that is the just-shown summary S8
  // keeps the dialog open to display, not a stale verdict to clear.
  const handleCurrencyChange = (raw: string) => {
    const next = raw.toUpperCase().slice(0, 3);
    setCurrency(next);
    if (!upload.result && upload.file && (upload.preview || upload.testResult)) {
      upload.choose(upload.file);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Upload proforma invoice</DialogTitle>
          <DialogDescription>
            Every invoice the file holds is priced and held against the chosen supplier.
            {supplierName ? ` Uploading as ${supplierName}.` : ''}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <div>
            <Label htmlFor="proforma-supplier" className="mb-1 block text-xs">
              Supplier
            </Label>
            <SearchableSelect
              id="proforma-supplier"
              value={supplierId ?? ''}
              onChange={(v: string) => setSupplierId(v || null)}
              onOptionChange={setSupplierOption}
              // Server-searched (S8-followup): the `/select` endpoint ilikes code + name and
              // caps at 100 rows, so a client-filtered static list silently hid any supplier
              // past that page. `fetchOptions` re-queries as the user types (debounced by
              // `SearchableSelect` itself).
              fetchOptions={(query) => getFulfilmentSuppliers(query)}
              selectedOption={supplierOption ?? undefined}
              placeholder="Choose a supplier"
              disabled={upload.previewing || upload.applying}
            />
          </div>

          <FileDropzone
            files={upload.file ? [upload.file] : []}
            onFilesChange={(next) => void upload.choose(next[0] ?? null)}
            onReject={upload.reject}
            accept={upload.accept}
            maxSizeMb={MAX_SIZE_MB}
            disabled={!supplierId || upload.previewing || upload.applying}
            aria-label="Proforma invoice file"
          />

          <div>
            <Label htmlFor="proforma-currency" className="mb-1 block text-xs">
              Currency
            </Label>
            <Input
              id="proforma-currency"
              value={currency}
              onChange={(e) => handleCurrencyChange(e.target.value)}
              maxLength={3}
              placeholder="CNY"
              autoComplete="off"
              className="w-28 uppercase"
              disabled={upload.previewing || upload.applying}
            />
            <p className="mt-1 text-2xs text-muted-foreground">
              Only needed when neither the file nor the supplier&apos;s price list says.
            </p>
          </div>

          {upload.previewing ? (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <LoaderCircle className="size-3.5 animate-spin" /> Reading the file...
            </p>
          ) : null}

          {upload.error ? (
            <Alert variant="destructive">
              <AlertDescription>{upload.error}</AlertDescription>
            </Alert>
          ) : null}

          {preview && !preview.ok ? (
            <Alert variant="destructive">
              <AlertDescription>
                {preview.missing_columns?.length
                  ? `This file has no ${preview.missing_columns.join(', ')} column.`
                  : 'No proforma invoice was found in this file.'}
              </AlertDescription>
            </Alert>
          ) : null}

          {preview?.ok && !result ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <CountTile label="Invoices" value={preview.document_count} />
                <CountTile label="Lines" value={preview.line_count} />
                <CountTile label="Not in catalogue" value={preview.unmatched_items} />
              </div>
              <div className="divide-y divide-border rounded-lg border">
                {preview.documents.map((doc) => {
                  const mismatch =
                    doc.stated_total != null &&
                    doc.total != null &&
                    Math.abs(doc.stated_total - doc.total) > TOTAL_TOLERANCE;
                  return (
                    <div key={doc.index} className="space-y-1 p-2.5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-xs font-medium">
                          {doc.pi_number}
                          {!doc.pi_number_stated ? (
                            <span className="ms-1.5 text-2xs font-normal text-muted-foreground">
                              (derived)
                            </span>
                          ) : null}
                        </span>
                        <span className="shrink-0 text-2xs text-muted-foreground">
                          {doc.invoice_date || EM_DASH}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2 text-2xs text-muted-foreground">
                        <span>{doc.container_no ? `Container ${doc.container_no}` : 'No container stated'}</span>
                        <span>{doc.lines} lines</span>
                      </div>
                      <div className="flex items-center justify-between gap-2 text-2xs">
                        <span className={mismatch ? 'font-medium text-amber-700' : 'text-muted-foreground'}>
                          Total {fmtSupplierCost(doc.total, doc.currency)}
                          {doc.stated_total != null
                            ? ` (stated ${fmtSupplierCost(doc.stated_total, doc.currency)})`
                            : ''}
                          {mismatch ? ' - does not match the lines' : ''}
                        </span>
                      </div>
                      <p className="text-2xs text-muted-foreground">
                        {doc.currency
                          ? `Priced in ${doc.currency} (${CURRENCY_SOURCE[doc.currency_source] ?? doc.currency_source}).`
                          : 'Nothing states which money this invoice is in - enter a currency above.'}
                      </p>
                      {doc.revision_candidate ? (
                        <label className="flex items-start gap-2 rounded-md bg-muted/50 p-2">
                          <Checkbox
                            className="mt-0.5"
                            checked={!!revisionOf[String(doc.index)]}
                            onCheckedChange={(checked) =>
                              setRevisionOf((prev) => {
                                const next = { ...prev };
                                if (checked) {
                                  next[String(doc.index)] = doc.revision_candidate!.invoice_id;
                                } else {
                                  delete next[String(doc.index)];
                                }
                                return next;
                              })
                            }
                            aria-label={`Upload as a revision of ${doc.revision_candidate.pi_number}`}
                          />
                          <span className="text-2xs">
                            <span className="font-medium">
                              Revision of {doc.revision_candidate.pi_number}
                            </span>
                            <span className="ms-1 text-muted-foreground">
                              {doc.revision_candidate.matched_items} of{' '}
                              {doc.revision_candidate.lines} item codes match. Untick to file
                              it as a new invoice.
                            </span>
                          </span>
                        </label>
                      ) : null}
                      {doc.unmatched_items.length ? (
                        <p className="text-2xs text-muted-foreground">
                          {doc.unmatched_items.slice(0, 8).join(', ')}
                          {doc.unmatched_items.length > 8
                            ? ` and ${doc.unmatched_items.length - 8} more`
                            : ''}{' '}
                          not in the catalogue.
                        </p>
                      ) : null}
                    </div>
                  );
                })}
              </div>
              {preview.unmatched_items > 0 ? (
                <p className="text-2xs text-muted-foreground">
                  {preview.unmatched_item_codes.slice(0, 8).join(', ')}
                  {preview.unmatched_items > 8
                    ? ` and ${preview.unmatched_items - 8} more`
                    : ''}{' '}
                  {preview.unmatched_items === 1 ? 'code is' : 'codes are'} not in the catalogue
                  ({preview.unmatched_items}). Those lines are still loaded, with no product
                  against them.
                </p>
              ) : null}
            </div>
          ) : null}

          {upload.testResult ? <UploadTestVerdict result={upload.testResult} /> : null}

          {result ? (
            <Alert>
              <AlertDescription>
                {result.documents_created > 0
                  ? `Created ${result.documents_created} invoice${result.documents_created === 1 ? '' : 's'}`
                  : 'Nothing new was created'}
                {result.documents_updated > 0
                  ? `, updated ${result.documents_updated}`
                  : ''}
                {result.results.some((r) => r.revision_of_id)
                  ? `. ${result.results.filter((r) => r.revision_of_id).length} filed as a revision, superseding what it replaces`
                  : ''}
                .
              </AlertDescription>
            </Alert>
          ) : null}
        </DialogBody>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => void upload.runTest()}
            disabled={!supplierId || !upload.file || upload.testing || upload.applying}
            title={!supplierId ? 'Choose a supplier first' : undefined}
          >
            {upload.testing ? (
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
              onClick={() => void upload.confirm()}
              disabled={!supplierId || !upload.canConfirm}
              title={!supplierId ? 'Choose a supplier first' : undefined}
            >
              {upload.applying ? <LoaderCircle className="size-4 animate-spin" /> : null}
              Confirm
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ProformaUploadDialog;
