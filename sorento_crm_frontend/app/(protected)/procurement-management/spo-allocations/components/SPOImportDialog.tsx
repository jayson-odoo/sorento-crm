'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { TestTube } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
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
import { toast } from 'sonner';
import { FileDropzone } from '@/components/common/FileDropzone';
import type { SPOImportResult, ValidateImportResult } from '../services/spoAllocationService';

const ACCEPT = '.xlsx,.xls';

interface SPOImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onTest?: (files: File[]) => Promise<ValidateImportResult>;
  onUpload: (files: File[]) => Promise<SPOImportResult>;
}

export function SPOImportDialog({
  open,
  onOpenChange,
  onTest,
  onUpload,
}: SPOImportDialogProps) {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [testResult, setTestResult] = useState<ValidateImportResult | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [isValidatingForImport, setIsValidatingForImport] = useState(false);
  const [warnConfirmOpen, setWarnConfirmOpen] = useState(false);
  const [showAllErrors, setShowAllErrors] = useState(false);
  const [showAllWarnings, setShowAllWarnings] = useState(false);
  const [showAllConfirmWarnings, setShowAllConfirmWarnings] = useState(false);

  // The same workbook dropped twice is the same import twice, so keep the
  // first-seen copy and ignore the repeat.
  const handleFilesChange = useCallback((next: File[]) => {
    const seen = new Set<string>();
    setFiles(
      next.filter((file) => {
        if (seen.has(file.name)) return false;
        seen.add(file.name);
        return true;
      }),
    );
    setTestResult(null);
  }, []);

  const handleTest = async () => {
    if (files.length === 0 || !onTest) return;
    setIsTesting(true);
    setTestResult(null);
    setShowAllErrors(false);
    setShowAllWarnings(false);
    try {
      const result = await onTest([...files]);
      setTestResult(result);
      if (result.valid && (result.warnings?.length ?? 0) === 0) {
        toast.success('Validation passed with no issues.');
      } else if (result.valid) {
        toast.success('Validation passed with warnings. Review below.');
      } else {
        toast.error('Validation found errors. Fix them before importing.');
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Validation failed');
    } finally {
      setIsTesting(false);
    }
  };

  const handleUpload = async () => {
    if (files.length === 0) {
      toast.error('Please select at least one Excel file.');
      return;
    }
    // Always validate all files first (even if the user never clicked Test) so
    // errors block the import and warnings (skipped rows) require acknowledgement.
    if (onTest) {
      setIsValidatingForImport(true);
      let result: ValidateImportResult;
      try {
        result = await onTest([...files]);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Validation failed');
        return;
      } finally {
        setIsValidatingForImport(false);
      }
      setTestResult(result);
      if (!result.valid) {
        toast.error('Validation found errors. Fix them before importing.');
        return;
      }
      if ((result.warnings?.length ?? 0) > 0) {
        setShowAllConfirmWarnings(false);
        setWarnConfirmOpen(true);
        return;
      }
    }
    doImport();
  };

  const doImport = () => {
    setWarnConfirmOpen(false);
    // Close dialog immediately; processing runs in background; toast when queued
    const filesToUpload = [...files];
    onOpenChange(false);
    setFiles([]);

    onUpload(filesToUpload)
      .then((result) => {
        const count = result.job_ids?.length ?? 0;
        toast.success('Import queued. Processing in the background.', {
          duration: 6000,
          action:
            count > 0
              ? {
                  label: count === 1 ? 'View job' : 'View jobs',
                  onClick: () =>
                    router.push(
                      count === 1
                        ? `/system-management/import-jobs/${result.job_ids[0]}`
                        : '/system-management/import-jobs'
                    ),
                }
              : undefined,
        });
      })
      .catch((error) => {
        toast.error(error instanceof Error ? error.message : 'Upload failed');
      });
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setFiles([]);
      setTestResult(null);
    }
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Import SPO Allocations</DialogTitle>
          <DialogDescription>
            Upload one or more Excel files (.xlsx or .xls).
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <FileDropzone
            multiple
            accept={ACCEPT}
            files={files}
            onFilesChange={handleFilesChange}
            onReject={(file) =>
              toast.error(`Skipped ${file.name}: only .xlsx and .xls are allowed.`)
            }
            title="Drag and drop your Excel files here, or click to browse"
            hint=".xlsx or .xls only"
            aria-label="SPO allocation workbooks"
          />
          {files.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                {files.length} file{files.length !== 1 ? 's' : ''} selected
              </p>
              {testResult !== null && (
                <div className="rounded-md border bg-muted/30 p-3 text-sm">
                  <p className="font-medium">
                    {testResult.valid
                      ? (testResult.warnings?.length ?? 0) > 0
                        ? 'Validation passed with warnings'
                        : 'Validation passed'
                      : 'Validation found errors'}
                  </p>
                  {testResult.errors?.length ? (
                    <div className="mt-2 max-h-32 overflow-y-auto">
                      <p className="text-destructive font-medium">Errors ({testResult.errors.length}):</p>
                      <ul className="list-disc pl-4 text-destructive">
                        {(showAllErrors ? testResult.errors : testResult.errors.slice(0, 50)).map((err, i) => (
                          <li key={i}>{err}</li>
                        ))}
                        {testResult.errors.length > 50 && (
                          <li className="list-none -ml-4 text-destructive">
                            {showAllErrors ? (
                              <button
                                type="button"
                                onClick={() => setShowAllErrors(false)}
                                className="underline"
                              >
                                show less
                              </button>
                            ) : (
                              <>
                                … and {testResult.errors.length - 50} more - {' '}
                                <button
                                  type="button"
                                  onClick={() => setShowAllErrors(true)}
                                  className="underline"
                                >
                                  show all
                                </button>
                              </>
                            )}
                          </li>
                        )}
                      </ul>
                    </div>
                  ) : null}
                  {testResult.warnings?.length ? (
                    <div className="mt-2 max-h-24 overflow-y-auto">
                      <p className="font-medium text-amber-600 dark:text-amber-500">Warnings ({testResult.warnings.length}):</p>
                      <ul className="list-disc pl-4 text-amber-600 dark:text-amber-500">
                        {(showAllWarnings ? testResult.warnings : testResult.warnings.slice(0, 20)).map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                        {testResult.warnings.length > 20 && (
                          <li className="list-none -ml-4 text-amber-600 dark:text-amber-500">
                            {showAllWarnings ? (
                              <button
                                type="button"
                                onClick={() => setShowAllWarnings(false)}
                                className="underline"
                              >
                                show less
                              </button>
                            ) : (
                              <>
                                … and {testResult.warnings.length - 20} more - {' '}
                                <button
                                  type="button"
                                  onClick={() => setShowAllWarnings(true)}
                                  className="underline"
                                >
                                  show all
                                </button>
                              </>
                            )}
                          </li>
                        )}
                      </ul>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          {onTest && (
            <Button
              variant="outline"
              onClick={handleTest}
              disabled={files.length === 0 || isTesting || isValidatingForImport}
            >
              <TestTube className="size-4 mr-2" />
              {isTesting ? 'Testing...' : files.length > 1 ? 'Test all files' : 'Test file'}
            </Button>
          )}
          <Button
            onClick={handleUpload}
            disabled={files.length === 0 || isTesting || isValidatingForImport}
            data-guide-target="procurement.spo-allocations.import-confirm-button"
          >
            {isValidatingForImport ? 'Validating...' : 'Import'}
          </Button>
        </DialogFooter>
      </DialogContent>

      <AlertDialog open={warnConfirmOpen} onOpenChange={setWarnConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Import with warnings?</AlertDialogTitle>
            <AlertDialogDescription>
              Validation surfaced {testResult?.warnings?.length ?? 0} warning
              {(testResult?.warnings?.length ?? 0) === 1 ? '' : 's'}.
              Affected rows will be skipped (not imported). Continue anyway?
            </AlertDialogDescription>
          </AlertDialogHeader>
          {testResult?.warnings?.length ? (
            <div className="max-h-60 overflow-y-auto rounded-md border bg-muted/30 p-3 text-sm">
              <ul className="list-disc pl-4 text-amber-600 dark:text-amber-500">
                {(showAllConfirmWarnings ? testResult.warnings : testResult.warnings.slice(0, 20)).map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
                {testResult.warnings.length > 20 && (
                  <li className="list-none -ml-4 text-amber-600 dark:text-amber-500">
                    {showAllConfirmWarnings ? (
                      <button
                        type="button"
                        onClick={() => setShowAllConfirmWarnings(false)}
                        className="underline"
                      >
                        show less
                      </button>
                    ) : (
                      <>
                        … and {testResult.warnings.length - 20} more - {' '}
                        <button
                          type="button"
                          onClick={() => setShowAllConfirmWarnings(true)}
                          className="underline"
                        >
                          show all
                        </button>
                      </>
                    )}
                  </li>
                )}
              </ul>
            </div>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={doImport}>Import anyway</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}
