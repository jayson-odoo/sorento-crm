'use client';

import { LoaderCircle, TestTube } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
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
  // Not "outstanding": the file carries the whole book, orders still owed and orders already
  // completed alike, and naming the action after half of it is what made the captain ask
  // which half he was meant to export.
  'sales-orders': 'Upload sales orders',
  'purchase-orders': 'Upload outstanding purchase orders',
};

/** The dropzone's accessible name, worded the same way its title is. */
const DROPZONE_LABELS: Record<OutstandingImportKind, string> = {
  'sales-orders': 'Sales orders file',
  'purchase-orders': 'Outstanding purchase orders file',
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

/**
 * The preview, read as the standard `{valid, errors, warnings, summary}` verdict.
 *
 * Derived in the browser rather than asked for: this channel's preview already carries every
 * fact the verdict needs, and a second `validate_only` round trip would read the same 80,000-row
 * workbook twice to say the same thing.
 *
 * ERRORS are the rows that will not import - a header missing a required column (nothing can
 * import at all), a row the reader could not turn into a line, a row naming a product or
 * warehouse we do not hold. WARNINGS are the things that cost the file nothing: a column we
 * ignored, an agent code that cannot classify an order yet. `valid` is false as soon as there
 * is one error, because the shared verdict shows the error list only when it is.
 */
export function verdictFromPreview(preview: OutstandingPreview): UploadTestResult {
  const errors = [
    ...preview.missing_columns.map((column) => `Missing required column: ${column}`),
    ...preview.row_problems.map(
      (p) => `Row ${p.row_number}: ${p.reason}${p.value ? ` (${p.value})` : ''}`,
    ),
    ...preview.resolution_issues.map(
      (i) => `Row ${i.row_number}: ${i.field}: ${i.reason}${i.value ? ` (${i.value})` : ''}`,
    ),
  ];
  const warnings = [
    ...(preview.unmapped_agents ?? []).map((agent) => `Agent ${agent.code}: ${agent.reason}`),
    ...preview.unmapped_headers.map((header) => `Column not recognised: ${header}`),
  ];
  const failedRows = preview.row_problems.length + preview.resolution_issues.length;
  return {
    valid: preview.ok && errors.length === 0,
    errors,
    warnings,
    summary: {
      total_rows: preview.total_rows,
      would_apply: preview.ok ? Math.max(preview.total_rows - failedRows, 0) : 0,
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

  const hasChanges = !!preview && ACTIONABLE_KINDS.some((k) => countOf(preview.counts, k) > 0);
  /**
   * Confirmable once a file is picked. Deliberately NOT "once it has been tested and shows
   * changes": Test is a tool, not a gate, and the same rule holds in every other import
   * dialog. A file already tested and known to change nothing is the one case worth
   * blocking, because there is nothing for the job to do.
   */
  const canConfirm = upload.canConfirm && (!preview || hasChanges);

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

          {/* The one thing the verdict cannot say, and the reason Confirm is disabled: the
              file reads perfectly and asks for nothing. */}
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
