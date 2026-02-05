'use client';

import { useState } from 'react';
import { Upload, X, FileSpreadsheet, AlertTriangle } from 'lucide-react';
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

type ImportResult = {
  job_id: string;
  status: string;
  message: string;
};

interface OrderTrackingUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpload: (file: File) => Promise<ImportResult>;
  accept?: string;
}

export function OrderTrackingUploadDialog({
  open,
  onOpenChange,
  onUpload,
  accept = '.xlsx,.xls',
}: OrderTrackingUploadDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [sheetSummary, setSheetSummary] = useState<{ masterRows: number; trackingRows: number } | null>(null);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;

    const validExtensions = accept.split(',').map(ext => ext.trim().replace('.', ''));
    const fileExtension = selectedFile.name.split('.').pop()?.toLowerCase();
    if (!fileExtension || !validExtensions.includes(fileExtension)) {
      toast.error(`Invalid file type. Please upload a file with extension: ${accept}`);
      return;
    }

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
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to read Excel file');
    } finally {
      setProgress(0);
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
      setProgress(40);
      const importResult = await onUpload(file);
      setProgress(100);
      // Job has been queued - show success message and close dialog
      toast.success('Import job queued successfully. Processing in background. Please refresh after a while to see results.', {
        duration: 5000,
      });
      onOpenChange(false);
      setFile(null);
      setSheetSummary(null);
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
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Import Order Tracking</DialogTitle>
          <DialogDescription>
            Upload an Excel file with Master and Daily Tracking sheets. The system will create or update orders by Doc No.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {!file ? (
            <div className="border-2 border-dashed border-muted-foreground/25 rounded-lg p-8 text-center">
              <FileSpreadsheet className="size-12 mx-auto mb-4 text-muted-foreground" />
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
          <Button onClick={handleUpload} disabled={!file || isUploading}>
            <Upload className="size-4 mr-2" />
            {isUploading ? 'Uploading...' : 'Import'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
