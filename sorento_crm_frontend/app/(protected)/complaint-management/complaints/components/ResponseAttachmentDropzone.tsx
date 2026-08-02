'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Clipboard, Paperclip, Upload, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';

interface ResponseAttachmentDropzoneProps {
  /** Staged files, not yet uploaded - committed only when the parent saves the response. */
  files: File[];
  onFilesChange: (files: File[]) => void;
  disabled?: boolean;
}

/**
 * Same whitelist the `response_attachment` type enforces server-side. Set on the
 * file input so the mobile picker offers the right sources instead of every file
 * on the device; the server stays the authority.
 */
const ACCEPT =
  '.jpg,.jpeg,.png,.webp,.heic,.pdf,.xls,.xlsx,.csv,.mp4,.mov,.m4v,.webm,.mkv,.avi,.3gp,.mpeg,.mpg,.wmv,.flv,.ogv';

/** Server cap for the response_attachment type. Checked here too so a 200 MB
 * file is rejected instantly instead of after a full upload. */
const MAX_FILE_MB = 100;

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Attachment dropzone for the "Edit purchasing response" / "Edit technical team
 * response" popups (stock inquiry + complaint). Mirrors the portal submission
 * form's dropzone UX (drop / choose / paste-from-clipboard) but never uploads
 * immediately - files stage locally and the parent uploads them on Save /
 * Update & Reply, so Cancel never leaves an orphaned upload.
 * See documentation/plans/UAC-response-attachments.md group C.
 */
export function ResponseAttachmentDropzone({
  files,
  onFilesChange,
  disabled,
}: ResponseAttachmentDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const addFiles = useCallback(
    (incoming: File[]) => {
      if (!incoming.length || disabled) return;
      const withinCap: File[] = [];
      for (const file of incoming) {
        if (file.size > MAX_FILE_MB * 1024 * 1024) {
          toast.error(`${file.name} is larger than ${MAX_FILE_MB} MB and was not attached.`);
          continue;
        }
        withinCap.push(file);
      }
      if (!withinCap.length) return;
      onFilesChange([...files, ...withinCap]);
    },
    [disabled, files, onFilesChange],
  );

  const handleSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selected = e.target.files ? Array.from(e.target.files) : [];
      addFiles(selected);
      if (inputRef.current) inputRef.current.value = '';
    },
    [addFiles],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);
      if (disabled) return;
      const dropped = e.dataTransfer.files ? Array.from(e.dataTransfer.files) : [];
      addFiles(dropped);
    },
    [addFiles, disabled],
  );

  // Desktop: paste an image/file directly into the page while this popup is open.
  useEffect(() => {
    if (disabled) return;
    const onPaste = (e: ClipboardEvent) => {
      if (!e.clipboardData) return;
      // Never hijack paste into the response textarea or any other text field.
      const target = e.target as HTMLElement | null;
      const active = typeof document !== 'undefined' ? (document.activeElement as HTMLElement | null) : null;
      const isEditable = (el: HTMLElement | null) =>
        !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable);
      if (isEditable(target) || isEditable(active)) return;
      const items = Array.from(e.clipboardData.items);
      const pasted: File[] = [];
      for (const item of items) {
        if (item.kind === 'file') {
          const file = item.getAsFile();
          if (file) pasted.push(file);
        }
      }
      if (pasted.length) {
        e.preventDefault();
        addFiles(pasted);
      }
    };
    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
  }, [addFiles, disabled]);

  // Mobile / clipboard-permission browsers: explicit Paste button using the Async
  // Clipboard API, since the `paste` event doesn't fire reliably without focus.
  const handleClipboardPaste = useCallback(async () => {
    if (typeof navigator === 'undefined' || !navigator.clipboard) {
      toast.error('Clipboard is not available in this browser.');
      return;
    }
    try {
      const reader = (navigator.clipboard as unknown as { read?: () => Promise<unknown[]> }).read;
      if (!reader) {
        toast.error('This browser cannot read clipboard images.');
        return;
      }
      const items = (await reader.call(navigator.clipboard)) as Array<{
        types: string[];
        getType: (t: string) => Promise<Blob>;
      }>;
      const pasted: File[] = [];
      for (const item of items) {
        const ts = new Date().toISOString().replace(/[:.]/g, '-');
        const imageType = item.types.find((t) => t.startsWith('image/'));
        if (imageType) {
          const blob = await item.getType(imageType);
          const ext = imageType.split('/')[1] || 'png';
          pasted.push(new File([blob], `pasted-${ts}.${ext}`, { type: imageType }));
        }
      }
      if (!pasted.length) {
        toast.error('No image found in clipboard.');
        return;
      }
      addFiles(pasted);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Clipboard paste failed.');
    }
  }, [addFiles]);

  const handleRemove = (index: number) => {
    onFilesChange(files.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-2">
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
        <Upload className="h-5 w-5 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Drop files here, paste a screenshot, or</p>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={disabled}
          >
            <Paperclip className="h-4 w-4 mr-2" />
            Choose file
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleClipboardPaste}
            disabled={disabled}
          >
            <Clipboard className="h-4 w-4 mr-2" />
            Paste from clipboard
          </Button>
        </div>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          multiple
          accept={ACCEPT}
          onChange={handleSelect}
        />
      </div>
      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((file, idx) => (
            <li
              key={`${file.name}-${idx}`}
              className="flex items-center gap-3 rounded-md border border-dashed border-border bg-muted/30 px-3 py-2"
            >
              <Paperclip className="size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium" title={file.name}>
                  {file.name}
                </p>
                <p className="text-xs text-muted-foreground">{formatFileSize(file.size)}</p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => handleRemove(idx)}
                disabled={disabled}
                aria-label={`Remove ${file.name}`}
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

export default ResponseAttachmentDropzone;
