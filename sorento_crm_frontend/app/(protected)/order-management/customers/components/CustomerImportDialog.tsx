'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { LoaderCircle, TestTube } from 'lucide-react';
import { toast } from 'sonner';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { CountTile } from '@/components/common/CountTile';
import { FileDropzone } from '@/components/common/FileDropzone';
import type {
  CustomerImportQueuedResult,
  CustomerImportValidateResult,
} from '../services/customerImportService';

const ACCEPT = '.xlsx,.xls,.xlsm';
const MAX_SIZE_MB = 25;
/** Problems shown before the show-all toggle. */
const PREVIEW_LIMIT = 8;

interface CustomerImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onTest: (file: File) => Promise<CustomerImportValidateResult>;
  onUpload: (file: File) => Promise<CustomerImportQueuedResult>;
}

function TestResultPanel({
  result,
  showAll,
  onToggleShowAll,
}: {
  result: CustomerImportValidateResult;
  showAll: boolean;
  onToggleShowAll: (next: boolean) => void;
}) {
  const summary = result.summary;

  if (!result.valid || !summary) {
    return (
      <Alert variant="destructive" appearance="light">
        <AlertDescription>
          <p className="font-medium">Nothing would be imported.</p>
          <ul className="mt-1 list-disc space-y-0.5 ps-4">
            {(result.errors.length ? result.errors : ['The file could not be read.']).map(
              (error, index) => (
                <li key={`${index}-${error}`}>{error}</li>
              ),
            )}
          </ul>
        </AlertDescription>
      </Alert>
    );
  }

  const problems = summary.problems ?? [];
  const shown = showAll ? problems : problems.slice(0, PREVIEW_LIMIT);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <CountTile label="New customers" value={summary.would_create} />
        <CountTile label="Updated" value={summary.would_update} />
        <CountTile label="Unchanged" value={summary.would_unchanged} />
        <CountTile label="Needs a look" value={summary.needs_review} />
      </div>

      {summary.needs_review > 0 ? (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
          {summary.needs_review.toLocaleString()} row
          {summary.needs_review === 1 ? '' : 's'} carry a name close to one already on the
          same customer code. They import; each one is listed on the job for a human.
        </div>
      ) : null}

      {summary.unmapped_headers.length ? (
        <div className="rounded-lg border p-3 text-sm">
          <p className="font-medium">
            {summary.unmapped_headers.length} column
            {summary.unmapped_headers.length === 1 ? '' : 's'} not recognised:
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {summary.unmapped_headers.join(', ')}
          </p>
        </div>
      ) : null}

      {problems.length ? (
        <div className="rounded-lg border p-3 text-sm">
          <p className="font-medium">
            {summary.would_skip.toLocaleString()} row
            {summary.would_skip === 1 ? '' : 's'} skipped:
          </p>
          <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
            {shown.map((problem, index) => (
              <li key={`${problem.row}-${index}`}>
                Row {problem.row}: {problem.reason}
              </li>
            ))}
          </ul>
          {problems.length > PREVIEW_LIMIT ? (
            <button
              type="button"
              className="mt-1 text-xs underline"
              onClick={() => onToggleShowAll(!showAll)}
            >
              {showAll ? 'Show less' : `Show all ${problems.length}`}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Import the customer book from a debtor listing.
 *
 * Two presses, in the journey's order: Test answers "did I get this right?" without
 * writing anything, then Confirm queues the job and hands the watching over to the
 * upload drawer. Same behaviour as the GRN and SPO import dialogs; the drop surface is
 * the shared `FileDropzone` rather than their older hand-rolled one (AC-5.2).
 *
 * A file with three bad rows out of 900 imports 897: row problems are warnings that ask
 * for an acknowledgement, never a block (AC-5.6). Only an unreadable file, or one with no
 * customer code / name column at all, stops the import.
 */
export function CustomerImportDialog({
  open,
  onOpenChange,
  onTest,
  onUpload,
}: CustomerImportDialogProps) {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [testResult, setTestResult] = useState<CustomerImportValidateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [isQueueing, setIsQueueing] = useState(false);
  const [warnConfirmOpen, setWarnConfirmOpen] = useState(false);
  const [showAllProblems, setShowAllProblems] = useState(false);

  const file = files[0] ?? null;
  const busy = isTesting || isQueueing;

  const reset = () => {
    setFiles([]);
    setTestResult(null);
    setError(null);
    setShowAllProblems(false);
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  const handleFilesChange = (next: File[]) => {
    setFiles(next.slice(0, 1));
    setTestResult(null);
    setError(null);
    setShowAllProblems(false);
  };

  const runTest = async (current: File): Promise<CustomerImportValidateResult | null> => {
    try {
      const result = await onTest(current);
      setTestResult(result);
      setError(null);
      return result;
    } catch (caught) {
      setTestResult(null);
      const message = caught instanceof Error ? caught.message : 'Could not read the file';
      setError(message);
      toast.error(message);
      return null;
    }
  };

  const handleTest = async () => {
    if (!file) return;
    setIsTesting(true);
    setShowAllProblems(false);
    const result = await runTest(file);
    setIsTesting(false);
    if (!result) return;
    if (!result.valid) {
      toast.error('Nothing would be imported. Check the file.');
    } else if (result.warnings.length) {
      toast.success('The file reads. Some rows need a look before you confirm.');
    } else {
      toast.success('The file reads cleanly.');
    }
  };

  const handleConfirm = async () => {
    if (!file) {
      toast.error('Choose a file first.');
      return;
    }
    // Always read the file first, even when the user never pressed Test: an
    // unreadable file must not become a queued job that fails in the background.
    setIsQueueing(true);
    const result = testResult ?? (await runTest(file));
    if (!result) {
      setIsQueueing(false);
      return;
    }
    if (!result.valid) {
      setIsQueueing(false);
      toast.error('Nothing would be imported. Check the file.');
      return;
    }
    setIsQueueing(false);
    if (result.warnings.length) {
      // Acknowledge the skipped rows first. "Import anyway" then queues.
      setWarnConfirmOpen(true);
      return;
    }
    void queueImport(file);
  };

  const queueImport = async (current: File) => {
    setWarnConfirmOpen(false);
    // The work is not tied to the tab: close, queue, and let the drawer follow it.
    onOpenChange(false);
    reset();
    try {
      const queued = await onUpload(current);
      toast.success('Customer import queued. Processing in the background.', {
        duration: 6000,
        action: {
          label: 'View job',
          onClick: () => router.push(`/system-management/import-jobs/${queued.job_id}`),
        },
      });
    } catch (caught) {
      toast.error(
        caught instanceof Error ? caught.message : 'Failed to queue the customer import',
      );
    }
  };

  const warningCount = testResult?.warnings.length ?? 0;
  /**
   * The skip claim comes from the summary, NEVER from the warning count. `warnings` mixes
   * four kinds of thing - row problems, unrecognised columns, unrecognised market segments,
   * and one aggregate line about near names - and only row problems skip. Counting them all
   * told the operator "3 rows need a look, those rows are skipped" about a clean 900-row
   * file that happened to carry three unrecognised columns, and contradicted the panel on
   * the previous screen.
   */
  const skipCount = testResult?.summary?.would_skip ?? 0;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Import customers</DialogTitle>
          {/* One clause, saying what the control does. The "what a re-import never
              overwrites" guarantee lives in UAC AC-3, not on screen: it is a feature
              explanation, and the description exists so Radix has something to point
              `aria-describedby` at. */}
          <DialogDescription>
            Update the customer book from a debtor listing export.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <FileDropzone
            files={files}
            onFilesChange={handleFilesChange}
            onReject={(rejected, reason) =>
              toast.error(
                reason === 'size'
                  ? `${rejected.name} is larger than ${MAX_SIZE_MB} MB.`
                  : reason === 'extra'
                    ? `${rejected.name} was not used - one file at a time.`
                    : `${rejected.name} is not an Excel file.`,
              )
            }
            accept={ACCEPT}
            maxSizeMb={MAX_SIZE_MB}
            disabled={busy}
            inputTestId="customer-import-file"
            aria-label="Customer listing"
          />

          {error ? (
            <Alert variant="destructive" appearance="light">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {isTesting ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
              Reading the file...
            </div>
          ) : null}

          {!isTesting && testResult ? (
            <TestResultPanel
              result={testResult}
              showAll={showAllProblems}
              onToggleShowAll={setShowAllProblems}
            />
          ) : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="outline" onClick={() => void handleTest()} disabled={!file || busy}>
            <TestTube className="size-4" />
            {isTesting ? 'Testing...' : 'Test'}
          </Button>
          <Button onClick={() => void handleConfirm()} disabled={!file || busy}>
            {isQueueing ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : null}
            Confirm
          </Button>
        </DialogFooter>
      </DialogContent>

      <AlertDialog open={warnConfirmOpen} onOpenChange={setWarnConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Import anyway?</AlertDialogTitle>
            <AlertDialogDescription>
              Validation surfaced {warningCount} warning{warningCount === 1 ? '' : 's'}.{' '}
              {skipCount > 0
                ? `${skipCount.toLocaleString()} row${skipCount === 1 ? '' : 's'} will be skipped; the rest of the file still imports.`
                : 'Every row still imports.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {testResult?.warnings.length ? (
            <div className="max-h-60 overflow-y-auto rounded-md border bg-muted/30 p-3 text-sm">
              <ul className="list-disc space-y-0.5 ps-4 text-muted-foreground">
                {testResult.warnings.slice(0, 20).map((warning, index) => (
                  <li key={`${index}-${warning}`}>{warning}</li>
                ))}
                {testResult.warnings.length > 20 ? (
                  <li>and {testResult.warnings.length - 20} more</li>
                ) : null}
              </ul>
            </div>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => file && void queueImport(file)}>
              Import anyway
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}

export default CustomerImportDialog;
