'use client';

import { useEffect, useRef, useState } from 'react';
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
import { FileDropzone } from '@/components/common/FileDropzone';
import { Label } from '@/components/ui/label';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { MAX_SIZE_MB, useTwoStepUpload } from '../../reorder/hooks/useTwoStepUpload';
import { UploadReadingIndicator } from '../../reorder/components/UploadReadingIndicator';
import {
  UploadTestVerdict,
  type UploadTestResult,
} from '../../reorder/components/UploadTestVerdict';
import { EM_DASH } from '../../lib/format';
import { getFulfilmentSuppliers } from '../../services/fulfilmentService';
import { useProformaInvoicesApplied } from '../../hooks/useProformaInvoices';
import {
  applyProformaInvoice,
  previewProformaInvoice,
  type ProformaApplyResult,
  type ProformaInvoicePreview,
  type RevisionSelection,
} from '../../services/proformaInvoiceService';

/**
 * The supplier's proforma invoice, uploaded and held.
 *
 * The SAME three presses as the purchase-order and sales-order uploads next door (R24,
 * superseding R13): pick a file, Test to read it, Confirm to write it. Choosing a file runs
 * nothing, and what Test says is the standard `{valid, errors, warnings, summary}` verdict
 * every other importer in this system shows. This dialog used to be the odd one out - it
 * read the file on drop and printed a card per invoice with a currency box and a revision
 * tickbox on each - and the captain's verdict was that it asks the operator to adjudicate
 * things the file already answers.
 *
 * WHAT IS NO LONGER ASKED, and why:
 *
 * - **Currency.** The document states it (`RMB`, `单价(元)`) or the supplier's price list
 *   does. Where NEITHER does, the verdict carries an error naming the invoices and Confirm
 *   is disabled - which is the honest answer, rather than inviting a guess into a document
 *   of record.
 * - **Which invoices are revisions.** The file's own numbers decide, and the candidates are
 *   applied as revisions by DEFAULT. A wrong link is undone on the invoice's own detail page
 *   ("Mark as revision of"), which is one press in the rare case instead of a tickbox to
 *   read in every case.
 *
 * The supplier is still chosen HERE rather than on the page behind it: the list's own
 * supplier filter is what to READ, and the upload's supplier is whose document this is - two
 * different questions that happen to often share an answer. The one screen where they ARE
 * the same question passes the answer in (`supplierId` / `supplierOption`): the loading plan
 * is built for one supplier, so the picker becomes a line of text.
 */

/** The invoice numbers, when the result carries them - never a bare count on its own where
 *  a name is available, because "updated 1" is what made a Confirm read as a no-op. */
function named(rows: { pi_number: string }[]): string | null {
  const numbers = rows.map((r) => r.pi_number).filter(Boolean);
  return numbers.length ? numbers.join(', ') : null;
}

/** At most this many names in one verdict line before it says "and N more". */
const NAME_LIMIT = 8;

function listed(names: string[]): string {
  const head = names.slice(0, NAME_LIMIT).join(', ');
  return names.length > NAME_LIMIT ? `${head} and ${names.length - NAME_LIMIT} more` : head;
}

/**
 * The preview, read as the standard `{valid, errors, warnings, summary}` verdict.
 *
 * Derived in the browser rather than asked for a second time - the same shape
 * `OutstandingUploadDialog.verdictFromPreview` uses, and for the same reason: this channel's
 * preview already carries every fact the verdict needs.
 *
 * ERRORS are what makes the FILE unusable - a missing column, a workbook holding no invoice
 * at all, or a priced invoice nothing can price in. WARNINGS are what the upload will still
 * do, differently from a clean run: codes that bind to no product (the lines still land,
 * with no product against them), documents that will supersede an earlier version, and the
 * rows the reader could not use.
 */
export function verdictFromPreview(preview: ProformaInvoicePreview): UploadTestResult {
  // Priced, and nothing anywhere says in which money. Named, because "some invoice has no
  // currency" is not something an operator can act on (AC-P3.2).
  const unpriceable = preview.documents
    .filter((doc) => !doc.currency && (doc.total ?? 0) > 0)
    .map((doc) => doc.pi_number);
  const errors = [
    ...preview.missing_columns.map((column) => `This file has no ${column} column.`),
    ...(!preview.ok && preview.missing_columns.length === 0
      ? ['No proforma invoice was found in this file.']
      : []),
    ...(unpriceable.length
      ? [
          `Nothing says which money ${unpriceable.length === 1 ? 'this invoice is' : 'these invoices are'} ` +
            `in: ${listed(unpriceable)}. State the currency on the document or the supplier's price list.`,
        ]
      : []),
  ];

  const revisions = preview.documents
    .filter((doc) => doc.revision_candidate)
    .map((doc) => doc.pi_number);
  const warnings = [
    ...(preview.unmatched_items > 0
      ? [
          `${preview.unmatched_items} ${preview.unmatched_items === 1 ? 'code is' : 'codes are'} ` +
            `not in the catalogue: ${listed(preview.unmatched_item_codes)}. Those lines still load, ` +
            'with no product against them.',
        ]
      : []),
    ...(revisions.length
      ? [
          `${revisions.length} ${revisions.length === 1 ? 'invoice updates' : 'invoices update'} ` +
            `an earlier version: ${listed(revisions)}.`,
        ]
      : []),
    ...preview.problems,
    ...preview.unmapped_headers.map((header) => `Column not recognised: ${header}`),
  ];

  return {
    valid: preview.ok && errors.length === 0,
    errors,
    warnings,
    summary: {
      total_rows: preview.rows_read,
      // The unit of THIS channel is a document, not a row: one file is routinely five
      // invoices, and "500 rows" never said how many invoices that is.
      document_count: preview.document_count,
      would_apply: preview.ok ? preview.line_count : 0,
      error_count: errors.length,
    },
  };
}

/** Every candidate, ticked. The file's own numbers decide; a wrong link is undone on the
 *  detail page rather than adjudicated here (R24). */
function revisionsFrom(preview: ProformaInvoicePreview | null): RevisionSelection {
  if (!preview) return {};
  return Object.fromEntries(
    preview.documents
      .filter((doc) => doc.revision_candidate)
      .map((doc) => [String(doc.index), doc.revision_candidate!.invoice_id]),
  );
}

export function ProformaUploadDialog({
  open,
  onOpenChange,
  onApplied,
  supplierId: fixedSupplierId = null,
  supplierOption: fixedSupplierOption = null,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  onApplied?: (result: ProformaApplyResult) => void;
  /** Opened from a screen that already knows whose document this is - the loading plan,
   *  where the supplier was picked before the plan was built. Asking a second time invites
   *  a different answer than the plan behind the dialog stands on, so the picker is replaced
   *  by the name. Absent, the dialog asks, as it does on the proforma-invoices list. */
  supplierId?: string | null;
  supplierOption?: SearchableSelectOption | null;
}) {
  const [supplierId, setSupplierId] = useState<string | null>(fixedSupplierId);
  // The picked option's own label, alongside the id - server-searched (below), so the
  // trigger and the "Uploading as ..." line cannot assume the chosen supplier is sitting in
  // whatever unfiltered first page happens to be cached (S8-followup: KAILU HARDWARE
  // FACTORY, picked by search, is well past the `/select` endpoint's 100-row cap).
  const [supplierOption, setSupplierOption] = useState<SearchableSelectOption | null>(null);
  const invalidateLists = useProformaInvoicesApplied();

  /**
   * The read Confirm applies WITH, held outside React state.
   *
   * Confirm files the file's revision candidates as revisions, so it needs the preview -
   * and the operator is not required to press Test first (testing is a tool, not ceremony,
   * in every dialog here). So: use the read Test already did, and where there is none, take
   * one on the Confirm press itself. Never on the file being picked - that is the behaviour
   * R24 removed.
   */
  const previewRef = useRef<ProformaInvoicePreview | null>(null);

  // Cleared on every open, like the file and the verdict: a supplier left over from the last
  // upload would silently file the next one under it.
  useEffect(() => {
    if (open) {
      setSupplierId(fixedSupplierId);
      setSupplierOption(fixedSupplierOption);
      previewRef.current = null;
    }
  }, [open, fixedSupplierId, fixedSupplierOption]);

  const upload = useTwoStepUpload<ProformaInvoicePreview, ProformaApplyResult>({
    open,
    preview: (file) => previewProformaInvoice(file, supplierId as string),
    apply: async (file) => {
      const read =
        previewRef.current ?? (await previewProformaInvoice(file, supplierId as string));
      return applyProformaInvoice(file, supplierId as string, revisionsFrom(read));
    },
    onApplied: (result) => {
      invalidateLists();
      onApplied?.(result);
    },
  });

  const { file, preview, previewing, applying, result, error } = upload;

  // The hook clears its preview on a new file, so this ref follows it rather than
  // accumulating one file's answer onto the next one's Confirm.
  useEffect(() => {
    previewRef.current = preview;
  }, [preview]);

  // One press, one answer: the preview IS the test read, so the verdict is derived from it
  // rather than costing the operator a second one.
  const verdict = preview ? verdictFromPreview(preview) : null;
  const supplierName = supplierOption?.label ?? null;
  // A file already KNOWN to be unusable is never confirmable; an untested one still is.
  const canConfirm = !!supplierId && upload.canConfirm && (!verdict || verdict.valid);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Upload proforma invoice</DialogTitle>
          {/* One line, and it earns its place twice over: it is the promise the two-step
              flow makes, and it is the dialog's accessible description. */}
          <DialogDescription>
            Test reads the file. Confirm holds every invoice it carries against the chosen
            supplier.
            {supplierName ? ` Uploading as ${supplierName}.` : ''}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
          <div>
            <Label
              htmlFor={fixedSupplierId ? undefined : 'proforma-supplier'}
              className="mb-1 block text-xs"
            >
              Supplier
            </Label>
            {fixedSupplierId ? (
              <p className="text-sm font-medium" data-testid="proforma-fixed-supplier">
                {supplierName ?? EM_DASH}
              </p>
            ) : (
              <SearchableSelect
                id="proforma-supplier"
                value={supplierId ?? ''}
                onChange={(v: string) => setSupplierId(v || null)}
                onOptionChange={setSupplierOption}
                // Server-searched (S8-followup): the `/select` endpoint ilikes code + name and
                // caps at 100 rows, so a client-filtered static list silently hid any supplier
                // past that page.
                fetchOptions={(query) => getFulfilmentSuppliers(query)}
                selectedOption={supplierOption ?? undefined}
                placeholder="Choose a supplier"
                disabled={previewing || applying}
              />
            )}
          </div>

          <FileDropzone
            files={file ? [file] : []}
            onFilesChange={(next) => upload.choose(next[0] ?? null)}
            onReject={upload.reject}
            accept={upload.accept}
            maxSizeMb={MAX_SIZE_MB}
            disabled={!supplierId || previewing || applying}
            aria-label="Proforma invoice file"
          />

          <UploadReadingIndicator reading={previewing} />

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {verdict && !result ? <UploadTestVerdict result={verdict} /> : null}

          {result ? (
            <Alert>
              <AlertDescription>
                {/* Every invoice NAMED. "Nothing new was created" on its own is how a
                    Confirm that landed on the document already on file reads as a Confirm
                    that did nothing at all. */}
                {result.documents_created > 0
                  ? `Created ${named(result.results.filter((r) => r.created)) ?? `${result.documents_created} invoice${result.documents_created === 1 ? '' : 's'}`}`
                  : 'Nothing new was created'}
                {result.documents_updated > 0
                  ? `. Updated ${named(result.results.filter((r) => !r.created)) ?? String(result.documents_updated)} in place`
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
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={applying}>
            {result ? 'Close' : 'Cancel'}
          </Button>
          {!result ? (
            <>
              <Button
                type="button"
                variant="outline"
                onClick={() => void upload.runTest()}
                disabled={!supplierId || !file || previewing || applying || upload.testing}
                title={!supplierId ? 'Choose a supplier first' : undefined}
              >
                {upload.testing ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden />
                ) : (
                  <TestTube className="size-4" aria-hidden />
                )}
                Test
              </Button>
              <Button
                onClick={() => void upload.confirm()}
                disabled={!canConfirm}
                // WHY it will not act. A button that is disabled and silent reads as a button
                // that was pressed and did nothing.
                title={
                  !supplierId
                    ? 'Choose a supplier first'
                    : verdict && !verdict.valid
                      ? verdict.errors[0]
                      : undefined
                }
              >
                {applying ? <LoaderCircle className="size-4 animate-spin" /> : null}
                Import proforma invoice
              </Button>
            </>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ProformaUploadDialog;
