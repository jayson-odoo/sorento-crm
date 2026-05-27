'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Upload, X, FileSpreadsheet, TestTube } from 'lucide-react';
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
  const [dragActive, setDragActive] = useState(false);
  const [testResult, setTestResult] = useState<ValidateImportResult | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [isValidatingForImport, setIsValidatingForImport] = useState(false);
  const [warnConfirmOpen, setWarnConfirmOpen] = useState(false);
  const [showAllErrors, setShowAllErrors] = useState(false);
  const [showAllWarnings, setShowAllWarnings] = useState(false);
  const [showAllConfirmWarnings, setShowAllConfirmWarnings] = useState(false);

  const validExtensions = ACCEPT.split(',').map((ext) => ext.trim().replace('.', ''));
  const isValidFile = (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase();
    return ext && validExtensions.includes(ext);
  };

  const handleFiles = useCallback((fileList: FileList | File[]) => {
    const list = Array.from(fileList);
    const valid = list.filter(isValidFile);
    const invalid = list.filter((f) => !isValidFile(f));
    
    if (invalid.length > 0) {
      toast.error(`Skipped ${invalid.length} file(s): only .xlsx and .xls are allowed.`);
    }
    
    if (valid.length > 0) {
      setFiles((prev) => {
        const names = new Set(prev.map((f) => f.name));
        const added = valid.filter((f) => !names.has(f.name));
        return [...prev, ...added];
      });
      setTestResult(null);
    }
  }, []);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);
      if (e.dataTransfer.files?.length) {
        handleFiles(e.dataTransfer.files);
      }
    },
    [handleFiles]
  );

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files;
    if (selected?.length) handleFiles(selected);
    e.target.value = '';
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setTestResult(null);
  };

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
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
              dragActive ? 'border-primary bg-primary/5' : 'border-border'
            }`}
          >
            <Upload className="size-8 mx-auto mb-3 text-muted-foreground" />
            <p className="text-sm text-muted-foreground mb-2">
              Drag and drop your Excel files here, or click to browse
            </p>
            <input
              type="file"
              accept={ACCEPT}
              multiple
              onChange={handleFileSelect}
              className="hidden"
              id="spo-import-files"
            />
            <label htmlFor="spo-import-files">
              <Button type="button" variant="outline" asChild>
                <span>Choose files</span>
              </Button>
            </label>
            <p className="text-xs text-muted-foreground mt-2">.xlsx or .xls only</p>
          </div>
          {files.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                {files.length} file{files.length !== 1 ? 's' : ''} selected
              </p>
              <ul className="max-h-40 overflow-y-auto rounded-md border bg-muted/40 p-2 space-y-1 text-sm">
                {files.map((file, i) => (
                  <li key={`${file.name}-${i}`} className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 truncate">
                      <FileSpreadsheet className="size-4 shrink-0 text-muted-foreground" />
                      {file.name}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-7 shrink-0"
                      onClick={() => removeFile(i)}
                      aria-label={`Remove ${file.name}`}
                    >
                      <X className="size-4" />
                    </Button>
                  </li>
                ))}
              </ul>
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
                                … and {testResult.errors.length - 50} more —{' '}
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
                                … and {testResult.warnings.length - 20} more —{' '}
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
                        … and {testResult.warnings.length - 20} more —{' '}
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
