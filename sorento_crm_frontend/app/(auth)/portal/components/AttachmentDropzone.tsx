'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Paperclip, Upload, X, Clipboard } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import {
  PortalAttachment,
  PortalSubmissionKind,
  deleteAttachment,
  uploadAttachment,
} from '../lib/portal-client';

interface Props {
  kind: PortalSubmissionKind;
  submissionId: string | null;
  attachments: PortalAttachment[];
  onChange: (next: PortalAttachment[]) => void;
  disabled?: boolean;
}

export function AttachmentDropzone({ kind, submissionId, attachments, onChange, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const addFiles = useCallback(
    async (files: File[]) => {
      if (!submissionId) {
        toast.error('Save this submission as draft first to attach files.');
        return;
      }
      if (!files.length) return;
      setBusy(true);
      const next = [...attachments];
      for (const file of files) {
        try {
          const att = await uploadAttachment(kind, submissionId, file);
          next.push(att);
          onChange([...next]);
        } catch (e) {
          toast.error(e instanceof Error ? e.message : 'Upload failed.');
        }
      }
      setBusy(false);
    },
    [attachments, kind, onChange, submissionId]
  );

  const handleSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files ? Array.from(e.target.files) : [];
      void addFiles(files);
      if (inputRef.current) inputRef.current.value = '';
    },
    [addFiles]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);
      if (disabled) return;
      const files = e.dataTransfer.files ? Array.from(e.dataTransfer.files) : [];
      void addFiles(files);
    },
    [addFiles, disabled]
  );

  // Desktop: paste image directly into the page (Ctrl/Cmd+V after screenshot).
  useEffect(() => {
    if (disabled || !submissionId) return;
    const onPaste = (e: ClipboardEvent) => {
      if (!e.clipboardData) return;
      const items = Array.from(e.clipboardData.items);
      const files: File[] = [];
      for (const item of items) {
        if (item.kind === 'file') {
          const file = item.getAsFile();
          if (file) files.push(file);
        }
      }
      if (files.length) {
        e.preventDefault();
        void addFiles(files);
      }
    };
    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
  }, [addFiles, disabled, submissionId]);

  // Mobile: explicit Paste button — iOS/Android Chrome don't fire `paste` reliably
  // without a focused input, so the Async Clipboard API is the path that works.
  const handleClipboardPaste = useCallback(async () => {
    if (typeof navigator === 'undefined' || !navigator.clipboard) {
      toast.error('Clipboard is not available in this browser.');
      return;
    }
    try {
      // navigator.clipboard.read is missing from older TS DOM lib types.
      const reader = (navigator.clipboard as unknown as { read?: () => Promise<unknown[]> }).read;
      if (!reader) {
        toast.error('This browser cannot read clipboard images.');
        return;
      }
      const items = (await reader.call(navigator.clipboard)) as Array<{
        types: string[];
        getType: (t: string) => Promise<Blob>;
      }>;
      const files: File[] = [];
      for (const item of items) {
        const imageType = item.types.find((t: string) => t.startsWith('image/'));
        if (!imageType) continue;
        const blob = await item.getType(imageType);
        const ext = imageType.split('/')[1] || 'png';
        files.push(new File([blob], `pasted-${Date.now()}.${ext}`, { type: imageType }));
      }
      if (!files.length) {
        toast.error('No image found in clipboard.');
        return;
      }
      await addFiles(files);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Clipboard paste failed.');
    }
  }, [addFiles]);

  const handleRemove = useCallback(
    async (linkId: string) => {
      try {
        await deleteAttachment(linkId);
        onChange(attachments.filter((a) => a.link_id !== linkId));
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Failed to remove attachment.');
      }
    },
    [attachments, onChange]
  );

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed p-4 text-center transition ${
          dragOver ? 'border-primary bg-primary/5' : 'border-border'
        } ${disabled ? 'opacity-50 pointer-events-none' : ''}`}
      >
        <Upload className="h-6 w-6 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          Drop a file here, paste a screenshot, or
        </p>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={busy || disabled}
          >
            <Paperclip className="h-4 w-4 mr-2" />
            Choose file
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleClipboardPaste}
            disabled={busy || disabled}
          >
            <Clipboard className="h-4 w-4 mr-2" />
            Paste from clipboard
          </Button>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="image/*,.pdf"
          className="hidden"
          multiple
          onChange={handleSelect}
        />
        {!submissionId && (
          <p className="text-xs text-amber-700">Save as draft first to attach files.</p>
        )}
      </div>
      {attachments.length > 0 && (
        <ul className="space-y-2">
          {attachments.map((a) => (
            <li
              key={a.link_id}
              className="flex items-center justify-between rounded-md border border-border px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium" title={a.filename ?? undefined}>
                  {a.filename || 'Attachment'}
                </p>
                {a.size != null && (
                  <p className="text-xs text-muted-foreground">{(a.size / 1024).toFixed(1)} KB</p>
                )}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => handleRemove(a.link_id)}
                disabled={disabled}
              >
                <X className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
