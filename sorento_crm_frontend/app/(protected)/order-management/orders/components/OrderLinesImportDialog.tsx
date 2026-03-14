'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Upload, X, FileSpreadsheet } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { importDeliveryOrderDetail } from '../services/orderService';

interface OrderLinesImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

const ACCEPT = '.xlsx,.xls';

export function OrderLinesImportDialog({
  open,
  onOpenChange,
  onSuccess,
}: OrderLinesImportDialogProps) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [isDragging, setIsDragging] = useState(false);

  const validExtensions = ACCEPT.split(',').map((ext) => ext.trim().replace(/^\./, ''));
  const validateFileType = (f: File): boolean => {
    const fileExtension = f.name.split('.').pop()?.toLowerCase();
    if (!fileExtension || !validExtensions.includes(fileExtension)) {
      toast.error(`Invalid file type. Please use: ${ACCEPT}`);
      return false;
    }
    return true;
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;
    if (!validateFileType(selectedFile)) return;
    setFile(selectedFile);
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
    if (!validateFileType(droppedFiles[0])) return;
    setFile(droppedFiles[0]);
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
      toast.success('Import job queued. Check "Latest order lines import" below for status.', {
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

  const handleRemoveFile = () => {
    setFile(null);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Import delivery order detail (order lines)</DialogTitle>
          <DialogDescription>
            Upload an Excel file with delivery order lines. Columns: <strong>Doc No</strong> (or Order Number), <strong>Item Code</strong> (or Product Code), <strong>Location</strong> (or Warehouse). Optional: Qty, Unit Price, Discount, Total, Tax, Total Excluding Tax, Total Including Tax. Rows are matched to orders by Doc No and upserted as order lines.
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
                isDragging ? 'border-primary bg-primary/5' : 'border-muted-foreground/25',
              )}
            >
              <FileSpreadsheet className="size-12 mx-auto mb-4 text-muted-foreground" />
              <p className="text-sm font-medium text-foreground mb-2">
                {isDragging ? 'Drop your file here' : 'Drag and drop or choose file'}
              </p>
              <Label htmlFor="order-lines-upload" className="cursor-pointer">
                <Button variant="outline" asChild>
                  <span>
                    <Upload className="size-4 mr-2" />
                    Choose File
                  </span>
                </Button>
              </Label>
              <input
                id="order-lines-upload"
                type="file"
                accept={ACCEPT}
                onChange={handleFileSelect}
                className="hidden"
              />
              <p className="text-sm text-muted-foreground mt-2">Accepted: .xlsx, .xls</p>
            </div>
          ) : (
            <div className="border rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileSpreadsheet className="size-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">{file.name}</p>
                    <p className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(2)} KB</p>
                  </div>
                </div>
                <Button variant="ghost" size="sm" onClick={handleRemoveFile} disabled={isUploading}>
                  <X className="size-4" />
                </Button>
              </div>
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
          <Button onClick={handleUpload} disabled={!file || isUploading}>
            <Upload className="size-4 mr-2" />
            {isUploading ? 'Queuing…' : 'Import'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
