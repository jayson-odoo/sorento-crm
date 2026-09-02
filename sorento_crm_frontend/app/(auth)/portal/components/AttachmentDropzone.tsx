'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Paperclip, Upload, X, Clipboard, Eye } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import { canPreviewLocally, portalFetchBytes, toPreviewItem } from '../lib/portal-preview';

function isTextFile(name?: string | null, type?: string | null): boolean {
  if (type?.startsWith('text/')) return true;
  return /\.txt$/i.test(name ?? '');
}
import {
  PortalAttachment,
  PortalLandingKind,
  deleteAttachment,
  uploadAttachment,
} from '../lib/portal-client';

function isImageAttachment(a: PortalAttachment): boolean {
  if (a.content_type?.startsWith('image/')) return true;
  const name = (a.filename ?? '').toLowerCase();
  return /\.(png|jpe?g|gif|webp|bmp|svg)$/.test(name);
}

function isVideoAttachment(a: PortalAttachment): boolean {
  if (a.content_type?.startsWith('video/')) return true;
  const name = (a.filename ?? '').toLowerCase();
  return /\.(mp4|mov|webm|m4v|3gp)$/.test(name);
}

interface Props {
  kind: PortalLandingKind;
  submissionId: string | null;
  attachments: PortalAttachment[];
  onChange: (next: PortalAttachment[]) => void;
  disabled?: boolean;
  // When no submissionId yet, files are buffered locally and surfaced via these
  // callbacks. Parent uploads them after creating the draft.
  pendingFiles?: File[];
  onPendingFilesChange?: (files: File[]) => void;
}

export function AttachmentDropzone({
  kind,
  submissionId,
  attachments,
  onChange,
  disabled,
  pendingFiles,
  onPendingFilesChange,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewIndex, setPreviewIndex] = useState(0);
  const [unlinkTarget, setUnlinkTarget] = useState<PortalAttachment | null>(null);
  const [unlinking, setUnlinking] = useState(false);

  // Local blob: urls for the files buffered before a draft exists, so a pending
  // row previews in place too instead of opening a tab. Created once per
  // pendingFiles change and revoked on the way out.
  const [pendingUrls, setPendingUrls] = useState<(string | null)[]>([]);
  useEffect(() => {
    const urls = (pendingFiles ?? []).map((f) =>
      canPreviewLocally(f) ? URL.createObjectURL(f) : null,
    );
    setPendingUrls(urls);
    return () => {
      urls.forEach((u) => {
        if (u) URL.revokeObjectURL(u);
      });
    };
  }, [pendingFiles]);

  // In-place preview only - nothing in the portal opens a new tab. One carousel
  // over everything on the form: uploaded rows first, then the pending ones.
  // Uploaded items carry the portal bytes route (token auth) so Download and
  // the inline Excel reader work with no NextAuth session; pending items are
  // local blobs with nothing to download yet.
  const previewItems = useMemo<AttachmentPreviewItem[]>(
    () => [
      ...attachments.map(toPreviewItem),
      ...(pendingFiles ?? []).map((file, idx) => ({
        id: `pending-${idx}-${file.name}`,
        name: file.name,
        url: pendingUrls[idx] ?? '',
        sizeBytes: file.size,
      })),
    ],
    [attachments, pendingFiles, pendingUrls],
  );

  const openPreview = useCallback(
    (linkId: string) => {
      const idx = attachments.findIndex((a) => a.link_id === linkId);
      setPreviewIndex(idx >= 0 ? idx : 0);
      setPreviewOpen(true);
    },
    [attachments],
  );

  const openPendingPreview = useCallback(
    (index: number) => {
      setPreviewIndex(attachments.length + index);
      setPreviewOpen(true);
    },
    [attachments.length],
  );

  const addFiles = useCallback(
    async (files: File[]) => {
      if (!files.length) return;
      if (!submissionId) {
        if (onPendingFilesChange) {
          onPendingFilesChange([...(pendingFiles ?? []), ...files]);
        } else {
          toast.error('Save this submission as draft first to attach files.');
        }
        return;
      }
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
    [attachments, kind, onChange, onPendingFilesChange, pendingFiles, submissionId]
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
    if (disabled) return;
    // When no submissionId yet, paste is supported via pending-files buffer.
    if (!submissionId && !onPendingFilesChange) return;
    const onPaste = (e: ClipboardEvent) => {
      if (!e.clipboardData) return;
      // Skip when a Radix dialog is open - the dialog owns the paste (e.g. AI Extract).
      if (typeof document !== 'undefined' &&
          document.querySelector('[role="dialog"][data-state="open"]')) {
        return;
      }
      // Let the native paste happen when the user is typing in a form field.
      // This window-level listener is a catch-all for screenshot/file paste; it
      // must NOT hijack text paste into DO number / customer name / any input,
      // textarea or contenteditable on the portal form.
      const target = e.target as HTMLElement | null;
      const active = (typeof document !== 'undefined'
        ? (document.activeElement as HTMLElement | null)
        : null);
      const isEditable = (el: HTMLElement | null) =>
        !!el && (
          el.tagName === 'INPUT' ||
          el.tagName === 'TEXTAREA' ||
          el.isContentEditable
        );
      if (isEditable(target) || isEditable(active)) {
        return;
      }
      const items = Array.from(e.clipboardData.items);
      const files: File[] = [];
      for (const item of items) {
        if (item.kind === 'file') {
          const file = item.getAsFile();
          if (file) files.push(file);
        }
      }
      // No file on the clipboard but there is text → save the paste as a .txt
      // file so it flows through the same upload path. (Only reached when focus
      // is NOT in an editable field - see guard above.)
      if (!files.length) {
        const text = e.clipboardData.getData('text/plain');
        if (text && text.trim()) {
          const ts = new Date().toISOString().replace(/[:.]/g, '-');
          files.push(new File([text], `pasted-${ts}.txt`, { type: 'text/plain' }));
        }
      }
      if (files.length) {
        e.preventDefault();
        void addFiles(files);
      }
    };
    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
  }, [addFiles, disabled, submissionId, onPendingFilesChange]);

  // Mobile: explicit Paste button - iOS/Android Chrome don't fire `paste` reliably
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
        const ts = new Date().toISOString().replace(/[:.]/g, '-');
        const imageType = item.types.find((t: string) => t.startsWith('image/'));
        if (imageType) {
          const blob = await item.getType(imageType);
          const ext = imageType.split('/')[1] || 'png';
          files.push(new File([blob], `pasted-${ts}.${ext}`, { type: imageType }));
          continue;
        }
        // No image - fall back to pasted text saved as a .txt file.
        if (item.types.includes('text/plain')) {
          const blob = await item.getType('text/plain');
          const text = (await blob.text()).trim();
          if (text) {
            files.push(new File([text], `pasted-${ts}.txt`, { type: 'text/plain' }));
          }
        }
      }
      if (!files.length) {
        toast.error('No image or text found in clipboard.');
        return;
      }
      await addFiles(files);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Clipboard paste failed.');
    }
  }, [addFiles]);

  const confirmRemove = useCallback(async () => {
    if (!unlinkTarget) return;
    setUnlinking(true);
    try {
      await deleteAttachment(unlinkTarget.link_id);
      onChange(attachments.filter((a) => a.link_id !== unlinkTarget.link_id));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to remove attachment.');
    } finally {
      setUnlinking(false);
      setUnlinkTarget(null);
    }
  }, [attachments, onChange, unlinkTarget]);

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
          Drop a file here, paste a screenshot or text, or
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
          accept="image/*,video/*,.pdf,.txt"
          className="hidden"
          multiple
          onChange={handleSelect}
        />
        {!submissionId && !onPendingFilesChange && (
          <p className="text-xs text-amber-700">Save as draft first to attach files.</p>
        )}
        {!submissionId && onPendingFilesChange && (pendingFiles?.length ?? 0) > 0 && (
          <p className="text-xs text-muted-foreground">
            {(pendingFiles?.length ?? 0)} file
            {(pendingFiles?.length ?? 0) === 1 ? '' : 's'} will upload when you save or submit.
          </p>
        )}
      </div>
      {(attachments.length > 0 || (pendingFiles?.length ?? 0) > 0) && (
        <ul className="space-y-2">
          {attachments.map((a) => (
            <UploadedRow
              key={a.link_id}
              attachment={a}
              disabled={disabled}
              onView={() => openPreview(a.link_id)}
              onRemove={() => setUnlinkTarget(a)}
            />
          ))}
          {(pendingFiles ?? []).map((file, idx) => (
            <PendingRow
              key={`pending-${idx}-${file.name}`}
              file={file}
              previewUrl={pendingUrls[idx] ?? null}
              disabled={disabled}
              onView={() => openPendingPreview(idx)}
              onRemove={() =>
                onPendingFilesChange?.(
                  (pendingFiles ?? []).filter((_, i) => i !== idx),
                )
              }
            />
          ))}
        </ul>
      )}

      <AttachmentPreviewModal
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        items={previewItems}
        startIndex={previewIndex}
        fetchBytes={portalFetchBytes}
      />

      <AlertDialog
        open={!!unlinkTarget}
        onOpenChange={(o) => {
          if (!o) setUnlinkTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this attachment?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone.
              {unlinkTarget?.filename ? ` "${unlinkTarget.filename}" will be removed.` : ''}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={unlinking}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmRemove}
              disabled={unlinking}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {unlinking ? 'Removing...' : 'Remove'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/** 'contact' → this is the contact's own upload ("you"); 'staff' → uploaded by
 * a CRM user; anything else (legacy rows with no uploader_kind) → unknown. */
function uploaderLabel(attachment: PortalAttachment): string | null {
  const name = (attachment.uploaded_by_name ?? '').trim();
  if (name) return name;
  if (attachment.uploaded_by_role === 'unknown') return 'Unknown';
  return null;
}

function UploadedRow({
  attachment,
  disabled,
  onView,
  onRemove,
}: {
  attachment: PortalAttachment;
  disabled?: boolean;
  onView: () => void;
  onRemove: () => void;
}) {
  const isImage = isImageAttachment(attachment);
  const isVideo = isVideoAttachment(attachment);
  const url = attachment.url ?? null;
  // Staff-uploaded rows can't be unlinked by the contact (server-enforced too).
  const canUnlink = attachment.can_unlink !== false;
  const uploader = uploaderLabel(attachment);
  return (
    <li className="flex items-center gap-3 rounded-md border border-border px-3 py-2">
      <button
        type="button"
        onClick={onView}
        className="shrink-0"
        aria-label={`Preview ${attachment.filename ?? 'attachment'}`}
      >
        {isImage && url ? (
          <img
            src={url}
            alt={attachment.filename ?? 'Attachment preview'}
            className="h-12 w-12 rounded object-cover border border-border"
          />
        ) : isVideo && url ? (
          <video
            src={url}
            muted
            playsInline
            preload="metadata"
            className="h-12 w-12 rounded object-cover border border-border"
          />
        ) : (
          <FileThumb interactive />
        )}
      </button>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium" title={attachment.filename ?? undefined}>
          {attachment.filename || 'Attachment'}
        </p>
        <div className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
          {attachment.size != null && <span>{(attachment.size / 1024).toFixed(1)} KB</span>}
          {uploader && <span>By {uploader}</span>}
        </div>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onView}
          aria-label="View attachment"
        >
          <Eye className="h-4 w-4" />
        </Button>
        {canUnlink && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onRemove}
            disabled={disabled}
            aria-label="Remove attachment"
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>
    </li>
  );
}

function PendingRow({
  file,
  previewUrl,
  disabled,
  onView,
  onRemove,
}: {
  file: File;
  /** blob: url owned by the parent (created + revoked there), or null for a
   *  type the modal cannot render inline. */
  previewUrl: string | null;
  disabled?: boolean;
  onView: () => void;
  onRemove: () => void;
}) {
  return (
    <li className="flex items-center gap-3 rounded-md border border-dashed border-border px-3 py-2 bg-muted/30">
      <div className="shrink-0">
        {previewUrl && file.type.startsWith('image/') ? (
          <button type="button" onClick={onView} aria-label={`Preview ${file.name}`}>
            <img
              src={previewUrl}
              alt={file.name}
              className="h-12 w-12 rounded object-cover border border-border"
            />
          </button>
        ) : previewUrl && file.type.startsWith('video/') ? (
          <button type="button" onClick={onView} aria-label={`Preview ${file.name}`}>
            <video
              src={previewUrl}
              muted
              playsInline
              preload="metadata"
              className="h-12 w-12 rounded object-cover border border-border"
            />
          </button>
        ) : previewUrl ? (
          <button type="button" onClick={onView} aria-label={`Preview ${file.name}`}>
            <FileThumb interactive />
          </button>
        ) : isTextFile(file.name, file.type) ? (
          <TextPreview name={file.name} loadText={() => file.text()}>
            <FileThumb interactive />
          </TextPreview>
        ) : (
          <FileThumb />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium" title={file.name}>
          {file.name}
        </p>
        <p className="text-xs text-muted-foreground">
          {(file.size / 1024).toFixed(1)} KB · pending upload
        </p>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onRemove}
        disabled={disabled}
        aria-label="Remove pending file"
      >
        <X className="h-4 w-4" />
      </Button>
    </li>
  );
}

function FileThumb({ interactive }: { interactive?: boolean }) {
  return (
    <div
      className={`h-12 w-12 rounded bg-muted flex items-center justify-center text-xs text-muted-foreground border border-border ${
        interactive ? 'cursor-pointer hover:bg-muted/70 transition' : ''
      }`}
    >
      FILE
    </div>
  );
}

function TextPreview({
  name,
  loadText,
  children,
}: {
  name: string;
  loadText: () => Promise<string>;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleOpen = useCallback(
    async (next: boolean) => {
      setOpen(next);
      if (next && content === null && error === null) {
        try {
          setContent(await loadText());
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Could not read file.');
        }
      }
    },
    [content, error, loadText],
  );

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <button
        type="button"
        onClick={() => handleOpen(true)}
        aria-label={`Preview ${name}`}
        className="block"
      >
        {children}
      </button>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="truncate" title={name}>
            {name}
          </DialogTitle>
        </DialogHeader>
        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : content === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/30 p-3 text-sm">
            {content || '(empty file)'}
          </pre>
        )}
      </DialogContent>
    </Dialog>
  );
}
