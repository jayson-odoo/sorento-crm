'use client';

import { useState } from 'react';
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
import { parseExcelSheets } from '@/lib/excel-utils';
import { toast } from 'sonner';
import { Progress } from '@/components/ui/progress';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
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
  accept = '.xlsx,.xls',
}: OrderTrackingUploadDialogProps) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [sheetSummary, setSheetSummary] = useState<{ masterRows: number; trackingRows: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [testResult, setTestResult] = useState<ValidateImportResult | null>(null);

  const validExtensions = accept.split(',').map((ext) => ext.trim().replace(/^\./, ''));
  const validateFileType = (f: File): boolean => {
    const fileExtension = f.name.split('.').pop()?.toLowerCase();
    if (!fileExtension || !validExtensions.includes(fileExtension)) {
      toast.error(`Invalid file type. Please use: ${accept}`);
      return false;
    }
    return true;
  };

  const processFile = async (selectedFile: File) => {
    try {
      setProgress(10);
      const parsed = await parseExcelSheets(selectedFile);
      if (!parsed.sheetNames.includes('Master') || !parsed.sheetNames.includes('Daily Tracking')) {
        toast.error('Excel file must contain both "Master" and "Daily Tracking" sheets.');
        setProgress(0);
        return;
      }
      setSheetSummary({
        masterRows: parsed.sheets['Master']?.length || 0,
        trackingRows: parsed.sheets['Daily Tracking']?.length || 0,
      });
      setFile(selectedFile);
      setTestResult(null);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to read Excel file');
    } finally {
      setProgress(0);
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;
    if (!validateFileType(selectedFile)) return;
    await processFile(selectedFile);
    e.target.value = '';
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isUploading) setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (isUploading) return;
    const droppedFiles = e.dataTransfer?.files;
    if (!droppedFiles?.length) return;
    const droppedFile = droppedFiles[0];
    if (!validateFileType(droppedFile)) return;
    processFile(droppedFile);
    setTestResult(null);
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

  const handleRemoveFile = () => {
    setFile(null);
    setSheetSummary(null);
    setTestResult(null);
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
            Upload an Excel file with Master and Daily Tracking sheets. The system will create or update orders by Doc No.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {!file ? (
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={cn(
                'border-2 border-dashed rounded-lg p-8 text-center transition-colors',
                isDragging
                  ? 'border-primary bg-primary/5'
                  : 'border-muted-foreground/25'
              )}
            >
              <FileSpreadsheet className="size-12 mx-auto mb-4 text-muted-foreground" />
              <p className="text-sm font-medium text-foreground mb-2">
                {isDragging ? 'Drop your file here' : 'or drag and drop'}
              </p>
              <Label htmlFor="order-tracking-upload" className="cursor-pointer">
                <Button variant="outline" asChild>
                  <span>
                    <Upload className="size-4 mr-2" />
                    Choose File
                  </span>
                </Button>
              </Label>
              <input
                id="order-tracking-upload"
                type="file"
                accept={accept}
                onChange={handleFileSelect}
                className="hidden"
              />
              <p className="text-sm text-muted-foreground mt-2">
                Accepted formats: {accept}
              </p>
            </div>
          ) : (
            <div className="border rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileSpreadsheet className="size-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">{file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {(file.size / 1024).toFixed(2)} KB
                    </p>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleRemoveFile}
                  disabled={isUploading}
                >
                  <X className="size-4" />
                </Button>
              </div>
              {sheetSummary && (
                <div className="text-xs text-muted-foreground">
                  Master rows: {sheetSummary.masterRows} • Daily Tracking rows: {sheetSummary.trackingRows}
                </div>
              )}
              {testResult !== null && (
                <div className="mt-3 rounded-md border bg-muted/30 p-3 text-sm">
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
