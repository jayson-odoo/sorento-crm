'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Upload, FileSpreadsheet, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import type { GRNImportResult } from '../services/grnService';

const ACCEPT = '.xlsx,.xls';

interface GRNImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  onUpload: (file: File) => Promise<GRNImportResult>;
}

export function GRNImportDialog({
  open,
  onOpenChange,
  title,
  description,
  onUpload,
}: GRNImportDialogProps) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const validExtensions = ACCEPT.split(',').map((ext) => ext.trim().replace('.', ''));
  const isValidFile = (f: File) => {
    const ext = f.name.split('.').pop()?.toLowerCase();
    return ext && validExtensions.includes(ext);
  };

  const handleFiles = useCallback((files: FileList | File[]) => {
    const list = Array.from(files);
    const first = list.find(isValidFile);
    if (!first) {
      toast.error('Only .xlsx and .xls files are allowed.');
      return;
    }
    if (list.length > 1) {
      toast.info('Using first Excel file only.');
    }
    setFile(first);
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

  const handleUpload = () => {
    if (!file) {
      toast.error('Please select an Excel file.');
      return;
    }
    // Close dialog immediately; processing runs in background; toast when queued
    const fileToUpload = file;
    onOpenChange(false);
    setFile(null);

    onUpload(fileToUpload)
      .then((result) => {
        toast.success('Import queued. Processing in the background.', {
          duration: 6000,
          action: {
            label: 'View job',
            onClick: () => router.push(`/system-management/import-jobs/${result.job_id}`),
          },
        });
      })
      .catch((error) => {
        toast.error(error instanceof Error ? error.message : 'Upload failed');
      });
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) setFile(null);
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
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
              Drag and drop your Excel file here, or click to browse
            </p>
            <input
              type="file"
              accept={ACCEPT}
              onChange={handleFileSelect}
              className="hidden"
              id="grn-import-file"
            />
            <label htmlFor="grn-import-file">
              <Button type="button" variant="outline" asChild>
                <span>Choose file</span>
              </Button>
            </label>
            <p className="text-xs text-muted-foreground mt-2">.xlsx or .xls only</p>
          </div>
          {file && (
            <div className="flex items-center justify-between gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm">
              <span className="flex items-center gap-2 truncate">
                <FileSpreadsheet className="size-4 shrink-0 text-muted-foreground" />
                {file.name}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-7 shrink-0"
                onClick={() => setFile(null)}
                aria-label="Remove file"
              >
                <X className="size-4" />
              </Button>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleUpload} disabled={!file}>
            Upload
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
