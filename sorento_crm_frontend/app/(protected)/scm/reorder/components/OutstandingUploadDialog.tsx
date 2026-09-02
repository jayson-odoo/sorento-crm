'use client';

import { LoaderCircle, TestTube } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { toast } from '@/lib/toast';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { FileDropzone } from '@/components/common/FileDropzone';
import { useImportJobDrawer } from '@/components/upload-activity/useImportJobDrawer';
import type { ImportQueuedResult } from '@/components/upload-activity/importQueue';
import { MAX_SIZE_MB, useTwoStepUpload } from '../hooks/useTwoStepUpload';
import {
  applyOutstandingImport,
  previewOutstandingImport,
  type OutstandingChangeKind,
  type OutstandingCounts,
  type OutstandingImportKind,
  type OutstandingPreview,
} from '../services/outstandingImportService';
import { UploadReadingIndicator } from './UploadReadingIndicator';
import { UploadTestVerdict, type UploadTestResult } from './UploadTestVerdict';

/**
 * SCM - the upload channel for the order book, until AutoCount is integrated.
 *
 * Test, then upload - the same three presses as the GRN, SPO and customer importers.
 * Choosing a file runs nothing; Test reads it and reports; Confirm queues the write as an
 * import job and hands the watching to the upload drawer. The whole reorder plan is computed
 * from this data, so a wrong file quietly imported is a week of unpicking.
 *
 * WHAT TEST SAYS is the standard verdict every other importer in this system shows: how many
 * rows were read, how many would import, what would fail, what is only a warning. It used to
 * be a bespoke diff report - count tiles per change kind, sample rows, scope chips, per-kind
 * problem sections - and the captain's verdict on it was that nobody reads it: "if i click
 * test i just need to know how many succeed, how many fail, how many warning, like the SPO /
 * product list / delivery order / GRN uploads". The diff is still computed by the preview
 * endpoint (it is what decides whether the file changes anything at all); it is just no longer
 * printed row by row.
 *
 * What the upload DID is not shown here: the write happens on the worker, so the counts do not
 * exist when this dialog closes. They land on the job page, which is where every other
 * importer in this system reports its outcome.
 */

const TITLES: Record<OutstandingImportKind, string> = {
  // Not "outstanding", on either side: the file carries the whole book, orders still owed
  // and orders already completed alike, and naming the action after half of it is what made
  // the captain ask which half he was meant to export.
  'sales-orders': 'Upload sales orders',
  'purchase-orders': 'Upload purchase orders',
};

/** The dropzone's accessible name, worded the same way its title is. */
const DROPZONE_LABELS: Record<OutstandingImportKind, string> = {
  'sales-orders': 'Sales orders file',
  'purchase-orders': 'Purchase orders file',
};

/** Everything except `unchanged` - what makes a file worth applying. */
const ACTIONABLE_KINDS: OutstandingChangeKind[] = [
  'added',
  'qty_changed',
  'date_moved',
  'date_and_qty_changed',
  'closed',
];

function countOf(counts: OutstandingCounts, kind: OutstandingChangeKind): number {
  return counts[kind] ?? 0;
}

/** `n thing`, pluralised, or nothing at all when there is none of it. */
function part(n: number, one: string, many = `${one}s`): string | null {
  return n > 0 ? `${n} ${n === 1 ? one : many}` : null;
}

/**
 * What the shipping-order half of a purchase book would do, in one line. `null` when the
 * book carries none, which is most sales books and plenty of purchase ones.
 *
 * The bare row count was already printed as a warning and it was not enough: the verdict
 * said "721 rows are shipping orders (SPO)" and, immediately under it, "Nothing would
 * change - every line already matches what we hold", because that sentence reads the
 * purchase-order diff and this half had no figure of its own to contradict it with.
 *
 * Zero parts are dropped, except `unchanged` - "0 unchanged" is the answer to "did it
 * really look at what we hold", and a line that silently omits it reads as a shorter list
 * rather than as a zero.
 */
export function shippingOrderNote(preview: OutstandingPreview): string | null {
  const lines = preview.spo_lines ?? 0;
  const closed = preview.spo_closed ?? 0;
  if (lines <= 0 && closed <= 0) return null;
  const parts = [
    part(preview.spo_documents ?? 0, 'document'),
    part(preview.spo_new ?? 0, 'new', 'new'),
    part(preview.spo_changed ?? 0, 'changed', 'changed'),
    `${preview.spo_unchanged ?? 0} unchanged`,
    closed > 0 ? `${closed} would close` : null,
    (preview.spo_unknown_locations ?? 0) > 0
      ? `${preview.spo_unknown_locations} with no warehouse`
      : null,
  ].filter(Boolean);
  return `Shipping orders: ${parts.join(', ')}`;
}

/** Shipping-order lines this upload would file, restate or settle. */
function spoChanges(preview: OutstandingPreview): number {
  return (preview.spo_new ?? 0) + (preview.spo_changed ?? 0) + (preview.spo_closed ?? 0);
}

/**
 * The preview, read as the standard `{valid, errors, warnings, summary}` verdict.
 *
 * Derived in the browser rather than asked for: this channel's preview already carries every
 * fact the verdict needs, and a second `validate_only` round trip would read the same 80,000-row
 * workbook twice to say the same thing.
 *
 * ERRORS are what makes the FILE unusable: a header missing a required column, so nothing in
 * it can import at all. Nothing else qualifies.
 *
 * WARNINGS are the rows the import merely SKIPS, the file-level notices the backend states
 * outright (`warnings`), plus the things that cost the file nothing.
 * A row with no item code, or one naming a warehouse we do not hold, does not stop the other
 * 4,346 rows landing - reporting it in red said "this upload failed" about a file that
 * imports perfectly, and the operator's only honest reaction was to stop reading the panel.
 * The count is still there, and it is the number that decides whether to fix the file first.
 */
export function verdictFromPreview(preview: OutstandingPreview): UploadTestResult {
  const unclassified = preview.unclassified_documents ?? [];
  const errors = [
    ...preview.missing_columns.map((column) => `Missing required column: ${column}`),
    // QP1: an order nothing can classify refuses the FILE, so it is an ERROR and not a
    // skipped row - the rest of the book does not go in without it. The per-row warnings
    // below name each order and its debtor; this is the one line that says why the upload
    // is blocked at all.
    ...(unclassified.length
      ? [
          `${unclassified.length} sales order${unclassified.length === 1 ? '' : 's'} ` +
            'carry no demand class, so nothing will be imported: ' +
            `${unclassified.slice(0, 10).join(', ')}` +
            `${unclassified.length > 10 ? ` and ${unclassified.length - 10} more` : ''}.`,
        ]
      : []),
  ];
  const skipped = [
    ...preview.row_problems.map(
      (p) => `Row ${p.row_number}: ${p.reason}${p.value ? ` (${p.value})` : ''}`,
    ),
    ...preview.resolution_issues.map(
      (i) => `Row ${i.row_number}: ${i.field}: ${i.reason}${i.value ? ` (${i.value})` : ''}`,
    ),
  ];
  const warnings = [
    ...skipped,
    ...(preview.unmapped_agents ?? []).map((agent) => `Agent ${agent.code}: ${agent.reason}`),
    ...preview.unmapped_headers.map((header) => `Column not recognised: ${header}`),
    // The file-level notices the backend already words as sentences: dates it could not
    // read, rows belonging to the other document family. They were computed and never
    // printed, so the operator learnt about them only from the job afterwards.
    ...(preview.warnings ?? []),
  ];
  const failedRows = preview.row_problems.length + preview.resolution_issues.length;
  // Rows this channel leaves out WHOLESALE - today only the shipping orders in a purchase
  // book. Not a row problem (nothing is wrong with them) and not a warning count, but they
  // do not import, so "would import" has to know about them.
  const otherFamilyRows = preview.shipping_order_rows ?? 0;
  const note = shippingOrderNote(preview);
  return {
    valid: preview.ok && errors.length === 0,
    errors,
    warnings,
    notes: note ? [note] : [],
    summary: {
      total_rows: preview.total_rows,
      would_apply: preview.ok
        ? Math.max(preview.total_rows - failedRows - otherFamilyRows, 0)
        : 0,
      // What the import would LEAVE OUT, named as its own figure. Read off the rows
      // themselves rather than off `warnings.length`, which also counts the file-level
      // notes (an unrecognised column skips no row at all).
      skipped_rows: failedRows,
      warning_count: warnings.length,
      error_count: errors.length,
    },
  };
}

// ── dialog ──────────────────────────────────────────────────────────────────

export interface OutstandingUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: OutstandingImportKind;
  /** Fired once the job is queued, so a page can react to the upload having started. */
  onQueued?: (queued: ImportQueuedResult) => void;
}

export function OutstandingUploadDialog({
  open,
  onOpenChange,
  kind,
  onQueued,
}: OutstandingUploadDialogProps) {
  const router = useRouter();
  const { notifyImportQueued } = useImportJobDrawer();
  const upload = useTwoStepUpload<OutstandingPreview, ImportQueuedResult>({
    open,
    preview: (f) => previewOutstandingImport(kind, f),
    apply: (f) => applyOutstandingImport(kind, f),
    onApplied: (queued) => {
      // The work is not tied to this tab: open the drawer, close the dialog, and let the
      // job be followed there.
      notifyImportQueued();
      onOpenChange(false);
      toast.success('Upload queued. Processing in the background.', {
        duration: 6000,
        action: {
          label: 'View job',
          onClick: () => router.push(`/system-management/import-jobs/${queued.job_id}`),
        },
      });
      onQueued?.(queued);
    },
  });
  const { file, preview, previewing, applying, error } = upload;

  // BOTH halves of the book, which is the whole fix: a purchase export can be entirely
  // shipping orders, and reading only the purchase-order diff had the dialog announce that
  // nothing would change while it filed 721 SPO lines.
  const hasChanges =
    !!preview &&
    (ACTIONABLE_KINDS.some((k) => countOf(preview.counts, k) > 0) || spoChanges(preview) > 0);
  /**
   * Confirmable once a file is picked, and that is the whole rule. Test is a tool, not a
   * gate, exactly as in every other import dialog.
   *
   * A tested file that changes nothing used to disable Confirm as well, and it was wrong on
   * its own terms: the diff answers for the QUANTITIES and DATES this channel writes, so a
   * book that restates them and nothing else still carries money, units and closures the
   * write path acts on - and a greyed button over a file the operator can see is readable
   * reads as a defect in the upload, not as a statement about the file. The note below still
   * says what the diff found; it just no longer decides for them.
   */
  const canConfirm = upload.canConfirm;

  // One press, one answer: the preview IS the test read, so the verdict is derived from it
  // rather than costing the operator a second one.
  const verdict = preview ? verdictFromPreview(preview) : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{TITLES[kind]}</DialogTitle>
          {/* One line, and it earns its place twice over: it is the promise the two-step
              flow makes, and it is the dialog's accessible description. Without a
              description Radix warns that the content has no `aria-describedby`. */}
          <DialogDescription>Test reads the file. Confirm queues the upload.</DialogDescription>
        </DialogHeader>

        <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <FileDropzone
            files={file ? [file] : []}
            onFilesChange={(next) => upload.choose(next[0] ?? null)}
            onReject={upload.reject}
            accept={upload.accept}
            maxSizeMb={MAX_SIZE_MB}
            disabled={previewing || applying}
            aria-label={DROPZONE_LABELS[kind]}
          />

          <UploadReadingIndicator reading={previewing} />

          {verdict ? <UploadTestVerdict result={verdict} /> : null}

          {/* The one thing the verdict cannot say: the file reads perfectly and the diff
              found nothing to move. Information, not a refusal - Confirm stays live. */}
          {preview && preview.ok && !hasChanges ? (
            <p className="text-sm font-medium">
              Nothing would change - every line already matches what we hold.
            </p>
          ) : null}
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={applying}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => void upload.runTest()}
            disabled={!file || previewing || applying || upload.testing}
          >
            {upload.testing ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
            ) : (
              <TestTube className="size-4" aria-hidden />
            )}
            Test
          </Button>
          <Button onClick={() => void upload.confirm()} disabled={!canConfirm}>
            {applying ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : null}
            Confirm upload
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default OutstandingUploadDialog;
