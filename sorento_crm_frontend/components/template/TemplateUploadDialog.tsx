'use client';

import { useState } from 'react';
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
import { parseExcelFile } from '@/lib/excel-utils';
import { useExcelAccept } from '@/hooks/use-excel-accept';
import { toast } from '@/lib/toast';
import { Progress } from '@/components/ui/progress';
import { FileDropzone } from '@/components/common/FileDropzone';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { AlertCircle, AlertTriangle, CheckCircle } from 'lucide-react';

export interface TemplateUploadHelpers {
  setProgress: (percent: number) => void;
  setStatus?: (label: string) => void;
}

export interface ValidateImportResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary?: Record<string, unknown>;
}

interface TemplateUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpload: (data: any[], helpers?: TemplateUploadHelpers, file?: File) => Promise<void>;
  /** When provided, a Test button is shown. Runs validation only and displays errors/warnings inline. */
  onTest?: (data: any[], file?: File) => Promise<ValidateImportResult>;
  accept?: string;
  maxRows?: number; // If undefined, no limit
  /** Override the dialog heading. Default: the generic Excel-upload copy. */
  title?: string;
  /** Override the sub-heading. Default: the generic Excel-upload copy. */
  description?: string;
}

export function TemplateUploadDialog({
  open,
  onOpenChange,
  onUpload,
  onTest,
  accept: acceptProp,
  maxRows = 100000, // Increased default to 100,000 rows
  title = 'Upload Excel File',
  description = 'Upload an Excel file to create or update records. The file should match the template format.',
}: TemplateUploadDialogProps) {
  const acceptFromSettings = useExcelAccept();
  const accept = acceptProp ?? acceptFromSettings;
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusLabel, setStatusLabel] = useState<string>('');
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
    setProgress(0);

    try {
      // Parse Excel file
      setProgress(25);
      const data = await parseExcelFile(file);
      
      if (data.length === 0) {
        toast.error('The Excel file is empty');
        setIsUploading(false);
        return;
      }

      if (maxRows !== undefined && data.length > maxRows) {
        toast.error(`File contains too many rows. Maximum allowed: ${maxRows.toLocaleString()}`);
        setIsUploading(false);
        return;
      }

      setProgress(10);
      setStatusLabel('Uploading…');

      const helpers: TemplateUploadHelpers = {
        setProgress,
        setStatus: setStatusLabel,
      };
      await onUpload(data, helpers, file);

      setProgress(100);
      setStatusLabel('Complete');
      // Dialog will be closed by the handler, but ensure it closes
      onOpenChange(false);
      setFile(null);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to upload file');
    } finally {
      setIsUploading(false);
      setProgress(0);
      setStatusLabel('');
    }
  };

  const handleTest = async () => {
    if (!file || !onTest) return;
    setIsTesting(true);
    setTestResult(null);
    try {
      const data = await parseExcelFile(file);
      if (data.length === 0) {
        toast.error('The Excel file is empty');
        return;
      }
      if (maxRows !== undefined && data.length > maxRows) {
        toast.error(`File contains too many rows. Maximum allowed: ${maxRows.toLocaleString()}`);
        return;
      }
      const result = await onTest(data, file);
      setTestResult(result);
      if (result.valid) {
        toast.success('Validation passed. You can upload when ready.');
      } else {
        toast.warning(`Validation found ${result.errors.length} error(s). Review below or upload anyway.`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Validation failed');
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] flex flex-col">
        <DialogHeader className="shrink-0">
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 min-h-0 flex-1 overflow-y-auto">
          <FileDropzone
            id="file-upload"
            accept={accept}
            disabled={isUploading}
            files={file ? [file] : []}
            onFilesChange={handleFilesChange}
            onReject={() => toast.error(`Invalid file type. Please use: ${accept}`)}
            title="Drop the Excel file here, or click to browse"
            hint={`Accepted formats: ${accept}`}
            aria-label="Excel file"
          />
          {isUploading && (
            <div className="space-y-2">
              <Progress value={progress} />
              <p className="text-xs text-muted-foreground text-center">
                {statusLabel || 'Processing file…'} {progress}%
              </p>
            </div>
          )}
          {testResult && (
            <div className="space-y-2 rounded-lg border p-3">
              <p className="text-sm font-medium">Validation result</p>
              {testResult.summary && typeof testResult.summary === 'object' && (
                <p className="text-xs text-muted-foreground">
                  {testResult.summary.total_rows != null && `Rows: ${testResult.summary.total_rows}`}
                  {testResult.summary.would_create != null && ` • Would create: ${testResult.summary.would_create}`}
                  {testResult.summary.would_update != null && ` • Would update: ${testResult.summary.would_update}`}
                  {testResult.summary.error_count != null && ` • Errors: ${testResult.summary.error_count}`}
                  {/* Master data the import will create for itself. */}
                  {testResult.summary.new_categories != null &&
                    ` • New categories: ${testResult.summary.new_categories}`}
                  {testResult.summary.new_brands != null && ` • New brands: ${testResult.summary.new_brands}`}
                  {testResult.summary.new_uoms != null && ` • New UOMs: ${testResult.summary.new_uoms}`}
                </p>
              )}
              {testResult.valid ? (
                <Alert className="border-green-200 bg-green-50 text-green-900">
                  <CheckCircle className="h-4 w-4 text-green-600" />
                  <AlertTitle>No errors</AlertTitle>
                  <AlertDescription>You can upload this file.</AlertDescription>
                </Alert>
              ) : (
                testResult.errors.length > 0 && (
                  <Alert variant="destructive" className="flex flex-col items-stretch">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    <div className="min-w-0 flex-1 space-y-1">
                      <AlertTitle>Errors ({testResult.errors.length})</AlertTitle>
                      <AlertDescription className="p-0">
                        <ScrollArea className="h-[280px] w-full rounded border border-red-300 bg-red-950/20 p-2 text-sm">
                          <ul className="list-inside list-disc space-y-0.5 pr-2">
                            {testResult.errors.map((err, i) => (
                              <li key={i}>{err}</li>
                            ))}
                          </ul>
                        </ScrollArea>
                      </AlertDescription>
                    </div>
                  </Alert>
                )
              )}
              {/* Warnings render whether or not the file is valid - a clean file can
                  still carry "N new categories will be created", which the operator
                  must see BEFORE uploading. */}
              {testResult.warnings.length > 0 && (
                <Alert className="border-amber-200 bg-amber-50 text-amber-900">
                  <AlertTriangle className="h-4 w-4 text-amber-600" />
                  <AlertTitle>Warnings ({testResult.warnings.length})</AlertTitle>
                  <AlertDescription className="p-0">
                    <ScrollArea className="h-[160px] w-full rounded border p-2 text-sm">
                      <ul className="list-inside list-disc space-y-0.5 pr-2">
                        {testResult.warnings.map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                    </ScrollArea>
                  </AlertDescription>
                </Alert>
              )}
            </div>
          )}
        </div>
        <DialogFooter className="shrink-0">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isUploading}>
            Cancel
          </Button>
          {onTest && (
            <Button
              type="button"
              variant="outline"
              data-guide-target="template-upload.test-button"
              onClick={handleTest}
              disabled={!file || isUploading || isTesting}
            >
              {isTesting ? (
                'Testing…'
              ) : (
                <>
                  <TestTube className="size-4 mr-2" />
                  Test
                </>
              )}
            </Button>
          )}
          <Button onClick={handleUpload} disabled={!file || isUploading} data-guide-target="template-upload.confirm-button">
            <Upload className="size-4 mr-2" />
            {isUploading ? 'Uploading...' : 'Upload'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
