'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Upload, TestTube } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { FileDropzone } from '@/components/common/FileDropzone';
import { toast } from '@/lib/toast';
import { importDeliveryOrderDetail } from '../services/orderService';
import { useExcelAccept } from '@/hooks/use-excel-accept';
import type { ValidateImportResult } from '../services/orderService';

interface OrderLinesImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
  onTest?: (file: File) => Promise<ValidateImportResult>;
}

export function OrderLinesImportDialog({
  open,
  onOpenChange,
  onSuccess,
  onTest,
}: OrderLinesImportDialogProps) {
  const router = useRouter();
  const ACCEPT = useExcelAccept();
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<ValidateImportResult | null>(null);

  const handleFilesChange = (files: File[]) => {
    setFile(files[0] ?? null);
    setTestResult(null);
  };

  const handleUpload = async () => {
    if (!file) {
      toast.error('Please select a file to upload');
      return;
    }

    setIsUploading(true);
    setProgress(30);

    try {
      const result = await importDeliveryOrderDetail(file);
      setProgress(100);
      onOpenChange(false);
      setFile(null);
      onSuccess?.();
      toast.success('Import job queued. Check System → Import jobs for status.', {
        duration: 5000,
        action: {
          label: 'View job',
          onClick: () => router.push(`/system-management/import-jobs/${result.job_id}`),
        },
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to queue import');
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
          <DialogTitle>Import delivery order lines</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <FileDropzone
            accept={ACCEPT}
            disabled={isUploading}
            files={file ? [file] : []}
            onFilesChange={handleFilesChange}
            onReject={() => toast.error(`Invalid file type. Please use: ${ACCEPT}`)}
            title="Drop the Excel file here, or click to browse"
            hint={`Accepted: ${ACCEPT}`}
            aria-label="Delivery order lines workbook"
          />
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
                    {testResult.errors.slice(0, 50).map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                    {testResult.errors.length > 50 && (
                      <li>... and {testResult.errors.length - 50} more</li>
                    )}
                  </ul>
                </div>
              ) : null}
            </div>
          )}
          {isUploading && (
            <div className="space-y-2">
              <Progress value={progress} />
              <p className="text-xs text-muted-foreground text-center">Queuing import…</p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isUploading}>
            Cancel
          </Button>
          {onTest && (
            <Button variant="outline" onClick={handleTest} disabled={!file || isUploading || isTesting}>
              <TestTube className="size-4 mr-2" />
              {isTesting ? 'Testing...' : 'Test'}
            </Button>
          )}
          <Button onClick={handleUpload} disabled={!file || isUploading}>
            <Upload className="size-4 mr-2" />
            {isUploading ? 'Queuing…' : 'Import'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
