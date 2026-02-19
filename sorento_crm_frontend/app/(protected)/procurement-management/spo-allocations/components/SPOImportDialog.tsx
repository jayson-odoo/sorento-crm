'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Upload, X, FileSpreadsheet, Loader2 } from 'lucide-react';
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
import type { SPOImportResult } from '../services/spoAllocationService';

const ACCEPT = '.xlsx,.xls';

interface SPOImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpload: (files: File[]) => Promise<SPOImportResult>;
}

export function SPOImportDialog({
  open,
  onOpenChange,
  onUpload,
}: SPOImportDialogProps) {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  const validExtensions = ACCEPT.split(',').map((ext) => ext.trim().replace('.', ''));
  const isValidFile = (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase();
    return ext && validExtensions.includes(ext);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files ?? []);
    const valid = selected.filter(isValidFile);
    const invalid = selected.filter((f) => !isValidFile(f));
    if (invalid.length > 0) {
      toast.error(`Skipped ${invalid.length} file(s): only .xlsx and .xls are allowed.`);
    }
    if (valid.length > 0) {
      setFiles((prev) => {
        const names = new Set(prev.map((f) => f.name));
        const added = valid.filter((f) => !names.has(f.name));
        return [...prev, ...added];
      });
    }
    e.target.value = '';
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (files.length === 0) {
      toast.error('Please select at least one Excel file.');
      return;
    }

    setIsUploading(true);
    try {
      const result = await onUpload(files);
      onOpenChange(false);
      setFiles([]);
      const count = result.job_ids?.length ?? 0;
      toast.success(result.message ?? `${count} import job(s) queued.`, {
        duration: 5000,
        action:
          count > 0
            ? {
                label: 'View import jobs',
                onClick: () =>
                  router.push(
                    count === 1
                      ? `/system-management/import-jobs/${result.job_ids[0]}`
                      : '/system-management/import-jobs'
                  ),
              }
            : undefined,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to upload files');
    } finally {
      setIsUploading(false);
    }
  };

  const handleOpenChange = (next: boolean) => {
    if (!next && !isUploading) {
      setFiles([]);
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
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <input
              type="file"
              accept={ACCEPT}
              multiple
              onChange={handleFileSelect}
              className="hidden"
              id="spo-import-files"
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => document.getElementById('spo-import-files')?.click()}
              disabled={isUploading}
            >
              <Upload className="mr-2 size-4" />
              Select files
            </Button>
            <span className="text-muted-foreground text-sm">
              {files.length === 0 ? 'No files selected' : `${files.length} file(s) selected`}
            </span>
          </div>
          {files.length > 0 && (
            <ul className="max-h-40 overflow-y-auto rounded-md border p-2 space-y-1 text-sm">
              {files.map((file, i) => (
                <li key={`${file.name}-${i}`} className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2 truncate">
                    <FileSpreadsheet className="size-4 shrink-0 text-muted-foreground" />
                    {file.name}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0 shrink-0"
                    onClick={() => removeFile(i)}
                    disabled={isUploading}
                    aria-label={`Remove ${file.name}`}
                  >
                    <X className="size-4" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={isUploading}>
            Cancel
          </Button>
          <Button onClick={handleUpload} disabled={files.length === 0 || isUploading}>
            {isUploading ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                Uploading…
              </>
            ) : (
              'Import'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
