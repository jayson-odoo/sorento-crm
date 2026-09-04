'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Upload, TestTube } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { parseExcelSheets } from '@/lib/excel-utils';
import { useExcelAccept } from '@/hooks/use-excel-accept';
import { toast } from '@/lib/toast';
import { Progress } from '@/components/ui/progress';
import { FileDropzone } from '@/components/common/FileDropzone';
import type { ValidateImportResult } from '../services/orderService';

type ImportResult = {
  job_id: string;
  status: string;
  message: string;
};

interface OrderTrackingUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onTest?: (file: File) => Promise<ValidateImportResult>;
  onUpload: (file: File) => Promise<ImportResult>;
  accept?: string;
}

export function OrderTrackingUploadDialog({
  open,
  onOpenChange,
  onTest,
  onUpload,
  accept: acceptProp,
}: OrderTrackingUploadDialogProps) {
  const acceptFromSettings = useExcelAccept();
  // Macro workbooks supported: backend strips VBA via maybe_strip and reads
  // the named Master / Overall Tracking sheets (PLAN-do-macro-upload).
  const accept = acceptProp ?? acceptFromSettings;
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [sheetSummary, setSheetSummary] = useState<{ masterRows: number; trackingRows: number } | null>(null);
  const [testResult, setTestResult] = useState<ValidateImportResult | null>(null);

  const processFile = async (selectedFile: File) => {
    try {
      setProgress(10);
      const parsed = await parseExcelSheets(selectedFile);
      if (!parsed.sheetNames.includes('Master') || !parsed.sheetNames.includes('Overall Tracking')) {
        toast.error('Excel file must contain both "Master" and "Overall Tracking" sheets.');
        setProgress(0);
        return;
      }
      setSheetSummary({
        masterRows: parsed.sheets['Master']?.length || 0,
        trackingRows: parsed.sheets['Overall Tracking']?.length || 0,
      });
      setFile(selectedFile);
      setTestResult(null);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to read Excel file');
    } finally {
      setProgress(0);
    }
  };

  const handleRemoveFile = () => {
    setFile(null);
    setSheetSummary(null);
    setTestResult(null);
  };

  // The file is only held once its sheets check out, so a rejected workbook
  // leaves the zone empty rather than parking an unusable file in it.
  const handleFilesChange = (files: File[]) => {
    const selected = files[0];
    if (!selected) {
      handleRemoveFile();
      return;
    }
    void processFile(selected);
  };

  const handleUpload = async () => {
    if (!file) {
      toast.error('Please select a file to upload');
      return;
    }

    setIsUploading(true);
    setProgress(0);

    try {
      setProgress(40);
      const importResult = await onUpload(file);
      setProgress(100);
      onOpenChange(false);
      setFile(null);
      setSheetSummary(null);
      toast.success('Import job queued. You can track progress on the import job page.', {
        duration: 5000,
        action: {
          label: 'View Status',
          onClick: () => router.push(`/system-management/import-jobs/${importResult.job_id}`),
        },
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to upload file');
    } finally {
      setIsUploading(false);
      setProgress(0);
    }
  };

  const handleTest = async () => {
    if (!file || !onTest) return;
    setIsTesting(true);
    setTestResult(null);
    try {
      const result = await onTest(file);
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Import Delivery Order Tracking</DialogTitle>
          <DialogDescription>
            Upload an Excel file with Master and Overall Tracking sheets. The system will create or update orders by Doc No.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <FileDropzone
            accept={accept}
            disabled={isUploading}
            files={file ? [file] : []}
            onFilesChange={handleFilesChange}
            onReject={() => toast.error(`Invalid file type. Please use: ${accept}`)}
            title="Drop the Excel file here, or click to browse"
            hint={`Accepted formats: ${accept}`}
            aria-label="Delivery order tracking workbook"
          />
          {(sheetSummary || testResult) && (
            <div className="border rounded-lg p-4 space-y-3">
              {sheetSummary && (
                <div className="text-xs text-muted-foreground">
                  Master rows: {sheetSummary.masterRows} • Overall Tracking rows: {sheetSummary.trackingRows}
                </div>
              )}
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
                        {(testResult.errors.slice(0, 50) as string[]).map((err, i) => (
                          <li key={i}>{err}</li>
                        ))}
                        {(testResult.errors.length as number) > 50 && (
                          <li>… and {testResult.errors.length - 50} more</li>
                        )}
                      </ul>
                    </div>
                  ) : null}
                  {testResult.warnings?.length ? (
                    <div className="mt-2 max-h-24 overflow-y-auto">
                      <p className="font-medium text-amber-600 dark:text-amber-500">Warnings ({testResult.warnings.length}):</p>
                      <ul className="list-disc pl-4 text-amber-600 dark:text-amber-500">
                        {(testResult.warnings.slice(0, 20) as string[]).map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                        {(testResult.warnings.length as number) > 20 && (
                          <li>… and {testResult.warnings.length - 20} more</li>
                        )}
                      </ul>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          )}
          {isUploading && (
            <div className="space-y-2">
              <Progress value={progress} />
              <p className="text-xs text-muted-foreground text-center">
                Processing file... {progress}%
              </p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isUploading}>
            Close
          </Button>
          {onTest && (
            <Button
              variant="outline"
              onClick={handleTest}
              disabled={!file || isUploading || isTesting}
            >
              <TestTube className="size-4 mr-2" />
              {isTesting ? 'Testing...' : 'Test'}
            </Button>
          )}
          <Button onClick={handleUpload} disabled={!file || isUploading}>
            <Upload className="size-4 mr-2" />
            {isUploading ? 'Uploading...' : 'Import'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
