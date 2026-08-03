'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Loader2, CheckCircle, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Alert, AlertDescription, AlertIcon } from '@/components/ui/alert';
import { AlertCircle } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { useBulkImportAttachment, useAttachmentTypesList, useDirectoryTree } from '../hooks/useAttachments';
import { getJobStatus } from '../services/attachmentService';
import { useContactAccessTypes } from '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes';
import { FileDropzone } from '@/components/common/FileDropzone';
import type { JobStatusResponse } from '../services/attachmentService';
import type { AttachmentType } from '../../attachment-types/types/attachmentType.types';
import type { AttachmentDirectoryTreeNode } from '../services/directoryService';
import { useQueryClient } from '@tanstack/react-query';

interface AttachmentBulkImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
  /** When set, the ZIP root will be placed under this folder. */
  defaultParentDirectoryId?: string | null;
}

function flattenTree(nodes: AttachmentDirectoryTreeNode[], depth = 0): Array<{ id: string; name: string; depth: number }> {
  const result: Array<{ id: string; name: string; depth: number }> = [];
  for (const node of nodes) {
    result.push({ id: node.id, name: node.name, depth });
    if (node.children?.length) {
      result.push(...flattenTree(node.children, depth + 1));
    }
  }
  return result;
}

export default function AttachmentBulkImportDialog({
  open,
  onOpenChange,
  onSuccess,
  defaultParentDirectoryId,
}: AttachmentBulkImportDialogProps) {
  const [selectedTypeId, setSelectedTypeId] = useState('');
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [parentDirectoryId, setParentDirectoryId] = useState<string>('');
  const { data: accessTypeOptions = [] } = useContactAccessTypes();
  const defaultAccessLevels = accessTypeOptions.length > 0 ? accessTypeOptions.map((o) => o.code) : ['dealer', 'end_user'];
  const [accessLevels, setAccessLevels] = useState<string[]>([]);
  const [validationError, setValidationError] = useState('');
  const [phase, setPhase] = useState<'form' | 'processing' | 'done'>('form');
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatusResponse | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const queryClient = useQueryClient();
  const { data: attachmentTypes = [], isLoading: isLoadingTypes } = useAttachmentTypesList();
  const { data: directoryTree = [] } = useDirectoryTree();
  const bulkImportMutation = useBulkImportAttachment();

  useEffect(() => {
    if (accessLevels.length === 0 && defaultAccessLevels.length > 0) {
      setAccessLevels(defaultAccessLevels);
    }
  }, [defaultAccessLevels, accessLevels.length]);

  useEffect(() => {
    if (!open) {
      setSelectedTypeId('');
      setZipFile(null);
      setParentDirectoryId(defaultParentDirectoryId ?? '');
      setAccessLevels(defaultAccessLevels);
      setValidationError('');
      setPhase('form');
      setJobId(null);
      setJobStatus(null);
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    } else if (defaultParentDirectoryId !== undefined) {
      setParentDirectoryId(defaultParentDirectoryId ?? '');
    }
  }, [open, defaultParentDirectoryId, defaultAccessLevels.join(',')]);

  // Poll job status when processing
  useEffect(() => {
    if (phase !== 'processing' || !jobId) return;

    const poll = async () => {
      try {
        const data = await getJobStatus(jobId);
        setJobStatus(data);
        if (data.status === 'finished' || data.status === 'failed') {
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
          }
          setPhase('done');
          queryClient.invalidateQueries({ queryKey: ['attachments'] });
          queryClient.invalidateQueries({ queryKey: ['attachment-directories-tree'] });
        }
      } catch {
        // ignore poll errors
      }
    };

    poll();
    pollIntervalRef.current = setInterval(poll, 2000);
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [phase, jobId, queryClient]);

  const flatDirs = flattenTree(directoryTree);

  const handleFilesChange = useCallback((files: File[]) => {
    const file = files[0] ?? null;
    if (file) setValidationError('');
    setZipFile(file);
  }, []);

  const handleSubmit = async () => {
    if (!selectedTypeId) {
      setValidationError('Please select an attachment type');
      return;
    }
    if (!zipFile) {
      setValidationError('Please select a ZIP file');
      return;
    }

    setValidationError('');
    try {
      const result = await bulkImportMutation.mutateAsync({
        zipFile,
        attachmentTypeId: selectedTypeId,
        accessLevels,
        parentDirectoryId: parentDirectoryId || undefined,
      });
      setJobId(result.job_id);
      setPhase('processing');
    } catch {
      // Error shown by mutation toast
    }
  };

  const isUploading = bulkImportMutation.isPending;

  const handleClose = () => {
    onSuccess?.();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Bulk import (ZIP)</DialogTitle>
        </DialogHeader>
        {phase === 'form' && (
          <>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label>
              Attachment type <span className="text-destructive">*</span>
            </Label>
            <SearchableSelect
              value={selectedTypeId}
              onChange={(v) => {
                setSelectedTypeId(v);
                setValidationError('');
              }}
              options={attachmentTypes.map((t: AttachmentType) => ({
                value: t.id,
                label: t.type_name,
              }))}
              placeholder="Select type"
              disabled={isLoadingTypes}
            />
          </div>

          <div className="space-y-2">
            <Label>Import into folder</Label>
            <SearchableSelect
              value={parentDirectoryId || 'root'}
              onChange={(v) => setParentDirectoryId(v === 'root' ? '' : v)}
              options={[
                { value: 'root', label: 'Root (no folder)' },
                ...flatDirs.map((d) => ({
                  value: d.id,
                  label: `${'  '.repeat(d.depth)}${d.name}`,
                  searchText: d.name,
                })),
              ]}
              placeholder="Root"
            />
          </div>

          <div className="space-y-2">
            <Label>Access levels</Label>
            <div className="flex flex-wrap gap-4">
              {accessTypeOptions.map((opt) => (
                <label key={opt.code} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={accessLevels.includes(opt.code)}
                    onCheckedChange={(checked) => {
                      const next = new Set(accessLevels);
                      if (checked) next.add(opt.code);
                      else next.delete(opt.code);
                      setAccessLevels(Array.from(next));
                    }}
                  />
                  {opt.name || opt.code}
                </label>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <Label>
              ZIP file <span className="text-destructive">*</span>
            </Label>
            <FileDropzone
              accept=".zip"
              files={zipFile ? [zipFile] : []}
              onFilesChange={handleFilesChange}
              onReject={() => setValidationError('Please select a ZIP file')}
              title="Drag and drop a ZIP file here, or click to select"
              hint="ZIP archive"
              aria-label="ZIP file"
            />
          </div>

          {validationError && (
            <Alert variant="destructive">
              <AlertIcon>
                <AlertCircle className="size-4" />
              </AlertIcon>
              <AlertDescription>{validationError}</AlertDescription>
            </Alert>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isUploading}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!selectedTypeId || !zipFile || isUploading}
            data-guide-target="resource-management.files.bulk-import-confirm-button"
          >
            {isUploading ? 'Starting…' : 'Import ZIP'}
          </Button>
        </DialogFooter>
          </>
        )}

        {phase === 'processing' && (
          <div className="space-y-4 py-4">
            <div className="flex items-center gap-3">
              <Loader2 className="size-6 animate-spin text-primary" />
              <span className="text-sm font-medium">Processing import in background…</span>
            </div>
            {jobStatus?.progress && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm text-muted-foreground">
                  <span>Files: {jobStatus.progress.processed} / {jobStatus.progress.total}</span>
                  <span>{jobStatus.progress.percentage}%</span>
                </div>
                <Progress value={jobStatus.progress.percentage} className="h-2" />
              </div>
            )}
            <p className="text-xs text-muted-foreground">You can close this dialog. Import will continue in the background.</p>
          </div>
        )}

        {phase === 'done' && jobStatus && (
          <div className="space-y-4 py-4">
            {jobStatus.status === 'finished' ? (
              <>
                <div className="flex items-center gap-3 text-green-600">
                  <CheckCircle className="size-6" />
                  <span className="font-medium">Import completed</span>
                </div>
                {jobStatus.result && (
                  <div className="text-sm text-muted-foreground space-y-1">
                    <p>Directories: {jobStatus.result.directories_created ?? 0}</p>
                    <p>Attachments created: {jobStatus.result.attachments_created ?? 0}</p>
                    {(jobStatus.result.errors?.length ?? 0) > 0 && (
                      <details className="text-amber-600">
                        <summary className="cursor-pointer">
                          View errors ({jobStatus.result.errors?.length})
                        </summary>
                        <ul className="mt-2 max-h-48 overflow-auto space-y-1 text-xs text-muted-foreground list-disc pl-5">
                          {(jobStatus.result.errors ?? []).map((err, i) => (
                            <li key={i} title={err}>{err}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </div>
                )}
              </>
            ) : (
              <>
                <div className="flex items-center gap-3 text-destructive">
                  <XCircle className="size-6" />
                  <span className="font-medium">Import failed</span>
                </div>
                {jobStatus.error && (
                  <p className="text-sm text-muted-foreground">{jobStatus.error}</p>
                )}
              </>
            )}
            <DialogFooter>
              <Button onClick={handleClose}>Close</Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
