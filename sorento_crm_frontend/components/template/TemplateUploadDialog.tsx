'use client';

import { useState } from 'react';
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
import { parseExcelFile } from '@/lib/excel-utils';
import { toast } from 'sonner';
import { Progress } from '@/components/ui/progress';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
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
}

export function TemplateUploadDialog({
  open,
  onOpenChange,
  onUpload,
  onTest,
  accept = '.xlsx,.xls',
  maxRows = 100000, // Increased default to 100,000 rows
}: TemplateUploadDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusLabel, setStatusLabel] = useState<string>('');
  const [isDragging, setIsDragging] = useState(false);
  const [testResult, setTestResult] = useState<ValidateImportResult | null>(null);

  const validExtensions = accept.split(',').map((ext) => ext.trim().replace(/^\./, ''));
  const validateFile = (f: File): boolean => {
    const fileExtension = f.name.split('.').pop()?.toLowerCase();
    if (!fileExtension || !validExtensions.includes(fileExtension)) {
      toast.error(`Invalid file type. Please use: ${accept}`);
      return false;
    }
    return true;
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile && validateFile(selectedFile)) {
      setFile(selectedFile);
      setTestResult(null);
    }
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
    if (validateFile(droppedFile)) {
      setFile(droppedFile);
      setTestResult(null);
    }
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

  const handleRemoveFile = () => {
    setFile(null);
    setTestResult(null);
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
          <DialogTitle>Upload Excel File</DialogTitle>
          <DialogDescription>
            Upload an Excel file to create or update records. The file should match the template format.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 min-h-0 flex-1 overflow-y-auto">
          {!file ? (
            <div
              role="button"
              tabIndex={0}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={cn(
                'border-2 border-dashed rounded-lg p-8 text-center transition-colors',
                isDragging
                  ? 'border-primary bg-primary/5'
                  : 'border-muted-foreground/25 hover:border-muted-foreground/40'
              )}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  document.getElementById('file-upload')?.click();
                }
              }}
            >
              <FileSpreadsheet className="size-12 mx-auto mb-4 text-muted-foreground" />
              <Label htmlFor="file-upload" className="cursor-pointer">
                <Button variant="outline" asChild>
                  <span>
                    <Upload className="size-4 mr-2" />
                    Choose File
                  </span>
                </Button>
              </Label>
              <input
                id="file-upload"
                type="file"
                accept={accept}
                onChange={handleFileSelect}
                className="hidden"
              />
              <p className="text-sm text-muted-foreground mt-2">
                {isDragging ? 'Drop your file here' : 'or drag and drop your file here'}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Accepted formats: {accept}
              </p>
            </div>
          ) : (
            <div className="border rounded-lg p-4">
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
            </div>
          )}
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
                </p>
              )}
              {testResult.valid ? (
                <Alert className="border-green-200 bg-green-50 text-green-900">
                  <CheckCircle className="h-4 w-4 text-green-600" />
                  <AlertTitle>No errors</AlertTitle>
                  <AlertDescription>You can upload this file.</AlertDescription>
                </Alert>
              ) : (
                <>
                  {testResult.errors.length > 0 && (
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
                  )}
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
                </>
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
          <Button onClick={handleUpload} disabled={!file || isUploading}>
            <Upload className="size-4 mr-2" />
            {isUploading ? 'Uploading...' : 'Upload'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
