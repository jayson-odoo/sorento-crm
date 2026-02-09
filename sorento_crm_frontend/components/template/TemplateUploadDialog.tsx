'use client';

import { useState } from 'react';
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
import { parseExcelFile } from '@/lib/excel-utils';
import { toast } from 'sonner';
import { Progress } from '@/components/ui/progress';
import { Label } from '@/components/ui/label';

export interface TemplateUploadHelpers {
  setProgress: (percent: number) => void;
  setStatus?: (label: string) => void;
}

interface TemplateUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpload: (data: any[], helpers?: TemplateUploadHelpers) => Promise<void>;
  accept?: string;
  maxRows?: number; // If undefined, no limit
}

export function TemplateUploadDialog({
  open,
  onOpenChange,
  onUpload,
  accept = '.xlsx,.xls',
  maxRows = 100000, // Increased default to 100,000 rows
}: TemplateUploadDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusLabel, setStatusLabel] = useState<string>('');

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      // Validate file type
      const validExtensions = accept.split(',').map(ext => ext.trim().replace('.', ''));
      const fileExtension = selectedFile.name.split('.').pop()?.toLowerCase();
      if (!fileExtension || !validExtensions.includes(fileExtension)) {
        toast.error(`Invalid file type. Please upload a file with extension: ${accept}`);
        return;
      }
      setFile(selectedFile);
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
      await onUpload(data, helpers);

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
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload Excel File</DialogTitle>
          <DialogDescription>
            Upload an Excel file to create or update records. The file should match the template format.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {!file ? (
            <div className="border-2 border-dashed border-muted-foreground/25 rounded-lg p-8 text-center">
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
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isUploading}>
            Cancel
          </Button>
          <Button onClick={handleUpload} disabled={!file || isUploading}>
            <Upload className="size-4 mr-2" />
            {isUploading ? 'Uploading...' : 'Upload'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
